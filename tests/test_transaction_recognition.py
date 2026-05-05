"""Tests pour le moteur de reconnaissance automatique des catégories."""
import pytest
from services.transaction_recognition import normalize, extract_keyword, find_rule, learn_rule


class TestNormalize:
    def test_lowercase(self):
        assert normalize("LIDL") == "lidl"

    def test_accents_removed(self):
        assert normalize("épicerie") == "epicerie"
        assert normalize("café") == "cafe"
        assert normalize("boulangère") == "boulangere"
        assert normalize("réseau") == "reseau"

    def test_empty_string(self):
        assert normalize("") == ""

    def test_none_like_empty(self):
        assert normalize(None) == ""

    def test_mixed(self):
        assert normalize("Château Étoile") == "chateau etoile"


class TestExtractKeyword:
    def test_extracts_longest_meaningful_word(self):
        kw = extract_keyword("PRLV SEPA NETFLIX")
        assert kw == "netflix"

    def test_ignores_generic_words(self):
        kw = extract_keyword("CARTE PAIEMENT LIDL")
        assert kw == "lidl"

    def test_ignores_numeric_codes(self):
        kw = extract_keyword("CARTE X4832 AMAZON")
        assert kw == "amazon"

    def test_ignores_dates(self):
        kw = extract_keyword("PRELEVEMENT 16/03 SFR")
        assert kw == "sfr"

    def test_returns_none_if_only_generics(self):
        kw = extract_keyword("CARTE VIREMENT SEPA")
        assert kw is None

    def test_returns_none_for_empty(self):
        assert extract_keyword("") is None

    def test_prefers_longer_word(self):
        kw = extract_keyword("VIR AMAZON PRIME")
        # "amazon" (6) et "prime" (5) → "amazon"
        assert kw == "amazon"

    def test_minimum_3_chars(self):
        kw = extract_keyword("ab cd ef SPOTIFY")
        assert kw == "spotify"


class TestFindRule:
    """Tests d'intégration — nécessitent la DB en mémoire (fixture conftest)."""

    def test_returns_none_for_empty(self):
        assert find_rule("") is None
        assert find_rule(None) is None

    def test_builtin_pattern_lidl(self, session):
        from models import Category
        cat = Category(name="courses", icon=None, color="#22c55e")
        session.add(cat); session.commit()
        from services.transaction_recognition import _invalidate_cache
        _invalidate_cache()
        result = find_rule("PAIEMENT CB LIDL 3355")
        assert result == cat.id

    def test_builtin_pattern_netflix(self, session):
        from models import Category
        cat = Category(name="loisirs", icon=None, color="#6366f1")
        session.add(cat); session.commit()
        from services.transaction_recognition import _invalidate_cache
        _invalidate_cache()
        result = find_rule("PRELEVEMENT NETFLIX")
        assert result == cat.id

    def test_user_rule_takes_priority(self, session):
        from models import Category, TransactionRule
        cat_auto = Category(name="courses", icon=None, color="#22c55e")
        cat_user = Category(name="divers", icon=None, color="#888888")
        session.add_all([cat_auto, cat_user]); session.commit()
        # Règle utilisateur qui pointe vers cat_user
        rule = TransactionRule(keyword="lidl", category_id=cat_user.id)
        session.add(rule); session.commit()
        from services.transaction_recognition import _invalidate_cache
        _invalidate_cache()
        result = find_rule("PAIEMENT CB LIDL 3355")
        assert result == cat_user.id

    def test_learn_rule_then_find(self, session):
        from models import Category
        cat = Category(name="telephonie", icon=None, color="#3b82f6")
        session.add(cat); session.commit()
        learn_rule("sfr", cat.id)
        from services.transaction_recognition import _invalidate_cache
        _invalidate_cache()
        result = find_rule("PRELEVEMENT SFR MOBILE")
        assert result == cat.id

    def test_learn_rule_updates_existing(self, session):
        from models import Category, TransactionRule
        cat1 = Category(name="A", icon=None, color="#111")
        cat2 = Category(name="B", icon=None, color="#222")
        session.add_all([cat1, cat2]); session.commit()
        learn_rule("orange", cat1.id)
        learn_rule("orange", cat2.id)  # mise à jour
        rule = session.query(TransactionRule).filter_by(keyword="orange").first()
        assert rule.category_id == cat2.id
