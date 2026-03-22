"""
Service d'import de relevés bancaires CSV.
Formats supportés :
  - Société Générale (séparateur ; colonnes Date/Libellé/Débit/Crédit/Détail)
  - Format interne Foyio (export maison)
"""
import csv
import logging
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from db import Session, safe_session
from models import Transaction, Category
from services.transaction_recognition import find_rule

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Structure d'une ligne importée (avant insertion en base)
# ──────────────────────────────────────────────────────────────
@dataclass
class ImportRow:
    date:        datetime
    label:       str
    amount:      float          # positif = revenu, négatif = dépense
    type:        str            # "income" ou "expense"
    category_id: Optional[int]  # détecté automatiquement, peut être None
    category_name: str = ""     # pour affichage
    is_duplicate: bool = False
    raw_line:    dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# Détection du format
# ──────────────────────────────────────────────────────────────
def detect_format(filepath: str) -> str:
    """
    Détecte le format du CSV en lisant les 5 premières lignes.
    Retourne : "sg_web" | "sg_gdb" | "sg" | "internal" | "unknown"

    Formats SG reconnus :
    - sg_web  : relevé téléchargé espace client (ligne 1 = en-tête compte,
                ligne 3 = Date;Libellé;Détail;Montant;Devise)
    - sg_gdb  : export application mobile SG (Date transaction;...;Num Compte;...;Montant)
    - sg      : relevé classique avec colonnes Débit/Crédit séparées
    """
    lines = []
    for enc in ["utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                lines = [f.readline() for _ in range(5)]
            break
        except Exception:
            continue
    if not lines:
        logger.warning("Impossible de lire le fichier : %s", filepath)

    # Texte complet des premières lignes (insensible à la casse et aux accents)
    all_text = " ".join(lines).lower()
    all_text = all_text.replace("é","e").replace("è","e").replace("ê","e").replace("â","a")

    # sg_web : "devise" apparaît dans les premières lignes (colonne Devise)
    if "devise" in all_text and "montant" in all_text:
        return "sg_web"

    # sg_gdb : contient "num compte" et "libelle" et "montant"
    if "num compte" in all_text and "libell" in all_text and "montant" in all_text:
        return "sg_gdb"

    # sg classique : débit/crédit séparés sur la première ligne
    first = lines[0].lower() if lines else ""
    if any(k in first for k in ["debit", "credit", "débit", "crédit"]) and ";" in first:
        return "sg"

    # Format interne Foyio
    if "type" in all_text and "montant" in all_text and "categorie" in all_text:
        return "internal"

    return "unknown"


# ──────────────────────────────────────────────────────────────
# Parseurs par format
# ──────────────────────────────────────────────────────────────
def _parse_amount_fr(s: str) -> float:
    """Convertit '1 234,56' ou '-45,20' ou '45.20' en float."""
    if not s or s.strip() in ("", "-", "—"):
        return 0.0
    s = s.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date_fr(s: str) -> Optional[datetime]:
    """Tente de parser une date française jj/mm/aaaa ou aaaa-mm-jj."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_sg(filepath: str) -> List[ImportRow]:
    """
    Parse un export CSV Société Générale.
    Colonnes attendues (flexibles) :
      Date ; Libellé ; Débit ; Crédit ; Détail de l'opération
    La SG exporte parfois avec BOM UTF-8 et encodage latin-1.
    """
    rows = []
    content = ""
    for enc in ["utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                content = f.read()
            break
        except Exception:
            continue
    if not content:
        logger.warning("Impossible de lire le fichier SG : %s", filepath)
        return rows

    lines = content.splitlines()

    # Trouver la ligne d'en-tête (contient "Date" ou "date")
    header_idx = 0
    for i, line in enumerate(lines):
        if re.search(r"date", line, re.IGNORECASE) and ";" in line:
            header_idx = i
            break

    reader = csv.DictReader(
        lines[header_idx:],
        delimiter=";",
        quotechar='"'
    )

    # Normaliser les noms de colonnes
    def find_col(fieldnames, *candidates):
        for fn in fieldnames:
            fn_clean = fn.strip().lower().replace(" ", "").replace("é", "e").replace("è", "e")
            for c in candidates:
                c_clean = c.lower().replace(" ", "").replace("é", "e").replace("è", "e")
                if c_clean in fn_clean:
                    return fn
        return None

    for row in reader:
        fns = list(row.keys())

        col_date   = find_col(fns, "date")
        col_label  = find_col(fns, "libellé", "libelle", "label", "opération")
        col_debit  = find_col(fns, "débit", "debit", "montant débit")
        col_credit = find_col(fns, "crédit", "credit", "montant crédit")
        col_detail = find_col(fns, "détail", "detail", "description")

        if not col_date or not col_label:
            continue

        date_val = _parse_date_fr(row.get(col_date, ""))
        if not date_val:
            continue

        label  = row.get(col_label, "").strip()
        detail = row.get(col_detail, "").strip() if col_detail else ""
        note   = detail if detail and detail.lower() != label.lower() else label

        debit  = abs(_parse_amount_fr(row.get(col_debit,  ""))) if col_debit  else 0.0
        credit = abs(_parse_amount_fr(row.get(col_credit, ""))) if col_credit else 0.0

        if debit > 0:
            amount = -debit
            ttype  = "expense"
        elif credit > 0:
            amount = credit
            ttype  = "income"
        else:
            continue  # ligne vide ou solde

        rows.append(ImportRow(
            date=date_val,
            label=note or label,
            amount=abs(amount),
            type=ttype,
            category_id=None,
            raw_line=dict(row),
        ))

    return rows



def parse_sg_web(filepath: str) -> List[ImportRow]:
    """
    Parse le relevé CSV téléchargé depuis l'espace client SG.
    Structure :
      Ligne 1 : ="numéro_compte";date_debut;date_fin;...  (en-tête compte)
      Ligne 2 : vide
      Ligne 3 : Date de l'opération;Libellé;Détail de l'écriture;Montant;Devise
      Ligne 4+ : données
    Encodage : utf-8-sig, séparateur ;, montant signé avec virgule
    """
    rows = []
    raw = ""
    for enc in ["utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                raw = f.read()
            break
        except Exception:
            continue
    if not raw:
        logger.warning("Impossible de lire le fichier SG web : %s", filepath)
        return rows

    lines = raw.splitlines()

    # Trouver la ligne d'en-tête (contient "Date" et "Montant")
    header_idx = None
    for i, line in enumerate(lines):
        ll = line.lower()
        if ("date" in ll and "montant" in ll) or ("libell" in ll and "montant" in ll):
            header_idx = i
            break

    if header_idx is None:
        return rows

    import csv as _csv
    reader = _csv.DictReader(
        lines[header_idx:], delimiter=";", quotechar='"'
    )

    # Structure fixe SG web : col0=Date, col1=Libellé, col2=Détail, col3=Montant, col4=Devise
    # On utilise les positions plutôt que les noms (encodage variable selon OS)
    for row in reader:
        vals = list(row.values())
        if len(vals) < 4:
            continue

        date_str = (vals[0] or "").strip()
        label    = (vals[2] or vals[1] or "").strip()   # Détail complet en priorité
        montant  = (vals[3] or "").strip()
        devise   = (vals[4] or "").strip() if len(vals) > 4 else ""

        if not date_str or not montant:
            continue

        # Ignorer les lignes non-données
        if montant.upper() in ("EUR", "USD", "") or not date_str[0].isdigit():
            continue

        date_val = _parse_date_fr(date_str)
        if not date_val:
            continue

        montant_clean = montant.replace("\xa0","").replace("\u202f","").replace(" ","").replace(",",".")
        try:
            amount = float(montant_clean)
        except ValueError:
            continue

        if amount == 0:
            continue

        ttype  = "income" if amount > 0 else "expense"
        amount = abs(amount)

        label = _clean_label(label)

        rows.append(ImportRow(
            date=date_val,
            label=label,
            amount=amount,
            type=ttype,
            category_id=None,
        ))

    return rows


def parse_sg_gdb(filepath: str) -> List[ImportRow]:
    """
    Parse l'export CSV GDB Société Générale.
    Colonnes : Date transaction ; Date comptabilisation ; Num Compte ;
               Libellé Compte ; Libellé opération ; Libellé complet ;
               Catégorie ; Sous-Catégorie ; Montant
    Encodage : latin-1 / cp1252
    Montant signé : négatif = dépense, positif = revenu
    """
    rows = []
    content_raw = ""
    for enc in ["latin-1", "cp1252", "utf-8-sig"]:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                content_raw = f.read()
            break
        except Exception:
            continue
    if not content_raw:
        logger.warning("Impossible de lire le fichier SG GDB : %s", filepath)
        return rows

    lines = content_raw.splitlines()
    if not lines:
        return rows

    reader = csv.DictReader(lines, delimiter=";", quotechar='"')
    for row in reader:
        # Trouver les colonnes (insensible à la casse et aux accents)
        def get(keys):
            for k in row:
                if k is None:
                    continue
                kn = k.strip().lower().replace("é","e").replace("è","e").replace("ê","e")
                for key in keys:
                    if key.lower() in kn:
                        v = row[k]
                        return v.strip() if v else ""
            return ""

        date_str = get(["date transaction", "date"])
        label    = get(["libelle operation", "libelle complet", "libelle"])
        montant  = get(["montant"])

        if not date_str or not montant:
            continue

        date_val = _parse_date_fr(date_str)
        if not date_val:
            continue

        # Nettoyer le montant (peut contenir des espaces insécables)
        montant_clean = montant.replace("\xa0","").replace(" ","").replace(",",".")
        try:
            amount = float(montant_clean)
        except ValueError:
            continue

        if amount == 0:
            continue

        ttype  = "income" if amount > 0 else "expense"
        amount = abs(amount)

        label = _clean_label(label)

        rows.append(ImportRow(
            date=date_val,
            label=label,
            amount=amount,
            type=ttype,
            category_id=None,
        ))

    return rows


def parse_internal(filepath: str) -> List[ImportRow]:
    """Parse le format d'export interne Foyio."""
    rows = []
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            date_val = _parse_date_fr(row.get("Date", ""))
            if not date_val:
                continue
            ttype  = "income" if "revenu" in row.get("Type", "").lower() else "expense"
            amount = abs(_parse_amount_fr(row.get("Montant (€)", "0")))
            if amount == 0:
                continue
            rows.append(ImportRow(
                date=date_val,
                label=row.get("Description", "").strip(),
                amount=amount,
                type=ttype,
                category_id=None,
                raw_line=dict(row),
            ))
    return rows


def _clean_label(label: str) -> str:
    """Nettoie un libellé bancaire SG."""
    import re as _re
    # Supprimer les caractères invisibles EN PREMIER
    label = label.replace('\ufffd', '').replace('\xa0', ' ')
    label = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', label)
    # Codes IOPD
    label = _re.sub(r"\s*\d+IOPD\s*", " ", label).strip()
    # Tout après ID:, REF:, MANDAT, MOTIF:
    label = _re.sub(r"\s+(ID:|REF:|MANDAT\s*\w*|MOTIF:|NORME\s*\w*).*", "", label, flags=_re.IGNORECASE).strip()
    # PRELEVEMENT EUROPEEN XXXXXXX DE: NOM
    label = _re.sub(r"^(PRELEVEMENT EUROPEEN|PRELEVEMENT)\s+[\w]+\s+DE:\s*", "", label, flags=_re.IGNORECASE).strip()
    # VIR INST RE XXXXXXX DE: NOM
    label = _re.sub(r"^VIR\s+INST\s+RE\s+[\w]+\s+(DE:\s*)?", "", label, flags=_re.IGNORECASE).strip()
    # VIR RECU XXXXXXX DE: NOM
    label = _re.sub(r"^VIR\s+RECU\s+[\w]+\s+(DE:\s*)?", "", label, flags=_re.IGNORECASE).strip()
    # VIR PERM POUR: NOM
    label = _re.sub(r"^(\d+\s+)?VIR\s+PERM\s+(POUR:\s*)?", "", label, flags=_re.IGNORECASE).strip()
    # Séquences alphanumériques longues
    label = _re.sub(r"\b\d{6,}\w*\b", "", label).strip()
    # Dates intégrées
    label = _re.sub(r"\s*DATE\s*[:\s]+\d{2}/\d{2}/\d{4}(\s+\d{2}:\d{2}(:\d{2})?)?\s*", " ", label, flags=_re.IGNORECASE).strip()
    # Montant EUR en fin
    label = _re.sub(r"\s+\d+,\d+\s+EUR.*$", "", label, flags=_re.IGNORECASE).strip()
    # DE: ou POUR: résiduels en début
    label = _re.sub(r"^(DE:|POUR:)\s*", "", label, flags=_re.IGNORECASE).strip()
    # Espaces multiples
    label = _re.sub(r"\s{2,}", " ", label).strip()
    label = label.strip(" -/.,:")
    return label

# ──────────────────────────────────────────────────────────────
# Enrichissement : catégories + doublons
# ──────────────────────────────────────────────────────────────
def enrich_rows(rows: List[ImportRow]) -> List[ImportRow]:
    """
    Pour chaque ligne :
    1. Tente de trouver une catégorie via les règles de reconnaissance
    2. Marque les doublons potentiels (même date + montant + label)
    """
    with Session() as session:
        from models import Transaction
        from sqlalchemy import func

        cats = {c.id: c.name for c in session.query(Category).all()}

        for row in rows:
            # Reconnaissance automatique
            cat_id = find_rule(row.label)
            row.category_id   = cat_id
            row.category_name = cats.get(cat_id, "") if cat_id else ""

            # Détection doublon — même montant + même date + même type + même compte
            import account_state as _as
            acc_id = _as.get_id()
            q = (
                session.query(Transaction)
                .filter(Transaction.amount == row.amount)
                .filter(func.strftime("%Y-%m-%d", Transaction.date)
                        == row.date.strftime("%Y-%m-%d"))
                .filter(Transaction.type == row.type)
            )
            if acc_id is not None:
                q = q.filter(Transaction.account_id == acc_id)
            existing = q.first()
            row.is_duplicate = existing is not None

    return rows


# ──────────────────────────────────────────────────────────────
# Import principal
# ──────────────────────────────────────────────────────────────
def load_csv(filepath: str):
    """
    Charge et analyse un CSV bancaire.
    Retourne (format_str, list[ImportRow]) ou lève ValueError si inconnu.
    """
    fmt = detect_format(filepath)

    if fmt == "sg_web":
        rows = parse_sg_web(filepath)
    elif fmt == "sg_gdb":
        rows = parse_sg_gdb(filepath)
    elif fmt == "sg":
        rows = parse_sg(filepath)
    elif fmt == "internal":
        rows = parse_internal(filepath)
    else:
        # Tentative GDB en dernier recours
        try:
            rows = parse_sg_gdb(filepath)
            if rows:
                fmt = "sg_gdb"
            else:
                raise ValueError("Aucune transaction trouvée.")
        except Exception:
            raise ValueError(
                "Format CSV non reconnu.\n"
                "Formats supportés : Société Générale (GDB ou relevé), export interne Foyio."
            )

    rows = enrich_rows(rows)
    return fmt, rows


def insert_row(row: ImportRow, category_id: int,
               account_id: int = None) -> bool:
    """Insère une ImportRow en base. Retourne True si succès, False si échec."""
    # Nettoyer les caractères invisibles de la note
    note = row.label or ''
    note = note.replace('\xa0', ' ')  # espace insécable
    note = note.replace('\ufffd', '')  # caractère de remplacement
    note = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', note)  # contrôle
    note = re.sub(r'\s{2,}', ' ', note).strip()
    try:
        with safe_session() as session:
            t = Transaction(
                date=row.date,
                amount=row.amount,
                type=row.type,
                note=note,
                category_id=category_id,
                account_id=account_id,
            )
            session.add(t)
        return True
    except Exception:
        logger.exception("Échec import ligne : %s %.2f %s", note, row.amount, row.date)
        return False


# ──────────────────────────────────────────────────────────────
# Import PDF — Société Générale
# ──────────────────────────────────────────────────────────────

def parse_pdf_sg(filepath: str) -> List[ImportRow]:
    """
    Parse un relevé PDF Société Générale en exploitant les positions X des mots.
    Colonnes mesurées sur PDF natif SG :
      Date x≈25-75 | Libellé x≈118-415 | Débit x≈415-495 | Crédit x≈495-565
    """
    try:
        import pdfplumber
    except ImportError:
        raise ValueError(
            "La librairie pdfplumber est requise.\n"
            "Installez-la avec : pip install pdfplumber"
        )

    import re as _re

    X_DATE   = (25,  75)
    X_LABEL  = (118, 415)
    X_DEBIT  = (415, 495)
    X_CREDIT = (495, 565)

    RE_DATE_FULL = _re.compile(r"^\d{2}/\d{2}/\d{4}$")
    # Lignes techniques à ne pas ajouter au libellé
    SKIP_PREFIXES = ("ID:", "REF:", "MANDAT", "MOTIF:", "DE:", "POUR:", "PROVENANCE:")
    # Mots parasites qui apparaissent quand les colonnes débordent
    SKIP_PATTERNS = _re.compile(
        r"(TOTAUXDESMOUVEMENTS|NOUVEAUSOLDE|SOLDEPRECEDENT|SOLDEAU|"
        r"552120222RCSParis|SiègeSocial|S\.A\.aucapital|suite>>>|"
        r"AU\d{2}/\d{2}/\d{4}|Haussmann|bdHaussmann|29,bd|"
        r"SociétéGénérale|GénéraleSociété)"
    )

    def in_col(word, col):
        return word["x0"] >= col[0] and word["x0"] < col[1]

    def parse_amount(s):
        """Accepte 1.862,89 (point millier) ou 1862,89 ou 36,97"""
        if not s:
            return 0.0
        s = s.strip().replace("\xa0", "").replace(" ", "")
        # Supprimer le point séparateur de milliers : 1.862,89 → 1862,89
        s = _re.sub(r"\.(?=\d{3},)", "", s)
        s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0

    def clean_label(text):
        """Nettoie le libellé : espaces manquants, textes parasites."""
        # Insérer espace avant majuscule isolée dans les mots collés
        # ex: CARTEX4832 → CARTE X4832 (optionnel, cosmétique)
        text = SKIP_PATTERNS.sub("", text).strip()
        # Supprimer les fragments courts parasites en fin
        parts = text.split()
        # Supprimer les mots qui ressemblent à des morceaux de numéros RCS/SIRET
        parts = [p for p in parts if not _re.match(r"^[A-Z]{2}\d{3,}$", p)]
        return " ".join(parts)

    rows = []

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)

            # Grouper les mots par ligne (y arrondi au point)
            lines = {}
            for w in words:
                lines.setdefault(round(w["top"]), []).append(w)

            current = None  # (date_str, label_parts, debit, credit)

            for y in sorted(lines.keys()):
                row = sorted(lines[y], key=lambda w: w["x0"])

                dw  = [w for w in row if in_col(w, X_DATE)]
                lw  = [w for w in row if in_col(w, X_LABEL)]
                dbw = [w for w in row if in_col(w, X_DEBIT)]
                crw = [w for w in row if in_col(w, X_CREDIT)]

                date_str   = dw[0]["text"]  if dw  else ""
                debit_str  = dbw[0]["text"] if dbw else ""
                credit_str = crw[0]["text"] if crw else ""
                label_part = " ".join(w["text"] for w in lw).strip()

                is_new_tx = bool(dw) and RE_DATE_FULL.match(date_str)

                if is_new_tx:
                    # Sauvegarder la transaction précédente
                    if current:
                        d, lparts, db, cr = current
                        label  = clean_label(" ".join(lparts))
                        amount = db if db > 0 else cr
                        ttype  = "expense" if db > 0 else "income"
                        if amount > 0 and label:
                            try:
                                rows.append(ImportRow(
                                    date=datetime.strptime(d, "%d/%m/%Y"),
                                    label=label, amount=amount, type=ttype,
                                    category_id=None,
                                ))
                            except ValueError:
                                logger.warning("Date invalide ignorée dans le PDF : %s", d)

                    db = parse_amount(debit_str)
                    cr = parse_amount(credit_str)
                    current = (date_str, [label_part] if label_part else [], db, cr)

                elif current and label_part:
                    d, lparts, db, cr = current
                    if not any(label_part.startswith(p) for p in SKIP_PREFIXES):
                        lparts.append(label_part)
                    current = (d, lparts, db, cr)

            # Dernière transaction de la page
            if current:
                d, lparts, db, cr = current
                label  = clean_label(" ".join(lparts))
                amount = db if db > 0 else cr
                ttype  = "expense" if db > 0 else "income"
                if amount > 0 and label:
                    try:
                        rows.append(ImportRow(
                            date=datetime.strptime(d, "%d/%m/%Y"),
                            label=label, amount=amount, type=ttype,
                            category_id=None,
                        ))
                    except ValueError:
                        pass

    # Dédoublonner (même date + montant + type)
    seen, unique = set(), []
    for r in rows:
        key = (r.date.date(), r.amount, r.type)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def load_pdf(filepath: str):
    """
    Charge et analyse un relevé PDF bancaire (Société Générale).
    Retourne ("pdf_sg", list[ImportRow]).
    """
    rows = parse_pdf_sg(filepath)
    if not rows:
        raise ValueError(
            "Aucune transaction trouvée dans ce PDF.\n"
            "Vérifiez qu'il s'agit d'un relevé Société Générale.\n"
            "Si le PDF est scanné (image), l'extraction est impossible."
        )
    rows = enrich_rows(rows)
    return "pdf_sg", rows
