"""
État global de la période sélectionnée.
Toutes les vues et services lisent ici pour savoir quel mois afficher.
"""
from datetime import datetime

_current = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get() -> datetime:
    """Retourne la période active (objet datetime, jour=1)."""
    return _current


def set_period(year: int, month: int):
    """Définit la période active."""
    global _current
    _current = datetime(_current.year, _current.month, 1).replace(year=year, month=month)


def is_current_month() -> bool:
    """Vrai si la période sélectionnée est le mois courant."""
    now = datetime.now()
    return _current.year == now.year and _current.month == now.month


def label() -> str:
    """Retourne un libellé lisible, ex: 'Mars 2026'."""
    MONTHS_FR = [
        "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ]
    return f"{MONTHS_FR[_current.month]} {_current.year}"


def prev():
    """Passe au mois précédent."""
    m, y = _current.month - 1, _current.year
    if m == 0:
        m, y = 12, y - 1
    set_period(y, m)


def next_period():
    """Passe au mois suivant (bloqué au mois courant)."""
    now = datetime.now()
    if _current.year == now.year and _current.month == now.month:
        return  # pas de navigation dans le futur
    m, y = _current.month + 1, _current.year
    if m == 13:
        m, y = 1, y + 1
    set_period(y, m)
