"""
Service Crypto-monnaie — Foyio
Gère le portefeuille crypto, les transactions et les alertes.
Prix via CoinGecko API (gratuit, sans clé).
"""
import logging
import time
import urllib.request
import json
from datetime import datetime

from db import Session, safe_session
from models import CryptoHolding, CryptoTransaction, CryptoAlert
import account_state

logger = logging.getLogger(__name__)

# ── Cache prix (évite les appels répétés) ────────────────────────────────────
_price_cache: dict = {}          # {coingecko_id: {"price": float, "change_24h": float, "ts": float}}
_CACHE_TTL = 60                  # secondes

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


# ── Appels API CoinGecko ─────────────────────────────────────────────────────

def _get(url: str, timeout: int = 8) -> dict | list | None:
    """GET JSON depuis CoinGecko. Retourne None en cas d'erreur."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Foyio/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning(f"CoinGecko API error: {e}")
        return None


def get_prices(coingecko_ids: list[str]) -> dict:
    """
    Retourne {id: {"price": float, "change_24h": float}} pour chaque id.
    Utilise le cache TTL=60s.
    """
    if not coingecko_ids:
        return {}

    now = time.time()
    to_fetch = [i for i in coingecko_ids
                if i not in _price_cache or now - _price_cache[i]["ts"] > _CACHE_TTL]

    if to_fetch:
        ids_param = ",".join(to_fetch)
        url = (f"{COINGECKO_BASE}/simple/price"
               f"?ids={ids_param}&vs_currencies=eur"
               f"&include_24hr_change=true&include_market_cap=true")
        data = _get(url)
        if data:
            for cid, info in data.items():
                _price_cache[cid] = {
                    "price":      info.get("eur", 0),
                    "change_24h": info.get("eur_24h_change", 0),
                    "market_cap": info.get("eur_market_cap", 0),
                    "ts":         now,
                }

    return {
        cid: {k: v for k, v in _price_cache[cid].items() if k != "ts"}
        for cid in coingecko_ids
        if cid in _price_cache
    }


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
    """
    url = (f"{COINGECKO_BASE}/coins/{coingecko_id}/market_chart"
           f"?vs_currency=eur&days={days}&interval=daily")
    data = _get(url)
    if not data:
        return []
    return [(int(p[0]), float(p[1])) for p in data.get("prices", [])]


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
            hit = (alert.alert_type == "above" and price >= alert.target_price) or \
                  (alert.alert_type == "below" and price <= alert.target_price)
            if hit:
                alert.triggered = True
                triggered.append({
                    "name":         holding.name,
                    "symbol":       holding.symbol,
                    "alert_type":   alert.alert_type,
                    "target_price": alert.target_price,
                    "current_price": price,
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
