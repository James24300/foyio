"""
Service Crypto-monnaie — Foyio
Gère le portefeuille crypto, les transactions et les alertes.
Prix via CoinGecko API (gratuit, sans clé).
"""
import logging
import time
import urllib.request
import json
from datetime import datetime, date as _date
from db import Session, safe_session
from models import CryptoHolding, CryptoTransaction, CryptoAlert, Category, CryptoDCA
import account_state

logger = logging.getLogger(__name__)

# ── Cache prix (évite les appels répétés) ────────────────────────────────────
_price_cache: dict = {}          # {coingecko_id: {"price": float, "change_24h": float, "ts": float}}
_CACHE_TTL = 300                 # secondes (5 min — réduit les appels API)

_history_cache: dict = {}        # {(coingecko_id, days): {"data": list, "ts": float}}
_HISTORY_CACHE_TTL = 1800        # 30 minutes

_image_url_cache: dict = {}  # {coingecko_id: image_url}

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# ── Rate limiter global ───────────────────────────────────────────────────────
import threading as _threading
_api_lock    = _threading.Lock()
_last_call_t = 0.0
_MIN_DELAY   = 6.0              # secondes minimum entre deux appels API


# ── Appels API CoinGecko ─────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> dict | list | None:
    """GET JSON depuis CoinGecko avec rate-limiting global et backoff exponentiel sur 429."""
    global _last_call_t
    with _api_lock:
        wait = _MIN_DELAY - (time.time() - _last_call_t)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Foyio/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result = json.loads(resp.read())
                _last_call_t = time.time()
                return result
            except urllib.error.HTTPError as e:
                _last_call_t = time.time()
                if e.code == 429:
                    backoff = (attempt + 1) * 10  # 10s, 20s, 30s, 40s
                    logger.warning(f"CoinGecko 429, attente {backoff}s (essai {attempt+1}/4)")
                    time.sleep(backoff)
                else:
                    logger.warning(f"CoinGecko HTTP error {e.code}: {e}")
                    return None
            except Exception as e:
                _last_call_t = time.time()
                logger.warning(f"CoinGecko API error: {e}")
                return None
        _last_call_t = time.time()
        logger.warning("CoinGecko 429 persistant après 4 essais, abandon.")
        return None


def get_prices(coingecko_ids: list[str]) -> dict:
    """
    Retourne {id: {"price": float, "change_24h": float}} pour chaque id.
    Utilise /coins/markets (un seul appel qui retourne prix ET image).
    Cache TTL=120s.
    """
    if not coingecko_ids:
        return {}

    now = time.time()
    to_fetch = [i for i in coingecko_ids
                if i not in _price_cache or now - _price_cache[i]["ts"] > _CACHE_TTL]

    if to_fetch:
        ids_param = ",".join(to_fetch)
        url = (f"{COINGECKO_BASE}/coins/markets"
               f"?vs_currency=eur&ids={ids_param}&per_page=250&page=1"
               f"&price_change_percentage=24h")
        data = _get(url)
        if data:
            for coin in data:
                cid = coin["id"]
                _price_cache[cid] = {
                    "price":      coin.get("current_price", 0) or 0,
                    "change_24h": coin.get("price_change_percentage_24h", 0) or 0,
                    "market_cap": coin.get("market_cap", 0) or 0,
                    "ts":         now,
                }
                # Image récupérée en même temps — aucun appel supplémentaire
                if coin.get("image"):
                    _image_url_cache[cid] = coin["image"]

    return {
        cid: {k: v for k, v in _price_cache[cid].items() if k != "ts"}
        for cid in coingecko_ids
        if cid in _price_cache
    }


def get_coin_image_urls(coingecko_ids: list[str]) -> dict[str, str]:
    """Retourne {id: image_url} — utilise le cache rempli par get_prices()."""
    # Si les images ne sont pas encore en cache (logos chargés avant les prix),
    # on fait un appel coins/markets uniquement pour les IDs manquants.
    to_fetch = [i for i in coingecko_ids if i not in _image_url_cache]
    if not to_fetch:
        return {cid: _image_url_cache[cid] for cid in coingecko_ids if cid in _image_url_cache}
    ids_param = ",".join(to_fetch)
    url = (f"{COINGECKO_BASE}/coins/markets"
           f"?vs_currency=eur&ids={ids_param}&per_page=250&page=1")
    data = _get(url)
    if data:
        for coin in data:
            _image_url_cache[coin["id"]] = coin.get("image", "")
    return {cid: _image_url_cache[cid] for cid in coingecko_ids if cid in _image_url_cache}


def search_coins(query: str) -> list[dict]:
    """
    Recherche des cryptos par nom/symbole.
    Retourne [{id, name, symbol, thumb}, …]
    """
    if not query or len(query) < 2:
        return []
    url = f"{COINGECKO_BASE}/search?query={urllib.parse.quote(query)}"
    data = _get(url)
    if not data:
        return []
    return [
        {
            "id":     c["id"],
            "name":   c["name"],
            "symbol": c["symbol"].upper(),
            "thumb":  c.get("thumb", ""),
        }
        for c in data.get("coins", [])[:20]
    ]


def get_price_history(coingecko_id: str, days: int = 30) -> list[tuple[int, float]]:
    """
    Retourne [(timestamp_ms, price_eur), …] sur N jours.
    Utilise un cache de 10 minutes pour éviter les erreurs 429.
    """
    key = (coingecko_id, days)
    now = time.time()
    cached = _history_cache.get(key)
    if cached and now - cached["ts"] < _HISTORY_CACHE_TTL:
        return cached["data"]

    url = (f"{COINGECKO_BASE}/coins/{coingecko_id}/market_chart"
           f"?vs_currency=eur&days={days}&interval=daily")
    data = _get(url)
    if not data:
        return cached["data"] if cached else []  # retourner l'ancien cache si dispo
    result = [(int(p[0]), float(p[1])) for p in data.get("prices", [])]
    _history_cache[key] = {"data": result, "ts": now}
    return result


def get_top_coins(limit: int = 50) -> list[dict]:
    """
    Retourne le top N cryptos par capitalisation boursière.
    """
    url = (f"{COINGECKO_BASE}/coins/markets"
           f"?vs_currency=eur&order=market_cap_desc"
           f"&per_page={limit}&page=1"
           f"&price_change_percentage=24h")
    data = _get(url)
    if not data:
        return []
    return [
        {
            "id":         c["id"],
            "name":       c["name"],
            "symbol":     c["symbol"].upper(),
            "price":      c.get("current_price", 0),
            "change_24h": c.get("price_change_percentage_24h", 0),
            "market_cap": c.get("market_cap", 0),
            "thumb":      c.get("image", ""),
        }
        for c in data
    ]


# ── CRUD Holdings ─────────────────────────────────────────────────────────────

def get_holdings(account_id: int = None) -> list:
    """Retourne les positions actives du portefeuille."""
    acc_id = account_id or account_state.get_id()
    with Session() as session:
        q = session.query(CryptoHolding).filter_by(active=True)
        if acc_id is not None:
            q = q.filter_by(account_id=acc_id)
        holdings = q.order_by(CryptoHolding.name).all()
        session.expunge_all()
        return holdings


def add_holding(symbol: str, name: str, coingecko_id: str,
                quantity: float, buy_price: float) -> CryptoHolding:
    """Ajoute une nouvelle position (ou met à jour si la crypto existe déjà)."""
    acc_id = account_state.get_id()
    with safe_session() as session:
        existing = (session.query(CryptoHolding)
                    .filter_by(coingecko_id=coingecko_id, account_id=acc_id, active=True)
                    .first())
        if existing:
            # Recalcul prix moyen pondéré
            total_qty   = existing.quantity + quantity
            total_cost  = existing.quantity * existing.avg_buy_price + quantity * buy_price
            existing.quantity      = round(total_qty, 8)
            existing.avg_buy_price = round(total_cost / total_qty, 2) if total_qty > 0 else buy_price
            holding = existing
        else:
            holding = CryptoHolding(
                symbol=symbol.upper(), name=name,
                coingecko_id=coingecko_id,
                quantity=round(quantity, 8),
                avg_buy_price=round(buy_price, 2),
                account_id=acc_id, active=True,
            )
            session.add(holding)
        session.flush()
        # Enregistrer la transaction d'achat
        tx = CryptoTransaction(
            holding_id=holding.id,
            type="buy",
            quantity=round(quantity, 8),
            price_eur=round(buy_price, 2),
            total_eur=round(quantity * buy_price, 2),
            date=datetime.now(),
            account_id=acc_id,
        )
        session.add(tx)
    return holding


def sell_holding(holding_id: int, quantity: float, sell_price: float, note: str = "") -> bool:
    """Enregistre une vente partielle ou totale."""
    acc_id = account_state.get_id()
    with safe_session() as session:
        holding = session.query(CryptoHolding).filter_by(id=holding_id).first()
        if not holding or holding.quantity < quantity:
            return False
        holding.quantity = round(holding.quantity - quantity, 8)
        if holding.quantity <= 0:
            holding.active = False
        tx = CryptoTransaction(
            holding_id=holding_id,
            type="sell",
            quantity=round(quantity, 8),
            price_eur=round(sell_price, 2),
            total_eur=round(quantity * sell_price, 2),
            date=datetime.now(),
            note=note.strip() or None,
            account_id=acc_id,
        )
        session.add(tx)
    return True


def update_holding(holding_id: int, quantity: float, avg_buy_price: float):
    """Modifie la quantité et le prix moyen d'achat d'une position."""
    with safe_session() as session:
        h = session.query(CryptoHolding).filter_by(id=holding_id).first()
        if h:
            h.quantity      = round(quantity, 8)
            h.avg_buy_price = round(avg_buy_price, 2)
            if h.quantity <= 0:
                h.active = False


def delete_holding(holding_id: int):
    """Supprime (désactive) une position."""
    with safe_session() as session:
        h = session.query(CryptoHolding).filter_by(id=holding_id).first()
        if h:
            h.active = False


def get_transactions(holding_id: int = None) -> list:
    """Retourne l'historique des transactions crypto."""
    acc_id = account_state.get_id()
    with Session() as session:
        q = session.query(CryptoTransaction)
        if holding_id:
            q = q.filter_by(holding_id=holding_id)
        elif acc_id is not None:
            q = q.filter_by(account_id=acc_id)
        txs = q.order_by(CryptoTransaction.date.desc()).limit(500).all()
        session.expunge_all()
        return txs


# ── CRUD Alertes ──────────────────────────────────────────────────────────────

def get_alerts() -> list:
    acc_id = account_state.get_id()
    with Session() as session:
        q = session.query(CryptoAlert).filter_by(active=True)
        if acc_id is not None:
            q = q.filter_by(account_id=acc_id)
        alerts = q.all()
        session.expunge_all()
        return alerts


def add_alert(holding_id: int, alert_type: str, target_price: float) -> CryptoAlert:
    acc_id = account_state.get_id()
    with safe_session() as session:
        alert = CryptoAlert(
            holding_id=holding_id,
            alert_type=alert_type,
            target_price=round(target_price, 2),
            active=True, triggered=False,
            account_id=acc_id,
        )
        session.add(alert)
    return alert


def delete_alert(alert_id: int):
    with safe_session() as session:
        a = session.query(CryptoAlert).filter_by(id=alert_id).first()
        if a:
            a.active = False


def check_alerts(current_prices: dict) -> list[dict]:
    """
    Vérifie les alertes actives contre les prix courants.
    Retourne la liste des alertes déclenchées.
    """
    triggered = []
    acc_id = account_state.get_id()
    with safe_session() as session:
        alerts = (session.query(CryptoAlert)
                  .filter_by(active=True, triggered=False)
                  .all())
        for alert in alerts:
            holding = session.query(CryptoHolding).filter_by(id=alert.holding_id).first()
            if not holding:
                continue
            price_info = current_prices.get(holding.coingecko_id, {})
            price = price_info.get("price", 0)
            if price == 0:
                continue
            change_24h = price_info.get("change_24h", 0) or 0
            hit = (
                (alert.alert_type == "above"   and price      >= alert.target_price) or
                (alert.alert_type == "below"   and price      <= alert.target_price) or
                (alert.alert_type == "pct_up"  and change_24h >= alert.target_price) or
                (alert.alert_type == "pct_down" and change_24h <= -abs(alert.target_price))
            )
            if hit:
                alert.triggered = True
                triggered.append({
                    "name":         holding.name,
                    "symbol":       holding.symbol,
                    "alert_type":   alert.alert_type,
                    "target_price": alert.target_price,
                    "current_price": price,
                    "change_24h":   change_24h,
                })
    return triggered


# ── Statistiques portefeuille ─────────────────────────────────────────────────

def get_portfolio_summary(holdings: list, prices: dict) -> dict:
    """
    Calcule la valeur totale, P&L total et variation 24h du portefeuille.
    """
    total_value    = 0.0
    total_invested = 0.0
    total_24h_change = 0.0

    for h in holdings:
        info    = prices.get(h.coingecko_id, {})
        price   = info.get("price", 0)
        chg_24h = info.get("change_24h", 0)
        value   = h.quantity * price
        invested = h.quantity * h.avg_buy_price

        total_value    += value
        total_invested += invested
        total_24h_change += value * chg_24h / 100

    pnl        = total_value - total_invested
    pnl_pct    = (pnl / total_invested * 100) if total_invested > 0 else 0

    return {
        "total_value":     round(total_value, 2),
        "total_invested":  round(total_invested, 2),
        "pnl":             round(pnl, 2),
        "pnl_pct":         round(pnl_pct, 2),
        "change_24h_eur":  round(total_24h_change, 2),
    }


# ── Simulateur DCA ────────────────────────────────────────────────────────────

def simulate_dca(monthly_eur: float, months: int,
                 annual_growth_rate: float = 10.0) -> dict:
    """
    Simule un investissement DCA (Dollar Cost Averaging).
    Retourne l'évolution mois par mois.
    """
    monthly_rate = annual_growth_rate / 100 / 12
    balance = 0.0
    invested = 0.0
    evolution = []

    for m in range(months):
        balance  = (balance + monthly_eur) * (1 + monthly_rate)
        invested += monthly_eur
        evolution.append({
            "month":    m + 1,
            "value":    round(balance, 2),
            "invested": round(invested, 2),
            "gain":     round(balance - invested, 2),
        })

    return {
        "final_value":    round(balance, 2),
        "total_invested": round(invested, 2),
        "total_gain":     round(balance - invested, 2),
        "gain_pct":       round((balance - invested) / invested * 100, 2) if invested > 0 else 0,
        "evolution":      evolution,
    }


def simulate_what_if(coingecko_id: str, invested_eur: float, months_ago: int) -> dict | None:
    """
    Simule 'Si j'avais investi X€ il y a N mois en [crypto]'.
    """
    history = get_price_history(coingecko_id, days=months_ago * 31)
    if not history or len(history) < 2:
        return None

    price_then = history[0][1]
    price_now  = history[-1][1]

    if price_then <= 0:
        return None

    qty_bought   = invested_eur / price_then
    current_value = qty_bought * price_now
    gain         = current_value - invested_eur
    gain_pct     = gain / invested_eur * 100

    return {
        "invested":      round(invested_eur, 2),
        "qty_bought":    round(qty_bought, 8),
        "price_then":    round(price_then, 2),
        "price_now":     round(price_now, 2),
        "current_value": round(current_value, 2),
        "gain":          round(gain, 2),
        "gain_pct":      round(gain_pct, 2),
        "history":       history,
    }


# Fix missing import
import urllib.parse


# ── Intégration transactions financières ──────────────────────────────────────

def _get_or_create_crypto_category() -> int:
    """Retourne l'id de la catégorie 'Crypto', la crée si elle n'existe pas."""
    with safe_session() as session:
        cat = session.query(Category).filter_by(name="Crypto").first()
        if not cat:
            cat = Category(name="Crypto", icon="money.png", color="#f59e0b")
            session.add(cat)
            session.flush()
        return cat.id


def link_to_transaction(amount: float, tx_type: str, note: str):
    """
    Crée une transaction financière liée à une opération crypto.
    tx_type : 'expense' (achat) ou 'income' (vente).
    """
    from services.transaction_service import add_transaction
    cat_id = _get_or_create_crypto_category()
    add_transaction(
        amount=round(amount, 2),
        type=tx_type,
        category_id=cat_id,
        note=note,
        date=datetime.now(),
    )


# ── Plans DCA récurrents ──────────────────────────────────────────────────────

def get_dca_plans() -> list:
    """Retourne tous les plans DCA avec leur holding associé."""
    with Session() as session:
        plans = session.query(CryptoDCA).all()
        session.expunge_all()
        return plans


def add_dca_plan(holding_id: int, amount_eur: float, day_of_month: int, note: str = "") -> CryptoDCA:
    """Crée un nouveau plan DCA."""
    with safe_session() as session:
        plan = CryptoDCA(
            holding_id=holding_id,
            amount_eur=amount_eur,
            day_of_month=max(1, min(28, day_of_month)),
            active=True,
            last_executed=None,
            note=note or None,
        )
        session.add(plan)
        session.flush()
        session.expunge(plan)
        return plan


def delete_dca_plan(plan_id: int):
    with safe_session() as session:
        plan = session.query(CryptoDCA).filter_by(id=plan_id).first()
        if plan:
            session.delete(plan)


def toggle_dca_plan(plan_id: int) -> bool:
    """Active/désactive un plan DCA. Retourne le nouvel état."""
    with safe_session() as session:
        plan = session.query(CryptoDCA).filter_by(id=plan_id).first()
        if plan:
            plan.active = not plan.active
            return plan.active
        return False


def update_dca_plan(plan_id: int, amount_eur: float, day_of_month: int, note: str = ""):
    """Met à jour un plan DCA existant."""
    with safe_session() as session:
        plan = session.query(CryptoDCA).filter_by(id=plan_id).first()
        if plan:
            plan.amount_eur   = amount_eur
            plan.day_of_month = max(1, min(28, day_of_month))
            plan.note         = note or None


def get_due_dca_plans() -> list:
    """
    Retourne les plans actifs dont le jour prévu est aujourd'hui
    et qui n'ont pas encore été exécutés ce mois-ci.
    """
    today = _date.today()
    with Session() as session:
        plans = session.query(CryptoDCA).filter_by(active=True).all()
        due = []
        for p in plans:
            if p.day_of_month != today.day:
                continue
            if p.last_executed and p.last_executed.year == today.year \
                    and p.last_executed.month == today.month:
                continue
            due.append(p)
        session.expunge_all()
        return due


def execute_dca(plan_id: int, link_financial: bool = False) -> dict | None:
    """
    Exécute un plan DCA :
    - Récupère le prix actuel
    - Calcule la quantité achetée
    - Crée une CryptoTransaction
    - Met à jour la quantité et le prix moyen du holding
    - Marque last_executed = aujourd'hui
    Retourne un dict résumé ou None en cas d'erreur.
    """
    with Session() as session:
        plan = session.query(CryptoDCA).filter_by(id=plan_id).first()
        if not plan:
            return None
        holding = session.query(CryptoHolding).filter_by(id=plan.holding_id).first()
        if not holding:
            return None
        session.expunge_all()
        plan_id_     = plan.id
        amount_eur   = plan.amount_eur
        holding_id   = holding.id
        cg_id        = holding.coingecko_id
        symbol       = holding.symbol
        name         = holding.name
        old_qty      = holding.quantity
        old_avg      = holding.avg_buy_price

    prices = get_prices([cg_id])
    if not prices or cg_id not in prices:
        return None

    price = prices[cg_id]["price"]
    if price <= 0:
        return None

    qty = amount_eur / price
    # Recalcul prix moyen pondéré
    new_qty = old_qty + qty
    new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty if new_qty > 0 else price

    today = _date.today()

    with safe_session() as session:
        # Créer la transaction crypto
        tx = CryptoTransaction(
            holding_id=holding_id,
            type="buy",
            quantity=round(qty, 8),
            price_eur=round(price, 2),
            total_eur=round(amount_eur, 2),
            date=datetime.now(),
            note=f"DCA automatique ({today.strftime('%d/%m/%Y')})",
        )
        session.add(tx)

        # Mettre à jour le holding
        h = session.query(CryptoHolding).filter_by(id=holding_id).first()
        if h:
            h.quantity      = round(new_qty, 8)
            h.avg_buy_price = round(new_avg, 2)

        # Marquer le plan exécuté
        p = session.query(CryptoDCA).filter_by(id=plan_id_).first()
        if p:
            p.last_executed = today

    if link_financial:
        link_to_transaction(
            amount=amount_eur,
            tx_type="expense",
            note=f"DCA {name} ({symbol.upper()}) — {today.strftime('%d/%m/%Y')}",
        )

    return {
        "symbol":   symbol,
        "name":     name,
        "qty":      round(qty, 8),
        "price":    round(price, 2),
        "total":    round(amount_eur, 2),
    }


# ── Rapport fiscal FIFO ───────────────────────────────────────────────────────

def compute_fifo_report(year: int) -> dict:
    """
    Calcule les plus/moins-values réalisées sur l'année `year` selon la méthode FIFO.

    Retourne :
    {
      "lots": [
        {
          "symbol": str,
          "name": str,
          "buy_date": date,
          "sell_date": date,
          "qty": float,
          "buy_price": float,   # prix unitaire d'achat
          "sell_price": float,  # prix unitaire de vente
          "buy_total": float,   # qty * buy_price
          "sell_total": float,  # qty * sell_price
          "gain": float,        # sell_total - buy_total
        },
        ...
      ],
      "total_gains": float,
      "total_losses": float,
      "net": float,
    }
    """
    from collections import deque

    with Session() as session:
        holdings = session.query(CryptoHolding).all()
        all_txs  = (
            session.query(CryptoTransaction)
            .order_by(CryptoTransaction.date)
            .all()
        )
        session.expunge_all()

    holding_map = {h.id: h for h in holdings}

    # Regrouper les transactions par holding
    buys_by_holding:  dict[int, deque] = {}
    sells_by_holding: dict[int, list]  = {}

    for tx in all_txs:
        hid = tx.holding_id
        if tx.type == "buy":
            buys_by_holding.setdefault(hid, deque()).append({
                "date":  tx.date.date() if hasattr(tx.date, "date") else tx.date,
                "qty":   tx.quantity,
                "price": tx.price_eur,
            })
        elif tx.type == "sell":
            sell_date = tx.date.date() if hasattr(tx.date, "date") else tx.date
            sells_by_holding.setdefault(hid, []).append({
                "date":  sell_date,
                "qty":   tx.quantity,
                "price": tx.price_eur,
            })

    lots = []

    for hid, sells in sells_by_holding.items():
        holding = holding_map.get(hid)
        if not holding:
            continue

        buy_queue = deque(
            {"date": b["date"], "qty": b["qty"], "price": b["price"]}
            for b in buys_by_holding.get(hid, [])
        )

        for sell in sells:
            # On ne garde que les ventes de l'année demandée
            if sell["date"].year != year:
                # Mais on doit quand même consommer les lots achetés avant
                # pour maintenir l'ordre FIFO correct → traiter silencieusement
                remaining = sell["qty"]
                while remaining > EPSILON and buy_queue:
                    lot = buy_queue[0]
                    matched = min(remaining, lot["qty"])
                    remaining     -= matched
                    lot["qty"]    -= matched
                    if lot["qty"] < EPSILON:
                        buy_queue.popleft()
                continue

            remaining = sell["qty"]
            while remaining > EPSILON and buy_queue:
                lot     = buy_queue[0]
                matched = min(remaining, lot["qty"])

                lots.append({
                    "symbol":     holding.symbol.upper(),
                    "name":       holding.name,
                    "buy_date":   lot["date"],
                    "sell_date":  sell["date"],
                    "qty":        round(matched, 8),
                    "buy_price":  round(lot["price"], 4),
                    "sell_price": round(sell["price"], 4),
                    "buy_total":  round(matched * lot["price"], 2),
                    "sell_total": round(matched * sell["price"], 2),
                    "gain":       round(matched * (sell["price"] - lot["price"]), 2),
                })

                remaining  -= matched
                lot["qty"] -= matched
                if lot["qty"] < EPSILON:
                    buy_queue.popleft()

            # Vente sans lot d'achat correspondant (LIFO/DCA antérieur ignoré)
            if remaining > EPSILON:
                lots.append({
                    "symbol":     holding.symbol.upper(),
                    "name":       holding.name,
                    "buy_date":   None,
                    "sell_date":  sell["date"],
                    "qty":        round(remaining, 8),
                    "buy_price":  0.0,
                    "sell_price": round(sell["price"], 4),
                    "buy_total":  0.0,
                    "sell_total": round(remaining * sell["price"], 2),
                    "gain":       round(remaining * sell["price"], 2),
                })

    lots.sort(key=lambda x: x["sell_date"] or _date.min)

    total_gains  = sum(l["gain"] for l in lots if l["gain"] > 0)
    total_losses = sum(l["gain"] for l in lots if l["gain"] < 0)
    net          = total_gains + total_losses

    return {
        "lots":         lots,
        "total_gains":  round(total_gains,  2),
        "total_losses": round(total_losses, 2),
        "net":          round(net,          2),
    }


EPSILON = 1e-9  # seuil de comparaison pour les quantités flottantes
