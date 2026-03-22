import logging

from db import Session
from models import Category, Account

logger = logging.getLogger(__name__)


def init_categories():
    """
    Initialise les catégories par défaut UNIQUEMENT si la table est vide
    (première installation). Ne recrée jamais une catégorie supprimée.
    """
    with Session() as session:
        if session.query(Category).count() > 0:
            return  # Déjà initialisé — ne rien faire

        default_categories = [
            ("Courses",   "groceries.png",     "#22c55e"),
            ("Carburant", "fuel.png",          "#f59e0b"),
            ("Maison",    "house.png",         "#3b82f6"),
            ("Santé",     "pharmacy.png",      "#ef4444"),
            ("Loisirs",   "entertainment.png", "#a855f7"),
            ("Salaire",   "money.png",         "#10b981"),
        ]

        for name, icon, color in default_categories:
            session.add(Category(name=name, icon=icon, color=color))
        session.commit()


# Catégories épargne à lier automatiquement aux comptes du même nom
SAVINGS_CATEGORIES = [
    ("Livret A",      "epargne.png", "#22c55e"),
    ("PEL",           "epargne.png", "#14b8a6"),
    ("LEP",           "epargne.png", "#06b6d4"),
    ("CEL",           "epargne.png", "#3b82f6"),
    ("Assurance Vie", "epargne.png", "#f59e0b"),
]


def init_savings_categories():
    """
    Crée les catégories épargne manquantes et les lie
    au compte du même nom (transfer_account_id).
    Appelé au démarrage après init_accounts().
    """
    with Session() as session:
        existing_cats = {c.name: c for c in session.query(Category).all()}
        accounts = {a.name: a.id for a in session.query(Account).all()}

        changed = False
        for name, icon, color in SAVINGS_CATEGORIES:
            acc_id = accounts.get(name)

            if name not in existing_cats:
                # Créer la catégorie
                cat = Category(
                    name=name, icon=icon, color=color,
                    transfer_account_id=acc_id
                )
                session.add(cat)
                changed = True
                logger.info(f"Catégorie épargne créée : {name}" +
                      (f" → compte {name}" if acc_id else ""))
            else:
                # Catégorie existe — mettre à jour le lien si manquant
                cat = existing_cats[name]
                if acc_id and not cat.transfer_account_id:
                    cat.transfer_account_id = acc_id
                    changed = True
                    logger.info(f"Catégorie {name} liée au compte {name}")

        # Lier aussi "Épargne" existante au Livret A si pas encore liée
        if "Épargne" in existing_cats:
            epargne = existing_cats["Épargne"]
            livret_id = accounts.get("Livret A")
            if livret_id and not epargne.transfer_account_id:
                epargne.transfer_account_id = livret_id
                changed = True
                logger.info("Catégorie Épargne liée au Livret A")

        if changed:
            session.commit()


# Mapping de migration : emoji → fichier PNG
_EMOJI_TO_PNG = {
    "🛒": "groceries.png",
    "⛽": "fuel.png",
    "🏠": "house.png",
    "💊": "pharmacy.png",
    "🎬": "entertainment.png",
    "💼": "money.png",
    "❓": "other.png",
}


def migrate_category_icons():
    """
    Corrige les catégories dont le champ icon contient un emoji
    ou une valeur qui n'est pas un fichier .png.
    À appeler au démarrage de l'application (main.py).
    """
    from utils.category_icons import get_category_icon

    with Session() as session:
        categories = session.query(Category).all()
        changed = 0

        for cat in categories:
            icon = cat.icon or ""

            # Cas 1 : emoji connu → remplacement direct
            if icon in _EMOJI_TO_PNG:
                cat.icon = _EMOJI_TO_PNG[icon]
                changed += 1

            # Cas 2 : pas un fichier .png (emoji inconnu, chaîne vide, etc.)
            elif not icon.endswith(".png"):
                cat.icon = get_category_icon(cat.name)
                changed += 1

        if changed:
            session.commit()
            logger.info("Migration icônes : %d catégorie(s) corrigée(s).", changed)
