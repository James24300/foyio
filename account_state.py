"""
État global du compte bancaire sélectionné.
Toutes les vues et services lisent ici pour filtrer par compte.
"""
from typing import Optional

_current_id:   Optional[int] = None   # None = pas encore chargé
_current_name: str           = ""


def get_id() -> Optional[int]:
    """Retourne l'ID du compte actif (None si pas de compte sélectionné)."""
    return _current_id


def get_name() -> str:
    return _current_name


def set_account(account_id: int, account_name: str):
    global _current_id, _current_name
    _current_id   = account_id
    _current_name = account_name
    from services.settings_service import set as _set_s 
    _set_s("last_account_id", account_id)                


def init_default():
    """
    Charge le dernier compte sélectionné (mémorisé dans les paramètres),
    ou à défaut le premier compte actif en base.
    Appelé au démarrage après create_all().
    """
    global _current_id, _current_name
    from db import Session
    from models import Account
    from services.settings_service import get as _get_s

    last_id = _get_s("last_account_id")

    with Session() as session:
        acc = None
        if last_id:
            acc = session.query(Account).filter_by(id=last_id, active=True).first()
        if acc is None:
            acc = session.query(Account).filter_by(active=True).first()
        if acc:
            _current_id   = acc.id
            _current_name = acc.name


def get_all_accounts():
    """Retourne tous les comptes actifs."""
    from db import Session
    from models import Account
    with Session() as session:
        accounts = session.query(Account).filter_by(active=True)\
                          .order_by(Account.name).all()
        session.expunge_all()
        return accounts
