"""Fonctions de formatage — Foyio"""

# Cache du symbole monétaire (évite de relire le fichier JSON à chaque appel)
_currency_symbol = None


def _get_symbol():
    global _currency_symbol
    if _currency_symbol is None:
        try:
            from services.settings_service import get as _get
            _currency_symbol = _get("currency_symbol") or "€"
        except Exception:
            _currency_symbol = "€"
    return _currency_symbol


def format_money(value):
    """Formate un montant en chaîne lisible (ex: 1 234,56 €)."""
    if value is None:
        value = 0
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + f" {_get_symbol()}"


def invalidate_currency_cache():
    """Appeler après changement de devise dans les paramètres."""
    global _currency_symbol
    _currency_symbol = None
