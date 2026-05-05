"""Tests pour forecast_service (helpers purs) et savings_service.simulate."""
import pytest
from services.forecast_service import _label, _next_month, _prev_month
from services.savings_service import simulate


# ── forecast_service helpers ─────────────────────────────────────────────────

class TestLabel:
    def test_basic(self):
        assert _label(2024, 3) == "Mar 2024"

    def test_january(self):
        assert _label(2025, 1) == "Jan 2025"

    def test_december(self):
        assert _label(2023, 12) == "Déc 2023"


class TestNextMonth:
    def test_mid_year(self):
        assert _next_month(2024, 6) == (2024, 7)

    def test_december_wraps(self):
        assert _next_month(2024, 12) == (2025, 1)

    def test_november(self):
        assert _next_month(2024, 11) == (2024, 12)


class TestPrevMonth:
    def test_mid_year(self):
        assert _prev_month(2024, 6) == (2024, 5)

    def test_january_wraps(self):
        assert _prev_month(2024, 1) == (2023, 12)

    def test_february(self):
        assert _prev_month(2024, 2) == (2024, 1)

    def test_roundtrip(self):
        y, m = _next_month(2024, 12)
        assert _prev_month(y, m) == (2024, 12)


# ── savings_service.simulate ─────────────────────────────────────────────────

class TestSimulate:
    def test_zero_monthly_returns_empty(self):
        r = simulate(0, 1000)
        assert r["months"] is None
        assert r["evolution"] == []

    def test_negative_monthly_returns_empty(self):
        r = simulate(-50, 1000)
        assert r["months"] is None

    def test_already_reached(self):
        r = simulate(100, 500, current=500)
        assert r["months"] == 0
        assert r["reached"] is True

    def test_simple_no_interest(self):
        r = simulate(100, 300, current=0, annual_rate=0)
        assert r["months"] == 3
        assert r["reached"] is True

    def test_with_partial_current(self):
        r = simulate(100, 300, current=200, annual_rate=0)
        assert r["months"] == 1

    def test_evolution_length(self):
        r = simulate(100, 400, current=0, annual_rate=0)
        # évolution contient solde initial + 1 entrée par mois
        assert len(r["evolution"]) == r["months"] + 1

    def test_with_interest_fewer_months(self):
        r_no  = simulate(100, 1200, current=0, annual_rate=0)
        r_yes = simulate(100, 1200, current=0, annual_rate=5.0)
        assert r_yes["months"] <= r_no["months"]

    def test_target_date_returned(self):
        r = simulate(500, 500, current=0, annual_rate=0)
        assert isinstance(r["target_date"], str)
        assert len(r["target_date"]) > 0
