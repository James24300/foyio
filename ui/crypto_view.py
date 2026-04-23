import logging
"""
Vue Crypto-monnaie — Foyio
4 onglets : Portefeuille | Transactions | Simulateur | Alertes
Prix en temps réel via CoinGecko API (gratuit, sans clé).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox,
    QSpinBox, QMessageBox, QFrame, QScrollArea, QSizePolicy,
    QProgressBar, QCheckBox
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QPieSeries, QValueAxis, QAreaSeries,
    QDateTimeAxis
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QDateTime
from PySide6.QtGui import QColor, QPainter, QFont, QPen

from utils.formatters import format_money
from utils.icons import get_icon
from ui.toast import Toast
from services.crypto_service import (
    get_holdings, add_holding, sell_holding, delete_holding, update_holding,
    get_transactions, get_prices, get_portfolio_summary,
    add_alert, get_alerts, delete_alert, check_alerts,
    simulate_dca, simulate_what_if, get_top_coins, search_coins,
    get_price_history, link_to_transaction,
    get_dca_plans, add_dca_plan, delete_dca_plan, toggle_dca_plan,
    get_due_dca_plans, execute_dca, compute_fifo_report,
    get_coin_image_urls, update_dca_plan,
    delete_crypto_transaction, update_crypto_transaction,
)
from services.watchlist_service import (
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    is_in_watchlist, get_watchlist_ids,
)


import urllib.request as _urllib_req
import time as _time
logger = logging.getLogger(__name__)
_pixmap_cache: dict = {}  # {coingecko_id: QPixmap} — partagé entre instances


# ── Label vertical (texte pivoté 90°) ────────────────────────────────────────
class _VertLabel(QWidget):
    """Widget affichant un texte pivoté -90° (lecture bas → haut)."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self.setSizePolicy(
            QSizePolicy.Fixed, QSizePolicy.Expanding
        )

    def setText(self, text):
        self._text = text
        self.update()

    def text(self):
        return self._text

    def sizeHint(self):
        from PySide6.QtCore import QSize
        fm = self.fontMetrics()
        return QSize(fm.height() + 8, fm.horizontalAdvance(self._text) + 8)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#c8cdd4"))
        p.setFont(self.font())
        p.translate(0, self.height())
        p.rotate(-90)
        p.drawText(0, 0, self.height(), self.width(), Qt.AlignCenter, self._text)
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
            self.done.emit({})


class _EvoFetcher(QThread):
    """Charge l'historique de prix de tous les holdings en arrière-plan."""
    done = Signal(dict)   # {coingecko_id: [(ts_ms, price)]}

    def __init__(self, holdings, days: int):
        super().__init__()
        self._holdings = holdings
        self._days = days

    def run(self):
        result = {}
        try:
            for h in self._holdings:
                hist = get_price_history(h.coingecko_id, self._days)
                if hist:
                    result[h.coingecko_id] = (h.quantity, hist)
        except Exception:
            logger.debug("Exception silencieuse", exc_info=True)
        self.done.emit(result)


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
            logger.debug("Exception silencieuse", exc_info=True)
        self.done.emit(result)


class _TopFetcher(QThread):
    done = Signal(list)

    def run(self):
        try:
            self.done.emit(get_top_coins(50))
        except Exception:
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
                logger.debug("Exception silencieuse", exc_info=True)
class CryptoView(QWidget):

    def __init__(self):
        super().__init__()
        self._prices: dict = {}
        self._holdings: list = []
        self._fetcher = None
        self._threads: list = []   # garde les threads en vie jusqu'à leur fin

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Barre de résumé ──
        self._summary_bar = self._build_summary_bar()
        layout.addWidget(self._summary_bar)

        # ── Onglets ──
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border:1px solid #2e3238; border-radius:10px; background:#1e2023; }
            QTabBar::tab {
                background:#26292e; color:#7a8494; border:none;
                padding:8px 20px; border-radius:8px 8px 0 0; font-size:12px;
            }
            QTabBar::tab:selected { background:#2e3238; color:#c8cdd4; font-weight:700; }
            QTabBar::tab:hover { background:#2a2d32; color:#a0a8b4; }
        """)
        self._tabs.addTab(self._build_portfolio_tab(),    "  Portefeuille")
        self._tabs.addTab(self._build_transactions_tab(), "  Transactions")
        self._tabs.addTab(self._build_top_tab(),          "  Top Cryptos")
        self._tabs.addTab(self._build_watchlist_tab(),    "  Watchlist")
        self._tabs.addTab(self._build_simulator_tab(),    "  Simulateur")
        self._tabs.addTab(self._build_alerts_tab(),       "  Alertes")
        self._tabs.addTab(self._build_dca_tab(),          "  DCA")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs, 1)

        # Rafraîchissement auto toutes les 3 min (évite les 429 CoinGecko)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_prices)
        self._refresh_timer.start(360_000)  # 6 min — aligné sur le TTL cache (5 min)

        self.load()

    # ── Barre de résumé ──────────────────────────────────────────────────────
    def _build_summary_bar(self):
        bar = QWidget()
        bar.setStyleSheet("background:#26292e; border-radius:12px; border:1px solid #3a3f47;")
        bar.setFixedHeight(64)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(20, 0, 20, 0)
        hl.setSpacing(40)

        def _cell(title):
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("font-size:10px; color:#5a6472; font-weight:600; letter-spacing:1px; background:transparent; border:none;")
            v = QLabel("—")
            v.setStyleSheet("font-size:15px; font-weight:700; color:#c8cdd4; background:transparent; border:none;")
            col.addWidget(t)
            col.addWidget(v)
            return col, v

        c1, self._lbl_total   = _cell("VALEUR TOTALE")
        c2, self._lbl_invest  = _cell("INVESTI")
        c3, self._lbl_pnl     = _cell("GAIN / PERTE")
        c4, self._lbl_chg24   = _cell("VARIATION 24H")

        for c in [c1, c2, c3, c4]:
            hl.addLayout(c)
        hl.addStretch()

        self._btn_refresh = QPushButton("  Actualiser")
        self._btn_refresh.setFixedHeight(34)
        self._btn_refresh.setStyleSheet("""
            QPushButton { background:#2e3238; border:1px solid #3d4248; border-radius:8px;
                          color:#7a8494; font-size:12px; padding:0 12px; }
            QPushButton:hover { background:#3a3f47; color:#c8cdd4; }
        """)
        self._btn_refresh.clicked.connect(self._fetch_prices)
        hl.addWidget(self._btn_refresh)
        return bar

    # ── Onglet Portefeuille ───────────────────────────────────────────────────
    def _build_portfolio_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        # Boutons
        btn_row = QHBoxLayout()
        _bs = "border:none; border-radius:8px; font-weight:700; padding:0 16px; text-align:center;"
        btn_add = QPushButton("Ajouter une crypto")
        btn_add.setMinimumHeight(36)
        btn_add.setStyleSheet(f"background:#22c55e; color:#000; {_bs}")
        btn_add.clicked.connect(self._dialog_add)

        self._btn_sell = QPushButton("Vendre")
        self._btn_sell.setMinimumHeight(36)
        self._btn_sell.setEnabled(False)
        self._btn_sell.setStyleSheet(f"background:#ef4444; color:#fff; {_bs}")
        self._btn_sell.clicked.connect(self._dialog_sell)

        self._btn_edit = QPushButton("Modifier")
        self._btn_edit.setMinimumHeight(36)
        self._btn_edit.setEnabled(False)
        self._btn_edit.setStyleSheet(f"background:#3b82f6; color:#fff; {_bs}")
        self._btn_edit.clicked.connect(self._dialog_edit)

        self._btn_del = QPushButton("Supprimer")
        self._btn_del.setMinimumHeight(36)
        self._btn_del.setEnabled(False)
        self._btn_del.setStyleSheet("background:#2e2020; color:#e89090; border:1px solid #503030; border-radius:8px; padding:0 16px; text-align:center;")
        self._btn_del.clicked.connect(self._delete_holding)

        btn_row.addWidget(btn_add)
        btn_row.addWidget(self._btn_sell)
        btn_row.addWidget(self._btn_edit)
        btn_row.addWidget(self._btn_del)
        btn_row.addStretch()
        _btn_fifo = QPushButton("Rapport fiscal")
        _btn_fifo.setMinimumHeight(36)
        _btn_fifo.setStyleSheet("background:#26292e; color:#c8cdd4; border:1px solid #3a3f47; border-radius:8px; padding:0 14px; text-align:center;")
        _btn_fifo.clicked.connect(self._dialog_fifo_report)
        btn_row.addWidget(_btn_fifo)
        _btn_export_p = QPushButton("Exporter CSV")
        _btn_export_p.setMinimumHeight(36)
        _btn_export_p.setStyleSheet("background:#26292e; color:#c8cdd4; border:1px solid #3a3f47; border-radius:8px; padding:0 14px; text-align:center;")
        _btn_export_p.clicked.connect(self._export_portfolio_csv)
        btn_row.addWidget(_btn_export_p)
        vl.addLayout(btn_row)

        # Tableau
        self._portfolio_table = QTableWidget(0, 9)
        self._portfolio_table.setHorizontalHeaderLabels([
            "", "Crypto", "Quantité", "Prix achat moy.", "Prix actuel €",
            "Prix actuel $", "Valeur", "P&L €", "P&L %"
        ])
        self._portfolio_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._portfolio_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._portfolio_table.setShowGrid(False)
        self._portfolio_table.verticalHeader().setVisible(False)
        self._portfolio_table.verticalHeader().setDefaultSectionSize(46)
        hdr = self._portfolio_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(0, 36)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(2, 120)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(3, 130)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(4, 130)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(5, 130)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(6, 120)
        hdr.setSectionResizeMode(7, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(7, 110)
        hdr.setSectionResizeMode(8, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(8, 90)
        self._portfolio_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        self._portfolio_table.itemSelectionChanged.connect(self._on_portfolio_selection)
        self._portfolio_table.cellDoubleClicked.connect(self._on_portfolio_double_click)
        self._portfolio_table.setMinimumHeight(120)
        self._portfolio_table.setMaximumHeight(320)
        vl.addWidget(self._portfolio_table)

        # Graphique camembert
        self._pie_chart_view = QChartView()
        self._pie_chart_view.setRenderHint(QPainter.Antialiasing)
        self._pie_chart_view.setFixedHeight(240)
        self._pie_chart_view.setStyleSheet("border:none;")
        self._pie_chart_view.setBackgroundBrush(QColor("#1e2023"))
        vl.addWidget(self._pie_chart_view)

        # ── Évolution de la valeur totale ──
        evo_header = QHBoxLayout()
        evo_lbl = QLabel("Évolution du portefeuille")
        evo_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#7a8494;")
        evo_header.addWidget(evo_lbl)
        evo_header.addStretch()

        self._evo_period = 30
        self._evo_btns = {}
        for label, days in [("7J", 7), ("30J", 30), ("90J", 90), ("1AN", 365)]:
            btn = QPushButton(label)
            btn.setFixedSize(52, 26)
            btn.setCheckable(True)
            btn.setChecked(days == 30)
            btn.setStyleSheet("""
                QPushButton { background:#26292e; color:#7a8494; border:1px solid #3a3f47;
                    border-radius:6px; font-size:11px; font-weight:600; }
                QPushButton:hover { color:#c8cdd4; }
                QPushButton:checked { background:#3b82f6; color:#fff; border:none; }
            """)
            btn.clicked.connect(lambda checked, d=days: self._set_evo_period(d))
            evo_header.addWidget(btn)
            self._evo_btns[days] = btn

        vl.addLayout(evo_header)

        # Ligne : label € vertical + graphique (ou message chargement)
        evo_row = QHBoxLayout()
        evo_row.setSpacing(2)
        evo_row.setContentsMargins(0, 0, 0, 0)

        self._evo_unit_lbl = _VertLabel("\u20ac")
        self._evo_unit_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._evo_unit_lbl.setStyleSheet("color:#c8cdd4; background:transparent;")
        self._evo_unit_lbl.setFixedWidth(22)
        evo_row.addWidget(self._evo_unit_lbl)

        evo_right = QVBoxLayout()
        evo_right.setSpacing(0)
        evo_right.setContentsMargins(0, 0, 0, 0)

        self._evo_loading = QLabel("Chargement du graphique…")
        self._evo_loading.setAlignment(Qt.AlignCenter)
        self._evo_loading.setStyleSheet("color:#5a6472; font-size:12px; background:transparent;")
        self._evo_loading.setFixedHeight(180)
        self._evo_loading.hide()
        evo_right.addWidget(self._evo_loading)

        self._evo_chart_view = QChartView()
        self._evo_chart_view.setRenderHint(QPainter.Antialiasing)
        self._evo_chart_view.setFixedHeight(180)
        self._evo_chart_view.setStyleSheet("border:none;")
        self._evo_chart_view.setBackgroundBrush(QColor("#1e2023"))
        evo_right.addWidget(self._evo_chart_view)

        evo_row.addLayout(evo_right)
        vl.addLayout(evo_row)
        return w

    # ── Onglet Transactions ───────────────────────────────────────────────────
    def _build_transactions_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        self._tx_table = QTableWidget(0, 6)
        self._tx_table.setHorizontalHeaderLabels([
            "Date", "Crypto", "Type", "Quantité", "Prix unitaire", "Total €"
        ])
        self._tx_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tx_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._tx_table.setShowGrid(False)
        self._tx_table.verticalHeader().setVisible(False)
        self._tx_table.verticalHeader().setDefaultSectionSize(38)
        self._tx_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tx_table.customContextMenuRequested.connect(self._ctx_crypto_tx)
        self._tx_table.itemDoubleClicked.connect(
            lambda item: self._edit_crypto_tx(
                self._tx_table.item(item.row(), 0).data(Qt.UserRole)
                if self._tx_table.item(item.row(), 0) else None
            )
        )
        hdr = self._tx_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed);  self._tx_table.setColumnWidth(0, 130)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed);  self._tx_table.setColumnWidth(2, 80)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed);  self._tx_table.setColumnWidth(3, 120)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed);  self._tx_table.setColumnWidth(4, 130)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._tx_table.setColumnWidth(5, 120)
        self._tx_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._tx_table, 1)

        tx_btn_row = QHBoxLayout()
        tx_btn_row.addStretch()
        _btn_export_t = QPushButton("Exporter CSV")
        _btn_export_t.setMinimumHeight(36)
        _btn_export_t.setStyleSheet("background:#26292e; color:#c8cdd4; border:1px solid #3a3f47; border-radius:8px; padding:0 14px; text-align:center;")
        _btn_export_t.clicked.connect(self._export_transactions_csv)
        tx_btn_row.addWidget(_btn_export_t)
        vl.addLayout(tx_btn_row)
        return w

    # ── Onglet Simulateur ─────────────────────────────────────────────────────
    def _build_simulator_tab(self):
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(20)

        def _card(title):
            card = QWidget()
            card.setStyleSheet("background:#26292e; border-radius:12px; border:1px solid #3a3f47;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(10)
            t = QLabel(title)
            t.setStyleSheet("font-size:13px; font-weight:700; color:#c8cdd4; background:transparent; border:none;")
            cl.addWidget(t)
            return card, cl

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("font-size:12px; color:#7a8494; background:transparent; border:none;")
            return l

        # ── DCA ──
        card_dca, cl_dca = _card("  Simulateur DCA — Investissement régulier")
        form_dca = QHBoxLayout()
        self._dca_monthly = QDoubleSpinBox(); self._dca_monthly.setRange(1, 99999); self._dca_monthly.setValue(100); self._dca_monthly.setSuffix(" €/mois"); self._dca_monthly.setMinimumHeight(34)
        self._dca_months  = QSpinBox();       self._dca_months.setRange(1, 600);    self._dca_months.setValue(60);  self._dca_months.setSuffix(" mois");    self._dca_months.setMinimumHeight(34)
        self._dca_rate    = QDoubleSpinBox(); self._dca_rate.setRange(0, 1000);     self._dca_rate.setValue(15);   self._dca_rate.setSuffix(" % / an");     self._dca_rate.setDecimals(1); self._dca_rate.setMinimumHeight(34)
        for lbl_txt, spin in [("Mensualité :", self._dca_monthly), ("Durée :", self._dca_months), ("Croissance annuelle :", self._dca_rate)]:
            col = QVBoxLayout(); col.addWidget(_lbl(lbl_txt)); col.addWidget(spin); form_dca.addLayout(col)
        cl_dca.addLayout(form_dca)
        btn_dca = QPushButton("  Simuler DCA"); btn_dca.setMinimumHeight(36); btn_dca.clicked.connect(self._run_dca)
        cl_dca.addWidget(btn_dca)
        self._dca_result = QLabel(); self._dca_result.setWordWrap(True); self._dca_result.setVisible(False)
        self._dca_result.setStyleSheet("font-size:12px; color:#22c55e; background:#1a2a1a; border-radius:8px; padding:10px;")
        cl_dca.addWidget(self._dca_result)
        self._dca_chart = QChartView()
        self._dca_chart.setRenderHint(QPainter.Antialiasing)
        self._dca_chart.setMinimumHeight(200)
        self._dca_chart.setStyleSheet("border:none;")
        self._dca_chart.setBackgroundBrush(QColor("#26292e"))
        self._dca_chart.setVisible(False)
        cl_dca.addWidget(self._dca_chart)
        vl.addWidget(card_dca)

        # ── What-if ──
        card_wi, cl_wi = _card("  Et si j'avais investi… ?")
        form_wi = QHBoxLayout()
        self._wi_amount = QDoubleSpinBox(); self._wi_amount.setRange(1, 9999999); self._wi_amount.setValue(1000); self._wi_amount.setSuffix(" €"); self._wi_amount.setMinimumHeight(34)
        self._wi_months = QSpinBox();       self._wi_months.setRange(1, 120);     self._wi_months.setValue(12);   self._wi_months.setSuffix(" mois ago"); self._wi_months.setMinimumHeight(34)
        self._wi_coin   = QComboBox();      self._wi_coin.setMinimumHeight(34);   self._wi_coin.setMinimumWidth(160)
        self._wi_coin.addItem("Bitcoin",  "bitcoin")
        self._wi_coin.addItem("Ethereum", "ethereum")
        self._wi_coin.addItem("Solana",   "solana")
        self._wi_coin.addItem("BNB",      "binancecoin")
        self._wi_coin.addItem("XRP",      "ripple")
        for lbl_txt, w2 in [("Montant :", self._wi_amount), ("Il y a :", self._wi_months), ("Crypto :", self._wi_coin)]:
            col = QVBoxLayout(); col.addWidget(_lbl(lbl_txt)); col.addWidget(w2); form_wi.addLayout(col)
        cl_wi.addLayout(form_wi)
        btn_wi = QPushButton("  Calculer"); btn_wi.setMinimumHeight(36); btn_wi.clicked.connect(self._run_what_if)
        cl_wi.addWidget(btn_wi)
        self._wi_result = QLabel(); self._wi_result.setWordWrap(True); self._wi_result.setVisible(False)
        self._wi_result.setStyleSheet("font-size:13px; font-weight:600; color:#c8cdd4; background:#292d32; border-radius:8px; padding:12px;")
        cl_wi.addWidget(self._wi_result)
        self._wi_chart = QChartView()
        self._wi_chart.setRenderHint(QPainter.Antialiasing)
        self._wi_chart.setMinimumHeight(200)
        self._wi_chart.setStyleSheet("border:none;")
        self._wi_chart.setBackgroundBrush(QColor("#26292e"))
        self._wi_chart.setVisible(False)
        cl_wi.addWidget(self._wi_chart)
        vl.addWidget(card_wi)
        # ── Carte Comparaison ──
        card_cmp, cl_cmp = _card("Comparaison — Portfolio vs Bitcoin vs Ethereum")

        cmp_bar = QHBoxLayout()
        cmp_bar.addStretch()
        self._cmp_period = 30
        self._cmp_btns: dict[int, QPushButton] = {}
        for label, days in [("7J", 7), ("30J", 30), ("90J", 90), ("1AN", 365)]:
            b = QPushButton(label)
            b.setFixedSize(52, 26)
            b.setCheckable(True)
            b.setChecked(days == 30)
            b.setStyleSheet("""
                QPushButton { background:#1e2023; color:#7a8494; border:1px solid #3a3f47;
                    border-radius:6px; font-size:11px; font-weight:600; }
                QPushButton:checked { background:#3b82f6; color:#fff; border:none; }
                QPushButton:hover { color:#c8cdd4; }
            """)
            b.clicked.connect(lambda _, d=days: self._run_comparison(d))
            cmp_bar.addWidget(b)
            self._cmp_btns[days] = b

        self._btn_run_cmp = QPushButton("Comparer")
        self._btn_run_cmp.setFixedHeight(26)
        self._btn_run_cmp.setStyleSheet(
            "background:#6366f1; color:#fff; border:none; border-radius:6px;"
            "font-size:11px; font-weight:700; padding:0 12px; margin-left:6px;"
        )
        self._btn_run_cmp.clicked.connect(lambda: self._run_comparison(self._cmp_period))
        btn_run_cmp = self._btn_run_cmp
        cmp_bar.addWidget(btn_run_cmp)
        cl_cmp.addLayout(cmp_bar)

        # Légende
        legend_row = QHBoxLayout()
        for color, label in [("#3b82f6", "● Portfolio"), ("#f7931a", "● Bitcoin"), ("#627eea", "● Ethereum")]:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{color}; font-size:11px; background:transparent; border:none;")
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        cl_cmp.addLayout(legend_row)

        self._cmp_chart = QChartView()
        self._cmp_chart.setRenderHint(QPainter.Antialiasing)
        self._cmp_chart.setFixedHeight(260)
        self._cmp_chart.setStyleSheet("border:none;")
        self._cmp_chart.setBackgroundBrush(QColor("#26292e"))
        self._cmp_chart.setVisible(False)
        cl_cmp.addWidget(self._cmp_chart)

        self._cmp_status = QLabel("Sélectionnez une période et cliquez sur Comparer.")
        self._cmp_status.setStyleSheet("color:#7a8494; font-size:11px; background:transparent; border:none;")
        cl_cmp.addWidget(self._cmp_status)

        vl.addWidget(card_cmp)
        vl.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(w); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        return w

    # ── Onglet Alertes ────────────────────────────────────────────────────────
    def _build_alerts_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        # Formulaire ajout alerte
        form_row = QHBoxLayout()
        form_row.setSpacing(8)

        self._alert_holding_combo = QComboBox()
        self._alert_holding_combo.setMinimumHeight(34)
        self._alert_holding_combo.setMinimumWidth(150)

        self._alert_type_combo = QComboBox()
        self._alert_type_combo.addItem("Prix au-dessus de", "above")
        self._alert_type_combo.addItem("Prix en-dessous de", "below")
        self._alert_type_combo.addItem("Hausse 24h ≥ +X%", "pct_up")
        self._alert_type_combo.addItem("Baisse 24h ≥ -X%", "pct_down")
        self._alert_type_combo.setMinimumHeight(34)
        self._alert_type_combo.setMinimumWidth(160)
        self._alert_type_combo.currentIndexChanged.connect(self._on_alert_type_changed)

        self._alert_price = QDoubleSpinBox()
        self._alert_price.setRange(0.000001, 9_999_999)
        self._alert_price.setDecimals(2)
        self._alert_price.setSuffix(" €")
        self._alert_price.setMinimumHeight(34)
        self._alert_price.setMinimumWidth(130)

        btn_add_alert = QPushButton("Ajouter l'alerte")
        btn_add_alert.setMinimumHeight(34)
        btn_add_alert.setStyleSheet(
            "background:#f59e0b; color:#000; border:none; border-radius:8px;"
            "font-weight:700; padding:0 12px; text-align:center;"
        )
        btn_add_alert.clicked.connect(self._add_alert)

        self._alert_price_lbl = QLabel("Prix cible :")
        self._alert_price_lbl.setStyleSheet("font-size:11px; color:#7a8494;")

        for lbl_txt, widget in [("Crypto :", self._alert_holding_combo),
                                 ("Condition :", self._alert_type_combo)]:
            col = QVBoxLayout()
            lbl = QLabel(lbl_txt)
            lbl.setStyleSheet("font-size:11px; color:#7a8494;")
            col.addWidget(lbl)
            col.addWidget(widget)
            form_row.addLayout(col)

        price_col = QVBoxLayout()
        price_col.addWidget(self._alert_price_lbl)
        price_col.addWidget(self._alert_price)
        form_row.addLayout(price_col)

        form_row.addWidget(btn_add_alert)
        form_row.addStretch()
        vl.addLayout(form_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
        vl.addWidget(sep)

        # Tableau alertes
        self._alerts_table = QTableWidget(0, 5)
        self._alerts_table.setHorizontalHeaderLabels(["Crypto", "Condition", "Prix cible", "Prix actuel", "Action"])
        self._alerts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._alerts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._alerts_table.setShowGrid(False)
        self._alerts_table.verticalHeader().setVisible(False)
        self._alerts_table.verticalHeader().setDefaultSectionSize(42)
        hdr = self._alerts_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed); self._alerts_table.setColumnWidth(1, 120)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed); self._alerts_table.setColumnWidth(2, 120)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed); self._alerts_table.setColumnWidth(3, 120)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed); self._alerts_table.setColumnWidth(4, 100)
        self._alerts_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._alerts_table, 1)
        return w

    # ── Onglet DCA ────────────────────────────────────────────────────────────
    def _build_dca_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        # En-tête explication
        info = QLabel(
            "Le DCA (Dollar Cost Averaging) consiste à investir un montant fixe "
            "régulièrement, quel que soit le prix. Foyio vous rappelle chaque mois "
            "et vous permet d'exécuter l'achat en un clic."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size:11px; color:#7a8494; padding:4px 0;")
        vl.addWidget(info)

        # Formulaire ajout plan
        form_card = QWidget()
        form_card.setStyleSheet(
            "background:#26292e; border-radius:10px; border:1px solid #3a3f47;"
        )
        form_vl = QVBoxLayout(form_card)
        form_vl.setContentsMargins(14, 12, 14, 12)
        form_vl.setSpacing(10)

        title_lbl = QLabel("Nouveau plan DCA")
        title_lbl.setStyleSheet(
            "font-size:13px; font-weight:700; color:#c8cdd4; background:transparent; border:none;"
        )
        form_vl.addWidget(title_lbl)

        row = QHBoxLayout()
        row.setSpacing(10)

        # Crypto
        col_crypto = QVBoxLayout()
        lbl_crypto = QLabel("Crypto")
        lbl_crypto.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_holding_combo = QComboBox()
        self._dca_holding_combo.setMinimumHeight(34)
        self._dca_holding_combo.setMinimumWidth(160)
        col_crypto.addWidget(lbl_crypto)
        col_crypto.addWidget(self._dca_holding_combo)
        row.addLayout(col_crypto)

        # Montant €
        col_amt = QVBoxLayout()
        lbl_amt = QLabel("Montant (€)")
        lbl_amt.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_amount = QDoubleSpinBox()
        self._dca_amount.setRange(1, 99_999)
        self._dca_amount.setDecimals(2)
        self._dca_amount.setSuffix(" €")
        self._dca_amount.setValue(50)
        self._dca_amount.setMinimumHeight(34)
        self._dca_amount.setMinimumWidth(120)
        col_amt.addWidget(lbl_amt)
        col_amt.addWidget(self._dca_amount)
        row.addLayout(col_amt)

        # Jour du mois
        col_day = QVBoxLayout()
        lbl_day = QLabel("Jour du mois")
        lbl_day.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_day = QSpinBox()
        self._dca_day.setRange(1, 28)
        self._dca_day.setValue(1)
        self._dca_day.setSuffix("e du mois")
        self._dca_day.setMinimumHeight(34)
        self._dca_day.setMinimumWidth(120)
        col_day.addWidget(lbl_day)
        col_day.addWidget(self._dca_day)
        row.addLayout(col_day)

        # Note
        col_note = QVBoxLayout()
        lbl_note = QLabel("Note (optionnelle)")
        lbl_note.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_note = QLineEdit()
        self._dca_note.setPlaceholderText("Ex : Épargne long terme")
        self._dca_note.setMinimumHeight(34)
        col_note.addWidget(lbl_note)
        col_note.addWidget(self._dca_note)
        row.addLayout(col_note, 1)

        # Bouton
        btn_add_dca = QPushButton("Créer le plan")
        btn_add_dca.setMinimumHeight(34)
        btn_add_dca.setStyleSheet(
            "background:#22c55e; color:#000; border:none; border-radius:8px;"
            "font-weight:700; padding:0 14px; text-align:center;"
        )
        btn_add_dca.clicked.connect(self._add_dca_plan)
        row.addWidget(btn_add_dca)

        form_vl.addLayout(row)
        vl.addWidget(form_card)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
        vl.addWidget(sep)

        # Tableau des plans existants
        self._dca_table = QTableWidget(0, 7)
        self._dca_table.setHorizontalHeaderLabels([
            "Crypto", "Montant", "Jour", "Dernier achat", "Prochain", "Statut", "Actions"
        ])
        self._dca_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._dca_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._dca_table.setShowGrid(False)
        self._dca_table.verticalHeader().setVisible(False)
        self._dca_table.verticalHeader().setDefaultSectionSize(48)
        hdr = self._dca_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, w_ in [(1, 110), (2, 80), (3, 120), (4, 100), (5, 90), (6, 340)]:
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._dca_table.setColumnWidth(col, w_)
        self._dca_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._dca_table, 1)
        return w

    # ── Logique DCA ───────────────────────────────────────────────────────────
    def _load_dca(self):
        """Charge les plans DCA et les affiche dans le tableau."""
        from datetime import date
        # Mise à jour du combo de création
        self._dca_holding_combo.clear()
        for h in self._holdings:
            self._dca_holding_combo.addItem(f"{h.name} ({h.symbol.upper()})", h.id)

        plans = get_dca_plans()
        holdings_map = {h.id: h for h in self._holdings}

        self._dca_table.setRowCount(0)
        today = date.today()

        for plan in plans:
            holding = holdings_map.get(plan.holding_id)
            if not holding:
                continue

            row = self._dca_table.rowCount()
            self._dca_table.insertRow(row)

            name_txt = f"{holding.name} ({holding.symbol.upper()})"
            self._dca_table.setItem(row, 0, QTableWidgetItem(name_txt))

            amt_item = QTableWidgetItem(f"{plan.amount_eur:.2f} €")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._dca_table.setItem(row, 1, amt_item)

            day_item = QTableWidgetItem(f"{plan.day_of_month}")
            day_item.setTextAlignment(Qt.AlignCenter)
            self._dca_table.setItem(row, 2, day_item)

            last_txt = plan.last_executed.strftime("%d/%m/%Y") if plan.last_executed else "Jamais"
            self._dca_table.setItem(row, 3, QTableWidgetItem(last_txt))

            # Prochain achat
            from datetime import date as _d
            import calendar
            if today.day <= plan.day_of_month:
                next_month = today.month
                next_year  = today.year
            else:
                if today.month == 12:
                    next_month = 1
                    next_year  = today.year + 1
                else:
                    next_month = today.month + 1
                    next_year  = today.year
            max_day  = calendar.monthrange(next_year, next_month)[1]
            next_day = min(plan.day_of_month, max_day)
            next_date = _d(next_year, next_month, next_day)
            is_due = (next_date == today)
            next_txt = "Aujourd'hui !" if is_due else next_date.strftime("%d/%m/%Y")
            next_item = QTableWidgetItem(next_txt)
            if is_due:
                next_item.setForeground(QColor("#22c55e"))
            self._dca_table.setItem(row, 4, next_item)

            # Statut
            status_txt = "Actif" if plan.active else "Inactif"
            status_item = QTableWidgetItem(status_txt)
            status_item.setForeground(QColor("#22c55e") if plan.active else QColor("#ef4444"))
            status_item.setTextAlignment(Qt.AlignCenter)
            self._dca_table.setItem(row, 5, status_item)

            # Actions
            cell = QWidget()
            cell.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cell)
            hl.setContentsMargins(4, 4, 4, 4)
            hl.setSpacing(4)

            _btn_s = "border:none; border-radius:6px; font-size:11px; font-weight:600; text-align:center; padding:0 8px;"

            btn_edit = QPushButton("Modifier")
            btn_edit.setFixedHeight(28)
            btn_edit.setFixedWidth(70)
            btn_edit.setStyleSheet(f"background:#6366f1; color:#fff; {_btn_s}")
            btn_edit.clicked.connect(lambda checked, pid=plan.id: self._edit_dca(pid))

            btn_exec = QPushButton("Exécuter")
            btn_exec.setFixedHeight(28)
            btn_exec.setFixedWidth(70)
            btn_exec.setEnabled(plan.active)
            btn_exec.setStyleSheet(f"background:#3b82f6; color:#fff; {_btn_s}")
            btn_exec.clicked.connect(lambda checked, pid=plan.id: self._execute_dca(pid))

            btn_toggle = QPushButton("Désactiver" if plan.active else "Activer")
            btn_toggle.setFixedHeight(28)
            btn_toggle.setFixedWidth(80)
            btn_toggle.setStyleSheet(f"background:#f59e0b; color:#000; {_btn_s}")
            btn_toggle.clicked.connect(lambda checked, pid=plan.id: self._toggle_dca(pid))

            btn_del = QPushButton("Suppr.")
            btn_del.setFixedHeight(28)
            btn_del.setFixedWidth(56)
            btn_del.setStyleSheet(f"background:#ef4444; color:#fff; {_btn_s}")
            btn_del.clicked.connect(lambda checked, pid=plan.id: self._delete_dca(pid))

            hl.addWidget(btn_edit)
            hl.addWidget(btn_exec)
            hl.addWidget(btn_toggle)
            hl.addWidget(btn_del)
            hl.addStretch()
            self._dca_table.setCellWidget(row, 6, cell)

    def _add_dca_plan(self):
        holding_id = self._dca_holding_combo.currentData()
        if holding_id is None:
            Toast.show(self, "Aucune crypto sélectionnée.", "warning")
            return
        amount = self._dca_amount.value()
        day    = self._dca_day.value()
        note   = self._dca_note.text().strip()
        add_dca_plan(holding_id, amount, day, note)
        self._dca_note.clear()
        self._load_dca()
        Toast.show(self, "Plan DCA créé.", "success")

    def _execute_dca(self, plan_id: int):
        dlg = QDialog(self)
        dlg.setWindowTitle("Exécuter le DCA")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet("background:#1e2023; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setSpacing(14)

        lbl = QLabel("Voulez-vous exécuter ce plan DCA maintenant ?\nL'achat sera enregistré au prix actuel du marché.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#c8cdd4; font-size:12px;")
        vl.addWidget(lbl)

        chk_link = QCheckBox("Lier à une transaction financière")
        chk_link.setStyleSheet("color:#a0a8b4; font-size:11px;")
        vl.addWidget(chk_link)

        row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet(
            "background:#2e3238; color:#7a8494; border:none; border-radius:8px; padding:0 14px;"
        )
        btn_cancel.clicked.connect(dlg.reject)

        btn_ok = QPushButton("Acheter maintenant")
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet(
            "background:#22c55e; color:#000; border:none; border-radius:8px;"
            "font-weight:700; padding:0 14px; text-align:center;"
        )
        btn_ok.clicked.connect(dlg.accept)

        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        vl.addLayout(row)

        if dlg.exec() != QDialog.Accepted:
            return

        result = execute_dca(plan_id, link_financial=chk_link.isChecked())
        if result is None:
            Toast.show(self, "Impossible de récupérer le prix actuel.", "error")
            return

        Toast.show(
            self,
            f"Acheté {result['qty']:.6f} {result['symbol'].upper()} "
            f"à {result['price']:.2f} € — Total : {result['total']:.2f} €",
            "success"
        )
        self._holdings = get_holdings()
        self._load_portfolio()
        self._load_transactions()
        self._load_dca()

    def _toggle_dca(self, plan_id: int):
        new_state = toggle_dca_plan(plan_id)
        self._load_dca()
        Toast.show(self, f"Plan {'activé' if new_state else 'désactivé'}.", "success")

    def _edit_dca(self, plan_id: int):
        from services.crypto_service import get_dca_plans
        plans = get_dca_plans()
        plan = next((p for p in plans if p.id == plan_id), None)
        if not plan:
            return

        holding = next((h for h in self._holdings if h.id == plan.holding_id), None)
        holding_name = f"{holding.name} ({holding.symbol.upper()})" if holding else f"ID {plan.holding_id}"

        dlg = QDialog(self)
        dlg.setWindowTitle("Modifier le plan DCA")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background:#1e2023; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        title = QLabel(f"Modifier — {holding_name}")
        title.setStyleSheet("font-size:13px; font-weight:700; color:#c8cdd4;")
        vl.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px; color:#7a8494;")
            return l

        amt_spin = QDoubleSpinBox()
        amt_spin.setRange(1, 99_999)
        amt_spin.setDecimals(2)
        amt_spin.setSuffix(" €")
        amt_spin.setValue(plan.amount_eur)
        amt_spin.setMinimumHeight(34)
        form.addRow(_lbl("Montant :"), amt_spin)

        day_spin = QSpinBox()
        day_spin.setRange(1, 28)
        day_spin.setSuffix("e du mois")
        day_spin.setValue(plan.day_of_month)
        day_spin.setMinimumHeight(34)
        form.addRow(_lbl("Jour du mois :"), day_spin)

        note_edit = QLineEdit()
        note_edit.setText(plan.note or "")
        note_edit.setPlaceholderText("Note optionnelle")
        note_edit.setMinimumHeight(34)
        form.addRow(_lbl("Note :"), note_edit)

        vl.addLayout(form)

        row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet("background:#2e3238; color:#7a8494; border:none; border-radius:8px; padding:0 14px;")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Enregistrer")
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet("background:#6366f1; color:#fff; border:none; border-radius:8px; font-weight:700; padding:0 14px; text-align:center;")
        btn_ok.clicked.connect(dlg.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        vl.addLayout(row)

        if dlg.exec() == QDialog.Accepted:
            update_dca_plan(plan_id, amt_spin.value(), day_spin.value(), note_edit.text().strip())
            self._load_dca()
            Toast.show(self, "Plan DCA modifié.", "success")

    def _delete_dca(self, plan_id: int):
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer le plan DCA")
        msg.setText("Voulez-vous vraiment supprimer ce plan DCA ?")
        btn_oui = msg.addButton("Oui", QMessageBox.DestructiveRole)
        msg.addButton("Non", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_oui:
            delete_dca_plan(plan_id)
            self._load_dca()
            Toast.show(self, "Plan supprimé.", "success")

    def _check_due_dca(self):
        """Vérifie les plans DCA dus aujourd'hui et envoie une notification systray."""
        due = get_due_dca_plans()
        if not due:
            return
        holdings_map = {h.id: h for h in self._holdings}
        for plan in due:
            h = holdings_map.get(plan.holding_id)
            if not h:
                continue
            msg = (
                f"DCA {h.name} ({h.symbol.upper()}) : "
                f"{plan.amount_eur:.0f} € prévu aujourd'hui !"
            )
            self._show_tray_msg("DCA récurrent", msg)

    # ── Logos crypto ─────────────────────────────────────────────────────────
    def _fetch_logos(self):
        """Charge les logos manquants depuis CoinGecko CDN."""
        ids = [h.coingecko_id for h in self._holdings]
        if not ids:
            return
        urls = get_coin_image_urls(ids)
        pairs = [(cid, url) for cid, url in urls.items() if cid not in _pixmap_cache]
        if not pairs:
            self._apply_logos()
            return
        fetcher = _LogoFetcher(pairs)
        fetcher.logo_ready.connect(self._on_logo_ready)
        fetcher.finished.connect(self._apply_logos)
        self._start_thread(fetcher)

    def _on_logo_ready(self, cg_id: str, raw: bytes):
        from PySide6.QtGui import QPixmap
        px = QPixmap()
        if px.loadFromData(raw):
            _pixmap_cache[cg_id] = px.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _apply_logos(self):
        """Met à jour les cellules icône dans le tableau portefeuille et DCA."""
        from PySide6.QtGui import QPixmap
        # Portefeuille : col 0
        for i, h in enumerate(self._holdings):
            px = _pixmap_cache.get(h.coingecko_id)
            if px:
                lbl = QLabel()
                lbl.setPixmap(px)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("background:transparent; border:none;")
                self._portfolio_table.setCellWidget(i, 0, lbl)
        # DCA : col 0 (widget nom+logo)
        self._refresh_dca_logos()

    def _refresh_dca_logos(self):
        """Met à jour les logos dans le tableau DCA."""
        from PySide6.QtGui import QPixmap
        holdings_map = {h.id: h for h in self._holdings}
        for row in range(self._dca_table.rowCount()):
            item = self._dca_table.item(row, 0)
            if not item:
                continue
            # Chercher le holding correspondant
            for h in self._holdings:
                if f"{h.name} ({h.symbol.upper()})" == item.text():
                    px = _pixmap_cache.get(h.coingecko_id)
                    if px:
                        cell = QWidget()
                        cell.setStyleSheet("background:transparent;")
                        hl = QHBoxLayout(cell)
                        hl.setContentsMargins(4, 2, 4, 2)
                        hl.setSpacing(6)
                        logo = QLabel()
                        logo.setPixmap(px)
                        logo.setStyleSheet("background:transparent; border:none;")
                        name_lbl = QLabel(item.text())
                        name_lbl.setStyleSheet("background:transparent; border:none; color:#c8cdd4; font-size:12px;")
                        hl.addWidget(logo)
                        hl.addWidget(name_lbl)
                        hl.addStretch()
                        self._dca_table.setCellWidget(row, 0, cell)
                        # Effacer le texte de l'item pour éviter le chevauchement
                        item.setText("")
                    break

    # ── Chargement données ────────────────────────────────────────────────────
    def load(self):
        self._holdings = get_holdings()
        self._evo_loaded = False   # reset : on rechargera l'évolution une fois les prix reçus
        self._load_portfolio()
        self._load_transactions()
        self._load_alerts()
        self._load_watchlist()
        self._load_dca()
        self._fetch_prices()
        if not self._holdings:
            self._update_summary()  # aucun holding → remettre la barre à zéro sans attendre les prix
        self._check_due_dca()

    def refresh(self):
        self.load()

    def _start_thread(self, thread):
        """Démarre un thread en gardant sa référence pour éviter le GC."""
        self._threads = [t for t in self._threads if t.isRunning()]
        self._threads.append(thread)
        thread.start()

    def _fetch_prices(self):
        ids = list({h.coingecko_id for h in self._holdings} | set(get_watchlist_ids()))
        if not ids:
            self._update_summary()  # portefeuille vide : remettre à zéro
            return
        self._fetcher = _PriceFetcher(ids)
        self._fetcher.done.connect(self._on_prices_received)
        self._start_thread(self._fetcher)

    def _on_prices_received(self, prices: dict):
        self._prices = prices
        self._load_portfolio()
        self._update_summary()
        self._check_alerts_now()
        self._refresh_watchlist_prices()
        self._fetch_logos()  # URLs déjà dans _image_url_cache grâce à coins/markets
        # Évolution : seulement au 1er refresh (pas à chaque timer 6 min)
        if self._holdings and not getattr(self, '_evo_loaded', False):
            self._fetch_evolution()

    def _update_summary(self):
        summary = get_portfolio_summary(self._holdings, self._prices)
        self._lbl_total.setText(format_money(summary['total_value']))
        self._lbl_invest.setText(format_money(summary['total_invested']))
        pnl = summary['pnl']
        pct = summary['pnl_pct']
        color = "#22c55e" if pnl >= 0 else "#ef4444"
        sign  = "+" if pnl >= 0 else ""
        self._lbl_pnl.setText(f"{sign}{format_money(pnl)}")
        self._lbl_pnl.setStyleSheet(f"font-size:15px; font-weight:700; color:{color}; background:transparent; border:none;")
        chg = summary['change_24h_eur']
        sign2 = "+" if chg >= 0 else ""
        color2 = "#22c55e" if chg >= 0 else "#ef4444"
        self._lbl_chg24.setText(f"{sign2}{format_money(chg)}")
        self._lbl_chg24.setStyleSheet(f"font-size:15px; font-weight:700; color:{color2}; background:transparent; border:none;")

    def _load_portfolio(self):
        tbl = self._portfolio_table
        tbl.setRowCount(len(self._holdings))
        pie = QPieSeries()

        COLORS = ["#f7931a","#627eea","#9945ff","#f0b90b","#00adef",
                  "#e84142","#ff007a","#2775ca","#26a17b","#ff6b35"]

        for i, h in enumerate(self._holdings):
            color = COLORS[i % len(COLORS)]
            info  = self._prices.get(h.coingecko_id, {})
            price = info.get("price", 0)
            chg   = info.get("change_24h", 0)
            value = h.quantity * price
            pnl   = value - h.quantity * h.avg_buy_price
            pnl_p = (pnl / (h.quantity * h.avg_buy_price) * 100) if h.avg_buy_price > 0 else 0

            # Col 0 : pastille couleur
            dot = QLabel("●")
            dot.setAlignment(Qt.AlignCenter)
            dot.setStyleSheet(f"color:{color}; font-size:18px; background:transparent; border:none;")
            tbl.setCellWidget(i, 0, dot)

            # Col 1 : nom + symbole
            name_item = QTableWidgetItem(f"{h.name}  ({h.symbol})")
            name_item.setData(Qt.UserRole, h.id)
            tbl.setItem(i, 1, name_item)

            def _item(text, align=Qt.AlignRight | Qt.AlignVCenter, fg=None):
                it = QTableWidgetItem(text)
                it.setTextAlignment(align)
                if fg:
                    it.setForeground(QColor(fg))
                return it

            price_usd = info.get("price_usd", 0)

            qty_str = f"{h.quantity:,.8f}".rstrip("0").rstrip(".")
            tbl.setItem(i, 2, _item(qty_str, Qt.AlignRight | Qt.AlignVCenter))
            tbl.setItem(i, 3, _item(f"{h.avg_buy_price:,.2f} €"))

            price_str = f"{price:,.2f} €" if price else "—"
            chg_color = "#22c55e" if chg >= 0 else "#ef4444"
            price_item = _item(price_str)
            if chg:
                price_item.setText(f"{price_str}  ({'+' if chg>=0 else ''}{chg:.1f}%)")
                price_item.setForeground(QColor(chg_color))
            tbl.setItem(i, 4, price_item)

            usd_str = f"${price_usd:,.2f}" if price_usd else "—"
            tbl.setItem(i, 5, _item(usd_str))

            tbl.setItem(i, 6, _item(f"{value:,.2f} €" if price else "—"))

            pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"
            tbl.setItem(i, 7, _item(f"{'+' if pnl>=0 else ''}{pnl:,.2f} €", Qt.AlignRight | Qt.AlignVCenter, pnl_c))
            tbl.setItem(i, 8, _item(f"{'+' if pnl_p>=0 else ''}{pnl_p:.1f}%", Qt.AlignRight | Qt.AlignVCenter, pnl_c))

            # Pie : valeur réelle si prix connu, sinon prix d'achat (fallback)
            pie_value = value if value > 0 else h.quantity * h.avg_buy_price
            if pie_value > 0:
                sl = pie.append(h.symbol, pie_value)
                sl.setColor(QColor(color))
                sl.setLabelVisible(False)
                sl.setLabelColor(QColor("#ffffff"))
                sl.setLabelPosition(sl.LabelOutside)

                def _hover(state, s=sl, sym=h.symbol):
                    if state:
                        s.setLabel(f"{sym}  {s.percentage() * 100:.1f} %")
                        s.setLabelVisible(True)
                        s.setExploded(True)
                        s.setExplodeDistanceFactor(0.08)
                    else:
                        s.setLabelVisible(False)
                        s.setExploded(False)

                sl.hovered.connect(_hover)

        chart = QChart()
        chart.addSeries(pie)
        chart.setBackgroundVisible(False)
        chart.layout().setContentsMargins(0, 0, 0, 0)
        legend = chart.legend()
        legend.setVisible(True)
        legend.setAlignment(Qt.AlignBottom)
        legend.setLabelColor(QColor("#c8cdd4"))
        from PySide6.QtGui import QFont as _QFont
        legend.setFont(_QFont("Arial", 9))
        legend.setBackgroundVisible(False)
        self._pie_chart_view.setChart(chart)

    def _load_transactions(self):
        holdings_map = {h.id: h for h in self._holdings}
        all_holdings = get_holdings()
        all_map = {h.id: h for h in all_holdings}
        txs = get_transactions()
        tbl = self._tx_table
        tbl.setRowCount(len(txs))
        for i, tx in enumerate(txs):
            h = all_map.get(tx.holding_id)
            name = f"{h.name} ({h.symbol})" if h else "—"
            color = "#22c55e" if tx.type == "buy" else "#ef4444"
            type_lbl = "Achat" if tx.type == "buy" else "Vente"

            date_item = QTableWidgetItem(tx.date.strftime("%d/%m/%Y %H:%M"))
            date_item.setData(Qt.UserRole, tx.id)
            tbl.setItem(i, 0, date_item)
            tbl.setItem(i, 1, QTableWidgetItem(name))
            ti = QTableWidgetItem(type_lbl); ti.setForeground(QColor(color)); tbl.setItem(i, 2, ti)

            qty_str = f"{tx.quantity:,.8f}".rstrip("0").rstrip(".")
            tbl.setItem(i, 3, QTableWidgetItem(qty_str))
            tbl.setItem(i, 4, QTableWidgetItem(f"{tx.price_eur:,.2f} €"))
            ti2 = QTableWidgetItem(f"{tx.total_eur:,.2f} €"); ti2.setForeground(QColor(color)); tbl.setItem(i, 5, ti2)

    # ── Transactions crypto : menu contextuel, modifier, supprimer ────────────

    def _ctx_crypto_tx(self, pos):
        item = self._tx_table.itemAt(pos)
        if not item:
            return
        col0 = self._tx_table.item(item.row(), 0)
        if not col0:
            return
        tx_id = col0.data(Qt.UserRole)
        if not tx_id:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#292d32; color:#c8cdd4; border:1px solid #3d4248;
                    border-radius:8px; padding:4px; }
            QMenu::item { padding:8px 20px; border-radius:6px; font-size:12px; }
            QMenu::item:selected { background:#3e4550; }
        """)
        act_edit = menu.addAction("  Modifier")
        menu.addSeparator()
        act_del  = menu.addAction("  Supprimer")
        action = menu.exec(self._tx_table.viewport().mapToGlobal(pos))
        if action == act_edit:
            self._edit_crypto_tx(tx_id)
        elif action == act_del:
            self._delete_crypto_tx(tx_id)

    def _delete_crypto_tx(self, tx_id: int):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer")
        msg.setText("Supprimer cette transaction crypto ?\nLe portefeuille sera recalculé.")
        btn_yes = msg.addButton("Oui", QMessageBox.DestructiveRole)
        msg.addButton("Non", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() != btn_yes:
            return
        delete_crypto_transaction(tx_id)
        self.load()
        Toast.show(self, "Transaction supprimée", kind="warning")

    def _edit_crypto_tx(self, tx_id):
        if not tx_id:
            return
        from db import Session as _S
        from models import CryptoTransaction as _CT, CryptoHolding as _CH
        from PySide6.QtWidgets import (
            QDialog, QFormLayout, QComboBox, QDoubleSpinBox,
            QDateTimeEdit, QLineEdit, QDialogButtonBox, QLabel
        )
        from PySide6.QtCore import QDateTime

        with _S() as s:
            tx = s.query(_CT).filter_by(id=tx_id).first()
            if not tx:
                return
            h = s.query(_CH).filter_by(id=tx.holding_id).first()
            crypto_name = f"{h.name} ({h.symbol})" if h else "—"
            t_type     = tx.type
            t_qty      = tx.quantity
            t_price    = tx.price_eur
            t_date     = tx.date
            t_note     = tx.note or ""

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Modifier — {crypto_name}")
        dlg.setMinimumWidth(360)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)

        type_combo = QComboBox()
        type_combo.addItem("Achat",  "buy")
        type_combo.addItem("Vente", "sell")
        type_combo.setCurrentIndex(0 if t_type == "buy" else 1)
        type_combo.setMinimumHeight(34)
        form.addRow("Type :", type_combo)

        qty_spin = QDoubleSpinBox()
        qty_spin.setRange(0.000001, 999_999_999)
        qty_spin.setDecimals(8)
        qty_spin.setValue(t_qty)
        qty_spin.setMinimumHeight(34)
        form.addRow("Quantité :", qty_spin)

        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.01, 999_999_999)
        price_spin.setDecimals(2)
        price_spin.setValue(t_price)
        price_spin.setSuffix(" €")
        price_spin.setMinimumHeight(34)
        form.addRow("Prix unitaire :", price_spin)

        dt_edit = QDateTimeEdit(QDateTime(
            t_date.year, t_date.month, t_date.day,
            t_date.hour, t_date.minute, t_date.second
        ))
        dt_edit.setCalendarPopup(True)
        dt_edit.setDisplayFormat("dd/MM/yyyy HH:mm")
        dt_edit.setMinimumHeight(34)
        form.addRow("Date :", dt_edit)

        note_edit = QLineEdit(t_note)
        note_edit.setPlaceholderText("Note optionnelle")
        note_edit.setMinimumHeight(34)
        form.addRow("Note :", note_edit)

        btns = QDialogButtonBox()
        btns.addButton("Enregistrer", QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler",     QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        from datetime import datetime as _dt
        qdt = dt_edit.dateTime()
        new_date = _dt(qdt.date().year(), qdt.date().month(), qdt.date().day(),
                       qdt.time().hour(), qdt.time().minute())
        update_crypto_transaction(
            tx_id,
            type_combo.currentData(),
            qty_spin.value(),
            price_spin.value(),
            new_date,
            note_edit.text(),
        )
        self.load()
        Toast.show(self, "Transaction modifiée", kind="success")

    def _load_alerts(self):
        holdings_map = {h.id: h for h in self._holdings}
        alerts = get_alerts()
        self._alerts_table.setRowCount(len(alerts))
        self._alert_holding_combo.clear()
        for h in self._holdings:
            self._alert_holding_combo.addItem(f"{h.name} ({h.symbol})", h.id)

        _cond_labels = {
            "above":    "▲ Prix ≥",
            "below":    "▼ Prix ≤",
            "pct_up":   "📈 Hausse ≥ +",
            "pct_down": "📉 Baisse ≥ -",
        }
        for i, a in enumerate(alerts):
            h = holdings_map.get(a.holding_id)
            name = f"{h.name} ({h.symbol})" if h else "—"
            cond = _cond_labels.get(a.alert_type, a.alert_type)
            price_info = self._prices.get(h.coingecko_id if h else "", {})
            current    = price_info.get("price", 0)
            change_24h = price_info.get("change_24h", 0) or 0

            is_pct = a.alert_type in ("pct_up", "pct_down")
            target_str  = f"{a.target_price:.1f}%" if is_pct else f"{a.target_price:,.2f} €"
            current_str = (f"{change_24h:+.1f}%" if is_pct else f"{current:,.2f} €") if current else "—"

            self._alerts_table.setItem(i, 0, QTableWidgetItem(name))
            self._alerts_table.setItem(i, 1, QTableWidgetItem(cond))
            self._alerts_table.setItem(i, 2, QTableWidgetItem(target_str))
            self._alerts_table.setItem(i, 3, QTableWidgetItem(current_str))

            btn_del = QPushButton("Supprimer")
            btn_del.setFixedHeight(28)
            btn_del.setStyleSheet("background:#2e2020; color:#e89090; border:1px solid #503030; border-radius:6px; font-size:11px;")
            btn_del.clicked.connect(lambda _, aid=a.id: self._delete_alert(aid))
            self._alerts_table.setCellWidget(i, 4, btn_del)

    def _on_portfolio_selection(self):
        has_sel = bool(self._portfolio_table.selectedItems())
        self._btn_sell.setEnabled(has_sel)
        self._btn_edit.setEnabled(has_sel)
        self._btn_del.setEnabled(has_sel)

    def _selected_holding(self):
        rows = self._portfolio_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        item = self._portfolio_table.item(row, 1)
        if not item:
            return None
        hid = item.data(Qt.UserRole)
        return next((h for h in self._holdings if h.id == hid), None)

    # ── Dialogues ─────────────────────────────────────────────────────────────
    def _dialog_add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajouter une crypto")
        dlg.setMinimumWidth(460)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        # Recherche
        search_row = QHBoxLayout()
        search_edit = QLineEdit(); search_edit.setPlaceholderText("Rechercher : Bitcoin, ETH…"); search_edit.setMinimumHeight(34)
        btn_search = QPushButton("Rechercher"); btn_search.setMinimumHeight(34)
        search_row.addWidget(search_edit); search_row.addWidget(btn_search)
        vl.addWidget(lbl("Recherche :")); vl.addLayout(search_row)

        result_combo = QComboBox(); result_combo.setMinimumHeight(34)
        vl.addWidget(lbl("Résultats :")); vl.addWidget(result_combo)

        # Champs
        qty_spin = QDoubleSpinBox(); qty_spin.setRange(0.000001, 999999); qty_spin.setDecimals(8); qty_spin.setValue(0.01); qty_spin.setMinimumHeight(34)
        price_spin = QDoubleSpinBox(); price_spin.setRange(0.000001, 9_999_999); price_spin.setDecimals(2); price_spin.setSuffix(" €"); price_spin.setValue(0); price_spin.setMinimumHeight(34)
        note_edit = QLineEdit(); note_edit.setPlaceholderText("Note (optionnel)"); note_edit.setMinimumHeight(34)

        chk_link = QCheckBox("Enregistrer comme dépense dans les transactions")
        chk_link.setChecked(True)
        chk_link.setStyleSheet("color:#c8cdd4; font-size:12px;")

        vl.addWidget(lbl("Quantité :")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix d'achat unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(lbl("Note :")); vl.addWidget(note_edit)
        vl.addWidget(chk_link)

        # Pré-remplir le prix depuis l'API
        def _on_coin_selected(idx):
            cid = result_combo.itemData(idx)
            if cid:
                prices = get_prices([cid])
                p = prices.get(cid, {}).get("price", 0)
                if p > 0:
                    price_spin.setValue(p)

        result_combo.currentIndexChanged.connect(_on_coin_selected)

        _search_thread = [None]

        def _on_search_done(results):
            btn_search.setEnabled(True)
            btn_search.setText("Rechercher")
            result_combo.clear()
            if not results:
                result_combo.addItem("Aucun résultat")
                return
            for r in results:
                result_combo.addItem(f"{r['name']} ({r['symbol']})", r["id"])
            result_combo.setProperty("_results", results)

        def _do_search():
            q = search_edit.text().strip()
            if not q:
                return
            btn_search.setEnabled(False)
            btn_search.setText("Recherche…")
            result_combo.clear()
            t = _SearchThread(q)
            _search_thread[0] = t
            t.done.connect(_on_search_done)
            t.start()

        btn_search.clicked.connect(_do_search)
        search_edit.returnPressed.connect(_do_search)

        # Boutons
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("  Ajouter"); btn_ok.setMinimumHeight(36)
        btn_cancel = QPushButton("Annuler"); btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet("background:#2e2020; color:#e89090; border:1px solid #503030; border-radius:8px;")
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do_add():
            idx = result_combo.currentIndex()
            if idx < 0 or not result_combo.currentData():
                Toast.show(self, "✕  Sélectionnez une crypto", kind="error"); return
            results = result_combo.property("_results") or []
            coin = next((r for r in results if r["id"] == result_combo.currentData()), None)
            if not coin:
                Toast.show(self, "✕  Crypto introuvable", kind="error"); return
            qty   = qty_spin.value()
            price = price_spin.value()
            if qty <= 0 or price <= 0:
                Toast.show(self, "✕  Quantité et prix doivent être > 0", kind="error"); return
            holding_id = add_holding(coin["symbol"], coin["name"], coin["id"], qty, price)
            if chk_link.isChecked():
                link_to_transaction(
                    qty * price, "expense",
                    f"Achat {qty} {coin['symbol']} à {price:.2f} €",
                    holding_id=holding_id,
                )
            dlg.accept()
            self.load()
            Toast.show(self, f"✓  {coin['name']} ajouté au portefeuille", kind="success")

        btn_ok.clicked.connect(_do_add)
        dlg.exec()

    def _dialog_sell(self):
        h = self._selected_holding()
        if not h:
            return
        info  = self._prices.get(h.coingecko_id, {})
        price = info.get("price", h.avg_buy_price)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Vendre — {h.name}")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        qty_spin = QDoubleSpinBox(); qty_spin.setRange(0.000001, h.quantity); qty_spin.setDecimals(8); qty_spin.setValue(h.quantity); qty_spin.setMinimumHeight(34)
        price_spin = QDoubleSpinBox(); price_spin.setRange(0.000001, 9_999_999); price_spin.setDecimals(2); price_spin.setSuffix(" €"); price_spin.setValue(round(price, 2)); price_spin.setMinimumHeight(34)
        note_edit = QLineEdit(); note_edit.setPlaceholderText("Note (optionnel)"); note_edit.setMinimumHeight(34)

        chk_link_sell = QCheckBox("Enregistrer comme revenu dans les transactions")
        chk_link_sell.setChecked(True)
        chk_link_sell.setStyleSheet("color:#c8cdd4; font-size:12px;")

        vl.addWidget(lbl(f"Quantité disponible : {h.quantity}")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix de vente unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(lbl("Note :")); vl.addWidget(note_edit)
        vl.addWidget(chk_link_sell)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("  Vendre"); btn_ok.setMinimumHeight(36); btn_ok.setStyleSheet("background:#ef4444; color:#fff; border:none; border-radius:8px; font-weight:700;")
        btn_cancel = QPushButton("Annuler"); btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do_sell():
            qty   = qty_spin.value()
            sp    = price_spin.value()
            ok = sell_holding(h.id, qty, sp, note_edit.text())
            if not ok:
                Toast.show(self, "✕  Quantité insuffisante", kind="error"); return
            if chk_link_sell.isChecked():
                link_to_transaction(
                    qty * sp, "income",
                    f"Vente {qty} {h.symbol} à {sp:.2f} €",
                    holding_id=h.id,
                )
            dlg.accept(); self.load()
            Toast.show(self, f"✓  Vente enregistrée", kind="success")

        btn_ok.clicked.connect(_do_sell)
        dlg.exec()

    def _dialog_edit(self):
        h = self._selected_holding()
        if not h:
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Modifier — {h.name}")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        qty_spin = QDoubleSpinBox()
        qty_spin.setRange(0.000001, 999999)
        qty_spin.setDecimals(8)
        qty_spin.setValue(h.quantity)
        qty_spin.setMinimumHeight(34)

        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.000001, 9_999_999)
        price_spin.setDecimals(2)
        price_spin.setSuffix(" €")
        price_spin.setValue(h.avg_buy_price)
        price_spin.setMinimumHeight(34)

        vl.addWidget(lbl(f"Crypto : {h.name} ({h.symbol})"))
        vl.addSpacing(4)
        vl.addWidget(lbl("Quantité :")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix moyen d'achat :")); vl.addWidget(price_spin)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("  Enregistrer")
        btn_ok.setMinimumHeight(36)
        btn_ok.setStyleSheet("background:#3b82f6; color:#fff; border:none; border-radius:8px; font-weight:700;")
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do_edit():
            update_holding(h.id, qty_spin.value(), price_spin.value())
            dlg.accept()
            self.load()
            Toast.show(self, f"✓  {h.name} mis à jour", kind="success")

        btn_ok.clicked.connect(_do_edit)
        dlg.exec()

    def _delete_holding(self):
        h = self._selected_holding()
        if not h:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer")
        msg.setText(f"Supprimer {h.name} du portefeuille ?")
        btn_yes = msg.addButton("Oui", QMessageBox.DestructiveRole)
        msg.addButton("Non", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_yes:
            delete_holding(h.id); self.load()
            Toast.show(self, f"✓  {h.name} supprimé", kind="success")

    def _on_alert_type_changed(self):
        atype = self._alert_type_combo.currentData()
        is_pct = atype in ("pct_up", "pct_down")
        if is_pct:
            self._alert_price.setSuffix(" %")
            self._alert_price.setRange(0.1, 100)
            self._alert_price.setDecimals(1)
            self._alert_price_lbl.setText("Seuil (%) :")
        else:
            self._alert_price.setSuffix(" €")
            self._alert_price.setRange(0.000001, 9_999_999)
            self._alert_price.setDecimals(2)
            self._alert_price_lbl.setText("Prix cible :")

    def _add_alert(self):
        hid = self._alert_holding_combo.currentData()
        if not hid:
            Toast.show(self, "✕  Aucune crypto disponible", kind="error"); return
        atype = self._alert_type_combo.currentData()
        price = self._alert_price.value()
        if price <= 0:
            Toast.show(self, "✕  Prix cible invalide", kind="error"); return
        add_alert(hid, atype, price)
        self._load_alerts()
        Toast.show(self, "✓  Alerte ajoutée", kind="success")

    def _delete_alert(self, alert_id):
        delete_alert(alert_id)
        self._load_alerts()
        Toast.show(self, "✓  Alerte supprimée", kind="success")

    # ── Historique de prix (double-clic) ─────────────────────────────────────
    # ── Onglet Watchlist ──────────────────────────────────────────────────────
    def _build_watchlist_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        bar = QHBoxLayout()
        btn_add_watch = QPushButton("Ajouter à la watchlist")
        btn_add_watch.setMinimumHeight(36)
        btn_add_watch.setStyleSheet(
            "background:#3b82f6; color:#fff; border:none; border-radius:8px;"
            "font-weight:700; padding:0 16px; text-align:center;"
        )
        btn_add_watch.clicked.connect(self._dialog_add_watchlist)
        bar.addWidget(btn_add_watch)
        bar.addStretch()
        vl.addLayout(bar)

        self._wl_table = QTableWidget(0, 6)
        self._wl_table.setHorizontalHeaderLabels([
            "Crypto", "Prix (€)", "24h %", "Note", "Depuis", "Action"
        ])
        self._wl_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._wl_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._wl_table.setShowGrid(False)
        self._wl_table.verticalHeader().setVisible(False)
        self._wl_table.verticalHeader().setDefaultSectionSize(46)
        hdr = self._wl_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed); self._wl_table.setColumnWidth(1, 130)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed); self._wl_table.setColumnWidth(2, 90)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed); self._wl_table.setColumnWidth(3, 160)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed); self._wl_table.setColumnWidth(4, 100)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed); self._wl_table.setColumnWidth(5, 170)
        self._wl_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._wl_table, 1)
        return w

    def _load_watchlist(self):
        items = get_watchlist()
        tbl = self._wl_table
        tbl.setRowCount(len(items))
        for i, item in enumerate(items):
            info  = self._prices.get(item.coingecko_id, {})
            price = info.get("price", 0)
            chg   = info.get("change_24h", 0) or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
            sign  = "+" if chg >= 0 else ""

            tbl.setItem(i, 0, QTableWidgetItem(f"{item.name}  ({item.symbol})"))

            price_str = (f"{price:,.4f} €" if price and price < 1 else f"{price:,.2f} €") if price else "—"
            p_item = QTableWidgetItem(price_str)
            p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(i, 1, p_item)

            chg_item = QTableWidgetItem(f"{sign}{chg:.2f}%" if price else "—")
            chg_item.setTextAlignment(Qt.AlignCenter)
            chg_item.setForeground(QColor(color))
            tbl.setItem(i, 2, chg_item)

            tbl.setItem(i, 3, QTableWidgetItem(item.note or ""))
            tbl.setItem(i, 4, QTableWidgetItem(item.added_at.strftime("%d/%m/%Y")))

            btn_row = QHBoxLayout()
            btn_buy = QPushButton("Acheter")
            btn_buy.setMinimumWidth(72)
            btn_buy.setFixedHeight(30)
            btn_buy.setStyleSheet(
                "background:#22c55e; color:#000; border:none; border-radius:6px;"
                "font-size:12px; font-weight:700; text-align:center;"
            )
            btn_buy.clicked.connect(lambda _, it=item: self._buy_from_watchlist(it))

            btn_del = QPushButton("Retirer")
            btn_del.setMinimumWidth(66)
            btn_del.setFixedHeight(30)
            btn_del.setStyleSheet(
                "background:#2e2020; color:#e89090; border:1px solid #503030;"
                "border-radius:6px; font-size:12px; text-align:center;"
            )
            btn_del.clicked.connect(lambda _, it=item: self._remove_watchlist(it))

            cell_w = QWidget()
            hl = QHBoxLayout(cell_w)
            hl.setContentsMargins(4, 6, 4, 6)
            hl.setSpacing(4)
            hl.addWidget(btn_buy)
            hl.addWidget(btn_del)
            tbl.setCellWidget(i, 5, cell_w)

    def _refresh_watchlist_prices(self):
        """Met à jour uniquement les colonnes prix/variation sans recharger tout."""
        if not hasattr(self, "_wl_table"):
            return
        items = get_watchlist()
        tbl = self._wl_table
        if tbl.rowCount() != len(items):
            self._load_watchlist()
            return
        for i, item in enumerate(items):
            info  = self._prices.get(item.coingecko_id, {})
            price = info.get("price", 0)
            chg   = info.get("change_24h", 0) or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
            sign  = "+" if chg >= 0 else ""
            price_str = (f"{price:,.4f} €" if price < 1 else f"{price:,.2f} €") if price else "—"
            if tbl.item(i, 1):
                tbl.item(i, 1).setText(price_str)
            if tbl.item(i, 2):
                tbl.item(i, 2).setText(f"{sign}{chg:.2f}%" if price else "—")
                tbl.item(i, 2).setForeground(QColor(color))

    def _dialog_add_watchlist(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajouter à la watchlist")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        search_row = QHBoxLayout()
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Rechercher : Bitcoin, ETH…")
        search_edit.setMinimumHeight(34)
        btn_search = QPushButton("Rechercher")
        btn_search.setMinimumHeight(34)
        search_row.addWidget(search_edit); search_row.addWidget(btn_search)
        vl.addWidget(lbl("Recherche :")); vl.addLayout(search_row)

        result_combo = QComboBox(); result_combo.setMinimumHeight(34)
        vl.addWidget(lbl("Résultats :")); vl.addWidget(result_combo)

        note_edit = QLineEdit()
        note_edit.setPlaceholderText("Note (optionnel)")
        note_edit.setMinimumHeight(34)
        vl.addWidget(lbl("Note :")); vl.addWidget(note_edit)

        _wl_search_thread = [None]

        def _on_wl_search_done(results):
            btn_search.setEnabled(True)
            btn_search.setText("Rechercher")
            result_combo.clear()
            if not results:
                result_combo.addItem("Aucun résultat")
                return
            for r in results:
                result_combo.addItem(f"{r['name']} ({r['symbol']})", r)

        def _do_search():
            q = search_edit.text().strip()
            if not q:
                return
            btn_search.setEnabled(False)
            btn_search.setText("Recherche…")
            result_combo.clear()
            t = _SearchThread(q)
            _wl_search_thread[0] = t
            t.done.connect(_on_wl_search_done)
            t.start()

        btn_search.clicked.connect(_do_search)
        search_edit.returnPressed.connect(_do_search)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Ajouter à la watchlist")
        btn_ok.setMinimumHeight(36)
        btn_ok.setStyleSheet(
            "background:#3b82f6; color:#fff; border:none; border-radius:8px; font-weight:700;"
        )
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do_add():
            coin = result_combo.currentData()
            if not coin:
                Toast.show(self, "✕  Sélectionnez une crypto", kind="error"); return
            ok = add_to_watchlist(coin["id"], coin["symbol"], coin["name"], note_edit.text())
            if not ok:
                Toast.show(self, f"✕  {coin['name']} est déjà dans la watchlist", kind="error"); return
            dlg.accept()
            self._load_watchlist()
            self._fetch_prices()
            Toast.show(self, f"✓  {coin['name']} ajouté à la watchlist", kind="success")

        btn_ok.clicked.connect(_do_add)
        dlg.exec()

    def _remove_watchlist(self, item):
        remove_from_watchlist(item.id)
        self._load_watchlist()
        Toast.show(self, f"✓  {item.name} retiré de la watchlist", kind="success")

    def _buy_from_watchlist(self, item):
        """Ouvre le dialog d'achat pré-rempli depuis la watchlist."""
        price = self._prices.get(item.coingecko_id, {}).get("price", 0)
        coin  = {"id": item.coingecko_id, "symbol": item.symbol, "name": item.name, "price": price}
        self._quick_add_from_top(coin)

    # ── Onglet Top Cryptos ────────────────────────────────────────────────────
    def _build_top_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        # Barre de recherche + bouton refresh
        top_bar = QHBoxLayout()
        self._top_search = QLineEdit()
        self._top_search.setPlaceholderText("Filtrer par nom ou symbole…")
        self._top_search.setMinimumHeight(34)
        self._top_search.setStyleSheet(
            "background:#26292e; border:1px solid #3a3f47; border-radius:8px;"
            "color:#c8cdd4; padding:0 10px; font-size:12px;"
        )
        self._top_search.textChanged.connect(self._filter_top_table)
        top_bar.addWidget(self._top_search)

        btn_refresh_top = QPushButton("Actualiser")
        btn_refresh_top.setMinimumHeight(34)
        btn_refresh_top.setStyleSheet(
            "background:#26292e; color:#c8cdd4; border:1px solid #3a3f47;"
            "border-radius:8px; padding:0 14px; text-align:center;"
        )
        btn_refresh_top.clicked.connect(self._fetch_top)
        top_bar.addWidget(btn_refresh_top)
        vl.addLayout(top_bar)

        # Tableau
        self._top_table = QTableWidget(0, 6)
        self._top_table.setHorizontalHeaderLabels([
            "#", "Crypto", "Prix (€)", "24h %", "Cap. marché (€)", "Action"
        ])
        self._top_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._top_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._top_table.setShowGrid(False)
        self._top_table.verticalHeader().setVisible(False)
        self._top_table.verticalHeader().setDefaultSectionSize(42)
        hdr = self._top_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed);  self._top_table.setColumnWidth(0, 40)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed);  self._top_table.setColumnWidth(2, 130)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed);  self._top_table.setColumnWidth(3, 90)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed);  self._top_table.setColumnWidth(4, 160)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._top_table.setColumnWidth(5, 200)
        self._top_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._top_table, 1)

        self._top_loading = QLabel("Chargement…")
        self._top_loading.setAlignment(Qt.AlignCenter)
        self._top_loading.setStyleSheet("color:#7a8494; font-size:13px;")
        vl.addWidget(self._top_loading)
        self._top_loading.hide()

        self._top_data: list = []
        return w

    def _on_tab_changed(self, index: int):
        # Index 2 = Top Cryptos ; Index 3 = Watchlist
        if index == 2 and not self._top_data:
            self._fetch_top()
        elif index == 3:
            self._load_watchlist()

    def _fetch_top(self):
        self._top_loading.show()
        self._top_table.setRowCount(0)
        self._top_fetcher = _TopFetcher()
        self._top_fetcher.done.connect(self._on_top_received)
        self._start_thread(self._top_fetcher)

    def _on_top_received(self, coins: list):
        self._top_loading.hide()
        self._top_data = coins
        self._populate_top_table(coins)

    def _filter_top_table(self, text: str):
        q = text.lower()
        filtered = [c for c in self._top_data
                    if q in c["name"].lower() or q in c["symbol"].lower()] if q else self._top_data
        self._populate_top_table(filtered)

    def _populate_top_table(self, coins: list):
        tbl = self._top_table
        tbl.setRowCount(len(coins))
        for i, c in enumerate(coins):
            chg   = c.get("change_24h", 0) or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
            sign  = "+" if chg >= 0 else ""

            rank = QTableWidgetItem(str(i + 1))
            rank.setTextAlignment(Qt.AlignCenter)
            rank.setForeground(QColor("#5a6472"))
            tbl.setItem(i, 0, rank)

            name_item = QTableWidgetItem(f"{c['name']}  ({c['symbol']})")
            name_item.setData(Qt.UserRole, c)
            tbl.setItem(i, 1, name_item)

            price_item = QTableWidgetItem(f"{c['price']:,.4f} €" if c['price'] < 1 else f"{c['price']:,.2f} €")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(i, 2, price_item)

            chg_item = QTableWidgetItem(f"{sign}{chg:.2f}%")
            chg_item.setTextAlignment(Qt.AlignCenter)
            chg_item.setForeground(QColor(color))
            tbl.setItem(i, 3, chg_item)

            mcap = c.get("market_cap", 0) or 0
            if mcap >= 1_000_000_000:
                mcap_str = f"{mcap/1_000_000_000:.1f} Md €"
            elif mcap >= 1_000_000:
                mcap_str = f"{mcap/1_000_000:.1f} M €"
            else:
                mcap_str = f"{mcap:,.0f} €"
            mcap_item = QTableWidgetItem(mcap_str)
            mcap_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(i, 4, mcap_item)

            cell_w = QWidget()
            hl = QHBoxLayout(cell_w)
            hl.setContentsMargins(3, 3, 3, 3)
            hl.setSpacing(3)

            btn_add = QPushButton("+ Acheter")
            btn_add.setFixedHeight(28)
            btn_add.setFixedWidth(90)
            btn_add.setStyleSheet(
                "background:#22c55e; color:#000; border:none; border-radius:6px;"
                "font-size:11px; font-weight:700; text-align:center;"
            )
            btn_add.clicked.connect(lambda _, coin=c: self._quick_add_from_top(coin))

            already = is_in_watchlist(c["id"])
            btn_watch = QPushButton("✓ WL" if already else "👁 WL")
            btn_watch.setFixedHeight(28)
            btn_watch.setFixedWidth(76)
            btn_watch.setStyleSheet(
                f"background:{'#374151' if already else '#26292e'}; color:#c8cdd4;"
                "border:1px solid #3a3f47; border-radius:6px; font-size:11px; text-align:center;"
            )
            btn_watch.setEnabled(not already)
            btn_watch.clicked.connect(lambda _, coin=c, b=btn_watch: self._watch_from_top(coin, b))

            hl.addWidget(btn_add)
            hl.addWidget(btn_watch)
            tbl.setCellWidget(i, 5, cell_w)

    def _watch_from_top(self, coin: dict, btn: QPushButton):
        ok = add_to_watchlist(coin["id"], coin["symbol"], coin["name"])
        if ok:
            btn.setText("✓ WL")
            btn.setEnabled(False)
            btn.setStyleSheet("background:#374151; color:#c8cdd4; border:1px solid #3a3f47; border-radius:6px; font-size:10px;")
            self._load_watchlist()
            self._fetch_prices()
            Toast.show(self, f"✓  {coin['name']} ajouté à la watchlist", kind="success")
        else:
            Toast.show(self, f"✕  Déjà dans la watchlist", kind="error")

    def _quick_add_from_top(self, coin: dict):
        """Ouvre le dialog d'ajout pré-rempli avec la crypto sélectionnée."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Ajouter — {coin['name']}")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        vl.addWidget(lbl(f"Crypto : {coin['name']} ({coin['symbol']})"))
        vl.addSpacing(4)

        qty_spin = QDoubleSpinBox()
        qty_spin.setRange(0.000001, 999999); qty_spin.setDecimals(8)
        qty_spin.setValue(1.0); qty_spin.setMinimumHeight(34)

        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.000001, 9_999_999); price_spin.setDecimals(2)
        price_spin.setSuffix(" €"); price_spin.setValue(round(coin["price"], 2))
        price_spin.setMinimumHeight(34)

        chk_link = QCheckBox("Enregistrer comme dépense dans les transactions")
        chk_link.setChecked(True)
        chk_link.setStyleSheet("color:#c8cdd4; font-size:12px;")

        vl.addWidget(lbl("Quantité :")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix d'achat unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(chk_link)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Ajouter")
        btn_ok.setMinimumHeight(36)
        btn_ok.setStyleSheet("background:#22c55e; color:#000; border:none; border-radius:8px; font-weight:700;")
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do():
            qty = qty_spin.value(); price = price_spin.value()
            holding_id = add_holding(coin["symbol"], coin["name"], coin["id"], qty, price)
            if chk_link.isChecked():
                link_to_transaction(qty * price, "expense",
                                    f"Achat {qty} {coin['symbol']} à {price:.2f} €",
                                    holding_id=holding_id)
            dlg.accept(); self.load()
            Toast.show(self, f"✓  {coin['name']} ajouté au portefeuille", kind="success")

        btn_ok.clicked.connect(_do)
        dlg.exec()

    # ── Rapport fiscal FIFO ──────────────────────────────────────────────────
    def _dialog_fifo_report(self):
        from datetime import date
        current_year = date.today().year

        dlg = QDialog(self)
        dlg.setWindowTitle("Rapport fiscal — Plus/moins-values FIFO")
        dlg.setMinimumSize(980, 580)
        dlg.setStyleSheet("""
            QDialog { background:#1e2023; color:#c8cdd4; }
            #fifoSummaryBar { background:#26292e; border-radius:10px; border:1px solid #3a3f47; }
            QSpinBox {
                background:#26292e; color:#c8cdd4;
                border:1px solid #3a3f47; border-radius:6px;
                padding:2px 8px; min-width:110px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width:16px; background:#3a3f47; border-radius:3px;
            }
        """)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(14)

        # Sélecteur d'année + bouton exporter
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        lbl_yr = QLabel("Année fiscale :")
        lbl_yr.setStyleSheet("font-size:12px; color:#7a8494;")
        top_row.addWidget(lbl_yr)

        year_spin = QSpinBox()
        year_spin.setRange(2015, current_year)
        year_spin.setValue(current_year - 1 if date.today().month < 6 else current_year)
        year_spin.setFixedWidth(110)
        year_spin.setFixedHeight(34)
        top_row.addWidget(year_spin)

        btn_calc = QPushButton("Calculer")
        btn_calc.setFixedHeight(34)
        btn_calc.setStyleSheet(
            "background:#3b82f6; color:#fff; border:none; border-radius:8px;"
            "font-weight:700; padding:0 16px; text-align:center;"
        )
        top_row.addWidget(btn_calc)

        btn_export_fifo = QPushButton("Exporter CSV")
        btn_export_fifo.setFixedHeight(34)
        btn_export_fifo.setStyleSheet(
            "background:#26292e; color:#c8cdd4; border:1px solid #3a3f47;"
            "border-radius:8px; padding:0 14px; text-align:center;"
        )
        btn_export_fifo.setEnabled(False)
        top_row.addWidget(btn_export_fifo)
        top_row.addStretch()
        vl.addLayout(top_row)

        # Barre résumé
        summary_bar = QWidget()
        summary_bar.setObjectName("fifoSummaryBar")
        summary_bar.setFixedHeight(72)
        sbl = QHBoxLayout(summary_bar)
        sbl.setContentsMargins(20, 10, 20, 10)
        sbl.setSpacing(40)

        def _summary_cell(title):
            col = QVBoxLayout()
            col.setSpacing(3)
            t = QLabel(title)
            t.setStyleSheet("font-size:10px; color:#5a6472; font-weight:600; background:transparent; border:none;")
            v = QLabel("—")
            v.setStyleSheet("font-size:15px; font-weight:700; color:#c8cdd4; background:transparent; border:none;")
            col.addWidget(t); col.addWidget(v)
            return col, v

        c1, lbl_gains   = _summary_cell("PLUS-VALUES")
        c2, lbl_losses  = _summary_cell("MOINS-VALUES")
        c3, lbl_net     = _summary_cell("NET IMPOSABLE")
        c4, lbl_nb_ops  = _summary_cell("OPÉRATIONS")
        for c in [c1, c2, c3, c4]:
            sbl.addLayout(c)
        sbl.addStretch()
        vl.addWidget(summary_bar)

        # Tableau des lots
        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels([
            "Crypto", "Qté vendue", "Date achat", "Prix achat unit.",
            "Date vente", "Prix vente unit.", "Coût total", "Gain / Perte"
        ])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        hdr = table.horizontalHeader()
        hdr.setMinimumSectionSize(100)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col_, w_ in [(1,100),(2,100),(3,120),(4,100),(5,120),(6,100),(7,100)]:
            hdr.setSectionResizeMode(col_, QHeaderView.Fixed)
            table.setColumnWidth(col_, w_)
        table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 6px; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:5px 8px; font-size:11px; }
        """)
        vl.addWidget(table, 1)

        # Avertissement légal
        disclaimer = QLabel(
            "Avertissement : ce rapport est fourni à titre indicatif. "
            "Consultez un conseiller fiscal pour votre déclaration officielle."
        )
        disclaimer.setStyleSheet("font-size:10px; color:#5a6472; font-style:italic;")
        disclaimer.setWordWrap(True)
        vl.addWidget(disclaimer)

        _report_data = [None]  # stockage pour l'export

        def _run_calc():
            year = year_spin.value()
            report = compute_fifo_report(year)
            _report_data[0] = report

            lots = report["lots"]
            table.setRowCount(0)
            for lot in lots:
                r = table.rowCount()
                table.insertRow(r)

                crypto_item = QTableWidgetItem(f"{lot['name']} ({lot['symbol']})")
                table.setItem(r, 0, crypto_item)

                qty_item = QTableWidgetItem(f"{lot['qty']:.6f}")
                qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 1, qty_item)

                buy_date_txt = lot["buy_date"].strftime("%d/%m/%Y") if lot["buy_date"] else "—"
                table.setItem(r, 2, QTableWidgetItem(buy_date_txt))

                buy_p_item = QTableWidgetItem(f"{lot['buy_price']:.4f} €")
                buy_p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 3, buy_p_item)

                sell_date_txt = lot["sell_date"].strftime("%d/%m/%Y") if lot["sell_date"] else "—"
                table.setItem(r, 4, QTableWidgetItem(sell_date_txt))

                sell_p_item = QTableWidgetItem(f"{lot['sell_price']:.4f} €")
                sell_p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 5, sell_p_item)

                cost_item = QTableWidgetItem(f"{lot['buy_total']:.2f} €")
                cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 6, cost_item)

                gain = lot["gain"]
                gain_item = QTableWidgetItem(
                    f"{'+'if gain>=0 else ''}{gain:.2f} €"
                )
                gain_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                gain_item.setForeground(
                    QColor("#22c55e") if gain >= 0 else QColor("#ef4444")
                )
                table.setItem(r, 7, gain_item)

            g = report["total_gains"]
            lo = report["total_losses"]
            net = report["net"]
            lbl_gains.setText(f"+{g:.2f} €")
            lbl_gains.setStyleSheet(
                "font-size:15px; font-weight:700; color:#22c55e; background:transparent; border:none;"
            )
            lbl_losses.setText(f"{lo:.2f} €")
            lbl_losses.setStyleSheet(
                "font-size:15px; font-weight:700; color:#ef4444; background:transparent; border:none;"
            )
            net_color = "#22c55e" if net >= 0 else "#ef4444"
            lbl_net.setText(f"{'+'if net>=0 else ''}{net:.2f} €")
            lbl_net.setStyleSheet(
                f"font-size:15px; font-weight:700; color:{net_color}; background:transparent; border:none;"
            )
            lbl_nb_ops.setText(str(len(lots)))
            lbl_nb_ops.setStyleSheet(
                "font-size:15px; font-weight:700; color:#c8cdd4; background:transparent; border:none;"
            )
            btn_export_fifo.setEnabled(bool(lots))

        def _export_fifo_csv():
            if not _report_data[0]:
                return
            from PySide6.QtWidgets import QFileDialog
            import csv
            year = year_spin.value()
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Exporter le rapport fiscal",
                f"rapport_fiscal_{year}.csv",
                "CSV (*.csv)"
            )
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([
                    "Crypto", "Quantité vendue", "Date achat", "Prix achat unit. (€)",
                    "Date vente", "Prix vente unit. (€)",
                    "Coût d'achat total (€)", "Produit de vente (€)", "Gain / Perte (€)"
                ])
                for lot in _report_data[0]["lots"]:
                    w.writerow([
                        f"{lot['name']} ({lot['symbol']})",
                        f"{lot['qty']:.8f}",
                        lot["buy_date"].strftime("%d/%m/%Y") if lot["buy_date"] else "",
                        f"{lot['buy_price']:.4f}",
                        lot["sell_date"].strftime("%d/%m/%Y") if lot["sell_date"] else "",
                        f"{lot['sell_price']:.4f}",
                        f"{lot['buy_total']:.2f}",
                        f"{lot['sell_total']:.2f}",
                        f"{lot['gain']:.2f}",
                    ])
                r = _report_data[0]
                w.writerow([])
                w.writerow(["", "", "", "", "", "", "PLUS-VALUES", "", f"{r['total_gains']:.2f}"])
                w.writerow(["", "", "", "", "", "", "MOINS-VALUES", "", f"{r['total_losses']:.2f}"])
                w.writerow(["", "", "", "", "", "", "NET IMPOSABLE", "", f"{r['net']:.2f}"])
            Toast.show(self, f"Rapport exporté : {path}", "success")

        btn_calc.clicked.connect(_run_calc)
        btn_export_fifo.clicked.connect(_export_fifo_csv)
        _run_calc()  # calcul immédiat sur l'année sélectionnée
        dlg.exec()

    # ── Export CSV ───────────────────────────────────────────────────────────
    def _export_portfolio_csv(self):
        from PySide6.QtWidgets import QFileDialog
        import csv, os
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le portefeuille", "portefeuille_crypto.csv",
            "Fichiers CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Crypto", "Symbole", "Quantité", "Prix moyen achat (€)",
                             "Prix actuel (€)", "Valeur (€)", "P&L (€)", "P&L (%)"])
                for h in self._holdings:
                    info  = self._prices.get(h.coingecko_id, {})
                    price = info.get("price", 0)
                    value = h.quantity * price
                    pnl   = value - h.quantity * h.avg_buy_price
                    pnl_p = (pnl / (h.quantity * h.avg_buy_price) * 100) if h.avg_buy_price > 0 else 0
                    w.writerow([h.name, h.symbol,
                                f"{h.quantity:.8f}".rstrip("0").rstrip("."),
                                f"{h.avg_buy_price:.2f}", f"{price:.2f}",
                                f"{value:.2f}", f"{pnl:.2f}", f"{pnl_p:.1f}"])
            Toast.show(self, f"✓  Export réussi", kind="success")
        except Exception as e:
            Toast.show(self, f"✕  Erreur : {e}", kind="error")

    def _export_transactions_csv(self):
        from PySide6.QtWidgets import QFileDialog
        import csv
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les transactions", "transactions_crypto.csv",
            "Fichiers CSV (*.csv)"
        )
        if not path:
            return
        try:
            holdings_map = {h.id: h for h in get_holdings()}
            txs = get_transactions()
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Date", "Crypto", "Symbole", "Type",
                             "Quantité", "Prix unitaire (€)", "Total (€)", "Note"])
                for tx in txs:
                    h = holdings_map.get(tx.holding_id)
                    w.writerow([
                        tx.date.strftime("%d/%m/%Y %H:%M"),
                        h.name if h else "—", h.symbol if h else "—",
                        "Achat" if tx.type == "buy" else "Vente",
                        f"{tx.quantity:.8f}".rstrip("0").rstrip("."),
                        f"{tx.price_eur:.2f}", f"{tx.total_eur:.2f}",
                        tx.note or ""
                    ])
            Toast.show(self, f"✓  Export réussi ({len(txs)} ligne(s))", kind="success")
        except Exception as e:
            Toast.show(self, f"✕  Erreur : {e}", kind="error")

    def _on_portfolio_double_click(self, row: int, _col: int):
        item = self._portfolio_table.item(row, 1)
        if not item:
            return
        holding_id = item.data(Qt.UserRole)
        h = next((x for x in self._holdings if x.id == holding_id), None)
        if h:
            self._dialog_history(h)

    def _dialog_history(self, h):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        info  = self._prices.get(h.coingecko_id, {})
        price = info.get("price", 0)
        chg   = info.get("change_24h", 0)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{h.name} ({h.symbol})")
        dlg.setMinimumSize(600, 460)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        # En-tête
        header = QHBoxLayout()
        name_lbl = QLabel(f"{h.name}  <span style='color:#7a8494;font-size:13px;'>({h.symbol})</span>")
        name_lbl.setStyleSheet("font-size:18px; font-weight:700; color:#e0e4ea;")
        name_lbl.setTextFormat(Qt.RichText)
        header.addWidget(name_lbl)
        header.addStretch()

        chg_color = "#22c55e" if chg >= 0 else "#ef4444"
        chg_sign  = "+" if chg >= 0 else ""
        price_lbl = QLabel(
            f"<span style='font-size:20px; font-weight:700; color:#e0e4ea;'>"
            f"{price:,.2f} €</span>"
            f"  <span style='font-size:13px; color:{chg_color};'>"
            f"{chg_sign}{chg:.2f}% 24h</span>"
        )
        price_lbl.setTextFormat(Qt.RichText)
        header.addWidget(price_lbl)
        vl.addLayout(header)

        # Infos holding
        pnl   = h.quantity * price - h.quantity * h.avg_buy_price
        pnl_p = (pnl / (h.quantity * h.avg_buy_price) * 100) if h.avg_buy_price > 0 else 0
        pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"
        pnl_s = "+" if pnl >= 0 else ""
        info_row = QHBoxLayout()
        for label, value in [
            ("Quantité",     f"{h.quantity:,.8f}".rstrip("0").rstrip(".")),
            ("Prix moyen",   f"{h.avg_buy_price:,.2f} €"),
            ("Valeur",       f"{h.quantity * price:,.2f} €"),
            ("P&L",          f"{pnl_s}{pnl:,.2f} € ({pnl_s}{pnl_p:.1f}%)"),
        ]:
            card = QLabel(f"<div style='color:#7a8494;font-size:10px;'>{label}</div>"
                          f"<div style='color:{'#c8cdd4' if label != 'P&L' else pnl_c};"
                          f"font-size:13px;font-weight:600;'>{value}</div>")
            card.setTextFormat(Qt.RichText)
            card.setStyleSheet("background:#26292e; border-radius:8px; padding:10px 14px;")
            info_row.addWidget(card)
        vl.addLayout(info_row)

        # Sélecteur de période
        period_row = QHBoxLayout()
        period_row.addStretch()
        _period_btns: dict[int, QPushButton] = {}
        _current_days = [30]

        chart_view = QChartView()
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setStyleSheet("background:transparent; border:none;")
        chart_view.setMinimumHeight(220)

        def _load_chart(days: int):
            _current_days[0] = days
            for d, b in _period_btns.items():
                b.setChecked(d == days)

            def _do():
                return get_price_history(h.coingecko_id, days)

            import threading
            result = [None]
            done_event = __import__("threading").Event()

            def _worker():
                result[0] = get_price_history(h.coingecko_id, days)
                done_event.set()

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            # Attente non-bloquante via QTimer
            def _check():
                if not done_event.is_set():
                    QTimer.singleShot(50, _check)
                    return
                _draw(result[0] or [])
            QTimer.singleShot(50, _check)

        def _draw(history):
            if len(history) < 2:
                return
            series = QLineSeries()
            pen = QPen(QColor("#3b82f6"))
            pen.setWidth(2)
            series.setPen(pen)
            for ts_ms, p in history:
                series.append(ts_ms, p)
            # Aire sous la courbe
            zero = QLineSeries()
            for ts_ms, _ in history:
                zero.append(ts_ms, 0)
            area = QAreaSeries(series, zero)
            from PySide6.QtGui import QLinearGradient, QGradient
            grad = QLinearGradient(0, 0, 0, 1)
            grad.setCoordinateMode(QGradient.ObjectMode)
            grad.setColorAt(0.0, QColor(59, 130, 246, 80))
            grad.setColorAt(1.0, QColor(59, 130, 246, 0))
            area.setBrush(grad)
            area.setPen(QPen(Qt.NoPen))

            chart = QChart()
            chart.addSeries(area)
            chart.addSeries(series)
            chart.setBackgroundBrush(QColor("#1e2124"))
            chart.setBackgroundRoundness(0)
            chart.legend().hide()
            chart.layout().setContentsMargins(0, 0, 0, 0)

            days = _current_days[0]
            ax = QDateTimeAxis()
            ax.setFormat("dd/MM" if days <= 90 else "MMM yy")
            ax.setLabelsColor(QColor("#7a8494"))
            ax.setGridLineColor(QColor("#2e3238"))
            ax.setTickCount(min(6, len(history)))
            chart.addAxis(ax, Qt.AlignBottom)
            series.attachAxis(ax)
            area.attachAxis(ax)

            prices_only = [p for _, p in history]
            ay = QValueAxis()
            ay.setRange(min(prices_only) * 0.97, max(prices_only) * 1.03)
            ay.setLabelsColor(QColor("#7a8494"))
            ay.setGridLineColor(QColor("#2e3238"))
            ay.setLabelFormat("%.2f €")
            ay.setTickCount(4)
            chart.addAxis(ay, Qt.AlignLeft)
            series.attachAxis(ay)
            area.attachAxis(ay)

            chart_view.setChart(chart)
            # Garder les références pour éviter GC
            chart_view._series = series
            chart_view._area   = area
            chart_view._zero   = zero

        for label, days in [("7J", 7), ("30J", 30), ("90J", 90), ("1AN", 365)]:
            btn = QPushButton(label)
            btn.setFixedSize(52, 26)
            btn.setCheckable(True)
            btn.setChecked(days == 30)
            btn.setStyleSheet("""
                QPushButton { background:#26292e; color:#7a8494; border:1px solid #3a3f47;
                    border-radius:6px; font-size:11px; font-weight:600; }
                QPushButton:hover { color:#c8cdd4; }
                QPushButton:checked { background:#3b82f6; color:#fff; border:none; }
            """)
            btn.clicked.connect(lambda _, d=days: _load_chart(d))
            period_row.addWidget(btn)
            _period_btns[days] = btn

        vl.addLayout(period_row)
        vl.addWidget(chart_view, 1)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)

        _load_chart(30)
        dlg.exec()

    # ── Évolution portefeuille ────────────────────────────────────────────────
    def _set_evo_period(self, days: int):
        self._evo_period = days
        for d, btn in self._evo_btns.items():
            btn.setChecked(d == days)
        if self._holdings:
            self._fetch_evolution()

    def _fetch_evolution(self):
        self._evo_chart_view.hide()
        self._evo_loading.show()
        self._evo_fetcher = _EvoFetcher(self._holdings, self._evo_period)
        self._evo_fetcher.done.connect(self._on_evo_received)
        self._start_thread(self._evo_fetcher)

    def _on_evo_received(self, data: dict):
        self._evo_loading.hide()
        self._evo_chart_view.show()
        self._evo_loaded = True   # ne pas re-fetcher au prochain refresh de prix
        """Reconstruit le graphique d'évolution à partir des historiques reçus."""
        if not data:
            return

        # Agréger la valeur totale par jour
        daily: dict[int, float] = {}
        for cg_id, (qty, history) in data.items():
            for ts_ms, price in history:
                day = (ts_ms // 86_400_000) * 86_400_000
                daily[day] = daily.get(day, 0.0) + qty * price

        if len(daily) < 2:
            return

        points = sorted(daily.items())
        min_v = min(v for _, v in points)
        max_v = max(v for _, v in points)

        # Choisir l'échelle selon l'ordre de grandeur
        if max_v >= 1_000_000:
            scale, unit_lbl, fmt = 1_000_000, "M\u20ac", "%.2f"
        elif max_v >= 10_000:
            scale, unit_lbl, fmt = 1_000,     "k\u20ac", "%.1f"
        else:
            scale, unit_lbl, fmt = 1,          "\u20ac",  "%.0f"

        points_sc = [(ts, v / scale) for ts, v in points]
        min_sc, max_sc = min_v / scale, max_v / scale

        self._evo_series = QLineSeries()
        pen = QPen(QColor("#3b82f6"))
        pen.setWidth(2)
        self._evo_series.setPen(pen)
        for ts_ms, value in points_sc:
            self._evo_series.append(ts_ms, value)

        # Mettre à jour le label vertical avec la bonne unité
        self._evo_unit_lbl.setText(unit_lbl)

        _bg = QColor("#1e2023")
        _axis_font = QFont("Segoe UI", 8)

        chart = QChart()
        chart.addSeries(self._evo_series)
        # Le chart peint lui-même son fond sombre — fiable sur Windows
        chart.setBackgroundBrush(_bg)
        chart.setBackgroundVisible(True)
        chart.setDropShadowEnabled(False)
        chart.setBackgroundRoundness(0)
        chart.legend().hide()
        chart.setContentsMargins(0, 0, 0, 0)
        chart.layout().setContentsMargins(0, 0, 0, 0)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd/MM" if self._evo_period <= 90 else "MMM yy")
        axis_x.setLabelsColor(QColor("#7a8494"))
        axis_x.setLabelsFont(_axis_font)
        axis_x.setGridLineColor(QColor("#2e3238"))
        axis_x.setTickCount(min(6, len(points)))
        chart.addAxis(axis_x, Qt.AlignBottom)
        self._evo_series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(min_sc * 0.98, max_sc * 1.02)
        axis_y.setLabelsColor(QColor("#7a8494"))
        axis_y.setLabelsFont(_axis_font)
        axis_y.setGridLineColor(QColor("#2e3238"))
        axis_y.setLabelFormat(fmt)   # unité dans _evo_unit_lbl (k€/M€/€)
        axis_y.setTickCount(4)
        chart.addAxis(axis_y, Qt.AlignLeft)
        self._evo_series.attachAxis(axis_y)

        self._evo_chart_view.setChart(chart)
        # setChart() peut réinitialiser le brush de la vue — on le force après
        self._evo_chart_view.setBackgroundBrush(_bg)
        self._evo_chart_view.viewport().update()

    def _show_tray_msg(self, title: str, message: str):
        """Affiche une notification systray en cherchant le _tray dans la hiérarchie."""
        from PySide6.QtWidgets import QSystemTrayIcon
        from PySide6.QtGui import QIcon
        import os
        # Chercher le _tray dans les parents ou dans les top-level widgets
        w = self.window()
        tray = getattr(w, "_tray", None)
        if tray is None:
            from PySide6.QtWidgets import QApplication
            for tw in QApplication.topLevelWidgets():
                if hasattr(tw, "_tray"):
                    tray = tw._tray
                    break
        if tray:
            tray.showMessage(title, message, QSystemTrayIcon.Information, 6000)

    def _check_alerts_now(self):
        triggered = check_alerts(self._prices)
        for t in triggered:
            atype = t["alert_type"]
            if atype == "above":
                msg = (f"{t['name']} ({t['symbol']}) a dépassé {t['target_price']:,.2f} €"
                       f"\nPrix actuel : {t['current_price']:,.2f} €")
            elif atype == "below":
                msg = (f"{t['name']} ({t['symbol']}) est passé sous {t['target_price']:,.2f} €"
                       f"\nPrix actuel : {t['current_price']:,.2f} €")
            elif atype == "pct_up":
                msg = (f"{t['name']} ({t['symbol']}) a progressé de "
                       f"+{t['change_24h']:.1f}% en 24h (seuil : +{t['target_price']:.1f}%)")
            else:  # pct_down
                msg = (f"{t['name']} ({t['symbol']}) a chuté de "
                       f"{t['change_24h']:.1f}% en 24h (seuil : -{t['target_price']:.1f}%)")
            Toast.show(self, f"🔔  {msg}", kind="info")
            self._show_tray_msg(f"🔔 Alerte Crypto — {t['name']}", msg)
        if triggered:
            self._load_alerts()

    # ── Simulateur DCA ────────────────────────────────────────────────────────
    # ── Comparaison Portfolio vs BTC vs ETH ───────────────────────────────────
    def _run_comparison(self, days: int):
        self._cmp_period = days
        for d, b in self._cmp_btns.items():
            b.setChecked(d == days)
        if not self._holdings:
            self._cmp_status.setText("Aucune crypto dans le portefeuille.")
            return
        self._btn_run_cmp.setEnabled(False)
        self._btn_run_cmp.setText("Chargement…")
        self._cmp_status.setText("Récupération des historiques en cours (peut prendre quelques secondes)…")
        self._comp_fetcher = _CompFetcher(self._holdings, days)
        self._comp_fetcher.done.connect(self._on_comp_received)
        self._start_thread(self._comp_fetcher)

    def _on_comp_received(self, data: dict):
        def _normalize(series_data):
            """Ramène la première valeur à 100 (base 100)."""
            if not series_data:
                return []
            first = series_data[0][1]
            if first == 0:
                return []
            return [(ts, val / first * 100) for ts, val in series_data]

        btc_norm  = _normalize(data.get("btc", []))
        eth_norm  = _normalize(data.get("eth", []))
        port_norm = _normalize(data.get("portfolio", []))

        if not any([btc_norm, eth_norm, port_norm]):
            self._btn_run_cmp.setEnabled(True)
            self._btn_run_cmp.setText("Comparer")
            self._cmp_status.setText("Données insuffisantes.")
            return

        chart = QChart()
        chart.setBackgroundBrush(QColor("#26292e"))
        chart.setBackgroundRoundness(0)
        chart.legend().hide()
        chart.layout().setContentsMargins(0, 0, 0, 0)

        def _make_series(points, color_hex, width=2):
            s = QLineSeries()
            pen = QPen(QColor(color_hex))
            pen.setWidth(width)
            s.setPen(pen)
            for ts, val in points:
                s.append(ts, val)
            return s

        all_vals = []
        series_list = []
        for points, color in [(port_norm, "#3b82f6"), (btc_norm, "#f7931a"), (eth_norm, "#627eea")]:
            if points:
                s = _make_series(points, color)
                chart.addSeries(s)
                series_list.append(s)
                all_vals.extend(v for _, v in points)

        ax = QDateTimeAxis()
        fmt = "dd/MM" if self._cmp_period <= 90 else "MMM yy"
        ax.setFormat(fmt)
        ax.setLabelsColor(QColor("#7a8494"))
        ax.setGridLineColor(QColor("#2e3238"))
        ax.setTickCount(6)
        chart.addAxis(ax, Qt.AlignBottom)

        mn, mx = min(all_vals) * 0.97, max(all_vals) * 1.03
        ay = QValueAxis()
        ay.setRange(mn, mx)
        ay.setLabelFormat("%.0f")
        ay.setLabelsColor(QColor("#7a8494"))
        ay.setGridLineColor(QColor("#2e3238"))
        ay.setTickCount(5)
        chart.addAxis(ay, Qt.AlignLeft)

        for s in series_list:
            s.attachAxis(ax)
            s.attachAxis(ay)

        # Stocker pour éviter le GC
        self._cmp_series_list = series_list
        self._cmp_chart.setChart(chart)
        self._cmp_chart.setVisible(True)

        labels = []
        if port_norm: labels.append(f"Portfolio {port_norm[-1][1]-100:+.1f}%")
        if btc_norm:  labels.append(f"BTC {btc_norm[-1][1]-100:+.1f}%")
        if eth_norm:  labels.append(f"ETH {eth_norm[-1][1]-100:+.1f}%")
        self._btn_run_cmp.setEnabled(True)
        self._btn_run_cmp.setText("Comparer")
        self._cmp_status.setText("  ·  ".join(labels))

    def _run_dca(self):
        monthly = self._dca_monthly.value()
        months  = self._dca_months.value()
        rate    = self._dca_rate.value()
        res     = simulate_dca(monthly, months, rate)

        self._dca_result.setText(
            f"Valeur finale : {res['final_value']:,.2f} €  |  "
            f"Investi : {res['total_invested']:,.2f} €  |  "
            f"Gain : {'+' if res['total_gain']>=0 else ''}{res['total_gain']:,.2f} € "
            f"({'+' if res['gain_pct']>=0 else ''}{res['gain_pct']:.1f}%)"
        )
        self._dca_result.setVisible(True)

        evol = res["evolution"]
        self._dca_upper = QLineSeries()
        self._dca_invest = QLineSeries()
        self._dca_upper.setColor(QColor("#22c55e"))
        self._dca_invest.setColor(QColor("#3b82f6"))
        for e in evol:
            self._dca_upper.append(e["month"], e["value"])
            self._dca_invest.append(e["month"], e["invested"])
        area = QAreaSeries(self._dca_upper)
        area.setColor(QColor(34, 197, 94, 30))
        area.setBorderColor(QColor("#22c55e"))
        chart = QChart()
        chart.addSeries(area)
        chart.addSeries(self._dca_invest)
        chart.setBackgroundBrush(QColor("#26292e"))
        chart.setBackgroundRoundness(0)
        chart.legend().setVisible(False)
        chart.createDefaultAxes()
        self._dca_chart.setChart(chart)
        self._dca_chart.setVisible(True)

    # ── Simulateur What-If ────────────────────────────────────────────────────
    def _run_what_if(self):
        amount     = self._wi_amount.value()
        months_ago = self._wi_months.value()
        cid        = self._wi_coin.currentData()
        res        = simulate_what_if(cid, amount, months_ago)

        if not res:
            Toast.show(self, "✕  Données historiques indisponibles", kind="error"); return

        gain_color = "#22c55e" if res["gain"] >= 0 else "#ef4444"
        sign = "+" if res["gain"] >= 0 else ""
        self._wi_result.setText(
            f"Investi : {res['invested']:,.2f} €  →  Valeur actuelle : {res['current_value']:,.2f} €\n"
            f"Gain : {sign}{res['gain']:,.2f} € ({sign}{res['gain_pct']:.1f}%)\n"
            f"Prix à l'achat : {res['price_then']:,.2f} €  |  Prix actuel : {res['price_now']:,.2f} €"
        )
        self._wi_result.setStyleSheet(
            f"font-size:13px; font-weight:600; color:{gain_color}; background:#292d32; border-radius:8px; padding:12px;"
        )
        self._wi_result.setVisible(True)

        history = res["history"]
        if len(history) >= 2:
            self._wi_series = QLineSeries()
            self._wi_series.setColor(QColor("#f7931a"))
            for ts, price in history:
                self._wi_series.append(float(ts), price)
            chart = QChart()
            chart.addSeries(self._wi_series)
            chart.setBackgroundBrush(QColor("#26292e"))
            chart.setBackgroundRoundness(0)
            chart.legend().setVisible(False)
            chart.createDefaultAxes()
            self._wi_chart.setChart(chart)
            self._wi_chart.setVisible(True)
