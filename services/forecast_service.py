"""
Service de prévisions budgétaires.

Projette les revenus, dépenses et solde cumulé mois par mois en combinant :
  - les transactions récurrentes actives (signal exact)
  - la moyenne historique des transactions variables (tendance)
"""
import logging
from datetime import date, datetime
from sqlalchemy import func

from db import Session
from models import Transaction, RecurringTransaction

logger = logging.getLogger(__name__)

MONTHS_FR = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
             "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


def _label(year: int, month: int) -> str:
    return f"{MONTHS_FR[month]} {year}"


def _next_month(year: int, month: int) -> tuple[int, int]:
    month += 1
    if month > 12:
        month = 1
        year += 1
    return year, month


def _prev_month(year: int, month: int) -> tuple[int, int]:
    month -= 1
    if month <= 0:
        month = 12
        year -= 1
    return year, month


def _month_sum(session, ttype: str, year: int, month: int, account_id) -> float:
    q = (
        session.query(func.sum(Transaction.amount))
        .filter(Transaction.type == ttype)
        .filter(func.extract("year",  Transaction.date) == year)
        .filter(func.extract("month", Transaction.date) == month)
    )
    if account_id is not None:
        q = q.filter(Transaction.account_id == account_id)
    return q.scalar() or 0.0


def _recurring_sums(session, year: int, month: int, account_id) -> tuple[float, float]:
    """Somme des récurrentes actives (income, expense) pour un mois donné."""
    q = session.query(RecurringTransaction).filter_by(active=True)
    if account_id is not None:
        q = q.filter(RecurringTransaction.account_id == account_id)
    rules = q.all()

    target = date(year, month, 1)
    income = expense = 0.0
    for r in rules:
        if r.start_date > target.replace(day=28):
            continue
        if r.type == "income":
            income += r.amount
        else:
            expense += r.amount
    return income, expense


def get_forecast(months_ahead: int = 6, history_months: int = 4,
                 account_id=None) -> dict:
    """
    Calcule les prévisions mois par mois.

    Paramètres
    ----------
    months_ahead   : nombre de mois futurs à projeter (3, 6 ou 12)
    history_months : nombre de mois passés affichés comme contexte
    account_id     : None = tous les comptes

    Retour
    ------
    {
      "months": [
        {
          "label", "year", "month",
          "income", "expense", "balance",
          "cumulative",
          "recurring_income", "recurring_expense",
          "variable_income", "variable_expense",
          "is_forecast",
        }, ...
      ],
      "avg_income":   float,  # moyenne mensuelle projetée
      "avg_expense":  float,
      "avg_savings":  float,  # avg_income - avg_expense
      "savings_rate": float,  # %
    }
    """
    now = datetime.now()
    cy, cm = now.year, now.month

    with Session() as session:
        # ── 1. Solde cumulé actuel (toutes transactions jusqu'à ce mois) ────
        q_bal = session.query(
            func.sum(Transaction.amount * func.case(
                (Transaction.type == "income",  1),
                (Transaction.type == "expense", -1),
                else_=0,
            ))
        ).filter(
            (func.extract("year",  Transaction.date) * 100 +
             func.extract("month", Transaction.date)) <= (cy * 100 + cm)
        )
        if account_id is not None:
            q_bal = q_bal.filter(Transaction.account_id == account_id)
        current_balance = q_bal.scalar() or 0.0

        # ── 2. Historique (pour tendance et affichage) ───────────────────────
        history = []
        hy, hm = cy, cm
        for _ in range(history_months):
            hy, hm = _prev_month(hy, hm)

        for _ in range(history_months):
            hy, hm = _next_month(hy, hm)

            income  = _month_sum(session, "income",  hy, hm, account_id)
            expense = _month_sum(session, "expense", hy, hm, account_id)
            rec_i, rec_e = _recurring_sums(session, hy, hm, account_id)

            history.append({
                "label":            _label(hy, hm),
                "year":             hy,
                "month":            hm,
                "income":           round(income, 2),
                "expense":          round(expense, 2),
                "balance":          round(income - expense, 2),
                "cumulative":       None,   # rempli après
                "recurring_income":  round(rec_i, 2),
                "recurring_expense": round(rec_e, 2),
                "variable_income":   round(income - rec_i, 2),
                "variable_expense":  round(expense - rec_e, 2),
                "is_forecast":       False,
            })

        # ── 3. Tendance variable (moyenne des 3 derniers mois complets) ──────
        # Exclure le mois courant (incomplet)
        past_full = [m for m in history if not (m["year"] == cy and m["month"] == cm)][-3:]
        if past_full:
            avg_var_income  = sum(m["variable_income"]  for m in past_full) / len(past_full)
            avg_var_expense = sum(m["variable_expense"] for m in past_full) / len(past_full)
        else:
            avg_var_income  = 0.0
            avg_var_expense = 0.0

        avg_var_income  = max(avg_var_income,  0.0)
        avg_var_expense = max(avg_var_expense, 0.0)

        # ── 4. Mois futurs projetés ───────────────────────────────────────────
        forecast = []
        fy, fm = cy, cm
        for _ in range(months_ahead):
            fy, fm = _next_month(fy, fm)
            rec_i, rec_e = _recurring_sums(session, fy, fm, account_id)
            income  = round(rec_i + avg_var_income,  2)
            expense = round(rec_e + avg_var_expense, 2)

            forecast.append({
                "label":             _label(fy, fm),
                "year":              fy,
                "month":             fm,
                "income":            income,
                "expense":           expense,
                "balance":           round(income - expense, 2),
                "cumulative":        None,
                "recurring_income":  round(rec_i, 2),
                "recurring_expense": round(rec_e, 2),
                "variable_income":   round(avg_var_income,  2),
                "variable_expense":  round(avg_var_expense, 2),
                "is_forecast":       True,
            })

    # ── 5. Calcul du solde cumulé running ────────────────────────────────────
    # Point de départ : solde cumulé réel à fin du mois précédent
    prev_y, prev_m = _prev_month(cy, cm)
    # On remonte au début de l'historique pour recalculer proprement
    all_months = history + forecast

    # Remettre les cumulés de l'historique en partant du plus ancien
    cum = current_balance - sum(m["balance"] for m in history)
    for m in history:
        cum += m["balance"]
        m["cumulative"] = round(cum, 2)

    # Continuer depuis le solde actuel vers le futur
    cum = current_balance
    for m in forecast:
        cum += m["balance"]
        m["cumulative"] = round(cum, 2)

    # ── 6. Statistiques de synthèse ──────────────────────────────────────────
    if forecast:
        avg_income  = round(sum(m["income"]  for m in forecast) / len(forecast), 2)
        avg_expense = round(sum(m["expense"] for m in forecast) / len(forecast), 2)
    else:
        avg_income = avg_expense = 0.0

    avg_savings  = round(avg_income - avg_expense, 2)
    savings_rate = round(avg_savings / avg_income * 100, 1) if avg_income > 0 else 0.0

    return {
        "months":       all_months,
        "avg_income":   avg_income,
        "avg_expense":  avg_expense,
        "avg_savings":  avg_savings,
        "savings_rate": savings_rate,
        "current_balance": round(current_balance, 2),
    }
