"""Tests pour le service de transactions."""
from datetime import date, datetime

from db import Session, safe_session
from models import Transaction, Category, TransactionRule
from services.transaction_service import (
    add_transaction,
    find_monthly_duplicates,
    _notes_match,
)
import account_state


class TestAddTransaction:
    def _add_category(self, session):
        cat = Category(name="Courses", icon="groceries.png", color="#22c55e")
        session.add(cat)
        session.commit()
        return cat.id

    def test_basic_add(self, session):
        cat_id = self._add_category(session)
        add_transaction(50.0, "expense", cat_id, "LIDL courses", datetime(2026, 3, 15))
        txns = session.query(Transaction).all()
        assert len(txns) == 1
        assert txns[0].amount == 50.0
        assert txns[0].note == "LIDL courses"

    def test_duplicate_exact_ignored(self, session):
        """Un doublon exact (même montant, date, type, note) est ignoré."""
        cat_id = self._add_category(session)
        add_transaction(50.0, "expense", cat_id, "LIDL courses", datetime(2026, 3, 15))
        add_transaction(50.0, "expense", cat_id, "LIDL courses", datetime(2026, 3, 15))
        assert session.query(Transaction).count() == 1

    def test_different_note_not_duplicate(self, session):
        """Même montant/date mais note différente → pas de doublon."""
        cat_id = self._add_category(session)
        add_transaction(50.0, "expense", cat_id, "LIDL courses", datetime(2026, 3, 15))
        add_transaction(50.0, "expense", cat_id, "CARREFOUR", datetime(2026, 3, 15))
        assert session.query(Transaction).count() == 2

    def test_auto_learns_rule(self, session):
        """Quand on ajoute une transaction avec note+catégorie, la règle est apprise."""
        cat_id = self._add_category(session)
        add_transaction(30.0, "expense", cat_id, "NETFLIX", datetime(2026, 3, 15))
        rule = session.query(TransactionRule).filter_by(keyword="netflix").first()
        assert rule is not None
        assert rule.category_id == cat_id


class TestNotesMatch:
    def test_both_empty(self):
        assert _notes_match(None, None) is True
        assert _notes_match("", "") is True

    def test_one_empty(self):
        assert _notes_match("hello", None) is False
        assert _notes_match(None, "hello") is False

    def test_exact_match(self):
        assert _notes_match("LIDL 3355", "LIDL 3355") is True

    def test_partial_match(self):
        assert _notes_match("LIDL", "LIDL PARIS 3355") is True

    def test_no_match(self):
        assert _notes_match("LIDL", "CARREFOUR") is False


class TestFindMonthlyDuplicates:
    def _setup_account(self, session):
        from models import Account
        acc = Account(name="Test", type="checking", active=True)
        session.add(acc)
        session.commit()
        return acc.id

    def test_detects_duplicates(self, session):
        """Deux transactions même montant + même catégorie = doublon."""
        acc_id = self._setup_account(session)
        cat = Category(name="Courses", icon="groceries.png", color="#22c55e")
        session.add(cat)
        session.commit()

        for _ in range(2):
            session.add(Transaction(
                date=date(2026, 3, 10), amount=50.0, type="expense",
                note="LIDL", category_id=cat.id, account_id=acc_id
            ))
        session.commit()

        dupes = find_monthly_duplicates(2026, 3, account_id=acc_id)
        assert len(dupes) == 1

    def test_no_false_positive(self, session):
        """Deux transactions montants différents → pas de doublon."""
        acc_id = self._setup_account(session)
        cat = Category(name="Courses", icon="groceries.png", color="#22c55e")
        session.add(cat)
        session.commit()

        session.add(Transaction(
            date=date(2026, 3, 10), amount=50.0, type="expense",
            note="LIDL", category_id=cat.id, account_id=acc_id
        ))
        session.add(Transaction(
            date=date(2026, 3, 10), amount=75.0, type="expense",
            note="LIDL", category_id=cat.id, account_id=acc_id
        ))
        session.commit()

        dupes = find_monthly_duplicates(2026, 3, account_id=acc_id)
        assert len(dupes) == 0
