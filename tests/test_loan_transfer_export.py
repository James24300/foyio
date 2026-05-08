"""Tests pour loan_service, transfer_service et export_service."""
import csv
import os
import tempfile
import pytest
from datetime import date
from unittest.mock import patch

from models import Loan, Account, Category, Transaction
from db import Session


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_account(session, name="Courant"):
    acc = Account(name=name, type="checking", active=True)
    session.add(acc)
    session.commit()
    return acc


def _make_category(session, name="Loyer", transfer_account_id=None):
    cat = Category(name=name, color="#fff", icon="",
                   transfer_account_id=transfer_account_id)
    session.add(cat)
    session.commit()
    return cat


def _make_loan(session, name="Immo", total=100_000.0, payment=500.0,
               rate=2.0, start=date(2024, 1, 1), end=date(2044, 1, 1),
               account_id=None):
    from services.loan_service import add_loan
    return add_loan(name, total, payment, rate, start, end, account_id)


# ── loan_service ─────────────────────────────────────────────────────────────

class TestLoanCRUD:

    def test_add_and_get(self, session):
        from services.loan_service import add_loan, get_loans
        add_loan("Voiture", 15000.0, 250.0, 3.5,
                 date(2024, 6, 1), date(2028, 6, 1))
        loans = get_loans(active_only=True)
        assert len(loans) == 1
        assert loans[0].name == "Voiture"
        assert loans[0].total_amount == 15000.0

    def test_delete_deactivates(self, session):
        from services.loan_service import add_loan, get_loans, delete_loan
        l = add_loan("Perso", 5000.0, 200.0, 0.0,
                     date(2024, 1, 1), date(2026, 1, 1))
        delete_loan(l.id)
        assert get_loans(active_only=True) == []

    def test_update(self, session):
        from services.loan_service import add_loan, update_loan, get_loans
        l = add_loan("Ancien", 10000.0, 300.0, 1.0,
                     date(2024, 1, 1), date(2027, 1, 1))
        update_loan(l.id, "Nouveau", 12000.0, 350.0, 1.5,
                    date(2024, 1, 1), date(2027, 1, 1))
        updated = get_loans(active_only=True)[0]
        assert updated.name == "Nouveau"
        assert updated.total_amount == 12000.0

    def test_get_empty(self):
        from services.loan_service import get_loans
        assert get_loans() == []


class TestComputeCurrentRemaining:

    def _mock_loan(self, total, payment, rate, start):
        """Crée un objet Loan sans DB."""
        class _L:
            total_amount    = total
            monthly_payment = payment
            interest_rate   = rate
            start_date      = start
        return _L()

    def test_before_start_returns_total(self):
        from services.loan_service import compute_current_remaining
        loan = self._mock_loan(10000.0, 300.0, 0.0, date(2030, 1, 1))
        with patch("services.loan_service.date") as md:
            class _FD(date):
                @classmethod
                def today(cls): return date(2026, 1, 1)
            import services.loan_service as _svc
            _svc_date_orig = _svc.date
            _svc.date = _FD
            result = compute_current_remaining(loan)
            _svc.date = _svc_date_orig
        assert result == 10000.0

    def test_zero_interest_reduces_by_principal(self):
        from services.loan_service import compute_current_remaining
        import services.loan_service as _svc

        # Prêt 0% : chaque mois enlève exactement la mensualité
        loan = self._mock_loan(1200.0, 100.0, 0.0, date(2026, 1, 1))
        _orig = _svc.date

        class _FD(date):
            @classmethod
            def today(cls): return date(2026, 3, 1)  # 2 mois après start

        _svc.date = _FD
        try:
            result = compute_current_remaining(loan)
        finally:
            _svc.date = _orig
        assert result == pytest.approx(1000.0, abs=1.0)

    def test_fully_repaid_returns_zero(self):
        from services.loan_service import compute_current_remaining
        import services.loan_service as _svc

        loan = self._mock_loan(500.0, 500.0, 0.0, date(2024, 1, 1))
        _orig = _svc.date

        class _FD(date):
            @classmethod
            def today(cls): return date(2026, 1, 1)  # bien après

        _svc.date = _FD
        try:
            result = compute_current_remaining(loan)
        finally:
            _svc.date = _orig
        assert result == 0.0


class TestAmortizationSchedule:

    def test_schedule_length(self, session):
        from services.loan_service import add_loan, get_amortization_schedule
        l = add_loan("Test", 12000.0, 1000.0, 0.0,
                     date(2026, 1, 1), date(2027, 1, 1))
        schedule = get_amortization_schedule(l.id)
        assert len(schedule) > 0

    def test_schedule_keys(self, session):
        from services.loan_service import add_loan, get_amortization_schedule
        l = add_loan("Test", 6000.0, 500.0, 0.0,
                     date(2026, 1, 1), date(2026, 12, 1))
        schedule = get_amortization_schedule(l.id)
        assert schedule
        row = schedule[0]
        for key in ("date", "payment", "principal", "interest", "remaining"):
            assert key in row

    def test_zero_interest_no_interest_payments(self, session):
        from services.loan_service import add_loan, get_amortization_schedule
        l = add_loan("0%", 1000.0, 100.0, 0.0,
                     date(2026, 1, 1), date(2026, 12, 1))
        schedule = get_amortization_schedule(l.id)
        for row in schedule:
            assert row["interest"] == pytest.approx(0.0, abs=0.01)


# ── transfer_service ─────────────────────────────────────────────────────────

class TestTransferService:

    def test_no_transfer_without_link(self, session):
        from services.transfer_service import get_transfer_account
        cat = _make_category(session, "Courses")
        acc_id, acc_name = get_transfer_account(cat.id)
        assert acc_id is None
        assert acc_name is None

    def test_no_transfer_invalid_category(self):
        from services.transfer_service import get_transfer_account
        acc_id, acc_name = get_transfer_account(9999)
        assert acc_id is None

    def test_no_transfer_none_category(self):
        from services.transfer_service import get_transfer_account
        acc_id, acc_name = get_transfer_account(None)
        assert acc_id is None

    def test_returns_linked_account(self, session):
        from services.transfer_service import get_transfer_account
        acc = _make_account(session, "Épargne")
        cat = _make_category(session, "Épargne cat",
                             transfer_account_id=acc.id)
        acc_id, acc_name = get_transfer_account(cat.id)
        assert acc_id == acc.id
        assert acc_name == "Épargne"

    def test_create_mirror_transaction(self, session):
        from services.transfer_service import create_mirror_transaction
        acc = _make_account(session)
        cat = _make_category(session)
        tx_id = create_mirror_transaction(
            source_date=date(2026, 5, 1),
            amount=500.0,
            category_id=cat.id,
            destination_account_id=acc.id,
            note="Virement test",
        )
        assert tx_id is not None
        tx = session.query(Transaction).filter_by(id=tx_id).first()
        assert tx.type == "income"
        assert tx.amount == 500.0
        assert tx.account_id == acc.id


# ── export_service ───────────────────────────────────────────────────────────

class TestExportService:

    def _make_transaction(self, session, amount=100.0, ttype="expense",
                          note="Test", tx_date=date(2026, 5, 1)):
        cat = _make_category(session, f"Cat{amount}")
        acc = session.query(Account).first()
        if acc is None:
            acc = _make_account(session)
        tx = Transaction(
            date=tx_date, amount=amount, type=ttype,
            note=note, category_id=cat.id, account_id=acc.id,
        )
        session.add(tx)
        session.commit()
        return tx

    def test_export_csv_creates_file(self, session):
        from services.export_service import export_transactions_csv
        self._make_transaction(session)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            count = export_transactions_csv(path, all_periods=True)
            assert count >= 1
            assert os.path.exists(path)
        finally:
            os.unlink(path)

    def test_export_csv_content(self, session):
        from services.export_service import export_transactions_csv
        self._make_transaction(session, amount=42.0, note="Carrefour")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False,
                                         mode="w") as f:
            path = f.name
        try:
            export_transactions_csv(path, all_periods=True)
            with open(path, encoding="utf-8-sig") as f:
                content = f.read()
            assert "Carrefour" in content or "42" in content
        finally:
            os.unlink(path)

    def test_export_empty_db(self):
        from services.export_service import export_transactions_csv
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            count = export_transactions_csv(path, all_periods=True)
            assert count == 0
        finally:
            os.unlink(path)
