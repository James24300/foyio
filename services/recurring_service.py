"""
Service de gestion des transactions récurrentes.
Au démarrage, génère automatiquement les transactions manquantes
pour tous les mois depuis start_date jusqu'au mois courant (backfill).
"""
import logging
from datetime import date

from sqlalchemy import func

from db import Session, safe_session
from models import RecurringTransaction, Transaction

logger = logging.getLogger(__name__)


def _iter_months(start: date, end: date):
    """Génère (year, month) de start à end inclus."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def apply_recurring():
    """
    Génère les transactions récurrentes manquantes pour tous les mois
    depuis start_date de chaque règle jusqu'au mois courant.
    Appelé au démarrage depuis main.py.
    Retourne le nombre de transactions créées.
    """
    today = date.today()
    created = 0

    with safe_session() as session:
        rules = session.query(RecurringTransaction).filter_by(active=True).all()

        # Pré-charger toutes les transactions récurrentes existantes
        # pour éviter une requête par règle × par mois
        existing_set = set(
            session.query(
                Transaction.recurring_id,
                func.extract("year",  Transaction.date),
                func.extract("month", Transaction.date),
            )
            .filter(Transaction.recurring_id.isnot(None))
            .all()
        )

        for rule in rules:
            rule_start = rule.start_date
            if today < rule_start:
                continue

            for year, month in _iter_months(rule_start, today):
                if (rule.id, year, month) in existing_set:
                    continue

                target_day = min(rule.day_of_month, 28)
                try:
                    target_date = date(year, month, target_day)
                except ValueError:
                    target_date = date(year, month, 28)

                session.add(Transaction(
                    date         = target_date,
                    amount       = rule.amount,
                    type         = rule.type,
                    note         = rule.label,
                    category_id  = rule.category_id,
                    recurring_id = rule.id,
                    account_id   = rule.account_id,
                ))
                created += 1

    if created:
        logger.info("Transactions récurrentes : %d créée(s).", created)
    return created


def get_recurring():
    """Retourne les règles récurrentes du compte actif."""
    import account_state
    acc_id = account_state.get_id()
    with Session() as session:
        q = session.query(RecurringTransaction)
        if acc_id is not None:
            q = q.filter(RecurringTransaction.account_id == acc_id)
        rules = q.order_by(
            RecurringTransaction.active.desc(),
            RecurringTransaction.label
        ).all()
        session.expunge_all()
        return rules


def add_recurring(label, amount, ttype, category_id, day_of_month=1, reminder_days=3):
    """Crée une nouvelle règle récurrente pour le compte actif."""
    import account_state
    with safe_session() as session:
        session.add(RecurringTransaction(
            label         = label.strip(),
            amount        = float(amount),
            type          = ttype,
            category_id   = category_id,
            account_id    = account_state.get_id(),
            day_of_month  = max(1, min(28, int(day_of_month))),
            active        = True,
            start_date    = date.today().replace(day=1),
            reminder_days = max(0, int(reminder_days)),
        ))


def toggle_recurring(rule_id):
    """Active ou désactive une règle."""
    with safe_session() as session:
        rule = session.query(RecurringTransaction).filter_by(id=rule_id).first()
        if rule:
            rule.active = not rule.active


def delete_recurring(rule_id):
    """Supprime une règle (les transactions déjà créées sont conservées)."""
    with safe_session() as session:
        rule = session.query(RecurringTransaction).filter_by(id=rule_id).first()
        if rule:
            session.delete(rule)


def get_overdue_recurring() -> list:
    """
    Retourne les règles récurrentes dont le jour est passé ce mois-ci
    et qui n'ont pas encore été générées.
    """
    today = date.today()
    overdue = []

    with Session() as session:
        import account_state
        acc_id = account_state.get_id()
        q = session.query(RecurringTransaction).filter_by(active=True)
        if acc_id is not None:
            q = q.filter(RecurringTransaction.account_id == acc_id)
        rules = q.all()

        for rule in rules:
            if today < rule.start_date:
                continue
            target_day = min(rule.day_of_month, 28)
            if target_day > today.day:
                continue  # pas encore due ce mois-ci

            existing = (
                session.query(Transaction)
                .filter(Transaction.recurring_id == rule.id)
                .filter(func.extract("year",  Transaction.date) == today.year)
                .filter(func.extract("month", Transaction.date) == today.month)
                .first()
            )
            if not existing:
                overdue.append({
                    "label":  rule.label,
                    "amount": rule.amount,
                    "type":   rule.type,
                    "day":    target_day,
                })
        session.expunge_all()

    return overdue


def get_upcoming_recurring(days_ahead: int = 3) -> list:
    """
    Retourne les récurrentes à venir dans les N prochains jours.
    Utilise le reminder_days de chaque règle si disponible,
    sinon utilise days_ahead comme valeur par défaut.
    """
    today = date.today()
    upcoming = []

    with Session() as session:
        import account_state
        acc_id = account_state.get_id()
        q = session.query(RecurringTransaction).filter_by(active=True)
        if acc_id is not None:
            q = q.filter(RecurringTransaction.account_id == acc_id)
        rules = q.all()

        for rule in rules:
            if today < rule.start_date:
                continue
            target_day = min(rule.day_of_month, 28)
            # Utiliser reminder_days de la règle si défini, sinon days_ahead
            rule_days = rule.reminder_days if rule.reminder_days is not None else days_ahead
            # Vérifier si l'échéance tombe dans les N prochains jours
            days_until = target_day - today.day
            if 0 < days_until <= rule_days:
                # Vérifier si pas déjà générée ce mois
                existing = (
                    session.query(Transaction)
                    .filter(Transaction.recurring_id == rule.id)
                    .filter(func.extract("year",  Transaction.date) == today.year)
                    .filter(func.extract("month", Transaction.date) == today.month)
                    .first()
                )
                if not existing:
                    upcoming.append({
                        "label":      rule.label,
                        "amount":     rule.amount,
                        "type":       rule.type,
                        "day":        target_day,
                        "days_until": days_until,
                    })
        session.expunge_all()

    return upcoming
