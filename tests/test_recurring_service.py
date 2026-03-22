"""Tests pour le service de transactions récurrentes."""
from datetime import date
from unittest.mock import patch

from db import Session, safe_session
from models import RecurringTransaction, Transaction
from services.recurring_service import apply_recurring, _iter_months


# ── Tests _iter_months ───────────────────────────────────────────

class TestIterMonths:
    def test_same_month(self):
        result = list(_iter_months(date(2026, 3, 1), date(2026, 3, 15)))
        assert result == [(2026, 3)]

    def test_several_months(self):
        result = list(_iter_months(date(2026, 1, 1), date(2026, 4, 1)))
        assert result == [(2026, 1), (2026, 2), (2026, 3), (2026, 4)]

    def test_cross_year(self):
        result = list(_iter_months(date(2025, 11, 1), date(2026, 2, 1)))
        assert result == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]

    def test_end_before_start(self):
        result = list(_iter_months(date(2026, 5, 1), date(2026, 3, 1)))
        assert result == []


# ── Tests apply_recurring ────────────────────────────────────────

class TestApplyRecurring:
    def _create_rule(self, session, **kwargs):
        defaults = dict(
            label="Loyer",
            amount=800.0,
            type="expense",
            category_id=1,
            account_id=None,
            day_of_month=5,
            active=True,
            start_date=date(2026, 1, 1),
        )
        defaults.update(kwargs)
        rule = RecurringTransaction(**defaults)
        session.add(rule)
        session.commit()
        return rule

    @patch("services.recurring_service.date")
    def test_generates_current_month(self, mock_date, session):
        """Doit générer la transaction du mois courant."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        self._create_rule(session)
        created = apply_recurring()

        assert created == 3  # Jan + Fev + Mars
        txns = session.query(Transaction).all()
        assert len(txns) == 3

    @patch("services.recurring_service.date")
    def test_backfill_missing_months(self, mock_date, session):
        """Si l'app n'a pas tourné en Jan et Fev, doit rattraper."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        self._create_rule(session)
        created = apply_recurring()

        assert created == 3
        dates = sorted(t.date for t in session.query(Transaction).all())
        assert dates[0].month == 1
        assert dates[1].month == 2
        assert dates[2].month == 3

    @patch("services.recurring_service.date")
    def test_no_duplicate_on_rerun(self, mock_date, session):
        """Relancer apply_recurring ne doit pas recréer de transactions."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        self._create_rule(session)
        apply_recurring()
        created2 = apply_recurring()

        assert created2 == 0
        assert session.query(Transaction).count() == 3

    @patch("services.recurring_service.date")
    def test_skips_future_rule(self, mock_date, session):
        """Règle avec start_date dans le futur → rien généré."""
        mock_date.today.return_value = date(2026, 1, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        self._create_rule(session, start_date=date(2026, 6, 1))
        created = apply_recurring()

        assert created == 0

    @patch("services.recurring_service.date")
    def test_inactive_rule_ignored(self, mock_date, session):
        """Règle inactive → rien généré."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        self._create_rule(session, active=False)
        created = apply_recurring()

        assert created == 0

    @patch("services.recurring_service.date")
    def test_day_capped_at_28(self, mock_date, session):
        """Jour > 28 doit être capé à 28."""
        mock_date.today.return_value = date(2026, 2, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        self._create_rule(session, day_of_month=31, start_date=date(2026, 2, 1))
        apply_recurring()

        txn = session.query(Transaction).first()
        assert txn.date == date(2026, 2, 28)
