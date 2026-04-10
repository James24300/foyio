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


def get_cumulative_balance() -> float:
    """
    Solde cumulé depuis la première transaction jusqu'à la fin
    de la période sélectionnée (revenus − dépenses, compte actif).
    """
    import calendar
    p = period_state.get()
    last_day = calendar.monthrange(p.year, p.month)[1]
    cutoff = datetime(p.year, p.month, last_day, 23, 59, 59)

    with Session() as session:
        q = session.query(
            func.sum(case(
                (Transaction.type == "income",   Transaction.amount),
                (Transaction.type == "expense", -Transaction.amount),
                else_=0,
            ))
        ).filter(Transaction.date <= cutoff)
        return _af(q).scalar() or 0.0


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


def monthly_income_expense(months: int = 12, ref_month: int = None, ref_year: int = None):
    """Revenus et dépenses mois par mois sur N mois pour le compte actif."""
    MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                 "Juil","Août","Sep","Oct","Nov","Déc"]

    today  = datetime.now()
    base_m = ref_month if ref_month is not None else today.month
    base_y = ref_year  if ref_year  is not None else today.year
    result = []

    with Session() as session:
        for i in range(0, months):
            m, y = base_m + i, base_y
            while m > 12:
                m -= 12; y += 1

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
