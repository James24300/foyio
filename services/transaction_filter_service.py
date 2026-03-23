import re
from datetime import date

# Formats de date reconnus dans la recherche
# Exemples supportés :
#   14/03/2026  → jour exact
#   03/2026     → tout le mois
#   2026        → toute l'année
#   14/03       → ce jour/mois toutes années
_RE_FULL   = re.compile(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$")  # jj/mm/aaaa
_RE_MONTH  = re.compile(r"^(\d{1,2})[/\-\.](\d{4})$")                   # mm/aaaa
_RE_YEAR   = re.compile(r"^(\d{4})$")                                    # aaaa
_RE_DAYMON = re.compile(r"^(\d{1,2})[/\-\.](\d{1,2})$")                 # jj/mm
_RE_RANGE  = re.compile(r"^(\d+(?:[.,]\d+)?)-(\d+(?:[.,]\d+)?)$")      # 50-200


def _parse_date_token(token: str):
    """
    Tente de parser un token comme filtre de date.
    Retourne un callable (date -> bool) ou None si ce n'est pas une date.
    """
    m = _RE_FULL.match(token)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return lambda dt: dt.day == d and dt.month == mo and dt.year == y

    m = _RE_MONTH.match(token)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        return lambda dt, _mo=mo, _y=y: dt.month == _mo and dt.year == _y

    m = _RE_YEAR.match(token)
    if m:
        y = int(m.group(1))
        # Seulement si l'année est plausible (évite de confondre "2026" avec un montant)
        if 2000 <= y <= 2100:
            return lambda dt, _y=y: dt.year == _y

    m = _RE_DAYMON.match(token)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return lambda dt, _d=d, _mo=mo: dt.day == _d and dt.month == _mo

    return None


def match_transaction(type_text, category_text, note_text, amount, tokens,
                      transaction_date: date = None, tag_text: str = ""):
    """
    Filtre une transaction selon une liste de tokens de recherche.

    Formats supportés :
      revenu / dépense          → filtre par type
      >100  <50                 → filtre par montant
      14/03/2026                → jour exact
      03/2026                   → mois entier
      2026                      → année entière
      14/03                     → jour/mois toutes années
      texte libre               → cherche dans type, catégorie, description
    """
    type_text     = type_text.lower()
    category_text = category_text.lower()
    note_text     = note_text.lower()
    tag_text      = tag_text.lower() if tag_text else ""

    for token in tokens:

        # ── Type ──
        if token in ("revenu", "revenus", "income"):
            if "revenu" not in type_text and "income" not in type_text:
                return False

        elif token in ("depense", "dépense", "depenses", "dépenses", "expense"):
            if "dépense" not in type_text and "expense" not in type_text:
                return False

        # ── Montant ──
        elif token.startswith(">"):
            try:
                if amount <= float(token[1:].replace(",", ".")):
                    return False
            except ValueError:
                pass

        elif token.startswith("<"):
            try:
                if amount >= float(token[1:].replace(",", ".")):
                    return False
            except ValueError:
                pass

        # ── Plage de montants (50-200) ──
        elif _RE_RANGE.match(token):
            m = _RE_RANGE.match(token)
            lo = float(m.group(1).replace(",", "."))
            hi = float(m.group(2).replace(",", "."))
            if not (lo <= amount <= hi):
                return False

        # ── Date ──
        else:
            date_filter = _parse_date_token(token)
            if date_filter is not None:
                if transaction_date is None or not date_filter(transaction_date):
                    return False
            # ── Texte libre ──
            elif (
                token not in type_text
                and token not in category_text
                and token not in note_text
                and token not in tag_text
            ):
                return False

    return True
