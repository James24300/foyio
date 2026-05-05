"""Tests pour les fonctions de parsing pures de import_service."""
import pytest
from datetime import datetime

from services.import_service import _parse_amount_fr, _parse_date_fr, _clean_label


# ── _parse_amount_fr ─────────────────────────────────────────────────────────

class TestParseAmountFr:
    def test_integer(self):
        assert _parse_amount_fr("100") == 100.0

    def test_decimal_comma(self):
        assert _parse_amount_fr("1 234,56") == 1234.56

    def test_decimal_dot(self):
        assert _parse_amount_fr("45.20") == 45.20

    def test_negative(self):
        assert _parse_amount_fr("-45,20") == -45.20

    def test_nbsp_separator(self):
        assert _parse_amount_fr("1\xa0234,56") == 1234.56

    def test_empty_string(self):
        assert _parse_amount_fr("") == 0.0

    def test_dash(self):
        assert _parse_amount_fr("-") == 0.0

    def test_em_dash(self):
        assert _parse_amount_fr("—") == 0.0

    def test_invalid(self):
        assert _parse_amount_fr("abc") == 0.0

    def test_zero(self):
        assert _parse_amount_fr("0,00") == 0.0


# ── _parse_date_fr ───────────────────────────────────────────────────────────

class TestParseDateFr:
    def test_slash_format(self):
        assert _parse_date_fr("14/03/2026") == datetime(2026, 3, 14)

    def test_iso_format(self):
        assert _parse_date_fr("2026-03-14") == datetime(2026, 3, 14)

    def test_dash_format(self):
        assert _parse_date_fr("14-03-2026") == datetime(2026, 3, 14)

    def test_dot_format(self):
        assert _parse_date_fr("14.03.2026") == datetime(2026, 3, 14)

    def test_invalid_returns_none(self):
        assert _parse_date_fr("not-a-date") is None

    def test_empty_returns_none(self):
        assert _parse_date_fr("") is None

    def test_strips_whitespace(self):
        assert _parse_date_fr("  14/03/2026  ") == datetime(2026, 3, 14)


# ── _clean_label ─────────────────────────────────────────────────────────────

class TestCleanLabel:
    def test_removes_iopd(self):
        result = _clean_label("LIDL 1234IOPD PARIS")
        assert "IOPD" not in result

    def test_removes_prelevement_prefix(self):
        result = _clean_label("PRELEVEMENT EUROPEEN ABC123 DE: NETFLIX")
        assert result == "NETFLIX"

    def test_removes_vir_perm(self):
        result = _clean_label("VIR PERM POUR: DUCHANGE ANNIE")
        assert result == "DUCHANGE ANNIE"

    def test_removes_vir_inst_re(self):
        result = _clean_label("VIR INST RE XYZABC DE: MON AMI")
        assert result == "MON AMI"

    def test_removes_long_numeric_codes(self):
        result = _clean_label("AMAZON 1234567890 PARIS")
        assert "1234567890" not in result

    def test_collapses_spaces(self):
        result = _clean_label("LIDL    PARIS")
        assert "  " not in result

    def test_strips_trailing_punctuation(self):
        result = _clean_label("SOME LABEL -")
        assert not result.endswith("-")

    def test_removes_invisible_chars(self):
        result = _clean_label("LABEL�NAME")
        assert "�" not in result

    def test_plain_label_unchanged(self):
        assert _clean_label("CARREFOUR") == "CARREFOUR"
