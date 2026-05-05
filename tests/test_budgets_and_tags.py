"""Tests pour les budgets (mensuel/annuel) et le système de tags."""
import pytest
from datetime import datetime

from models import Category, Transaction, Budget, Tag, TransactionTag
from services.transaction_service import (
    add_transaction,
    set_budget, delete_budget, get_budget_status,
    set_annual_budget, delete_annual_budget, get_annual_budget_status,
    save_tags, get_tags_for_transaction, get_tags_for_transactions,
)
import account_state
import period_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_category(session, name="Test"):
    cat = Category(name=name, icon=None, color="#ffffff")
    session.add(cat); session.commit()
    return cat.id


def _make_transaction(session, cat_id, amount=100.0, type_="expense",
                      note="note", year=2026, month=3):
    from db import Session as S
    t = Transaction(
        date=datetime(year, month, 15),
        amount=amount, type=type_,
        note=note, category_id=cat_id,
        account_id=account_state.get_id(),
    )
    session.add(t); session.commit()
    return t.id


# ── Budgets mensuels ──────────────────────────────────────────────────────────

class TestMonthlyBudget:
    def test_set_and_get(self, session):
        cat_id = _make_category(session)
        set_budget(cat_id, 500.0)
        b = session.query(Budget).filter_by(category_id=cat_id).first()
        assert b is not None
        assert b.monthly_limit == 500.0

    def test_update_existing(self, session):
        cat_id = _make_category(session)
        set_budget(cat_id, 300.0)
        set_budget(cat_id, 600.0)
        budgets = session.query(Budget).filter_by(category_id=cat_id).all()
        assert len(budgets) == 1
        assert budgets[0].monthly_limit == 600.0

    def test_delete(self, session):
        cat_id = _make_category(session)
        set_budget(cat_id, 200.0)
        delete_budget(cat_id)
        b = session.query(Budget).filter_by(category_id=cat_id).first()
        assert b is None

    def test_get_budget_status_tracks_spending(self, session, monkeypatch):
        cat_id = _make_category(session)
        set_budget(cat_id, 500.0)

        # Forcer la période au mois courant des transactions
        import period_state as ps
        monkeypatch.setattr(ps, "get", lambda: type("P", (), {"year": 2026, "month": 3})())

        _make_transaction(session, cat_id, amount=120.0, year=2026, month=3)
        _make_transaction(session, cat_id, amount=80.0,  year=2026, month=3)

        results = get_budget_status()
        assert len(results) == 1
        cid, limit, spent = results[0]
        assert cid == cat_id
        assert limit == 500.0
        assert spent == pytest.approx(200.0)

    def test_budget_status_ignores_income(self, session, monkeypatch):
        cat_id = _make_category(session)
        set_budget(cat_id, 500.0)
        import period_state as ps
        monkeypatch.setattr(ps, "get", lambda: type("P", (), {"year": 2026, "month": 3})())

        _make_transaction(session, cat_id, amount=300.0, type_="income", year=2026, month=3)

        results = get_budget_status()
        _, _, spent = results[0]
        assert spent == 0.0


# ── Budgets annuels ───────────────────────────────────────────────────────────

class TestAnnualBudget:
    def test_set_and_get(self, session):
        cat_id = _make_category(session)
        set_annual_budget(cat_id, 6000.0)
        b = session.query(Budget).filter_by(category_id=cat_id).first()
        assert b.annual_limit == 6000.0

    def test_update_existing_keeps_monthly(self, session):
        cat_id = _make_category(session)
        set_budget(cat_id, 500.0)
        set_annual_budget(cat_id, 6000.0)
        b = session.query(Budget).filter_by(category_id=cat_id).first()
        assert b.monthly_limit == 500.0
        assert b.annual_limit == 6000.0

    def test_delete_annual_keeps_monthly(self, session):
        cat_id = _make_category(session)
        set_budget(cat_id, 500.0)
        set_annual_budget(cat_id, 6000.0)
        delete_annual_budget(cat_id)
        b = session.query(Budget).filter_by(category_id=cat_id).first()
        assert b is not None
        assert b.monthly_limit == 500.0
        assert b.annual_limit is None

    def test_delete_annual_removes_row_if_no_monthly(self, session):
        cat_id = _make_category(session)
        set_annual_budget(cat_id, 6000.0)
        delete_annual_budget(cat_id)
        b = session.query(Budget).filter_by(category_id=cat_id).first()
        assert b is None

    def test_get_annual_status_sums_year(self, session):
        cat_id = _make_category(session)
        set_annual_budget(cat_id, 12000.0)
        _make_transaction(session, cat_id, amount=1000.0, year=2026, month=1)
        _make_transaction(session, cat_id, amount=2000.0, year=2026, month=6)
        _make_transaction(session, cat_id, amount=500.0,  year=2025, month=12)  # autre année

        results = get_annual_budget_status(year=2026)
        assert len(results) == 1
        cid, limit, spent = results[0]
        assert cid == cat_id
        assert limit == 12000.0
        assert spent == pytest.approx(3000.0)


# ── Tags ──────────────────────────────────────────────────────────────────────

class TestTags:
    def test_save_and_get_tags(self, session):
        cat_id = _make_category(session)
        tx_id = _make_transaction(session, cat_id)
        save_tags(tx_id, ["vacances", "été"])
        tags = get_tags_for_transaction(tx_id)
        assert set(tags) == {"vacances", "été"}

    def test_save_creates_missing_tags(self, session):
        cat_id = _make_category(session)
        tx_id = _make_transaction(session, cat_id)
        save_tags(tx_id, ["nouveau_tag"])
        tag = session.query(Tag).filter_by(name="nouveau_tag").first()
        assert tag is not None

    def test_save_replaces_existing_tags(self, session):
        cat_id = _make_category(session)
        tx_id = _make_transaction(session, cat_id)
        save_tags(tx_id, ["ancien"])
        save_tags(tx_id, ["nouveau"])
        tags = get_tags_for_transaction(tx_id)
        assert tags == ["nouveau"]

    def test_save_empty_tags_clears(self, session):
        cat_id = _make_category(session)
        tx_id = _make_transaction(session, cat_id)
        save_tags(tx_id, ["vacances"])
        save_tags(tx_id, [])
        tags = get_tags_for_transaction(tx_id)
        assert tags == []

    def test_get_tags_for_transactions_batch(self, session):
        cat_id = _make_category(session)
        tx1 = _make_transaction(session, cat_id, note="tx1")
        tx2 = _make_transaction(session, cat_id, note="tx2")
        save_tags(tx1, ["sport"])
        save_tags(tx2, ["culture", "loisir"])
        result = get_tags_for_transactions([tx1, tx2])
        assert result[tx1] == ["sport"]
        assert set(result[tx2]) == {"culture", "loisir"}

    def test_get_tags_for_empty_list(self):
        result = get_tags_for_transactions([])
        assert result == {}

    def test_tags_ignore_blank_names(self, session):
        cat_id = _make_category(session)
        tx_id = _make_transaction(session, cat_id)
        save_tags(tx_id, ["valide", "  ", ""])
        tags = get_tags_for_transaction(tx_id)
        assert tags == ["valide"]
