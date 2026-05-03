import logging
from datetime import datetime

from sqlalchemy import func

from db import Session, safe_session
from models import Transaction, Category, Budget, TransactionRule, Tag, TransactionTag
from services.stats_service import monthly_totals
from services.transaction_recognition import find_rule, extract_keyword, learn_rule
import period_state
import account_state

logger = logging.getLogger(__name__)


def save_tags(transaction_id, tag_names):
    """Sauvegarde les tags pour une transaction (crée les tags manquants)."""
    if not tag_names:
        return
    with safe_session() as session:
        # Supprimer les liens existants
        session.query(TransactionTag).filter_by(transaction_id=transaction_id).delete()
        for name in tag_names:
            name = name.strip()
            if not name:
                continue
            tag = session.query(Tag).filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
                session.add(tag)
                session.flush()
            session.add(TransactionTag(transaction_id=transaction_id, tag_id=tag.id))


def get_tags_for_transaction(transaction_id):
    """Retourne la liste des noms de tags pour une transaction."""
    with Session() as session:
        rows = (
            session.query(Tag.name)
            .join(TransactionTag, TransactionTag.tag_id == Tag.id)
            .filter(TransactionTag.transaction_id == transaction_id)
            .all()
        )
        return [r[0] for r in rows]


def get_tags_for_transactions(transaction_ids):
    """Retourne un dict {transaction_id: [tag_name, ...]} pour un lot de transactions."""
    if not transaction_ids:
        return {}
    with Session() as session:
        rows = (
            session.query(TransactionTag.transaction_id, Tag.name)
            .join(Tag, Tag.id == TransactionTag.tag_id)
            .filter(TransactionTag.transaction_id.in_(transaction_ids))
            .all()
        )
    from collections import defaultdict
    result = defaultdict(list)
    for tid, name in rows:
        result[tid].append(name)
    return dict(result)


def add_transaction(amount, type, category_id, note=None, date=None, tags=None, crypto_holding_id=None):
    if date is None:
        date = datetime.now()

    note_clean = note.strip() if note else None

    if not category_id and note_clean:
        category_id = find_rule(note_clean)

    with safe_session() as session:
        acc_id = account_state.get_id()
        # Doublon exact : même montant + même date + même type + même compte
        q = (
            session.query(Transaction)
            .filter(Transaction.amount == float(amount))
            .filter(Transaction.type == type)
            .filter(func.strftime("%Y-%m-%d", Transaction.date) == date.strftime("%Y-%m-%d"))
        )
        if acc_id is not None:
            q = q.filter(Transaction.account_id == acc_id)
        # Si note identique → doublon certain
        exact = q.filter(Transaction.note == note_clean).first()
        if exact:
            logger.debug("Transaction doublon ignorée : {amount} {note_clean} {date.date()}")
            return
        # Si note vide des deux côtés → doublon probable
        if not note_clean:
            no_note = q.filter(Transaction.note == None).first()  # noqa
            if no_note:
                logger.debug("Transaction doublon (sans note) ignorée : {amount} {date.date()}")
                return

        t = Transaction(
            date=date, amount=float(amount),
            type=type, note=note_clean, category_id=category_id,
            account_id=account_state.get_id(),
            crypto_holding_id=crypto_holding_id,
        )
        session.add(t)
        session.flush()  # obtenir t.id pour les tags

        if tags:
            for name in tags:
                name = name.strip()
                if not name:
                    continue
                tag = session.query(Tag).filter_by(name=name).first()
                if not tag:
                    tag = Tag(name=name)
                    session.add(tag)
                    session.flush()
                session.add(TransactionTag(transaction_id=t.id, tag_id=tag.id))

        if note_clean and category_id:
            keyword = extract_keyword(note_clean)
            if keyword:
                existing = session.query(TransactionRule).filter_by(keyword=keyword).first()
                if existing:
                    existing.category_id = category_id
                else:
                    session.add(TransactionRule(keyword=keyword, category_id=category_id))


def get_transactions(limit=200, offset=0):
    with Session() as session:
        data = (
            session.query(Transaction)
            .order_by(Transaction.date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        session.expunge_all()
        return data


def get_transactions_for_period(limit=500, offset=0):
    """Transactions filtrées sur la période sélectionnée."""
    with Session() as session:
        p = period_state.get()
        q = (
            session.query(Transaction)
            .filter(func.extract("year",  Transaction.date) == p.year)
            .filter(func.extract("month", Transaction.date) == p.month)
        )
        acc_id = account_state.get_id()
        if acc_id is not None:
            q = q.filter(Transaction.account_id == acc_id)
        data = q.order_by(Transaction.date.desc()).offset(offset).limit(limit).all()
        session.expunge_all()
        return data


def get_month_summary():
    return monthly_totals()


def set_budget(category_id, amount):
    acc_id = account_state.get_id()
    with safe_session() as session:
        existing = session.query(Budget).filter_by(
            category_id=category_id, account_id=acc_id
        ).first()
        if existing:
            existing.monthly_limit = amount
        else:
            session.add(Budget(
                category_id=category_id,
                account_id=acc_id,
                monthly_limit=amount
            ))


def delete_transaction(transaction_id):
    with safe_session() as session:
        t = session.query(Transaction).filter_by(id=transaction_id).first()
        if t:
            session.delete(t)


def delete_budget(category_id: int):
    """Supprime le budget d'une catégorie pour le compte actif."""
    acc_id = account_state.get_id()
    with safe_session() as session:
        q = session.query(Budget).filter_by(category_id=category_id)
        if acc_id is not None:
            q = q.filter(Budget.account_id == acc_id)
        q.delete()


def get_budget_status():
    """Budget vs dépenses réelles pour la période et le compte actifs."""
    p      = period_state.get()
    acc_id = account_state.get_id()
    results = []

    with Session() as session:
        # Budgets du compte actif uniquement
        bq = session.query(Budget)
        if acc_id is not None:
            bq = bq.filter(Budget.account_id == acc_id)
        budgets = bq.all()
        for b in budgets:
            q = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.category_id == b.category_id)
                .filter(Transaction.type == "expense")
                .filter(func.extract("year",  Transaction.date) == p.year)
                .filter(func.extract("month", Transaction.date) == p.month)
            )
            if acc_id is not None:
                q = q.filter(Transaction.account_id == acc_id)
            spent = q.scalar() or 0
            results.append((b.category_id, b.monthly_limit, spent))

    return results


def set_annual_budget(category_id: int, amount: float):
    """Définit ou met à jour le budget annuel d'une catégorie pour le compte actif."""
    acc_id = account_state.get_id()
    with safe_session() as session:
        existing = session.query(Budget).filter_by(
            category_id=category_id, account_id=acc_id
        ).first()
        if existing:
            existing.annual_limit = amount
        else:
            # Crée une ligne Budget avec monthly_limit=0 et annual_limit renseigné
            session.add(Budget(
                category_id=category_id,
                account_id=acc_id,
                monthly_limit=0.0,
                annual_limit=amount,
            ))


def delete_annual_budget(category_id: int):
    """Supprime uniquement le budget annuel (conserve le budget mensuel si existant)."""
    acc_id = account_state.get_id()
    with safe_session() as session:
        q = session.query(Budget).filter_by(category_id=category_id)
        if acc_id is not None:
            q = q.filter(Budget.account_id == acc_id)
        b = q.first()
        if b:
            b.annual_limit = None
            # Si aucun budget mensuel non nul, supprimer la ligne entière
            if not b.monthly_limit:
                session.delete(b)


def get_annual_budget_status(year: int = None) -> list:
    """
    Retourne [(category_id, annual_limit, ytd_spent)] pour le compte actif.
    ytd_spent = dépenses cumulées du 1er janvier au 31 décembre de l'année.
    """
    from datetime import datetime
    acc_id = account_state.get_id()
    if year is None:
        year = datetime.now().year
    results = []

    with Session() as session:
        bq = session.query(Budget).filter(Budget.annual_limit.isnot(None))
        if acc_id is not None:
            bq = bq.filter(Budget.account_id == acc_id)
        budgets = bq.all()

        for b in budgets:
            if not b.annual_limit:
                continue
            q = (
                session.query(func.sum(Transaction.amount))
                .filter(Transaction.category_id == b.category_id)
                .filter(Transaction.type == "expense")
                .filter(func.extract("year", Transaction.date) == year)
            )
            if acc_id is not None:
                q = q.filter(Transaction.account_id == acc_id)
            spent = q.scalar() or 0.0
            results.append((b.category_id, b.annual_limit, round(spent, 2)))

    return results


# ──────────────────────────────────────────────────────────────
# Détection de doublons mensuels
# ──────────────────────────────────────────────────────────────

def find_monthly_duplicates(year: int = None, month: int = None,
                             account_id: int = None) -> list:
    """
    Détecte les transactions probablement en doublon sur un mois donné.

    Un doublon probable est défini comme :
    - Même montant exact
    - Même type (income/expense)
    - Même mois/année
    - Même compte
    - Note similaire (ou les deux vides)

    Retourne une liste de tuples (transaction_a, transaction_b, raison).
    La liste est vide si aucun doublon n'est détecté.
    """
    from datetime import datetime as _dt
    import account_state as _as

    if year is None or month is None:
        now = _dt.now()
        year, month = now.year, now.month

    if account_id is None:
        account_id = _as.get_id()

    with Session() as session:
        q = (
            session.query(Transaction)
            .filter(func.extract("year",  Transaction.date) == year)
            .filter(func.extract("month", Transaction.date) == month)
            .filter(Transaction.type == "expense")
        )
        if account_id is not None:
            q = q.filter(Transaction.account_id == account_id)

        transactions = q.all()
        session.expunge_all()

    # Grouper par montant pour ne comparer que les transactions
    # ayant le même montant (O(n) au lieu de O(n²))
    from collections import defaultdict
    by_amount = defaultdict(list)
    for t in transactions:
        by_amount[t.amount].append(t)

    duplicates = []
    seen = set()

    for group in by_amount.values():
        if len(group) < 2:
            continue
        for i, t1 in enumerate(group):
            for t2 in group[i + 1:]:
                pair_key = (min(t1.id, t2.id), max(t1.id, t2.id))
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                same_category = (t1.category_id == t2.category_id
                                 and t1.category_id is not None)
                notes_similar = _notes_match(t1.note, t2.note)

                if same_category or notes_similar:
                    raison = []
                    if same_category:
                        raison.append("même catégorie")
                    if notes_similar:
                        raison.append("libellé similaire")
                    duplicates.append((t1, t2, " + ".join(raison)))

    return duplicates


def _notes_match(note1: str, note2: str) -> bool:
    """Retourne True si les deux notes sont similaires."""
    if not note1 and not note2:
        return True  # les deux vides
    if not note1 or not note2:
        return False

    from services.transaction_recognition import normalize
    n1 = normalize(note1.lower().strip())
    n2 = normalize(note2.lower().strip())

    if n1 == n2:
        return True

    # Correspondance partielle : un libellé contient l'autre
    shorter, longer = (n1, n2) if len(n1) <= len(n2) else (n2, n1)
    if len(shorter) >= 4 and shorter in longer:
        return True

    # Mots en commun significatifs (>= 4 lettres)
    import re
    STOPWORDS = {"carte", "virement", "prel", "prlv", "sepa", "pour",
                 "avec", "chez", "euro", "recu", "inst"}
    words1 = {w for w in re.split(r"\W+", n1) if len(w) >= 4 and w not in STOPWORDS}
    words2 = {w for w in re.split(r"\W+", n2) if len(w) >= 4 and w not in STOPWORDS}

    if words1 and words2:
        common = words1 & words2
        overlap = len(common) / min(len(words1), len(words2))
        return overlap >= 0.5

    return False


def get_duplicate_count(year: int = None, month: int = None,
                         account_id: int = None) -> int:
    """Retourne le nombre de paires de doublons probables."""
    return len(find_monthly_duplicates(year, month, account_id))


def search_all_periods(query: str, account_id=None) -> list:
    """
    Recherche globale dans toutes les périodes.
    Cherche dans le libellé et les catégories.
    Retourne une liste de Transaction triées par date décroissante.
    """
    if not query or len(query.strip()) < 2:
        return []

    from models import Transaction, Category
    from sqlalchemy import or_
    import account_state

    q_str = query.strip().lower()

    with Session() as session:
        results = (
            session.query(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .filter(
                or_(
                    Transaction.note.ilike(f"%{q_str}%"),
                    Category.name.ilike(f"%{q_str}%"),
                )
            )
        )
        if account_id is not None:
            results = results.filter(Transaction.account_id == account_id)
        elif account_state.get_id():
            results = results.filter(
                Transaction.account_id == account_state.get_id()
            )

        results = results.order_by(Transaction.date.desc()).limit(200).all()
        session.expunge_all()
        return results


def get_transactions_for_date_range(date_from, date_to, account_id=None):
    """Retourne les transactions entre deux dates."""
    from db import Session
    from models import Transaction
    import account_state

    acc_id = account_id or account_state.get_id()
    with Session() as session:
        q = session.query(Transaction)            .filter(Transaction.date >= date_from)            .filter(Transaction.date <= date_to)
        if acc_id:
            q = q.filter(Transaction.account_id == acc_id)
        transactions = q.order_by(Transaction.date.desc()).all()
        session.expunge_all()
    return transactions
