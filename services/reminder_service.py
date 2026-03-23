"""
Service de rappels de paiements récurrents.
Vérifie les transactions récurrentes dont l'échéance approche
et retourne la liste des rappels à afficher.
"""
import logging
from datetime import date
import calendar

from db import Session
from models import RecurringTransaction

logger = logging.getLogger(__name__)


def get_upcoming_reminders(account_id=None) -> list:
    """
    Retourne les rappels de paiements à venir.
    Pour chaque transaction récurrente active, vérifie si le jour d'échéance
    tombe dans les `reminder_days` prochains jours.

    Retourne une liste de dicts :
        {label, amount, type, due_date, days_until, reminder_days}
    """
    today = date.today()
    reminders = []

    with Session() as session:
        q = session.query(RecurringTransaction).filter_by(active=True)
        if account_id is not None:
            q = q.filter(RecurringTransaction.account_id == account_id)
        rules = q.all()

        for rule in rules:
            if today < rule.start_date:
                continue

            reminder_days = rule.reminder_days if rule.reminder_days is not None else 3
            if reminder_days <= 0:
                continue  # rappels désactivés pour cette règle

            target_day = min(rule.day_of_month, 28)

            # Calculer la prochaine date d'échéance
            # D'abord essayer ce mois-ci
            year, month = today.year, today.month
            last_day = calendar.monthrange(year, month)[1]
            actual_day = min(target_day, last_day)

            try:
                due_this_month = date(year, month, actual_day)
            except ValueError:
                due_this_month = date(year, month, 28)

            if due_this_month >= today:
                # L'échéance est encore à venir ce mois-ci
                due_date = due_this_month
            else:
                # L'échéance est passée ce mois-ci, prendre le mois suivant
                if month == 12:
                    next_year, next_month = year + 1, 1
                else:
                    next_year, next_month = year, month + 1
                last_day_next = calendar.monthrange(next_year, next_month)[1]
                actual_day_next = min(target_day, last_day_next)
                try:
                    due_date = date(next_year, next_month, actual_day_next)
                except ValueError:
                    due_date = date(next_year, next_month, 28)

            days_until = (due_date - today).days

            if 0 <= days_until <= reminder_days:
                reminders.append({
                    "label":         rule.label,
                    "amount":        rule.amount,
                    "type":          rule.type,
                    "due_date":      due_date,
                    "days_until":    days_until,
                    "reminder_days": reminder_days,
                })

        session.expunge_all()

    # Trier par proximité (le plus proche en premier)
    reminders.sort(key=lambda r: r["days_until"])
    return reminders
