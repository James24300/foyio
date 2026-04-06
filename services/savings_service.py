"""
Service épargne — objectifs, taux, évolution, simulation.
"""
import math
from datetime import datetime, date
from db import Session, safe_session
from models import SavingsGoal, Transaction, Category
from sqlalchemy import func
import account_state


# ── Objectifs ────────────────────────────────────────────────────────────────

def get_goals() -> list:
    with Session() as session:
        goals = session.query(SavingsGoal).filter_by(active=True)\
                       .order_by(SavingsGoal.name).all()
        session.expunge_all()
        return goals


def add_goal(name: str, target: float, current: float = 0.0,
             icon: str = "epargne.png", color: str = "#22c55e",
             deadline: date = None, monthly_target: float = 0.0,
             category_id: int = None, payment_day: int = None) -> SavingsGoal:
    with safe_session() as session:
        goal = SavingsGoal(
            name=name, target_amount=target, current_amount=current,
            icon=icon, color=color, deadline=deadline,
            monthly_target=monthly_target,
            category_id=category_id,
            payment_day=payment_day,
            account_id=account_state.get_id()
        )
        session.add(goal)
    return goal


def update_goal(goal_id: int, **kwargs):
    with safe_session() as session:
        goal = session.query(SavingsGoal).filter_by(id=goal_id).first()
        if goal:
            for k, v in kwargs.items():
                setattr(goal, k, v)


def delete_goal(goal_id: int):
    with safe_session() as session:
        goal = session.query(SavingsGoal).filter_by(id=goal_id).first()
        if goal:
            goal.active = False


# ── Taux d'épargne mensuel ───────────────────────────────────────────────────

def monthly_savings_rate(months: int = 12) -> list:
    """
    Retourne [(label_mois, revenu, epargne, taux%), ...] pour les N derniers mois.
    L'épargne est détectée via la catégorie dont le nom contient "pargne" ou "livret".
    """
    from sqlalchemy import case, extract

    now = datetime.now()
    results = []

    with Session() as session:
        # Trouver les catégories épargne
        savings_cats = session.query(Category).filter(
            Category.name.ilike("%pargne%") |
            Category.name.ilike("%livret%") |
            Category.name.ilike("%LEP%") |
            Category.name.ilike("%PEL%") |
            Category.name.ilike("%CEL%")
        ).all()
        savings_cat_ids = [c.id for c in savings_cats]

        for i in range(months - 1, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1

            # Revenus du mois
            q_income = session.query(func.sum(Transaction.amount))\
                .filter(Transaction.type == "income")\
                .filter(func.extract("year",  Transaction.date) == y)\
                .filter(func.extract("month", Transaction.date) == m)
            if account_state.get_id():
                q_income = q_income.filter(
                    Transaction.account_id == account_state.get_id()
                )
            income = q_income.scalar() or 0.0

            # Épargne du mois (dépenses dans catégories épargne)
            savings = 0.0
            if savings_cat_ids:
                q_sav = session.query(func.sum(Transaction.amount))\
                    .filter(Transaction.type == "expense")\
                    .filter(Transaction.category_id.in_(savings_cat_ids))\
                    .filter(func.extract("year",  Transaction.date) == y)\
                    .filter(func.extract("month", Transaction.date) == m)
                if account_state.get_id():
                    q_sav = q_sav.filter(
                        Transaction.account_id == account_state.get_id()
                    )
                savings = q_sav.scalar() or 0.0

            rate = (savings / income * 100) if income > 0 else 0.0
            MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                         "Juil","Août","Sep","Oct","Nov","Déc"]
            label = f"{MONTHS_FR[m]} {y}"
            results.append((label, income, savings, rate))

    return results


# ── Simulation ───────────────────────────────────────────────────────────────

def simulate(monthly_amount: float, target: float,
             current: float = 0.0, annual_rate: float = 0.0) -> dict:
    """
    Simulation d'épargne.
    Retourne mois nécessaires, date d'atteinte, évolution mois par mois.
    """
    if monthly_amount <= 0:
        return {"months": None, "target_date": None, "evolution": []}

    balance = current
    evolution = [balance]
    months = 0
    max_months = 600  # 50 ans max

    monthly_rate = annual_rate / 100 / 12

    while balance < target and months < max_months:
        balance += monthly_amount
        if monthly_rate > 0:
            balance *= (1 + monthly_rate)
        balance = round(balance, 2)
        evolution.append(min(balance, target))
        months += 1

    now = datetime.now()
    target_month = now.month + months
    target_year  = now.year
    while target_month > 12:
        target_month -= 12
        target_year  += 1

    MONTHS_FR = ["","Janvier","Février","Mars","Avril","Mai","Juin",
                 "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]

    return {
        "months":      months,
        "target_date": f"{MONTHS_FR[target_month]} {target_year}",
        "evolution":   evolution,
        "reached":     balance >= target,
    }


def withdraw_contribution(goal_id: int, amount: float, label: str = 'Retrait'):
    """Retire un montant d'un objectif."""
    from datetime import datetime
    from models import SavingsMovement
    import account_state
    with safe_session() as session:
        goal = session.query(SavingsGoal).filter_by(id=goal_id).first()
        if goal:
            manual  = float(goal.manual_amount or 0)
            current = float(goal.current_amount or 0)
            withdraw = min(amount, current)
            goal.manual_amount  = max(0, round(manual - withdraw, 2))
            goal.current_amount = max(0, round(current - withdraw, 2))
            session.add(SavingsMovement(
                goal_id=goal_id, amount=round(-withdraw, 2),
                label=label, moved_at=datetime.now(),
                account_id=account_state.get_id()
            ))


def add_contribution(goal_id: int, amount: float, label: str = 'Versement'):
    """Ajoute un versement manuel — incrémente manual_amount et current_amount."""
    from datetime import datetime
    from models import SavingsMovement
    import account_state
    with safe_session() as session:
        goal = session.query(SavingsGoal).filter_by(id=goal_id).first()
        if goal:
            manual = float(goal.manual_amount or 0)
            current = float(goal.current_amount or 0)
            goal.manual_amount = round(manual + amount, 2)
            goal.current_amount = min(
                round(current + amount, 2),
                goal.target_amount
            )
            session.add(SavingsMovement(
                goal_id=goal_id, amount=round(amount, 2),
                label=label, moved_at=datetime.now(),
                account_id=account_state.get_id()
            ))


def estimate_months_to_goal(goal) -> dict:
    """
    Estime le nombre de mois pour atteindre l'objectif.
    Priorité : 1) versement mensuel cible (monthly_target)
               2) taux d'épargne moyen des 3 derniers mois
    """
    from datetime import date
    reste = goal.target_amount - goal.current_amount
    if reste <= 0:
        return {"months": 0, "date": "Atteint !", "monthly_needed": 0, "on_track": True}

    MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                 "Juil","Août","Sep","Oct","Nov","Déc"]

    # 1. Utiliser le versement mensuel cible si défini
    monthly_target = getattr(goal, "monthly_target", 0) or 0
    if monthly_target > 0:
        avg_monthly = monthly_target
    else:
        # 2. Fallback : taux moyen 3 derniers mois
        data = monthly_savings_rate(3)
        avg_monthly = sum(d[2] for d in data) / len(data) if data else 0

    if avg_monthly <= 0:
        # Calculer ce qu'il faudrait si échéance connue
        if goal.deadline:
            from datetime import date as _date
            delta = (goal.deadline - _date.today()).days
            months_avail = max(1, delta // 30)
            return {
                "months": None,
                "date": "Définir un versement mensuel",
                "monthly_needed": round(reste / months_avail, 2),
                "on_track": False,
            }
        return {"months": None, "date": "Définir un versement mensuel",
                "monthly_needed": 0, "on_track": False}

    months = math.ceil(reste / avg_monthly)
    now = date.today()
    m, y = now.month + months, now.year
    while m > 12:
        m -= 12
        y += 1

    # Vérifier si on est dans les temps par rapport à l'échéance
    on_track = True
    if goal.deadline:
        delta_days = (goal.deadline - now).days
        months_avail = max(1, delta_days // 30)
        on_track = months <= months_avail

    return {
        "months":         months,
        "date":           f"{MONTHS_FR[m]} {y}",
        "monthly_needed": round(avg_monthly, 2),
        "on_track":       on_track,
    }


def sync_savings_from_transactions():
    """
    Retourne le total des transactions dans les catégories épargne.
    Ne modifie PAS current_amount — celui-ci est géré uniquement
    par add_contribution() et add_allocation().
    """
    from models import Transaction
    from sqlalchemy import func
    import account_state

    acc_id = account_state.get_id()
    total_global = 0.0

    with Session() as session:
        savings_cats = session.query(Category).filter(
            Category.name.ilike("%pargne%") |
            Category.name.ilike("%livret%") |
            Category.name.ilike("%LEP%") |
            Category.name.ilike("%PEL%") |
            Category.name.ilike("%CEL%")
        ).all()
        cat_ids = [c.id for c in savings_cats]
        if not cat_ids:
            return 0.0

        q = session.query(func.sum(Transaction.amount))            .filter(Transaction.type == "expense")            .filter(Transaction.category_id.in_(cat_ids))
        if acc_id:
            q = q.filter(Transaction.account_id == acc_id)
        total_global = q.scalar() or 0.0

    return round(total_global, 2)

def check_monthly_targets() -> list:
    """
    Vérifie si les versements mensuels cibles ont été effectués ce mois.
    Retourne la liste des objectifs en retard.
    """
    from datetime import datetime
    from models import Transaction
    from sqlalchemy import func

    now = datetime.now()
    alerts = []

    with Session() as session:
        savings_cats = session.query(Category).filter(
            Category.name.ilike("%pargne%") |
            Category.name.ilike("%livret%") |
            Category.name.ilike("%LEP%") |
            Category.name.ilike("%PEL%") |
            Category.name.ilike("%CEL%")
        ).all()
        savings_cat_ids = [c.id for c in savings_cats]

        goals = session.query(SavingsGoal).filter(
            SavingsGoal.active == True,
            SavingsGoal.monthly_target > 0
        ).all()

        today_day = now.day

        for goal in goals:
            if goal.current_amount >= goal.target_amount:
                continue  # Objectif atteint

            # Ne rappeler qu'à partir du jour de versement configuré
            if goal.payment_day and today_day < goal.payment_day:
                continue

            # Total versé ce mois dans catégories épargne
            total_this_month = 0.0
            if savings_cat_ids:
                q = session.query(func.sum(Transaction.amount))                    .filter(Transaction.type == "expense")                    .filter(Transaction.category_id.in_(savings_cat_ids))                    .filter(func.extract("year",  Transaction.date) == now.year)                    .filter(func.extract("month", Transaction.date) == now.month)
                if goal.account_id:
                    q = q.filter(Transaction.account_id == goal.account_id)
                total_this_month = q.scalar() or 0.0

            if total_this_month < goal.monthly_target:
                manque = goal.monthly_target - total_this_month
                alerts.append({
                    "name":    goal.name,
                    "target":  goal.monthly_target,
                    "done":    total_this_month,
                    "missing": manque,
                })
        session.expunge_all()

    return alerts


def savings_rate_target(target_rate: float = None) -> dict:
    """
    Gère l'objectif de taux d'épargne personnel.
    Lit/écrit dans un fichier config simple.
    """
    import json, os
    from config import APP_DIR
    cfg_path = os.path.join(APP_DIR, "savings_config.json")

    if target_rate is not None:
        with open(cfg_path, "w") as f:
            json.dump({"target_rate": target_rate}, f)
        return {"target_rate": target_rate}

    try:
        with open(cfg_path) as f:
            return json.load(f)
    except Exception:
        return {"target_rate": 10.0}  # défaut 10%


def get_savings_transactions() -> list:
    """
    Retourne toutes les transactions dans les catégories épargne
    avec le total déjà ventilé et le reste à ventiler.
    """
    from models import Transaction, SavingsAllocation
    from sqlalchemy import func
    import account_state

    acc_id = account_state.get_id()

    with Session() as session:
        # Catégories épargne
        savings_cats = session.query(Category).filter(
            Category.name.ilike("%pargne%") |
            Category.name.ilike("%livret%") |
            Category.name.ilike("%LEP%") |
            Category.name.ilike("%PEL%") |
            Category.name.ilike("%CEL%")
        ).all()
        cat_ids = [c.id for c in savings_cats]
        cat_names = {c.id: c.name for c in savings_cats}

        if not cat_ids:
            return []

        q = session.query(Transaction)            .filter(Transaction.type == "expense")            .filter(Transaction.category_id.in_(cat_ids))
        if acc_id:
            q = q.filter(Transaction.account_id == acc_id)
        transactions = q.order_by(Transaction.date.desc()).all()

        results = []
        for t in transactions:
            allocated = session.query(func.sum(SavingsAllocation.amount))                .filter(SavingsAllocation.transaction_id == t.id).scalar() or 0.0
            results.append({
                "id":         t.id,
                "date":       t.date,
                "amount":     t.amount,
                "note":       t.note or "",
                "cat_name":   cat_names.get(t.category_id, ""),
                "allocated":  round(allocated, 2),
                "remaining":  round(t.amount - allocated, 2),
            })
        session.expunge_all()
    return results


def get_allocations(transaction_id: int) -> list:
    """Retourne les ventilations d'une transaction."""
    from models import SavingsAllocation
    with Session() as session:
        rows = session.query(SavingsAllocation)            .filter_by(transaction_id=transaction_id).all()
        goals = {g.id: g.name for g in session.query(SavingsGoal).all()}
        result = [
            {"id": r.id, "goal_id": r.goal_id,
             "goal_name": goals.get(r.goal_id, "?"),
             "amount": r.amount}
            for r in rows
        ]
        session.expunge_all()
    return result


def add_allocation(transaction_id: int, goal_id: int, amount: float) -> bool:
    """
    Ajoute une ventilation. Vérifie que le total ne dépasse pas le montant
    de la transaction. Met à jour current_amount de l'objectif.
    Retourne True si OK, False si dépassement.
    """
    from models import Transaction, SavingsAllocation
    from sqlalchemy import func
    import account_state

    with Session() as session:
        t = session.query(Transaction).filter_by(id=transaction_id).first()
        if not t:
            return False
        already = session.query(func.sum(SavingsAllocation.amount))            .filter(SavingsAllocation.transaction_id == transaction_id).scalar() or 0.0
        if already + amount > t.amount + 0.01:
            return False

    with safe_session() as session:
        session.add(SavingsAllocation(
            transaction_id=transaction_id,
            goal_id=goal_id,
            amount=round(amount, 2),
            account_id=account_state.get_id(),
        ))
        # Recalculer current_amount de l'objectif
        session.flush()  # s'assurer que l'allocation est en base
        goal = session.query(SavingsGoal).filter_by(id=goal_id).first()
        if goal:
            total = session.query(func.sum(SavingsAllocation.amount))\
                .filter(SavingsAllocation.goal_id == goal_id).scalar() or 0.0
            manual = getattr(goal, 'manual_amount', 0) or 0
            goal.current_amount = min(
                round(total + manual, 2), goal.target_amount
            )
    return True


def delete_allocation(allocation_id: int):
    """Supprime une ventilation et recalcule l'objectif."""
    from models import SavingsAllocation
    from sqlalchemy import func

    with safe_session() as session:
        alloc = session.query(SavingsAllocation).filter_by(id=allocation_id).first()
        if not alloc:
            return
        goal_id = alloc.goal_id
        session.delete(alloc)
        session.flush()
        # Recalculer current_amount
        goal = session.query(SavingsGoal).filter_by(id=goal_id).first()
        if goal:
            total = session.query(func.sum(SavingsAllocation.amount))\
                .filter(SavingsAllocation.goal_id == goal_id).scalar() or 0.0
            manual = getattr(goal, 'manual_amount', 0) or 0
            goal.current_amount = min(
                round(total + manual, 2), goal.target_amount
            )


def get_movements(goal_id: int) -> list:
    """Retourne l'historique des mouvements d'un objectif."""
    from models import SavingsMovement
    with Session() as session:
        rows = session.query(SavingsMovement)            .filter_by(goal_id=goal_id)            .order_by(SavingsMovement.moved_at.desc())            .all()
        result = [{
            "id":       r.id,
            "amount":   r.amount,
            "label":    r.label or "",
            "moved_at": r.moved_at,
        } for r in rows]
        session.expunge_all()
    return result


def get_savings_total_by_goal() -> dict:
    """Retourne {goal_id: total_mouvements} pour le mini-widget dashboard."""
    from models import SavingsMovement
    from sqlalchemy import func
    with Session() as session:
        rows = session.query(
            SavingsMovement.goal_id,
            func.sum(SavingsMovement.amount)
        ).group_by(SavingsMovement.goal_id).all()
        session.expunge_all()
    return {r[0]: round(r[1], 2) for r in rows}
