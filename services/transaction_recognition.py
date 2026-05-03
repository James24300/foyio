"""
Reconnaissance automatique des catégories de transactions.

Trois niveaux de correspondance (du plus prioritaire au moins prioritaire) :
  1. Règles utilisateur (TransactionRule en base) — exactes, apprises manuellement
  2. Patterns intégrés (BUILTIN_PATTERNS) — couvrent les commerçants/prestataires courants
  3. Apprentissage depuis l'historique — fréquence d'association label→catégorie

Usage :
    from services.transaction_recognition import find_rule, learn_rule, learn_from_history
    cat_id = find_rule("LIDL 3355")       # → id catégorie "Courses"
    learn_rule("netflix", cat_id)         # mémoriser une règle
    learn_from_history()                  # apprendre depuis les transactions existantes
"""

import re
from db import Session
from models import TransactionRule, Transaction, Category


# ──────────────────────────────────────────────────────────────
# Normalisation
# ──────────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    """Minuscules + suppression des accents."""
    if not text:
        return ""
    text = text.lower()
    for src, dst in [
        ("é","e"),("è","e"),("ê","e"),("ë","e"),
        ("à","a"),("â","a"),("ä","a"),
        ("ù","u"),("û","u"),("ü","u"),
        ("ô","o"),("ö","o"),
        ("î","i"),("ï","i"),
        ("ç","c"),
    ]:
        text = text.replace(src, dst)
    return text


# ──────────────────────────────────────────────────────────────
# Patterns intégrés : (regex, nom_catégorie_cible)
# ──────────────────────────────────────────────────────────────
# Les noms de catégories sont mis en minuscules normalisés pour comparaison.
# On cherche la catégorie par nom (insensible à la casse) en base.

BUILTIN_PATTERNS = [
    # ── Alimentation / Courses ──
    (r"lidl|aldi|intermarche|super u|carrefour|leclerc|casino|monoprix|"
     r"picard|franprix|bio c bon|naturalia|biocoop|match|netto|u express|"
     r"epicerie|boulangerie|boucherie|poissonnerie|primeur", "courses"),

    # ── Restaurants / Bars ──
    (r"restaurant|brasserie|bistro|cafe|bar |pizz|burger|mcdonald|quick|"
     r"kfc|subway|domino|pizza hut|sushi|kebab|le qg|caprices dantan|"
     r"ciseaux angeline|caats", "restaurant"),

    # ── Carburant ──
    (r"total|bp |shell|esso|leclerc carbu|intermarche carbu|"
     r"station|carburant|essence|gazole", "carburant"),

    # ── Transport ──
    (r"sncf|ratp|blablacar|uber|bolt|heetch|taxi|parking|indigo|"
     r"vélib|lime |tier |bird |trottinette|bus |train |metro", "transport"),

    # ── Loyer / Immobilier ──
    (r"loyer|duchange|agence immo|foncier|charges locatives|"
     r"syndic|copropri", "maison"),

    # ── Energie ──
    (r"totalenergies|edf|engie|direct energie|ekwateur|"
     r"electricite|gaz france|gaz reseau|gaz de france", "electricite"),

    # ── Eau ──
    (r"veolia|suez|eau |lyonnaise des eaux|perigord nontron", "eau"),

    # ── Téléphonie / Internet ──
    (r"orange|sfr|bouygues|free |sosh|b&you|la poste mobile|"
     r"red by sfr|prixtel|lebara|nrj mobile|coriolis", "telephone"),

    # ── Abonnements streaming / jeux ──
    (r"netflix|spotify|deezer|amazon prime|disney|canal\+|apple|"
     r"youtube premium|twitch|xbox|playstation|nintendo|steam|"
     r"fnac darty|sobrio|caats\.co|ginara", "loisirs"),

    # ── Santé ──
    (r"pharmacie|medecin|docteur|hopital|clinique|dentiste|"
     r"opticien|kiné|infirmier|cpam|ameli|mutuelle|lamie|"
     r"siaci saint honore|remboursement sante", "sante"),

    # ── Assurance ──
    (r"maaf|axa|allianz|groupama|macif|matmut|mma |gmf |"
     r"april|covea|cardif|pacifica|assurance", "assurance"),

    # ── Banque / Crédit ──
    (r"franfinance|cetelem|sofinco|cofidis|floa|boursorama|"
     r"credit agricole|bnp|societe generale|caisse epargne|"
     r"credit mutuel|lcl |hsbc|ing |credit|diac sa|prelevement.*credit", "credit"),

    # ── Salaire / Revenus ──
    (r"salaire|paie |paye |virement.*salaire|tresorerie.*hospitalier|"
     r"ch de nontron|employeur", "salaire"),

    # ── Remboursements ──
    (r"cpam|c\.p\.a\.m|caf |assurance maladie|caisse primaire|"
     r"securite sociale|vir recu.*perigueux", "remboursement"),

    # ── Achats en ligne / Divers ──
    (r"amazon(?! prime)|ebay|vinted|leboncoin|wish|aliexpress|"
     r"cdiscount|fnac(?! darty)|darty|boulanger|alma home", "loisirs"),

    # ── PayPal (neutre — laisser en "Divers" si pas d'autre règle) ──
    (r"paypal", None),  # None = pas de catégorie forcée, on laisse l'utilisateur choisir
]

# Compilation des regex
_COMPILED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), cat_name)
    for pattern, cat_name in BUILTIN_PATTERNS
]


# ──────────────────────────────────────────────────────────────
# Résolution : nom de catégorie → id
# ──────────────────────────────────────────────────────────────
_CATEGORY_CACHE: dict = {}  # {nom_normalisé: id}

def _get_category_id(name: str) -> int | None:
    """Résout un nom de catégorie (insensible casse/accents) en id."""
    if not name:
        return None

    global _CATEGORY_CACHE
    key = normalize(name)

    if key in _CATEGORY_CACHE:
        return _CATEGORY_CACHE[key]

    with Session() as session:
        cats = session.query(Category).all()
        for c in cats:
            _CATEGORY_CACHE[normalize(c.name)] = c.id

    return _CATEGORY_CACHE.get(key)


def _invalidate_cache():
    """Vide le cache catégories (appeler après ajout/suppression)."""
    global _CATEGORY_CACHE
    _CATEGORY_CACHE = {}


# ──────────────────────────────────────────────────────────────
# find_rule — point d'entrée principal
# ──────────────────────────────────────────────────────────────
def find_rule(note: str) -> int | None:
    """
    Cherche la catégorie la plus probable pour un libellé de transaction.

    Priorité :
      1. Règles utilisateur en base (TransactionRule)
      2. Patterns intégrés (BUILTIN_PATTERNS)
      3. Historique : catégorie la plus fréquente pour ce libellé

    Retourne l'id de catégorie ou None si aucune correspondance.
    """
    if not note:
        return None

    note_n = normalize(note)

    # ── Niveau 1 : règles utilisateur ──
    with Session() as session:
        rules = session.query(TransactionRule).all()
        for rule in rules:
            if normalize(rule.keyword) in note_n:
                return rule.category_id

    # ── Niveau 2 : patterns intégrés ──
    for compiled, cat_name in _COMPILED_PATTERNS:
        if compiled.search(note):
            if cat_name is None:
                break  # PayPal et similaires → pas de forçage
            cat_id = _get_category_id(cat_name)
            if cat_id:
                return cat_id

    # ── Niveau 3 : apprentissage depuis l'historique ──
    return _find_from_history(note_n)


def _find_from_history(note_n: str) -> int | None:
    """
    Cherche la catégorie la plus fréquemment associée aux transactions
    dont le libellé normalisé contient un mot commun avec note_n.
    """
    # Extraire les mots significatifs (>= 4 lettres, pas de mots génériques)
    STOPWORDS = {"carte", "virement", "prel", "prlv", "sepa", "euro",
                 "recu", "inst", "pour", "motif", "mandat", "avec", "chez",
                 "prelevement", "europeen", "commerce", "electronique"}

    words = [w for w in re.split(r"\W+", note_n)
             if len(w) >= 4 and w not in STOPWORDS]

    if not words:
        return None

    with Session() as session:
        from sqlalchemy import func

        best_id    = None
        best_count = 0

        for word in words[:3]:  # max 3 mots pour les perfs
            results = (
                session.query(
                    Transaction.category_id,
                    func.count(Transaction.id).label("cnt")
                )
                .filter(Transaction.note.ilike(f"%{word}%"))
                .filter(Transaction.category_id.isnot(None))
                .group_by(Transaction.category_id)
                .order_by(func.count(Transaction.id).desc())
                .limit(1)
                .all()
            )
            for cat_id, count in results:
                if count > best_count:
                    best_count = count
                    best_id    = cat_id

    return best_id if best_count >= 1 else None


# ──────────────────────────────────────────────────────────────
# Apprentissage manuel
# ──────────────────────────────────────────────────────────────
def clean_bad_rules():
    """Supprime les règles apprises sur des mots-clés trop génériques."""
    BAD_KEYWORDS = {
        "carte", "super", "sarl", "retrait", "frais", "paiement",
        "commerce", "electronique", "hors", "zone", "euro", "prelevement",
        "virement", "europeen", "abonnement", "x4832", "x3093", "x4832",
        "16/03", "15/03", "14/03", "13/03", "12/03", "action", "nfc",
        "iopd", "dab", "payments", "subscription",
    }
    from db import safe_session
    with safe_session() as session:
        from models import TransactionRule
        rules = session.query(TransactionRule).all()
        for r in rules:
            if r.keyword.lower() in BAD_KEYWORDS or len(r.keyword) <= 2:
                session.delete(r)


def learn_rule(keyword: str, category_id: int):
    """Enregistre ou met à jour une règle de reconnaissance utilisateur."""
    keyword = normalize(keyword.strip())
    if not keyword:
        return

    from db import safe_session
    with safe_session() as session:
        existing = session.query(TransactionRule).filter_by(keyword=keyword).first()
        if existing:
            existing.category_id = category_id
        else:
            session.add(TransactionRule(keyword=keyword, category_id=category_id))


def learn_from_import(transactions_and_categories: list):
    """
    Apprend depuis un import : pour chaque (label, category_id),
    crée une règle si le libellé est assez spécifique.
    """
    for label, cat_id in transactions_and_categories:
        if not label or not cat_id:
            continue
        keyword = extract_keyword(label)
        if keyword:
            learn_rule(keyword, cat_id)


def extract_keyword(note: str) -> str | None:
    """
    Extrait le mot-clé le plus représentatif d'un libellé de transaction.
    Ignore les mots génériques, les codes numériques et les dates.
    Retourne None si aucun mot exploitable n'est trouvé.
    """
    SKIP = {"carte", "super", "sarl", "retrait", "frais", "paiement",
            "commerce", "electronique", "hors", "zone", "euro",
            "prelevement", "virement", "europeen", "abonnement",
            "recu", "inst", "pour", "motif", "mandat", "avec", "chez",
            "sepa", "prlv", "prel"}
    note_n = normalize(note)
    words = [w for w in re.split(r"\W+", note_n)
             if len(w) >= 3
             and w not in SKIP
             and not re.match(r'^x?\d+$', w)       # exclure X4832, 3355
             and not re.match(r'^\d{2}/\d{2}$', w) # exclure 16/03
             and not re.match(r'^\d+$', w)]         # exclure nombres purs
    if not words:
        return None
    return max(words, key=len)
