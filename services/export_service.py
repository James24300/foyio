"""
Service d'export des transactions au format CSV.
"""
import csv
import os
from datetime import datetime

from db import Session
from models import Transaction, Category
import period_state


def export_transactions_csv(filepath: str, all_periods: bool = False) -> int:
    """
    Exporte les transactions en CSV.
    - all_periods=False : seulement la période sélectionnée
    - all_periods=True  : toutes les transactions
    Retourne le nombre de lignes exportées.
    """
    with Session() as session:
        categories = {c.id: c.name for c in session.query(Category).all()}

        query = session.query(Transaction).order_by(Transaction.date.desc())

        if not all_periods:
            p = period_state.get()
            from sqlalchemy import func
            query = query.filter(
                func.extract("year",  Transaction.date) == p.year
            ).filter(
                func.extract("month", Transaction.date) == p.month
            )

        transactions = query.all()

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")

            # En-tête
            writer.writerow([
                "Date", "Type", "Montant (€)", "Catégorie", "Description"
            ])

            for t in transactions:
                writer.writerow([
                    t.date.strftime("%d/%m/%Y"),
                    "Revenu" if t.type == "income" else "Dépense",
                    f"{t.amount:.2f}".replace(".", ","),
                    categories.get(t.category_id, "Inconnu"),
                    t.note or ""
                ])

    return len(transactions)


def default_export_path(all_periods: bool = False) -> str:
    """Propose un nom de fichier par défaut."""
    if all_periods:
        name = f"transactions_complet_{datetime.now().strftime('%Y%m%d')}.csv"
    else:
        p = period_state.get()
        name = f"transactions_{p.year}_{p.month:02d}.csv"

    # Dossier Documents si disponible, sinon Bureau
    for candidate in [
        os.path.join(os.path.expanduser("~"), "Documents"),
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.expanduser("~"),
    ]:
        if os.path.isdir(candidate):
            return os.path.join(candidate, name)

    return name


def export_transactions_csv_filtered(filepath: str, date_from, date_to,
                                      category_id=None, types=None) -> int:
    """Export CSV avec filtres période, catégorie et type."""
    import csv as _csv
    from db import Session
    from models import Transaction, Category
    import account_state

    types = types or ["income", "expense"]
    acc_id = account_state.get_id()

    with Session() as session:
        q = session.query(Transaction, Category)            .outerjoin(Category, Category.id == Transaction.category_id)            .filter(Transaction.date >= date_from)            .filter(Transaction.date <= date_to)            .filter(Transaction.type.in_(types))
        if category_id:
            q = q.filter(Transaction.category_id == category_id)
        if acc_id:
            q = q.filter(Transaction.account_id == acc_id)
        rows = q.order_by(Transaction.date.desc()).all()

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = _csv.writer(f, delimiter=";")
        writer.writerow(["Date", "Type", "Montant", "Catégorie", "Description"])
        for t, cat in rows:
            writer.writerow([
                t.date.strftime("%d/%m/%Y"),
                "Revenu" if t.type == "income" else "Dépense",
                f"{t.amount:.2f}".replace(".", ","),
                cat.name if cat else "",
                t.note or "",
            ])
    return len(rows)
