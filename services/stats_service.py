from datetime import datetime

from sqlalchemy import func, case

from db import Session
from models import Transaction, Category
import period_state
import account_state


def _af(query):
    """Applique le filtre compte actif sur une requête Transaction."""
    acc_id = account_state.get_id()
    if acc_id is not None:
        query = query.filter(Transaction.account_id == acc_id)
    return query


def expenses_by_category():
    """Dépenses par catégorie pour la période et le compte sélectionnés."""
    with Session() as session:
        p = period_state.get()
        q = (
            session.query(Category.name, func.sum(Transaction.amount))
            .join(Category, Category.id == Transaction.category_id)
            .filter(Transaction.type == "expense")
            .filter(func.extract("year",  Transaction.date) == p.year)
            .filter(func.extract("month", Transaction.date) == p.month)
        )
        return _af(q).group_by(Category.name).all()


def expenses_by_category_annual(months: int = 12):
    """Dépenses par catégorie sur les N derniers mois pour le compte actif."""
    from datetime import datetime
    from sqlalchemy import and_

    now = datetime.now()
    # Date de début : il y a N mois
    start_month = now.month - months + 1
    start_year  = now.year
    while start_month <= 0:
        start_month += 12
        start_year  -= 1

    with Session() as session:
        q = (
            session.query(Category.name, func.sum(Transaction.amount))
            .join(Category, Category.id == Transaction.category_id)
            .filter(Transaction.type == "expense")
            .filter(
                (func.extract("year", Transaction.date) * 100 +
                 func.extract("month", Transaction.date)) >=
                (start_year * 100 + start_month)
            )
            .filter(
                (func.extract("year", Transaction.date) * 100 +
                 func.extract("month", Transaction.date)) <=
                (now.year * 100 + now.month)
            )
        )
        return _af(q).group_by(Category.name).order_by(
            func.sum(Transaction.amount).desc()
        ).all()


def monthly_balance():
    """Solde net par mois pour le compte actif."""
    MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                 "Juil","Août","Sep","Oct","Nov","Déc"]

    with Session() as session:
        q = session.query(
            func.strftime("%Y-%m", Transaction.date),
            func.sum(case(
                (Transaction.type == "income", Transaction.amount),
                else_=-Transaction.amount
            ))
        )
        data = (
            _af(q)
            .group_by(func.strftime("%Y-%m", Transaction.date))
            .order_by(func.strftime("%Y-%m", Transaction.date))
            .all()
        )

    result = []
    for raw_label, value in data:
        try:
            y, m = int(raw_label[:4]), int(raw_label[5:7])
            label = f"{MONTHS_FR[m]} {y}"
        except (ValueError, IndexError):
            label = raw_label
        result.append((label, value))
    return result


def monthly_totals():
    """Retourne (revenus, dépenses, solde) pour la période et le compte actifs."""
    with Session() as session:
        p = period_state.get()

        def _sum(ttype):
            q = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.type == ttype)
                .filter(func.extract("year",  Transaction.date) == p.year)
                .filter(func.extract("month", Transaction.date) == p.month)
            )
            return _af(q).scalar() or 0

        income  = _sum("income")
        expense = _sum("expense")

    return income, expense, income - expense


def monthly_income_expense(months: int = 12):
    """Revenus et dépenses mois par mois sur N mois pour le compte actif."""
    MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                 "Juil","Août","Sep","Oct","Nov","Déc"]

    today  = datetime.now()
    result = []

    with Session() as session:
        for i in range(months - 1, -1, -1):
            m, y = today.month - i, today.year
            while m <= 0:
                m += 12; y -= 1

            def _s(ttype):
                q = (
                    session.query(func.sum(Transaction.amount))
                    .filter(Transaction.type == ttype)
                    .filter(func.extract("year",  Transaction.date) == y)
                    .filter(func.extract("month", Transaction.date) == m)
                )
                return _af(q).scalar() or 0

            result.append((f"{MONTHS_FR[m]} {y}", _s("income"), _s("expense")))

    return result


def expenses_by_category_all():
    """Alias de expenses_by_category pour l'onglet camembert."""
    return expenses_by_category()
