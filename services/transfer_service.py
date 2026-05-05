import logging
"""
Service de transfert automatique — Foyio
Quand une dépense est ajoutée sur une catégorie liée à un compte épargne,
propose de créer automatiquement le revenu correspondant sur ce compte.
"""
from db import Session, safe_session
from models import Category, Transaction, Account

logger = logging.getLogger(__name__)


def get_transfer_account(category_id: int):
    """
    Vérifie si une catégorie est liée à un compte de transfert.
    Retourne (account_id, account_name) ou (None, None).
    """
    if not category_id:
        return None, None

    with Session() as session:
        cat = session.query(Category).filter_by(id=category_id).first()
        if not cat or not cat.transfer_account_id:
            return None, None

        acc = session.query(Account).filter_by(
            id=cat.transfer_account_id, active=True
        ).first()
        if not acc:
            return None, None

        return acc.id, acc.name


def create_mirror_transaction(
    source_date,
    amount: float,
    category_id: int,
    destination_account_id: int,
    note: str = ""
):
    """
    Crée la transaction miroir (revenu) sur le compte destination.
    Retourne l'ID de la transaction créée.
    """
    with safe_session() as session:
        t = Transaction(
            date=source_date,
            amount=amount,
            type="income",
            note=note,
            category_id=category_id,
            account_id=destination_account_id,
        )
        session.add(t)
        session.flush()
        return t.id
