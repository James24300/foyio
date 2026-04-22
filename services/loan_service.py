"""
Service prêts — gestion des crédits, tableau d'amortissement, résumé.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from db import Session, safe_session
from models import Loan
import account_state


def add_loan(name: str, total_amount: float, monthly_payment: float,
             interest_rate: float, start_date: date, end_date: date,
             account_id: int = None) -> Loan:
    """Crée un nouveau prêt."""
    with safe_session() as session:
        loan = Loan(
            name=name,
            total_amount=total_amount,
            remaining_amount=total_amount,
            monthly_payment=monthly_payment,
            interest_rate=interest_rate,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id or account_state.get_id(),
            active=True,
        )
        session.add(loan)
    return loan


def get_loans(account_id: int = None, active_only: bool = True) -> list:
    """Retourne la liste des prêts."""
    with Session() as session:
        q = session.query(Loan)
        if active_only:
            q = q.filter_by(active=True)
        if account_id:
            q = q.filter_by(account_id=account_id)
        loans = q.order_by(Loan.name).all()
        session.expunge_all()
        return loans


def update_loan(loan_id: int, name: str, total_amount: float, monthly_payment: float,
                interest_rate: float, start_date: date, end_date: date):
    """Met à jour un prêt existant."""
    with safe_session() as session:
        loan = session.query(Loan).filter_by(id=loan_id).first()
        if loan:
            loan.name            = name
            loan.total_amount    = total_amount
            loan.monthly_payment = monthly_payment
            loan.interest_rate   = interest_rate
            loan.start_date      = start_date
            loan.end_date        = end_date


def delete_loan(loan_id: int):
    """Supprime (désactive) un prêt."""
    with safe_session() as session:
        loan = session.query(Loan).filter_by(id=loan_id).first()
        if loan:
            loan.active = False


def get_amortization_schedule(loan_id: int) -> list:
    """
    Calcule le tableau d'amortissement mensuel.
    Retourne une liste de dicts :
    {month_num, date, payment, principal, interest, remaining}
    """
    with Session() as session:
        loan = session.query(Loan).filter_by(id=loan_id).first()
        if not loan:
            return []

        remaining = loan.total_amount
        monthly_rate = (loan.interest_rate / 100) / 12
        payment = loan.monthly_payment
        current_date = loan.start_date
        schedule = []
        month_num = 0

        while remaining > 0.01 and month_num < 600:  # max 50 ans
            month_num += 1
            interest = remaining * monthly_rate
            principal = min(payment - interest, remaining)

            # Dernier mois : ajuster le paiement
            if principal <= 0:
                # Le paiement ne couvre même pas les intérêts
                principal = 0
                actual_payment = interest
            else:
                actual_payment = principal + interest

            if remaining - principal < 0.01:
                principal = remaining
                actual_payment = principal + interest

            remaining -= principal

            schedule.append({
                "month_num": month_num,
                "date": current_date.strftime("%m/%Y"),
                "payment": round(actual_payment, 2),
                "principal": round(principal, 2),
                "interest": round(interest, 2),
                "remaining": round(max(remaining, 0), 2),
            })

            current_date = current_date + relativedelta(months=1)

        return schedule


def compute_current_remaining(loan) -> float:
    """Capital restant dû à ce jour, calculé par le tableau d'amortissement."""
    from datetime import date as _date
    today = _date.today()
    if today <= loan.start_date:
        return float(loan.total_amount)

    remaining = float(loan.total_amount)
    monthly_rate = (loan.interest_rate / 100) / 12
    payment = float(loan.monthly_payment)
    current = loan.start_date

    while current < today and remaining > 0.01:
        interest = remaining * monthly_rate
        principal = min(payment - interest, remaining)
        if principal <= 0:
            break
        remaining = max(remaining - principal, 0.0)
        current = current + relativedelta(months=1)

    return round(remaining, 2)


def get_loan_summary() -> dict:
    """
    Résumé global des prêts actifs :
    - total_remaining : dette restante totale
    - total_monthly   : total des mensualités
    - estimated_end   : date de fin la plus éloignée
    """
    with Session() as session:
        loans = session.query(Loan).filter_by(active=True).all()

        if not loans:
            return {
                "total_remaining": 0.0,
                "total_monthly": 0.0,
                "estimated_end": None,
            }

        total_remaining = sum(compute_current_remaining(l) for l in loans)
        total_monthly = sum(l.monthly_payment for l in loans)
        estimated_end = max(l.end_date for l in loans)

        return {
            "total_remaining": total_remaining,
            "total_monthly": total_monthly,
            "estimated_end": estimated_end,
        }
