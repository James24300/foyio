"""
Fixtures partagées pour les tests Foyio.
Crée une base SQLite en mémoire pour chaque test.
"""
import sys
import os

# Ajouter le répertoire racine au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db as db_module
from db import Base

# Modules qui font `from db import Session` (référence capturée à l'import)
_MODULES_WITH_SESSION = [
    "services.transaction_service",
    "services.recurring_service",
    "services.reminder_service",
    "services.account_service",
    "services.init_categories",
    "services.transaction_recognition",
]


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    """Remplace la DB par une SQLite en mémoire pour chaque test."""
    engine = create_engine("sqlite:///:memory:")
    TestSession = sessionmaker(bind=engine)

    @contextmanager
    def test_safe_session():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Patcher le module db
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "Session", TestSession)
    monkeypatch.setattr(db_module, "safe_session", test_safe_session)

    # Patcher les références capturées dans les services
    for mod_name in _MODULES_WITH_SESSION:
        try:
            mod = __import__(mod_name, fromlist=["Session"])
            if hasattr(mod, "Session"):
                monkeypatch.setattr(mod, "Session", TestSession)
            if hasattr(mod, "safe_session"):
                monkeypatch.setattr(mod, "safe_session", test_safe_session)
        except ImportError:
            pass

    # Importer tous les modèles pour que les tables soient enregistrées
    import models  # noqa: F401
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)


@pytest.fixture
def session(in_memory_db):
    """Fournit une session DB pour les tests."""
    from db import Session
    s = Session()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def reset_account_state(monkeypatch):
    """Réinitialise l'état du compte actif entre chaque test."""
    import account_state
    monkeypatch.setattr(account_state, "_current_id", None)
    monkeypatch.setattr(account_state, "_current_name", "")
