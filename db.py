"""
Module base de données — Foyio
Gère la connexion SQLAlchemy, les sessions et les migrations de schéma.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False}
)

Session = sessionmaker(bind=engine)
Base = declarative_base()


@contextmanager
def safe_session():
    """Context manager avec commit automatique et rollback en cas d'erreur."""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        import traceback
        print("Erreur SQL :", e)
        traceback.print_exc()
        raise
    finally:
        session.close()


# ── Utilitaires d'introspection ──────────────────────────────────────

def _col_exists(inspector, table, col):
    cols = [c["name"] for c in inspector.get_columns(table)]
    return col in cols


def _table_exists(inspector, table):
    return table in inspector.get_table_names()


# ── Migration centralisée ────────────────────────────────────────────

def migrate_database():
    """
    Applique TOUTES les migrations dans l'ordre.
    Fonction unique appelée une seule fois au démarrage depuis main.py.
    """
    inspector = inspect(engine)

    # v3.1 : recurring_id sur transactions
    if _table_exists(inspector, "transactions") and \
       not _col_exists(inspector, "transactions", "recurring_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE transactions ADD COLUMN recurring_id "
                "INTEGER REFERENCES recurring_transactions(id)"))
            conn.commit()
        print("Migration v3.1 : recurring_id ajouté")

    # v3.2a : account_id sur transactions
    if _table_exists(inspector, "transactions") and \
       not _col_exists(inspector, "transactions", "account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE transactions ADD COLUMN account_id "
                "INTEGER REFERENCES accounts(id)"))
            conn.commit()
        print("Migration v3.2a : account_id sur transactions ajouté")

    # v3.2b : account_id sur recurring_transactions
    if _table_exists(inspector, "recurring_transactions") and \
       not _col_exists(inspector, "recurring_transactions", "account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE recurring_transactions ADD COLUMN account_id "
                "INTEGER REFERENCES accounts(id)"))
            conn.commit()
        print("Migration v3.2b : account_id sur recurring_transactions ajouté")

    # v3.3 : account_id sur budgets
    if _table_exists(inspector, "budgets") and \
       not _col_exists(inspector, "budgets", "account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE budgets ADD COLUMN account_id "
                "INTEGER REFERENCES accounts(id)"))
            conn.commit()
        print("Migration v3.3 : account_id sur budgets ajouté")

    # v3.4 : url sur accounts
    if _table_exists(inspector, "accounts") and \
       not _col_exists(inspector, "accounts", "url"):
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN url VARCHAR(500)"))
            conn.commit()
        print("Migration v3.4 : url sur accounts ajouté")

    # Rafraîchir l'inspector après les ALTER
    inspector = inspect(engine)

    # v4.0 : table savings_goals
    if not _table_exists(inspector, "savings_goals"):
        from models import SavingsGoal
        SavingsGoal.__table__.create(engine)
        print("Migration v4.0 : table savings_goals créée")
        inspector = inspect(engine)

    # v4.1 : table transaction_history
    if not _table_exists(inspector, "transaction_history"):
        from models import TransactionHistory
        TransactionHistory.__table__.create(engine)
        print("Migration v4.1 : table transaction_history créée")
        inspector = inspect(engine)

    # v4.2 : monthly_target sur savings_goals
    if _table_exists(inspector, "savings_goals") and \
       not _col_exists(inspector, "savings_goals", "monthly_target"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_goals "
                "ADD COLUMN monthly_target FLOAT DEFAULT 0.0"))
            conn.commit()
        print("Migration v4.2 : monthly_target ajouté")

    # v4.3 : manual_amount sur savings_goals
    if _table_exists(inspector, "savings_goals") and \
       not _col_exists(inspector, "savings_goals", "manual_amount"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_goals "
                "ADD COLUMN manual_amount FLOAT DEFAULT 0.0"))
            conn.commit()
        print("Migration v4.3 : manual_amount ajouté")

    # v4.4 : category_id sur savings_goals
    if _table_exists(inspector, "savings_goals") and \
       not _col_exists(inspector, "savings_goals", "category_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_goals "
                "ADD COLUMN category_id INTEGER REFERENCES categories(id)"))
            conn.commit()
        print("Migration v4.4 : category_id ajouté sur savings_goals")

    # v4.5 : table savings_allocations
    if not _table_exists(inspector, "savings_allocations"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS savings_allocations (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                    goal_id INTEGER NOT NULL REFERENCES savings_goals(id),
                    amount FLOAT NOT NULL,
                    account_id INTEGER REFERENCES accounts(id)
                )"""))
            conn.commit()
        print("Migration v4.5 : table savings_allocations créée")

    # v4.6 : table savings_movements
    if not _table_exists(inspector, "savings_movements"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS savings_movements (
                    id INTEGER PRIMARY KEY,
                    goal_id INTEGER NOT NULL REFERENCES savings_goals(id),
                    amount FLOAT NOT NULL,
                    label VARCHAR(100),
                    moved_at DATETIME NOT NULL,
                    account_id INTEGER REFERENCES accounts(id)
                )"""))
            conn.commit()
        print("Migration v4.6 : table savings_movements créée")

    # v4.7 : transfer_account_id sur categories
    inspector = inspect(engine)
    if _table_exists(inspector, "categories") and \
       not _col_exists(inspector, "categories", "transfer_account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE categories "
                "ADD COLUMN transfer_account_id INTEGER REFERENCES accounts(id)"))
            conn.commit()
        print("Migration v4.7 : transfer_account_id ajouté sur categories")
