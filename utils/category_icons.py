DEFAULT_ICONS = [
    "shopping.png",
    "groceries.png",
    "fuel.png",
    "car.png",
    "bus.png",
    "train.png",
    "restaurant.png",
    "coffee.png",
    "movie.png",
    "music.png",
    "hotel.png",
    "plane.png",
    "internet.png",
    "phone.png",
    "doctor.png",
    "pharmacy.png",
    "money.png",
    "bank.png"
]

CATEGORY_ICONS = {

    "courses": "groceries.png",
    "carburant": "fuel.png",
    "eau": "water.png",
    "electricite": "electricity.png",
    "gaz": "gas.png",
    "loisirs": "entertainment.png",
    "maison": "house.png",
    "salaire": "money.png",
    "sante": "doctor.png",
    "telephone": "phone.png",
    "internet": "internet.png",
    "credit auto": "car.png",
    "credit moto": "bike.png",
}

CATEGORY_KEYWORDS = {

    # =========================
    # COURSES / SUPERMARCHES
    # =========================
    "carrefour": "groceries.png",
    "leclerc": "groceries.png",
    "intermarche": "groceries.png",
    "auchan": "groceries.png",
    "casino": "groceries.png",
    "monoprix": "groceries.png",
    "lidl": "groceries.png",
    "aldi": "groceries.png",
    "super u": "groceries.png",
    "u express": "groceries.png",
    "cora": "groceries.png",
    "match": "groceries.png",

    # =========================
    # CARBURANT
    # =========================
    "total": "fuel.png",
    "totalenergies": "fuel.png",
    "esso": "fuel.png",
    "bp": "fuel.png",
    "shell": "fuel.png",
    "station service": "fuel.png",
    "carburant": "fuel.png",
    "essence": "fuel.png",

    # =========================
    # ELECTRICITE
    # =========================
    "edf": "electricity.png",
    "electricite": "electricity.png",
    "électricité": "electricity.png",
    "total energies": "electricity.png",

    # =========================
    # GAZ
    # =========================
    "engie": "gas.png",
    "total energies": "gas.png",
    "gaz": "gas.png",

    # =========================
    # EAU
    # =========================
    "veolia": "water.png",
    "suez": "water.png",
    "eau": "water.png",

    # =========================
    # RESTAURATION
    # =========================
    "restaurant": "restaurant.png",
    "mcdo": "restaurant.png",
    "mcdonald": "restaurant.png",
    "burger king": "restaurant.png",
    "kfc": "restaurant.png",
    "quick": "restaurant.png",
    "subway": "restaurant.png",
    "dominos": "restaurant.png",
    "pizza hut": "restaurant.png",

    # =========================
    # CAFE
    # =========================
    "cafe": "coffee.png",
    "café": "coffee.png",
    "starbucks": "coffee.png",

    # =========================
    # SHOPPING
    # =========================
    "amazon": "shopping.png",
    "zalando": "shopping.png",
    "shein": "shopping.png",
    "aliexpress": "shopping.png",
    "cdiscount": "shopping.png",
    "ebay": "shopping.png",
    "fnac": "shopping.png",
    "darty": "shopping.png",
    "boulanger": "shopping.png",

    # =========================
    # TRANSPORT
    # =========================
    "uber": "transport.png",
    "bolt": "transport.png",
    "taxi": "transport.png",
    "sncf": "train.png",
    "ratp": "bus.png",
    "metro": "bus.png",
    "bus": "bus.png",
    "train": "train.png",
    "voiture": "car.png",

    # =========================
    # INTERNET / TELECOM
    # =========================
    "orange": "internet.png",
    "sfr": "internet.png",
    "free": "internet.png",
    "bouygues": "internet.png",
    "internet": "internet.png",
    "wifi": "internet.png",
    "téléphone": "phone.png",

    # =========================
    # DIVERTISSEMENT
    # =========================
    "netflix": "movie.png",
    "spotify": "music.png",
    "deezer": "music.png",
    "youtube": "movie.png",
    "disney": "movie.png",
    "cinema": "movie.png",

    # =========================
    # SANTE
    # =========================
    "pharmacie": "pharmacy.png",
    "pharma": "pharmacy.png",
    "docteur": "doctor.png",
    "medecin": "doctor.png",
    "dentiste": "doctor.png",
    "mutuelle": "doctor.png",

    # =========================
    # VOYAGE
    # =========================
    "airbnb": "hotel.png",
    "hotel": "hotel.png",
    "booking": "hotel.png",
    "voyage": "travel.png",
    "vol": "plane.png",

    # =========================
    # TRAVAIL / SALAIRE
    # =========================
    "salaire": "money.png",
    "paie": "money.png",
    "indemnité journalière": "money.png",

    # =========================
    # BANQUE
    # =========================
    "banque": "bank.png",
    "virement": "bank.png",
    "credit": "bank.png",
    "crédit auto": "car.png",
    "pret": "bank.png",
    "credit moto": "bike.png",
}

CATEGORY_COLORS = {

    # énergie
    "electricite": "#facc15",
    "gaz": "#f97316",
    "eau": "#38bdf8",

    # logement
    "loyer": "#3b82f6",
    "maison": "#3b82f6",

    # alimentation
    "courses": "#22c55e",
    "restaurant": "#ef4444",

    # transport
    "carburant": "#f59e0b",
    "transport": "#6366f1",
    "parking": "#64748b",

    # communication
    "telephone": "#a855f7",
    "internet": "#06b6d4",

    # santé
    "sante": "#ec4899",

    # travail / revenus
    "salaire": "#16a34a",
    "banque": "#0ea5e9",

    # loisirs
    "loisirs": "#8b5cf6",
    "voyage": "#14b8a6"
}

CATEGORY_PALETTE = [
    "#3b82f6",  # bleu
    "#22c55e",  # vert
    "#f59e0b",  # orange
    "#ef4444",  # rouge
    "#a855f7",  # violet
    "#06b6d4",  # cyan
    "#f97316",  # orange foncé
    "#14b8a6",  # turquoise
    "#6366f1",  # indigo
    "#ec4899",  # rose
]

def normalize(text):

    text = text.lower()

    return (
        text.replace("é","e")
        .replace("è","e")
        .replace("ê","e")
        .replace("à","a")
        .replace("ù","u")
        .replace("ç","c")
    )

def get_category_icon(text):

    if not text:
        return "other.png"

    text = normalize(text)

    # priorité : catégories
    for keyword, icon in CATEGORY_ICONS.items():
        if keyword in text:
            return icon

    # marchands / transactions
    for keyword, icon in CATEGORY_KEYWORDS.items():
        if keyword in text:
            return icon

    # icône par défaut
    return get_default_icon(text)

def get_category_color(name):

    if not name:
        return "#888888"

    name = name.lower()

    # priorité : couleurs définies
    for key, color in CATEGORY_COLORS.items():
        if key in name:
            return color

    # sinon choisir une couleur stable
    index = abs(hash(name)) % len(CATEGORY_PALETTE)

    return CATEGORY_PALETTE[index]

def get_default_icon(name):

    if not name:
        return "shopping.png"

    index = abs(hash(name)) % len(DEFAULT_ICONS)

    return DEFAULT_ICONS[index]

def detect_category_from_text(text):

    if not text:
        return None

    text = normalize(text)

    for keyword, icon in CATEGORY_KEYWORDS.items():
        if keyword in text:
            return keyword

    return None