"""
Service de gestion des comptes bancaires.
"""
import logging

from db import Session, safe_session
from models import Account, Transaction

logger = logging.getLogger(__name__)


# Comptes créés au premier démarrage
DEFAULT_ACCOUNTS = [
    ("Compte courant", "checking", "#3b82f6", "bank.png"),
    ("Compte joint",   "joint",    "#8b5cf6", "bank.png"),
    ("Livret A",       "savings",  "#22c55e", "money.png"),
    ("PEL",            "savings",  "#14b8a6", "epargne.png"),
    ("LEP",            "savings",  "#06b6d4", "epargne.png"),
    ("CEL",            "savings",  "#3b82f6", "epargne.png"),
    ("Assurance Vie",  "savings",  "#f59e0b", "epargne.png"),
]


def init_accounts():
    """
    Crée les comptes par défaut au premier démarrage,
    et ajoute les nouveaux comptes manquants aux démarrages suivants.
    """
    with safe_session() as session:
        existing = {a.name for a in session.query(Account).all()}
        for name, atype, color, icon in DEFAULT_ACCOUNTS:
            if name not in existing:
                session.add(Account(
                    name=name, type=atype,
                    color=color, icon=icon, active=True
                ))


def migrate_transactions_to_default_account():
    """
    Assigne les transactions existantes (account_id IS NULL)
    au premier compte (Compte courant).
    Migration non destructive appelée une seule fois.
    """
    with safe_session() as session:
        default = session.query(Account).filter_by(name="Compte courant").first()
        if not default:
            default = session.query(Account).filter_by(active=True).first()
        if not default:
            return

        updated = (
            session.query(Transaction)
            .filter(Transaction.account_id == None)  # noqa
            .update({"account_id": default.id})
        )
        if updated:
            logger.info("Migration : %d transaction(s) assignée(s) au compte '%s'", updated, default.name)


def get_accounts():
    with Session() as session:
        accs = session.query(Account).filter_by(active=True)\
                      .order_by(Account.name).all()
        session.expunge_all()
        return accs


def add_account(name: str, atype: str = "checking",
                color: str = "#3b82f6", icon: str = "bank.png"):
    with safe_session() as session:
        session.add(Account(name=name.strip(), type=atype,
                            color=color, icon=icon, active=True))


def rename_account(account_id: int, new_name: str):
    with safe_session() as session:
        acc = session.query(Account).filter_by(id=account_id).first()
        if acc:
            acc.name = new_name.strip()


def delete_account(account_id: int):
    """
    Désactive un compte (soft delete).
    Ne supprime pas les transactions associées.
    """
    with safe_session() as session:
        acc = session.query(Account).filter_by(id=account_id).first()
        if acc:
            acc.active = False


def get_account_balance(account_id: int) -> tuple:
    """
    Retourne (revenus_total, dépenses_total, solde) pour un compte donné
    sur l'ensemble de l'historique (toutes périodes confondues).
    """
    from sqlalchemy import func
    with Session() as session:
        income = (
            session.query(func.sum(Transaction.amount))
            .filter(Transaction.account_id == account_id)
            .filter(Transaction.type == "income")
            .scalar()
        ) or 0
        expense = (
            session.query(func.sum(Transaction.amount))
            .filter(Transaction.account_id == account_id)
            .filter(Transaction.type == "expense")
            .scalar()
        ) or 0
    return income, expense, income - expense


def get_account_tx_count(account_id: int) -> int:
    """Nombre total de transactions sur un compte."""
    with Session() as session:
        return session.query(Transaction)\
                      .filter(Transaction.account_id == account_id).count()


def update_account_url(account_id: int, url: str):
    """Met à jour l'URL de l'espace client bancaire pour un compte."""
    with safe_session() as session:
        acc = session.query(Account).filter_by(id=account_id).first()
        if acc:
            acc.url = url.strip() if url and url.strip() else None
