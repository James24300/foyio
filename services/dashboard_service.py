from datetime import datetime

from sqlalchemy import func

from db import Session
from models import Transaction, Category
from services.stats_service import monthly_totals
import period_state
import account_state


def _af(query):
    """Filtre par compte actif."""
    acc_id = account_state.get_id()
    if acc_id is not None:
        query = query.filter(Transaction.account_id == acc_id)
    return query


def dashboard_stats():
    return monthly_totals()


def top_expenses(limit=3):
    """Top N catégories dépensières pour la période et le compte actifs."""
    with Session() as session:
        p = period_state.get()
        q = (
            session.query(Category.name, func.sum(Transaction.amount))
            .join(Category, Transaction.category_id == Category.id)
            .filter(Transaction.type == "expense")
            .filter(func.extract("year",  Transaction.date) == p.year)
            .filter(func.extract("month", Transaction.date) == p.month)
        )
        return (
            _af(q)
            .group_by(Category.name)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(limit)
            .all()
        )


def forecast_balance():
    """Prévision ou solde réel selon la période, filtré par compte."""
    p   = period_state.get()
    now = datetime.now()
    import calendar

    with Session() as session:
        def _sum(ttype, year, month):
            q = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.type == ttype)
                .filter(func.extract("year",  Transaction.date) == year)
                .filter(func.extract("month", Transaction.date) == month)
            )
            return _af(q).scalar() or 0

        if p.year == now.year and p.month == now.month:
            # Mois courant : projection sur base des 3 mois précédents
            total_exp = 0
            for i in range(1, 4):
                m, y = p.month - i, p.year
                if m <= 0: m += 12; y -= 1
                total_exp += _sum("expense", y, m)
            avg_daily_exp = (total_exp / 3) / 30
            days_left = calendar.monthrange(p.year, p.month)[1] - now.day
            income_cur  = _sum("income",  p.year, p.month)
            expense_cur = _sum("expense", p.year, p.month)
            forecast_exp = expense_cur + avg_daily_exp * days_left
            return income_cur - forecast_exp
        else:
            # Mois passé : solde réel
            return (_sum("income",  p.year, p.month)
                  - _sum("expense", p.year, p.month))


def forecast_income(account_id=None):
    """Projection des revenus : moyenne, tendance, projection mois courant."""
    now = datetime.now()
    import calendar

    with Session() as session:
        def _income(year, month):
            q = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.type == "income")
                .filter(func.extract("year",  Transaction.date) == year)
                .filter(func.extract("month", Transaction.date) == month)
            )
            if account_id is not None:
                q = q.filter(Transaction.account_id == account_id)
            else:
                q = _af(q)
            return q.scalar() or 0

        # Collecter les revenus des 6 derniers mois (hors mois courant)
        monthly = []
        for i in range(1, 7):
            m, y = now.month - i, now.year
            while m <= 0:
                m += 12; y -= 1
            val = _income(y, m)
            monthly.append(val)

        # Ne garder que les mois avec des revenus (min 1 mois)
        active = [v for v in monthly if v > 0]
        if not active:
            active = monthly[:3] if monthly else [0]

        avg_monthly = sum(active) / len(active) if active else 0

        # Revenu actuel du mois courant
        current_income = _income(now.year, now.month)

        # Projection : proportionnelle au jour du mois
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        day_of_month  = now.day

        if day_of_month > 0 and current_income > 0:
            # Extrapoler le revenu actuel sur le mois complet
            projected = (current_income / day_of_month) * days_in_month
        else:
            projected = avg_monthly

        # Pondérer entre extrapolation et moyenne historique
        if day_of_month >= 20:
            weight = 0.8  # fin de mois, plus de poids sur l'actuel
        elif day_of_month >= 10:
            weight = 0.5
        else:
            weight = 0.3  # début de mois, plus de poids sur la moyenne

        if current_income > 0:
            projected = projected * weight + avg_monthly * (1 - weight)
        else:
            projected = avg_monthly

        # Tendance : comparer les 3 derniers mois aux 3 précédents
        recent = sum(monthly[:3])
        older  = sum(monthly[3:6])
        if older > 0:
            change = ((recent - older) / older) * 100
            if change > 5:
                trend = "up"
            elif change < -5:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = "stable"

    return {
        "average_monthly": avg_monthly,
        "projected_current_month": projected,
        "current_income": current_income,
        "trend": trend,
    }


def biggest_category():
    """Catégorie la plus dépensière pour la période et le compte actifs."""
    with Session() as session:
        p = period_state.get()
        q = (
            session.query(Category.name, func.sum(Transaction.amount))
            .join(Category, Transaction.category_id == Category.id)
            .filter(Transaction.type == "expense")
            .filter(func.extract("year",  Transaction.date) == p.year)
            .filter(func.extract("month", Transaction.date) == p.month)
        )
        return (
            _af(q)
            .group_by(Category.name)
            .order_by(func.sum(Transaction.amount).desc())
            .first()
        )


def compare_with_previous():
    """Comparaison avec le mois précédent pour le compte actif."""
    p = period_state.get()
    pm, py = p.month - 1, p.year
    if pm <= 0: pm += 12; py -= 1

    with Session() as session:
        def _totals(year, month):
            def _s(ttype):
                q = (
                    session.query(func.sum(Transaction.amount))
                    .filter(Transaction.type == ttype)
                    .filter(func.extract("year",  Transaction.date) == year)
                    .filter(func.extract("month", Transaction.date) == month)
                )
                return _af(q).scalar() or 0
            return _s("income"), _s("expense")

        ci, ce = _totals(p.year, p.month)
        pi, pe = _totals(py, pm)

    def pct(cur, prv):
        return ((cur - prv) / prv * 100) if prv else None

    return pct(ci, pi), pct(ce, pe)


def recent_transactions(limit=5):
    """Dernières transactions du compte actif."""
    from services.transaction_service import get_transactions_for_period
    return get_transactions_for_period(limit, 0)


def budget_alerts():
    """Budgets dépassés ou proches du seuil pour le compte actif."""
    from services.transaction_service import get_budget_status
    from db import Session
    from models import Category

    data = get_budget_status()
    alerts = []

    with Session() as session:
        cats = {c.id: c.name for c in session.query(Category).all()}

    for cat_id, limit, spent in data:
        if limit <= 0:
            continue
        pct = (spent / limit) * 100
        if pct >= 80:
            alerts.append((cats.get(cat_id, "Inconnu"), limit, spent, pct))

    alerts.sort(key=lambda x: x[3], reverse=True)
    return alerts
