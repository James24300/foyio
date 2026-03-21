from db import Session
from models import Category


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
            print(f"Migration icônes : {changed} catégorie(s) corrigée(s).")
