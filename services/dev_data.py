import random
from datetime import datetime, timedelta
from db import safe_session
from models import Transaction, Category

DESCRIPTIONS = [
    "EDF facture",
    "CARREFOUR courses",
    "TOTAL carburant",
    "AMAZON achat",
    "NETFLIX abonnement",
    "UBER trajet",
    "PHARMACIE centre",
    "AUCHAN supermarché"
]

def generate_transactions(n=200):

    print("Génération des transactions...")

    with safe_session() as session:

        categories = session.query(Category).all()

        if not categories:
            return

        for _ in range(n):

            cat = random.choice(categories)

            # type de transaction
            ttype = random.choice(["expense", "income"])

            # montants réalistes selon le type
            if ttype == "income":
                amount = round(random.uniform(1200, 3500), 2)
            else:
                amount = round(random.uniform(5, 120), 2)

            import account_state
            t = Transaction(
                date=datetime.now() - timedelta(days=random.randint(0, 90)),
                amount=amount,
                type=ttype,
                note=random.choice(DESCRIPTIONS),
                category_id=cat.id,
                account_id=account_state.get_id(),
            )

            session.add(t)

def clear_transactions():

    from db import safe_session
    from models import Transaction

    with safe_session() as session:

        session.query(Transaction).delete()
