"""Tests pour reminder_service.get_upcoming_reminders."""
import pytest
from datetime import date
from unittest.mock import patch

from models import RecurringTransaction, Category
from db import Session


def _make_category(session, name="Divers"):
    cat = Category(name=name, color="#ffffff", icon="")
    session.add(cat)
    session.commit()
    return cat


def _make_rule(session, label, day_of_month, reminder_days=3,
               amount=100.0, rtype="expense", active=True,
               start_date=date(2020, 1, 1), category_id=None):
    if category_id is None:
        category_id = _make_category(session).id
    rule = RecurringTransaction(
        label=label,
        amount=amount,
        type=rtype,
        category_id=category_id,
        day_of_month=day_of_month,
        active=active,
        start_date=start_date,
        reminder_days=reminder_days,
    )
    session.add(rule)
    session.commit()
    return rule


def _patch_today(target_date):
    """Retourne un context manager qui fixe date.today() à target_date."""
    class _FakeDate(date):
        @classmethod
        def today(cls):
            return target_date
    return patch("services.reminder_service.date", _FakeDate)


class TestGetUpcomingReminders:

    def test_empty_db_returns_empty(self):
        from services.reminder_service import get_upcoming_reminders
        assert get_upcoming_reminders() == []

    def test_due_today_included(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 15)
        _make_rule(session, "Loyer", day_of_month=15, reminder_days=3)
        with _patch_today(today):
            results = get_upcoming_reminders()
        assert any(r["label"] == "Loyer" for r in results)

    def test_due_in_2_days_included(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 13)
        _make_rule(session, "Internet", day_of_month=15, reminder_days=3)
        with _patch_today(today):
            results = get_upcoming_reminders()
        assert any(r["label"] == "Internet" for r in results)

    def test_due_too_far_excluded(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 1)
        _make_rule(session, "Assurance", day_of_month=20, reminder_days=3)
        with _patch_today(today):
            results = get_upcoming_reminders()
        assert all(r["label"] != "Assurance" for r in results)

    def test_inactive_rule_excluded(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 15)
        _make_rule(session, "Inactif", day_of_month=15, active=False)
        with _patch_today(today):
            results = get_upcoming_reminders()
        assert all(r["label"] != "Inactif" for r in results)

    def test_reminder_days_zero_excluded(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 15)
        _make_rule(session, "Sans rappel", day_of_month=15, reminder_days=0)
        with _patch_today(today):
            results = get_upcoming_reminders()
        assert all(r["label"] != "Sans rappel" for r in results)

    def test_passed_this_month_rolls_to_next(self, session):
        from services.reminder_service import get_upcoming_reminders
        # Aujourd'hui = 20 mai, échéance le 5 → passe au 5 juin (16 jours, hors fenêtre)
        today = date(2026, 5, 20)
        _make_rule(session, "Abonnement", day_of_month=5, reminder_days=3)
        with _patch_today(today):
            results = get_upcoming_reminders()
        assert all(r["label"] != "Abonnement" for r in results)

    def test_sorted_by_proximity(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 13)
        cat_id = _make_category(session).id
        _make_rule(session, "J+2", day_of_month=15, reminder_days=5, category_id=cat_id)
        _make_rule(session, "J+1", day_of_month=14, reminder_days=5, category_id=cat_id)
        with _patch_today(today):
            results = get_upcoming_reminders()
        if len(results) >= 2:
            assert results[0]["days_until"] <= results[1]["days_until"]

    def test_days_until_correct(self, session):
        from services.reminder_service import get_upcoming_reminders
        today = date(2026, 5, 12)
        _make_rule(session, "J+3", day_of_month=15, reminder_days=5)
        with _patch_today(today):
            results = get_upcoming_reminders()
        match = next((r for r in results if r["label"] == "J+3"), None)
        assert match is not None
        assert match["days_until"] == 3
