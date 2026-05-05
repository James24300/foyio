"""
Threads et widget bulles pour la vue crypto — extraits de crypto_view.py.
"""
import logging
import math
import urllib.request as _urllib_req
import time as _time

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QBrush

from services.crypto_service import get_prices, get_top_coins, get_price_history

logger = logging.getLogger(__name__)
_pixmap_cache: dict = {}  # {coingecko_id: QPixmap} — partagé entre instances


# ── Widget bulles (style CryptoBubbles) ──────────────────────────────────────
class _BubbleWidget(QWidget):
    """Bulles animées : taille ∝ valeur €, couleur ∝ P&L %, physique simple."""

    _COLORS = [
        (10,  "#15803d"), (5,  "#16a34a"), (2,  "#22c55e"), (0,  "#4ade80"),
        (-2, "#f87171"), (-5, "#ef4444"), (-10, "#dc2626"), (None, "#b91c1c"),
    ]

    def __init__(self, parent=None):
        import random as _rnd
        super().__init__(parent)
        self._items    = []   # [(symbol, pnl_pct, value_eur, coingecko_id)]
        self._radii    = []   # rayon de chaque bulle
        self._cur_pos  = []   # [[cx, cy], ...] positions animées courantes
        self._vel      = []   # [[vx, vy], ...] vitesses
        self._rnd      = _rnd
        self.setMinimumHeight(220)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(16)   # ≈ 60 fps

    @staticmethod
    def _pnl_color(pct):
        for threshold, color in _BubbleWidget._COLORS:
            if threshold is None or pct >= threshold:
                return QColor(color)
        return QColor("#b91c1c")

    def set_data(self, items):
        self._items = items
        self._recompute(reset=True)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute(reset=False)
        self.update()

    def _recompute(self, reset=False):
        W, H = self.width(), self.height()
        if not self._items or W < 20 or H < 20:
            self._radii = []; self._cur_pos = []; self._vel = []
            return

        values = [max(it[2], 0.01) for it in self._items]
        max_v  = max(values)
        base_r = max(22, min(W, H) * 0.16)
        self._radii = [max(20, int(base_r * math.sqrt(v / max_v))) for v in values]

        # Positions initiales en grille centrée
        init = self._packed_positions(W, H, self._radii)
        n = len(self._items)

        if reset or len(self._cur_pos) != n:
            self._cur_pos = [[p[0], p[1]] for p in init]
            self._vel = [
                [self._rnd.uniform(-0.8, 0.8), self._rnd.uniform(-0.8, 0.8)]
                for _ in range(n)
            ]
        else:
            # Juste recadrer dans les nouvelles dimensions
            for i in range(n):
                r = self._radii[i]
                self._cur_pos[i][0] = max(float(r), min(float(W - r), self._cur_pos[i][0]))
                self._cur_pos[i][1] = max(float(r), min(float(H - r), self._cur_pos[i][1]))

    @staticmethod
    def _packed_positions(W, H, radii):
        order  = sorted(range(len(radii)), key=lambda i: -radii[i])
        margin = 12
        rows, cur, cw = [], [], margin
        for idx in order:
            d = radii[idx] * 2 + margin
            if cur and cw + d > W - margin:
                rows.append(cur[:]);  cur, cw = [idx], margin + d
            else:
                cur.append(idx);      cw += d
        if cur:
            rows.append(cur)
        rh_list = [max(radii[i] for i in row) * 2 for row in rows]
        total_h = sum(rh_list) + margin * (len(rows) + 1)
        y = max(margin, (H - total_h) // 2 + margin)
        pos = [None] * len(radii)
        for ri, row in enumerate(rows):
            rh  = rh_list[ri]
            row_w = sum(radii[i] * 2 + margin for i in row) + margin
            x = max(margin, (W - row_w) // 2 + margin)
            for idx in row:
                r = radii[idx]
                pos[idx] = (x + r, y + rh // 2)
                x += r * 2 + margin
            y += rh + margin
        return pos

    def _animate(self):
        W, H = self.width(), self.height()
        n = len(self._cur_pos)
        if n == 0:
            return
        pos = self._cur_pos
        vel = self._vel
        radii = self._radii

        for i in range(n):
            r  = radii[i]
            x, y   = pos[i]
            vx, vy = vel[i]

            # Répulsion entre bulles
            for j in range(n):
                if i == j:
                    continue
                ox, oy = pos[j]
                dx, dy = x - ox, y - oy
                dist   = math.sqrt(dx * dx + dy * dy) or 0.001
                gap    = r + radii[j] + 6
                if dist < gap:
                    f  = (gap - dist) / gap * 0.45
                    vx += dx / dist * f
                    vy += dy / dist * f

            # Rebond mural souple
            mg = 4
            if x - r < mg:   vx += (mg - (x - r)) * 0.35
            if x + r > W - mg: vx -= (x + r - (W - mg)) * 0.35
            if y - r < mg:   vy += (mg - (y - r)) * 0.35
            if y + r > H - mg: vy -= (y + r - (H - mg)) * 0.35

            # Légère attraction vers le centre
            vx += (W / 2 - x) * 0.0008
            vy += (H / 2 - y) * 0.0008

            # Impulsion aléatoire occasionnelle (~1% de chance par frame)
            if self._rnd.random() < 0.01:
                vx += self._rnd.uniform(-0.4, 0.4)
                vy += self._rnd.uniform(-0.4, 0.4)

            # Pas d'amortissement — vitesse constante
            # Vitesse min/max pour mouvement permanent
            MIN_SPD = 0.3
            MAX_SPD = 1.4
            spd = math.sqrt(vx * vx + vy * vy) or 0.001
            # Variation aléatoire de la vitesse à chaque frame
            target_spd = self._rnd.uniform(MIN_SPD, MAX_SPD)
            if spd > target_spd * 1.1:
                vx = vx / spd * (spd * 0.98)
                vy = vy / spd * (spd * 0.98)
            elif spd < MIN_SPD:
                vx = vx / spd * MIN_SPD
                vy = vy / spd * MIN_SPD
            pos[i] = [x + vx, y + vy]
            vel[i] = [vx, vy]

        self.update()

    def paintEvent(self, event):
        if not self._items or not self._cur_pos:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#1e2023"))

        for i, (symbol, pnl_pct, _val, cg_id) in enumerate(self._items):
            if i >= len(self._cur_pos):
                continue
            cx, cy = self._cur_pos[i]
            r  = self._radii[i]
            color = self._pnl_color(pnl_pct)

            # Cercle principal
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), float(r), float(r))

            # Reflet
            glow = QColor(color.red(), color.green(), color.blue(), 55)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(cx, cy - r * 0.18), r * 0.55, r * 0.38)

            # Logo
            px = _pixmap_cache.get(cg_id)
            if px and r >= 26:
                logo_sz = min(r - 6, 22)
                sc = px.scaled(logo_sz, logo_sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(int(cx - sc.width() / 2), int(cy - r * 0.38 - sc.height() / 2), sc)

            # Symbole
            p.setPen(QColor("#ffffff"))
            sym_fs = max(7, min(11, r // 3))
            p.setFont(QFont("Segoe UI", sym_fs, QFont.Bold))
            y_sym = cy - r * 0.08 if (px and r >= 26) else cy - r * 0.25
            p.drawText(QRectF(cx - r, y_sym, r * 2, r * 0.55), Qt.AlignHCenter | Qt.AlignVCenter, symbol)

            # P&L %
            pnl_fs = max(6, min(10, r // 4))
            p.setFont(QFont("Segoe UI", pnl_fs))
            pnl_str = f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%"
            y_pnl = cy + r * 0.28 if (px and r >= 26) else cy + r * 0.22
            p.drawText(QRectF(cx - r, y_pnl, r * 2, r * 0.45), Qt.AlignHCenter | Qt.AlignVCenter, pnl_str)

        p.end()

# ── Thread de recherche de cryptos ───────────────────────────────────────────
class _SearchThread(QThread):
    done = Signal(list)

    def __init__(self, query: str):
        super().__init__()
        self._query = query

    def run(self):
        try:
            from services.crypto_service import search_coins
            results = search_coins(self._query)
            self.done.emit(results)
        except Exception:
            logger.debug("Recherche crypto échouée", exc_info=True)
            self.done.emit([])


# ── Thread de rafraîchissement des prix ──────────────────────────────────────
class _PriceFetcher(QThread):
    done = Signal(dict)

    def __init__(self, ids):
        super().__init__()
        self._ids = ids

    def run(self):
        try:
            prices = get_prices(self._ids)
            self.done.emit(prices)
        except Exception:
            logger.debug("Récupération des prix échouée", exc_info=True)
            self.done.emit({})



class _CompFetcher(QThread):
    """Charge l'historique de BTC, ETH et du portefeuille pour la comparaison."""
    done = Signal(dict)  # {"btc": [...], "eth": [...], "portfolio": [(ts, value)]}

    def __init__(self, holdings, days: int):
        super().__init__()
        self._holdings = holdings
        self._days = days

    def run(self):
        result = {}
        try:
            result["btc"] = get_price_history("bitcoin", self._days)
            result["eth"] = get_price_history("ethereum", self._days)
            daily: dict[int, float] = {}
            for h in self._holdings:
                hist = get_price_history(h.coingecko_id, self._days)
                for ts_ms, price in hist:
                    day = (ts_ms // 86_400_000) * 86_400_000
                    daily[day] = daily.get(day, 0.0) + h.quantity * price
            result["portfolio"] = sorted(daily.items())
        except Exception:
            logger.debug("Erreur calcul historique portefeuille", exc_info=True)
        self.done.emit(result)


class _TopFetcher(QThread):
    done = Signal(list)

    def run(self):
        try:
            self.done.emit(get_top_coins(50))
        except Exception:
            logger.debug("Récupération top cryptos échouée", exc_info=True)
            self.done.emit([])


class _LogoFetcher(QThread):
    """Télécharge les logos crypto depuis CoinGecko CDN en arrière-plan."""
    logo_ready = Signal(str, bytes)  # (coingecko_id, raw_bytes)

    def __init__(self, id_url_pairs: list):
        super().__init__()
        self._pairs = id_url_pairs

    def run(self):
        for cg_id, url in self._pairs:
            if not url or cg_id in _pixmap_cache:
                continue
            try:
                req = _urllib_req.Request(url, headers={"User-Agent": "Foyio/1.0"})
                with _urllib_req.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                self.logo_ready.emit(cg_id, data)
                _time.sleep(0.05)
            except Exception:
                logger.debug("Erreur téléchargement logo crypto", exc_info=True)
