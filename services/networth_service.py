"""
Service Patrimoine Net — agrège comptes, épargne, crypto et prêts.
"""
import logging
from sqlalchemy import func
from db import Session
from models import Account, Transaction, SavingsGoal, Loan, CryptoHolding

logger = logging.getLogger(__name__)


def get_account_balances() -> list[dict]:
    """Retourne le solde cumulé (toutes périodes) de chaque compte actif."""
    with Session() as session:
        accounts = (
            session.query(Account)
            .filter_by(active=True)
            .order_by(Account.name)
            .all()
        )
        result = []
        for acc in accounts:
            income = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.account_id == acc.id, Transaction.type == "income")
                .scalar()
            ) or 0.0
            expense = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.account_id == acc.id, Transaction.type == "expense")
                .scalar()
            ) or 0.0
            result.append({
                "id":      acc.id,
                "name":    acc.name,
                "type":    acc.type,
                "color":   acc.color,
                "balance": round(income - expense, 2),
            })
        return result


def get_savings_totals() -> list[dict]:
    """Retourne le montant actuel de chaque objectif d'épargne actif."""
    with Session() as session:
        goals = session.query(SavingsGoal).filter_by(active=True).order_by(SavingsGoal.name).all()
        return [
            {
                "name":   g.name,
                "amount": round(g.current_amount or 0.0, 2),
                "color":  g.color,
                "icon":   g.icon,
            }
            for g in goals
        ]


def get_loans_totals() -> list[dict]:
    """Retourne le capital restant dû pour chaque prêt actif."""
    with Session() as session:
        loans = session.query(Loan).filter_by(active=True).order_by(Loan.name).all()
        return [
            {
                "name":            l.name,
                "remaining":       round(l.remaining_amount, 2),
                "monthly_payment": round(l.monthly_payment, 2),
                "interest_rate":   l.interest_rate,
            }
            for l in loans
        ]


def get_crypto_holdings() -> list[dict]:
    """Retourne les crypto actives (sans prix — récupérés de façon asynchrone)."""
    with Session() as session:
        holdings = (
            session.query(CryptoHolding)
            .filter_by(active=True)
            .order_by(CryptoHolding.name)
            .all()
        )
        return [
            {
                "id":           h.id,
                "name":         h.name,
                "symbol":       h.symbol,
                "coingecko_id": h.coingecko_id,
                "quantity":     h.quantity,
                "avg_buy_price": h.avg_buy_price,
            }
            for h in holdings
        ]


def get_net_worth_data() -> dict:
    """
    Agrège toutes les données patrimoniales (sans crypto — asynchrone).
    Retourne un dict prêt à l'emploi pour la vue.
    """
    accounts = get_account_balances()
    savings  = get_savings_totals()
    loans    = get_loans_totals()
    holdings = get_crypto_holdings()

    total_accounts = sum(a["balance"] for a in accounts)
    total_savings  = sum(s["amount"]  for s in savings)
    total_loans    = sum(l["remaining"] for l in loans)

    return {
        "accounts":       accounts,
        "savings":        savings,
        "loans":          loans,
        "holdings":       holdings,
        "total_accounts": round(total_accounts, 2),
        "total_savings":  round(total_savings,  2),
        "total_loans":    round(total_loans,    2),
        "crypto_value":   0.0,   # mis à jour après fetch asynchrone
    }
