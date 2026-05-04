# -*- coding: utf-8 -*-

"""
Service d'Import de relevés bancaires CSV et PDF.
"""
import csv
import logging
import re
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional

from db import Session, safe_session
from models import Transaction, Category
from services.transaction_recognition import find_rule

logger = logging.getLogger(__name__)

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
# Utilitaires communs
# ──────────────────────────────────────────────────────────────

def _parse_amount_fr(s: str) -> float:
    if not s or s.strip() in ("", "-", "—"):
        return 0.0
    s = s.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def _parse_date_fr(s: str) -> Optional[datetime]:
    s = s.strip().lower()
    # Remplacement des mois en français par leurs équivalents numériques pour un parsing robuste
    months = {
        'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
        'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
        'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12',
        'janv.': '01', 'févr.': '02', 'avr.': '04', 'juil.': '07', 'sept.': '09', 'oct.': '10', 'nov.': '11', 'déc.': '12'
    }
    for name, num in months.items():
        if name in s:
            s = s.replace(name, num)
            break
            
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d %m %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def _clean_label(text: str) -> str:
    SKIP_PATTERNS = re.compile(
        r"(TOTAUXDESMOUVEMENTS|NOUVEAUSOLDE|SOLDEPRECEDENT|SOLDEAU|"
        r"552120222RCSParis|SiègeSocial|S\.A\.aucapital|suite>>>|"
        r"AU\d{2}/\d{2}/\d{4}|Haussmann|bdHaussmann|29,bd|"
        r"SociétéGénérale|GénéraleSociété)",
        re.IGNORECASE
    )
    text = SKIP_PATTERNS.sub("", text).strip()
    parts = text.split()
    parts = [p for p in parts if not re.match(r"^[A-Z]{2}\d{3,}$", p)]
    return " ".join(parts)

def enrich_rows(rows: List[ImportRow]) -> List[ImportRow]:
    unique_rows = []
    seen = set()
    for row in rows:
        category = find_rule(row.label)
        if category:
            row.category_id = category.id
            row.category_name = category.name
        key = (row.date.date(), row.amount, row.type, row.label)
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
        else:
            row.is_duplicate = True
    return unique_rows

# ──────────────────────────────────────────────────────────────
# Import PDF Générique
# ──────────────────────────────────────────────────────────────

def _parse_amount_pdf(s: str) -> float:
    if not s: return 0.0
    s = s.strip()
    trailing_minus = s.endswith("-") or s.endswith("–")
    s = s.rstrip("-–").strip()
    s = s.replace("\xa0", "").replace("\u202f", "").replace(" ", "")
    s = re.sub(r"\.(?=\d{3}(,|$))", "", s)
    s = s.replace(",", ".")
    try:
        val = float(s)
        return -val if trailing_minus else val
    except ValueError:
        return 0.0

def parse_pdf_generic(filepath: str) -> List[ImportRow]:
    try:
        import pdfplumber
    except ImportError:
        raise ValueError("pdfplumber est requis: pip install pdfplumber")

    RE_DATE_FULL  = re.compile(r"(\d{2}[/.\-]\d{2}[/.\-]\d{4})")
    RE_DATE_SHORT = re.compile(r"(\d{2}[/.\-]\d{2})(?!\d)")
    RE_AMOUNT     = re.compile(r"(-?\s*\d[\d\s.]*,\d{2})\s*-?")
    RE_YEAR_HEADER = re.compile(r"(?:relev[eé]|p[eé]riode|arr[eê]t[eé]|du|mois)\s+.*?(\d{2}[/.\-]\d{2}[/.\-](\d{4}))", re.IGNORECASE)
    RE_SKIP = re.compile(
        r"(SOLDE\s*(PR[EÉ]C[EÉ]DENT|NOUVEAU|CREDITEUR|DEBITEUR|AU|EN)|"
        r"TOTAL\s*DES|TOTAUX|REPORT|NOUVEAU\s*SOLDE|"
        r"DATE\s+OP[EÉ]RATION|DATE\s+VALEUR|LIBELL[EÉ]|"
        r"R[EÉ]F[EÉ]RENCE|NUM[EÉ]RO\s*DE\s*COMPTE|IBAN|BIC|"
        r"PAGE\s+\d|SUITE\s*>>>|RELEV[EÉ]\s*DE\s*COMPTE|"
        r"^\s*$|^\s*\d{1,2}\s+de\s+\d{4}\s*$)", re.IGNORECASE
    )

    rows = []
    default_year = None
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages[:3]:
            text = page.extract_text() or ""
            m = RE_YEAR_HEADER.search(text)
            if m:
                default_year = int(m.group(2))
                break
        if not default_year:
            default_year = datetime.now().year

        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            for line in text.split("\n"):
                line = line.strip()
                if not line or RE_SKIP.search(line): continue
                date_val = None
                date_end = 0
                m_full = RE_DATE_FULL.search(line)
                if m_full and m_full.start() < 20:
                    date_val = _parse_date_fr(m_full.group(1).replace(".", "/").replace("-", "/"))
                    date_end = m_full.end()
                if not date_val:
                    m_short = RE_DATE_SHORT.search(line)
                    if m_short and m_short.start() < 20:
                        try:
                            d, m = m_short.group(1).replace(".", "/").replace("-", "/").split("/")
                            date_val = datetime(default_year, int(m), int(d))
                            date_end = m_short.end()
                        except: pass
                if not date_val: continue
                rest = line[date_end:].strip()
                amounts = list(RE_AMOUNT.finditer(rest))
                if not amounts: continue
                amount = _parse_amount_pdf(amounts[-1].group(0))
                description = rest[:amounts[-1].start()].strip()
                if amount == 0: continue
                rows.append(ImportRow(
                    date=date_val, label=_clean_label(description),
                    amount=abs(amount), type="income" if amount > 0 else "expense"
                ))
    return rows

def load_pdf(filepath: str):
    try:
        rows = parse_pdf_generic(filepath)
        return "pdf_generic", enrich_rows(rows)
    except Exception as e:
        raise ValueError(f"Erreur PDF: {e}")

# (Autres parseurs CSV/OFX/QIF à rajouter si nécessaire, simplifiés ici pour la démo)
