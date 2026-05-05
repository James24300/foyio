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
    QProgressBar, QCheckBox, QStackedWidget
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QPieSeries, QValueAxis, QAreaSeries,
    QDateTimeAxis, QStackedBarSeries, QBarSet, QBarCategoryAxis
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QDateTime, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QBrush
import math

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


logger = logging.getLogger(__name__)

from ui.crypto_threads import (
    _BubbleWidget, _SearchThread, _PriceFetcher, _CompFetcher,
    _TopFetcher, _LogoFetcher, _pixmap_cache,
)
from ui._crypto_dca_mixin import _CryptoDcaMixin
from ui._crypto_watchlist_mixin import _CryptoWatchlistMixin
from ui._crypto_top_mixin import _CryptoTopMixin
from ui._crypto_simulator_mixin import _CryptoSimulatorMixin
from ui._crypto_fiscal_mixin import _CryptoFiscalMixin
from ui._crypto_history_mixin import _CryptoHistoryMixin


class CryptoView(_CryptoDcaMixin, _CryptoWatchlistMixin, _CryptoTopMixin,
                 _CryptoSimulatorMixin, _CryptoFiscalMixin, _CryptoHistoryMixin,
                 QWidget):

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
        self._refresh_timer.start(120_000)  # 2 min — le cache service (5 min TTL) évite les appels API redondants

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
        hdr.setSectionResizeMode(0, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(0, 44)
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

        # ── Graphiques de performance ──────────────────────────────────────
        perf_hdr = QHBoxLayout()
        perf_lbl = QLabel("Performance du portefeuille")
        perf_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#7a8494;")
        perf_hdr.addWidget(perf_lbl)
        perf_hdr.addStretch()

        _tog = """
            QPushButton { background:#26292e; color:#7a8494; border:1px solid #3a3f47;
                border-radius:6px; font-size:11px; font-weight:600; }
            QPushButton:hover { color:#c8cdd4; }
            QPushButton:checked { background:#3b82f6; color:#fff; border:none; }
        """
        self._btn_viz_bubble = QPushButton("Bulles")
        self._btn_viz_bubble.setFixedSize(72, 32)
        self._btn_viz_bubble.setCheckable(True)
        self._btn_viz_bubble.setChecked(True)
        self._btn_viz_bubble.setStyleSheet(_tog)
        self._btn_viz_bubble.clicked.connect(lambda: self._set_viz_mode(0))

        self._btn_viz_bar = QPushButton("Barres")
        self._btn_viz_bar.setFixedSize(72, 32)
        self._btn_viz_bar.setCheckable(True)
        self._btn_viz_bar.setStyleSheet(_tog)
        self._btn_viz_bar.clicked.connect(lambda: self._set_viz_mode(1))

        perf_hdr.addWidget(self._btn_viz_bubble)
        perf_hdr.addWidget(self._btn_viz_bar)
        vl.addLayout(perf_hdr)

        self._viz_stack = QStackedWidget()
        self._viz_stack.setFixedHeight(260)

        self._bubble_widget = _BubbleWidget()
        self._viz_stack.addWidget(self._bubble_widget)

        self._bar_chart_view = QChartView()
        self._bar_chart_view.setRenderHint(QPainter.Antialiasing)
        self._bar_chart_view.setStyleSheet("border:none;")
        self._bar_chart_view.setBackgroundBrush(QColor("#1e2023"))
        self._viz_stack.addWidget(self._bar_chart_view)

        vl.addWidget(self._viz_stack)
        return w

    # ── Onglet Transactions ───────────────────────────────────────────────────
    def _build_transactions_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        self._tx_table = QTableWidget(0, 7)
        self._tx_table.setHorizontalHeaderLabels([
            "Date", "Crypto", "Type", "Quantité", "Prix unitaire", "Frais", "Total €"
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
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._tx_table.setColumnWidth(5, 90)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed);  self._tx_table.setColumnWidth(6, 120)
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
            _pixmap_cache[cg_id] = px.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)

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
                lbl.setScaledContents(False)
                lbl.setStyleSheet("background:transparent; border:none; padding:0; margin:0;")
                self._portfolio_table.setCellWidget(i, 0, lbl)
        # DCA : col 0 (widget nom+logo)
        self._refresh_dca_logos()

    def load(self):
        self._holdings = get_holdings()
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

    # ── Vues de performance (bulles / barres) ────────────────────────────────

    def _set_viz_mode(self, mode: int):
        self._viz_stack.setCurrentIndex(mode)
        self._btn_viz_bubble.setChecked(mode == 0)
        self._btn_viz_bar.setChecked(mode == 1)

    def _update_viz_charts(self, items):
        """items : [(symbol, pnl_pct, value_eur, coingecko_id)]"""
        self._bubble_widget.set_data(items)
        self._build_bar_chart(items)

    def _build_bar_chart(self, items):
        """Graphique barres : P&L % par crypto (vert = gain, rouge = perte)."""
        if not items:
            self._bar_chart_view.setChart(QChart())
            return

        green_set = QBarSet("")
        red_set   = QBarSet("")
        green_set.setColor(QColor("#22c55e"))
        green_set.setBorderColor(QColor("#22c55e"))
        red_set.setColor(QColor("#ef4444"))
        red_set.setBorderColor(QColor("#ef4444"))

        categories = []
        for sym, pnl_pct, _val, _cid in items:
            categories.append(sym)
            green_set.append(max(0.0, pnl_pct))
            red_set.append(min(0.0, pnl_pct))

        series = QStackedBarSeries()
        series.setBarWidth(0.55)
        series.append(green_set)
        series.append(red_set)

        vals = [it[1] for it in items]
        mn, mx = min(vals), max(vals)
        pad = max(2.0, (abs(mx) + abs(mn)) * 0.15 + 1.0)

        _bg   = QColor("#1e2023")
        _ax_f = QFont("Segoe UI", 8)
        _ax_c = QColor("#7a8494")

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor("#c8cdd4"))
        axis_x.setLabelsFont(QFont("Segoe UI", 9))
        axis_x.setGridLineVisible(False)

        axis_y = QValueAxis()
        axis_y.setRange(min(-1.0, mn - pad), max(1.0, mx + pad))
        axis_y.setLabelsColor(_ax_c)
        axis_y.setLabelsFont(_ax_f)
        axis_y.setGridLineColor(QColor("#2e3238"))
        axis_y.setLabelFormat("%.1f%%")
        axis_y.setTickCount(5)

        chart = QChart()
        chart.addSeries(series)
        chart.setBackgroundBrush(_bg)
        chart.setBackgroundVisible(True)
        chart.setDropShadowEnabled(False)
        chart.setBackgroundRoundness(0)
        chart.legend().hide()
        chart.setContentsMargins(0, 0, 0, 0)
        chart.layout().setContentsMargins(0, 0, 0, 0)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        self._bar_chart_view.setChart(chart)
        self._bar_chart_view.setBackgroundBrush(_bg)
        self._bar_chart_view.viewport().update()

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
        viz_items = []

        COLORS = ["#f7931a","#627eea","#9945ff","#f0b90b","#00adef",
                  "#e84142","#ff007a","#2775ca","#26a17b","#ff6b35"]

        def _assign_colors(n, colors):
            """Répartit les couleurs pour éviter que deux teintes proches se touchent."""
            if n == 0:
                return []
            if n >= len(colors):
                # Intercaler les couleurs : prendre 1 sur 2 puis le reste
                pool = colors * ((n // len(colors)) + 1)
            else:
                pool = colors
            # Réorganiser en prenant alternativement début/fin de la liste
            result = []
            left, right = 0, len(pool) - 1
            toggle = True
            while len(result) < n:
                if toggle:
                    result.append(pool[left]); left += 1
                else:
                    result.append(pool[right]); right -= 1
                toggle = not toggle
            return result

        assigned_colors = _assign_colors(len(self._holdings), COLORS)

        # Calculer la valeur totale pour le seuil minimum
        pie_raw = []
        for i, h in enumerate(self._holdings):
            info  = self._prices.get(h.coingecko_id, {})
            price = info.get("price", 0)
            value = h.quantity * price
            pie_value = value if value > 0 else h.quantity * h.avg_buy_price
            pie_raw.append(pie_value)

        total_pie = sum(pie_raw) or 1
        # Seuil minimum : 2% de la valeur totale pour qu'une tranche soit visible
        MIN_PCT = 0.02

        for i, h in enumerate(self._holdings):
            color = assigned_colors[i]
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

            # Viz (bulles / barres)
            viz_val = value if value > 0 else h.quantity * h.avg_buy_price
            viz_items.append((h.symbol.upper(), pnl_p, viz_val, h.coingecko_id))

            # Pie : valeur réelle si prix connu, sinon prix d'achat (fallback)
            pie_value = value if value > 0 else h.quantity * h.avg_buy_price
            if pie_value > 0:
                # Appliquer un minimum de 2% pour les toutes petites tranches
                effective_pie_value = max(pie_value, total_pie * MIN_PCT)
                sl = pie.append(h.symbol, effective_pie_value)
                sl.setColor(QColor(color))
                sl.setLabelVisible(False)

                def _hover(state, s=sl, sym=h.symbol):
                    if state:
                        from PySide6.QtWidgets import QToolTip
                        from PySide6.QtGui import QCursor
                        QToolTip.showText(
                            QCursor.pos(),
                            f"{sym}  {s.percentage() * 100:.1f} %"
                        )
                        s.setExploded(True)
                        s.setExplodeDistanceFactor(0.08)
                    else:
                        from PySide6.QtWidgets import QToolTip
                        QToolTip.hideText()
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
        self._update_viz_charts(viz_items)

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

            fees = tx.fees or 0.0
            fees_item = QTableWidgetItem(f"{fees:,.2f} €" if fees else "—")
            fees_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if fees:
                fees_item.setForeground(QColor("#f59e0b"))
            tbl.setItem(i, 5, fees_item)

            ti2 = QTableWidgetItem(f"{tx.total_eur:,.2f} €")
            ti2.setForeground(QColor(color))
            tbl.setItem(i, 6, ti2)

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
            t_fees     = tx.fees or 0.0
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

        fees_spin = QDoubleSpinBox()
        fees_spin.setRange(0, 999_999)
        fees_spin.setDecimals(2)
        fees_spin.setValue(t_fees)
        fees_spin.setSuffix(" €")
        fees_spin.setMinimumHeight(34)
        form.addRow("Frais :", fees_spin)

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
            fees_spin.value(),
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
        chk_link.setChecked(False)
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
        fees_spin = QDoubleSpinBox(); fees_spin.setRange(0, 9_999_999); fees_spin.setDecimals(2); fees_spin.setSuffix(" €"); fees_spin.setValue(0.0); fees_spin.setMinimumHeight(34)
        note_edit = QLineEdit(); note_edit.setPlaceholderText("Note (optionnel)"); note_edit.setMinimumHeight(34)

        chk_link_sell = QCheckBox("Enregistrer comme revenu dans les transactions")
        chk_link_sell.setChecked(False)
        chk_link_sell.setStyleSheet("color:#c8cdd4; font-size:12px;")

        vl.addWidget(lbl(f"Quantité disponible : {h.quantity}")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix de vente unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(lbl("Frais de transaction :")); vl.addWidget(fees_spin)
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
            ok = sell_holding(h.id, qty, sp, note_edit.text(), fees_spin.value())
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

    def _show_tray_msg(self, title: str, message: str):
        from services import notification_service as _notif
        _notif.send(title, message)

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

