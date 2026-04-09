from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, DateTime, Index
from db import Base


class Attachment(Base):
    """Pièce jointe (reçu, facture) liée à une transaction."""
    __tablename__ = "attachments"

    id             = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    filename       = Column(String(255), nullable=False)
    filepath       = Column(String(500), nullable=False)
    added_at       = Column(DateTime, nullable=False)


class Account(Base):
    """Compte bancaire (courant, joint, livret...)."""
    __tablename__ = "accounts"

    id     = Column(Integer, primary_key=True)
    name   = Column(String(100), nullable=False, unique=True)
    type   = Column(String(30),  default="checking")
    color  = Column(String(7),   default="#3b82f6")
    icon   = Column(String(50),  default="bank.png")
    active = Column(Boolean,     default=True)
    url    = Column(String(500),  nullable=True)  # URL espace client bancaire


class Category(Base):
    """Catégorie de transaction — partagée entre tous les comptes."""
    __tablename__ = "categories"

    id    = Column(Integer, primary_key=True)
    name  = Column(String,  nullable=False)
    icon  = Column(String)
    color = Column(String,  default="#3b82f6")
    transfer_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class RecurringTransaction(Base):
    """Règle récurrente liée à un compte spécifique."""
    __tablename__ = "recurring_transactions"

    id           = Column(Integer, primary_key=True)
    label        = Column(String(255), nullable=False)
    amount       = Column(Float,       nullable=False)
    type         = Column(String(10),  nullable=False)
    category_id  = Column(Integer, ForeignKey("categories.id"), nullable=False)
    account_id   = Column(Integer, ForeignKey("accounts.id"),   nullable=True)
    day_of_month   = Column(Integer, default=1)
    active         = Column(Boolean, default=True)
    start_date     = Column(Date,    nullable=False)
    reminder_days  = Column(Integer, default=3)


class Transaction(Base):
    """Transaction liée à un compte spécifique."""
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_date", "account_id", "date"),
        Index("ix_transactions_category",     "category_id"),
        Index("ix_transactions_recurring",    "recurring_id"),
        Index("ix_transactions_date",         "date"),
    )

    id                = Column(Integer, primary_key=True)
    date              = Column(Date,        nullable=False)
    amount            = Column(Float,       nullable=False)
    type              = Column(String(10),  nullable=False)
    note              = Column(String(255))
    category_id       = Column(Integer, ForeignKey("categories.id"))
    recurring_id      = Column(Integer, ForeignKey("recurring_transactions.id"), nullable=True)
    account_id        = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    crypto_holding_id = Column(Integer, ForeignKey("crypto_holdings.id"), nullable=True)


class Budget(Base):
    """Budget mensuel par catégorie et par compte."""
    __tablename__ = "budgets"

    id            = Column(Integer, primary_key=True)
    category_id   = Column(Integer, ForeignKey("categories.id"), nullable=False)
    account_id    = Column(Integer, ForeignKey("accounts.id"),   nullable=True)
    monthly_limit = Column(Float, nullable=False)


class TransactionRule(Base):
    """Règle de reconnaissance automatique de catégorie."""
    __tablename__ = "transaction_rules"

    id          = Column(Integer, primary_key=True)
    keyword     = Column(String, unique=True, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)


class AccountCategory(Base):
    """
    Visibilité d'une catégorie sur un compte donné.
    Si une ligne existe avec hidden=True, la catégorie est masquée sur ce compte.
    Absence de ligne = catégorie visible (comportement par défaut).
    """
    __tablename__ = "account_categories"

    id          = Column(Integer, primary_key=True)
    account_id  = Column(Integer, ForeignKey("accounts.id"),   nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    hidden      = Column(Boolean, default=False)


class SavingsGoal(Base):
    """Objectif d'épargne (vacances, voiture, travaux...)."""
    __tablename__ = "savings_goals"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(100), nullable=False)
    target_amount= Column(Float,       nullable=False)
    current_amount= Column(Float,      default=0.0)
    icon         = Column(String(50),  default="epargne.png")
    color        = Column(String(7),   default="#22c55e")
    deadline     = Column(Date,        nullable=True)
    account_id   = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    monthly_target= Column(Float,      default=0.0)   # versement mensuel cible
    payment_day  = Column(Integer,     nullable=True) # jour du mois pour le versement (1-28)
    category_id  = Column(Integer, ForeignKey('categories.id'), nullable=True)
    manual_amount = Column(Float,      default=0.0)   # versements manuels cumulés
    active       = Column(Boolean,     default=True)


class TransactionHistory(Base):
    """Historique des modifications d'une transaction."""
    __tablename__ = "transaction_history"

    id             = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    changed_at     = Column(DateTime, nullable=False)
    field_name     = Column(String(50),  nullable=False)
    old_value      = Column(String(255), nullable=True)
    new_value      = Column(String(255), nullable=True)
    account_id     = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class SavingsAllocation(Base):
    """Ventilation d'une transaction épargne vers un objectif."""
    __tablename__ = "savings_allocations"

    id             = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    goal_id        = Column(Integer, ForeignKey("savings_goals.id"), nullable=False)
    amount         = Column(Float, nullable=False)
    account_id     = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class Tag(Base):
    """Étiquette libre pour les transactions."""
    __tablename__ = "tags"

    id    = Column(Integer, primary_key=True)
    name  = Column(String, nullable=False, unique=True)
    color = Column(String, default="#6366f1")


class TransactionTag(Base):
    """Lien many-to-many entre transactions et tags."""
    __tablename__ = "transaction_tags"

    id             = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    tag_id         = Column(Integer, ForeignKey("tags.id"), nullable=False)


class SavingsMovement(Base):
    """Historique des versements et retraits sur un objectif."""
    __tablename__ = "savings_movements"

    id         = Column(Integer, primary_key=True)
    goal_id    = Column(Integer, ForeignKey("savings_goals.id"), nullable=False)
    amount     = Column(Float,   nullable=False)   # positif=versement, négatif=retrait
    label      = Column(String(100), nullable=True)
    moved_at   = Column(DateTime, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class Loan(Base):
    """Prêt / crédit suivi par l'utilisateur."""
    __tablename__ = "loans"

    id              = Column(Integer, primary_key=True)
    name            = Column(String(100), nullable=False)
    total_amount    = Column(Float, nullable=False)
    remaining_amount= Column(Float, nullable=False)
    monthly_payment = Column(Float, nullable=False)
    interest_rate   = Column(Float, nullable=False)
    start_date      = Column(Date, nullable=False)
    end_date        = Column(Date, nullable=False)
    account_id      = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    active          = Column(Boolean, default=True)


class CryptoHolding(Base):
    """Crypto-monnaie détenue dans le portefeuille."""
    __tablename__ = "crypto_holdings"

    id             = Column(Integer, primary_key=True)
    symbol         = Column(String(20),  nullable=False)   # BTC, ETH…
    name           = Column(String(100), nullable=False)   # Bitcoin, Ethereum…
    coingecko_id   = Column(String(100), nullable=False)   # bitcoin, ethereum…
    quantity       = Column(Float, nullable=False, default=0.0)
    avg_buy_price  = Column(Float, nullable=False, default=0.0)  # € moyen d'achat
    account_id     = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    active         = Column(Boolean, default=True)


class CryptoTransaction(Base):
    """Achat ou vente d'une crypto."""
    __tablename__ = "crypto_transactions"

    id         = Column(Integer, primary_key=True)
    holding_id = Column(Integer, ForeignKey("crypto_holdings.id"), nullable=False)
    type       = Column(String(10), nullable=False)   # buy / sell
    quantity   = Column(Float, nullable=False)
    price_eur  = Column(Float, nullable=False)         # prix unitaire en € au moment de la tx
    total_eur  = Column(Float, nullable=False)         # quantité × prix
    date       = Column(DateTime, nullable=False)
    note       = Column(String(500), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class CryptoAlert(Base):
    """Alerte de prix sur une crypto."""
    __tablename__ = "crypto_alerts"

    id          = Column(Integer, primary_key=True)
    holding_id  = Column(Integer, ForeignKey("crypto_holdings.id"), nullable=False)
    alert_type  = Column(String(10), nullable=False)   # above / below
    target_price= Column(Float, nullable=False)
    active      = Column(Boolean, default=True)
    triggered   = Column(Boolean, default=False)
    account_id  = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class Idea(Base):
    """Suggestion ou idée soumise par un utilisateur."""
    __tablename__ = "ideas"

    id           = Column(Integer,      primary_key=True)
    author       = Column(String(100),  nullable=False)
    content      = Column(String(2000), nullable=False)
    submitted_at = Column(DateTime,     nullable=False)
    read         = Column(Boolean,      default=False)
    account_id   = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    status       = Column(String(30),   default="en_attente")
    response     = Column(String(2000), nullable=True)


class WatchlistItem(Base):
    """Crypto surveillée sans position ouverte."""
    __tablename__ = "watchlist"

    id            = Column(Integer,      primary_key=True)
    coingecko_id  = Column(String(100),  nullable=False, unique=True)
    symbol        = Column(String(20),   nullable=False)
    name          = Column(String(100),  nullable=False)
    added_at      = Column(DateTime,     nullable=False)
    note          = Column(String(500),  nullable=True)


class CryptoDCA(Base):
    """Plan DCA récurrent : investissement automatique mensuel sur une crypto."""
    __tablename__ = "crypto_dca"

    id             = Column(Integer,      primary_key=True)
    holding_id     = Column(Integer,      ForeignKey("crypto_holdings.id"), nullable=False)
    amount_eur     = Column(Float,        nullable=False)   # montant à investir en €
    day_of_month   = Column(Integer,      nullable=False, default=1)   # 1-28
    active         = Column(Boolean,      default=True)
    last_executed  = Column(Date,         nullable=True)    # date de la dernière exécution
    note           = Column(String(200),  nullable=True)
