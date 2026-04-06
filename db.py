"""
Module base de données — Foyio
Gère la connexion SQLAlchemy, les sessions et les migrations de schéma.
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DB_PATH

logger = logging.getLogger(__name__)

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
    except Exception:
        session.rollback()
        logger.exception("Erreur SQL")
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
        logger.info("Migration v3.1 : recurring_id ajouté")

    # v3.2a : account_id sur transactions
    if _table_exists(inspector, "transactions") and \
       not _col_exists(inspector, "transactions", "account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE transactions ADD COLUMN account_id "
                "INTEGER REFERENCES accounts(id)"))
            conn.commit()
        logger.info("Migration v3.2a : account_id sur transactions ajouté")

    # v3.2b : account_id sur recurring_transactions
    if _table_exists(inspector, "recurring_transactions") and \
       not _col_exists(inspector, "recurring_transactions", "account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE recurring_transactions ADD COLUMN account_id "
                "INTEGER REFERENCES accounts(id)"))
            conn.commit()
        logger.info("Migration v3.2b : account_id sur recurring_transactions ajouté")

    # v3.3 : account_id sur budgets
    if _table_exists(inspector, "budgets") and \
       not _col_exists(inspector, "budgets", "account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE budgets ADD COLUMN account_id "
                "INTEGER REFERENCES accounts(id)"))
            conn.commit()
        logger.info("Migration v3.3 : account_id sur budgets ajouté")

    # v3.4 : url sur accounts
    if _table_exists(inspector, "accounts") and \
       not _col_exists(inspector, "accounts", "url"):
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN url VARCHAR(500)"))
            conn.commit()
        logger.info("Migration v3.4 : url sur accounts ajouté")

    # Rafraîchir l'inspector après les ALTER
    inspector = inspect(engine)

    # v4.0 : table savings_goals
    if not _table_exists(inspector, "savings_goals"):
        from models import SavingsGoal
        SavingsGoal.__table__.create(engine)
        logger.info("Migration v4.0 : table savings_goals créée")
        inspector = inspect(engine)

    # v4.1 : table transaction_history
    if not _table_exists(inspector, "transaction_history"):
        from models import TransactionHistory
        TransactionHistory.__table__.create(engine)
        logger.info("Migration v4.1 : table transaction_history créée")
        inspector = inspect(engine)

    # v4.2 : monthly_target sur savings_goals
    if _table_exists(inspector, "savings_goals") and \
       not _col_exists(inspector, "savings_goals", "monthly_target"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_goals "
                "ADD COLUMN monthly_target FLOAT DEFAULT 0.0"))
            conn.commit()
        logger.info("Migration v4.2 : monthly_target ajouté")

    # v4.3 : manual_amount sur savings_goals
    if _table_exists(inspector, "savings_goals") and \
       not _col_exists(inspector, "savings_goals", "manual_amount"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_goals "
                "ADD COLUMN manual_amount FLOAT DEFAULT 0.0"))
            conn.commit()
        logger.info("Migration v4.3 : manual_amount ajouté")

    # v4.4 : category_id sur savings_goals
    if _table_exists(inspector, "savings_goals") and \
       not _col_exists(inspector, "savings_goals", "category_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_goals "
                "ADD COLUMN category_id INTEGER REFERENCES categories(id)"))
            conn.commit()
        logger.info("Migration v4.4 : category_id ajouté sur savings_goals")

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
        logger.info("Migration v4.5 : table savings_allocations créée")

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
        logger.info("Migration v4.6 : table savings_movements créée")

    # v4.7 : transfer_account_id sur categories
    inspector = inspect(engine)
    if _table_exists(inspector, "categories") and \
       not _col_exists(inspector, "categories", "transfer_account_id"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE categories "
                "ADD COLUMN transfer_account_id INTEGER REFERENCES accounts(id)"))
            conn.commit()
        logger.info("Migration v4.7 : transfer_account_id ajouté sur categories")

    # v5.0 : index de performance sur transactions
    if _table_exists(inspector, "transactions"):
        _indexes = {
            "ix_transactions_account_date": "CREATE INDEX IF NOT EXISTS ix_transactions_account_date ON transactions(account_id, date)",
            "ix_transactions_category":     "CREATE INDEX IF NOT EXISTS ix_transactions_category ON transactions(category_id)",
            "ix_transactions_recurring":    "CREATE INDEX IF NOT EXISTS ix_transactions_recurring ON transactions(recurring_id)",
            "ix_transactions_date":         "CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions(date)",
        }
        with engine.connect() as conn:
            for name, ddl in _indexes.items():
                conn.execute(text(ddl))
            conn.commit()
        logger.info("Migration v5.0 : index de performance créés sur transactions")

    # v5.1 : table tags
    inspector = inspect(engine)
    if not _table_exists(inspector, "tags"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR NOT NULL UNIQUE,
                    color VARCHAR DEFAULT '#6366f1'
                )"""))
            conn.commit()
        logger.info("Migration v5.1 : table tags créée")

    # v5.2 : table transaction_tags
    inspector = inspect(engine)
    if not _table_exists(inspector, "transaction_tags"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS transaction_tags (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                    tag_id INTEGER NOT NULL REFERENCES tags(id)
                )"""))
            conn.commit()
        logger.info("Migration v5.2 : table transaction_tags créée")

    # v5.3 : reminder_days sur recurring_transactions
    inspector = inspect(engine)
    if _table_exists(inspector, "recurring_transactions") and \
       not _col_exists(inspector, "recurring_transactions", "reminder_days"):
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE recurring_transactions "
                "ADD COLUMN reminder_days INTEGER DEFAULT 3"))
            conn.commit()
        logger.info("Migration v5.3 : reminder_days ajouté sur recurring_transactions")

    # v5.4 : table attachments (pièces jointes)
    inspector = inspect(engine)
    if not _table_exists(inspector, "attachments"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                    filename VARCHAR(255) NOT NULL,
                    filepath VARCHAR(500) NOT NULL,
                    added_at DATETIME NOT NULL
                )"""))
            conn.commit()
        logger.info("Migration v5.4 : table attachments créée")

    # v5.5 : table loans (prêts / crédits)
    inspector = inspect(engine)
    if not _table_exists(inspector, "loans"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS loans (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    total_amount FLOAT NOT NULL,
                    remaining_amount FLOAT NOT NULL,
                    monthly_payment FLOAT NOT NULL,
                    interest_rate FLOAT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    account_id INTEGER REFERENCES accounts(id),
                    active BOOLEAN DEFAULT 1
                )"""))
            conn.commit()
        logger.info("Migration v5.5 : table loans créée")

    # v6.0 : table crypto_holdings
    inspector = inspect(engine)
    if not _table_exists(inspector, "crypto_holdings"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS crypto_holdings (
                    id INTEGER PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    coingecko_id VARCHAR(100) NOT NULL,
                    quantity FLOAT NOT NULL DEFAULT 0.0,
                    avg_buy_price FLOAT NOT NULL DEFAULT 0.0,
                    account_id INTEGER REFERENCES accounts(id),
                    active BOOLEAN DEFAULT 1
                )"""))
            conn.commit()
        logger.info("Migration v6.0 : table crypto_holdings créée")

    # v6.1 : table crypto_transactions
    inspector = inspect(engine)
    if not _table_exists(inspector, "crypto_transactions"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS crypto_transactions (
                    id INTEGER PRIMARY KEY,
                    holding_id INTEGER NOT NULL REFERENCES crypto_holdings(id),
                    type VARCHAR(10) NOT NULL,
                    quantity FLOAT NOT NULL,
                    price_eur FLOAT NOT NULL,
                    total_eur FLOAT NOT NULL,
                    date DATETIME NOT NULL,
                    note VARCHAR(500),
                    account_id INTEGER REFERENCES accounts(id)
                )"""))
            conn.commit()
        logger.info("Migration v6.1 : table crypto_transactions créée")

    # v6.2 : table crypto_alerts
    inspector = inspect(engine)
    if not _table_exists(inspector, "crypto_alerts"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS crypto_alerts (
                    id INTEGER PRIMARY KEY,
                    holding_id INTEGER NOT NULL REFERENCES crypto_holdings(id),
                    alert_type VARCHAR(10) NOT NULL,
                    target_price FLOAT NOT NULL,
                    active BOOLEAN DEFAULT 1,
                    triggered BOOLEAN DEFAULT 0,
                    account_id INTEGER REFERENCES accounts(id)
                )"""))
            conn.commit()
        logger.info("Migration v6.2 : table crypto_alerts créée")

    # v6.3 : table ideas (boîte à idées)
    inspector = inspect(engine)
    if not _table_exists(inspector, "ideas"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ideas (
                    id INTEGER PRIMARY KEY,
                    author VARCHAR(100) NOT NULL,
                    content VARCHAR(2000) NOT NULL,
                    submitted_at DATETIME NOT NULL,
                    read BOOLEAN DEFAULT 0,
                    account_id INTEGER REFERENCES accounts(id)
                )"""))
            conn.commit()
        logger.info("Migration v6.3 : table ideas créée")

    # v6.4 : table watchlist
    if not _table_exists(inspector, "watchlist"):
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY,
                    coingecko_id VARCHAR(100) NOT NULL UNIQUE,
                    symbol VARCHAR(20) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    added_at DATETIME NOT NULL,
                    note VARCHAR(500)
                )"""))
            conn.commit()
        logger.info("Migration v6.4 : table watchlist créée")
