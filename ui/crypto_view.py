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
    QProgressBar
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QPieSeries, QValueAxis, QAreaSeries
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QFont

from utils.formatters import format_money
from utils.icons import get_icon
from ui.toast import Toast
from services.crypto_service import (
    get_holdings, add_holding, sell_holding, delete_holding,
    get_transactions, get_prices, get_portfolio_summary,
    add_alert, get_alerts, delete_alert, check_alerts,
    simulate_dca, simulate_what_if, get_top_coins, search_coins,
    get_price_history,
)


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


class CryptoView(QWidget):

    def __init__(self):
        super().__init__()
        self._prices: dict = {}
        self._holdings: list = []
        self._fetcher = None

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
        self._tabs.addTab(self._build_simulator_tab(),    "  Simulateur")
        self._tabs.addTab(self._build_alerts_tab(),       "  Alertes")
        layout.addWidget(self._tabs, 1)

        # Rafraîchissement auto toutes les 60s
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._fetch_prices)
        self._refresh_timer.start(60_000)

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
        btn_add = QPushButton("  Ajouter une crypto")
        btn_add.setMinimumHeight(36)
        btn_add.setStyleSheet("background:#22c55e; color:#000; border:none; border-radius:8px; font-weight:700; padding:0 16px;")
        btn_add.clicked.connect(self._dialog_add)

        self._btn_sell = QPushButton("  Vendre")
        self._btn_sell.setMinimumHeight(36)
        self._btn_sell.setEnabled(False)
        self._btn_sell.setStyleSheet("background:#ef4444; color:#fff; border:none; border-radius:8px; font-weight:700; padding:0 16px;")
        self._btn_sell.clicked.connect(self._dialog_sell)

        self._btn_del = QPushButton("  Supprimer")
        self._btn_del.setMinimumHeight(36)
        self._btn_del.setEnabled(False)
        self._btn_del.setStyleSheet("background:#2e2020; color:#e89090; border:1px solid #503030; border-radius:8px; padding:0 16px;")
        self._btn_del.clicked.connect(self._delete_holding)

        btn_row.addWidget(btn_add)
        btn_row.addWidget(self._btn_sell)
        btn_row.addWidget(self._btn_del)
        btn_row.addStretch()
        vl.addLayout(btn_row)

        # Tableau
        self._portfolio_table = QTableWidget(0, 8)
        self._portfolio_table.setHorizontalHeaderLabels([
            "", "Crypto", "Quantité", "Prix achat moy.", "Prix actuel",
            "Valeur", "P&L €", "P&L %"
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
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(5, 120)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(6, 110)
        hdr.setSectionResizeMode(7, QHeaderView.Fixed);  self._portfolio_table.setColumnWidth(7, 90)
        self._portfolio_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        self._portfolio_table.itemSelectionChanged.connect(self._on_portfolio_selection)
        vl.addWidget(self._portfolio_table, 1)

        # Graphique camembert
        self._pie_chart_view = QChartView()
        self._pie_chart_view.setRenderHint(QPainter.Antialiasing)
        self._pie_chart_view.setMinimumHeight(200)
        self._pie_chart_view.setMaximumHeight(220)
        self._pie_chart_view.setStyleSheet("background:transparent; border:none;")
        vl.addWidget(self._pie_chart_view)
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
        self._dca_chart = QChartView(); self._dca_chart.setRenderHint(QPainter.Antialiasing); self._dca_chart.setMinimumHeight(200); self._dca_chart.setVisible(False)
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
        self._wi_chart = QChartView(); self._wi_chart.setRenderHint(QPainter.Antialiasing); self._wi_chart.setMinimumHeight(200); self._wi_chart.setVisible(False)
        cl_wi.addWidget(self._wi_chart)
        vl.addWidget(card_wi)
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
        self._alert_type_combo.addItem("Au-dessus de", "above")
        self._alert_type_combo.addItem("En-dessous de", "below")
        self._alert_type_combo.setMinimumHeight(34)

        self._alert_price = QDoubleSpinBox()
        self._alert_price.setRange(0.000001, 9_999_999)
        self._alert_price.setDecimals(2)
        self._alert_price.setSuffix(" €")
        self._alert_price.setMinimumHeight(34)
        self._alert_price.setMinimumWidth(130)

        btn_add_alert = QPushButton("  Ajouter l'alerte")
        btn_add_alert.setMinimumHeight(34)
        btn_add_alert.setStyleSheet("background:#f59e0b; color:#000; border:none; border-radius:8px; font-weight:700; padding:0 12px;")
        btn_add_alert.clicked.connect(self._add_alert)

        for lbl_txt, widget in [("Crypto :", self._alert_holding_combo),
                                 ("Condition :", self._alert_type_combo),
                                 ("Prix cible :", self._alert_price)]:
            col = QVBoxLayout()
            lbl = QLabel(lbl_txt)
            lbl.setStyleSheet("font-size:11px; color:#7a8494;")
            col.addWidget(lbl)
            col.addWidget(widget)
            form_row.addLayout(col)

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

    # ── Chargement données ────────────────────────────────────────────────────
    def load(self):
        self._holdings = get_holdings()
        self._load_portfolio()
        self._load_transactions()
        self._load_alerts()
        self._fetch_prices()

    def refresh(self):
        self.load()

    def _fetch_prices(self):
        if not self._holdings:
            return
        ids = [h.coingecko_id for h in self._holdings]
        self._fetcher = _PriceFetcher(ids)
        self._fetcher.done.connect(self._on_prices_received)
        self._fetcher.start()

    def _on_prices_received(self, prices: dict):
        self._prices = prices
        self._load_portfolio()
        self._update_summary()
        self._check_alerts_now()

    def _update_summary(self):
        summary = get_portfolio_summary(self._holdings, self._prices)
        self._lbl_total.setText(f"{format_money(summary['total_value'])} €")
        self._lbl_invest.setText(f"{format_money(summary['total_invested'])} €")
        pnl = summary['pnl']
        pct = summary['pnl_pct']
        color = "#22c55e" if pnl >= 0 else "#ef4444"
        sign  = "+" if pnl >= 0 else ""
        self._lbl_pnl.setText(f"{sign}{format_money(pnl)} €")
        self._lbl_pnl.setStyleSheet(f"font-size:15px; font-weight:700; color:{color}; background:transparent; border:none;")
        chg = summary['change_24h_eur']
        sign2 = "+" if chg >= 0 else ""
        color2 = "#22c55e" if chg >= 0 else "#ef4444"
        self._lbl_chg24.setText(f"{sign2}{format_money(chg)} €")
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
            tbl.setItem(i, 5, _item(f"{value:,.2f} €" if price else "—"))

            pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"
            tbl.setItem(i, 6, _item(f"{'+' if pnl>=0 else ''}{pnl:,.2f} €", Qt.AlignRight | Qt.AlignVCenter, pnl_c))
            tbl.setItem(i, 7, _item(f"{'+' if pnl_p>=0 else ''}{pnl_p:.1f}%", Qt.AlignRight | Qt.AlignVCenter, pnl_c))

            if value > 0:
                sl = pie.append(h.symbol, value)
                sl.setColor(QColor(color))
                sl.setLabelVisible(True)
                sl.setLabel(f"{h.symbol} {value/max(sum(hh.quantity*(self._prices.get(hh.coingecko_id,{}).get('price',0)) for hh in self._holdings),1)*100:.0f}%")

        chart = QChart()
        chart.addSeries(pie)
        chart.setBackgroundVisible(False)
        chart.legend().setVisible(False)
        chart.setMargins(__import__('PySide6.QtCore', fromlist=['QMargins']).QMargins(0,0,0,0))
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

            tbl.setItem(i, 0, QTableWidgetItem(tx.date.strftime("%d/%m/%Y %H:%M")))
            tbl.setItem(i, 1, QTableWidgetItem(name))
            ti = QTableWidgetItem(type_lbl); ti.setForeground(QColor(color)); tbl.setItem(i, 2, ti)

            qty_str = f"{tx.quantity:,.8f}".rstrip("0").rstrip(".")
            tbl.setItem(i, 3, QTableWidgetItem(qty_str))
            tbl.setItem(i, 4, QTableWidgetItem(f"{tx.price_eur:,.2f} €"))
            ti2 = QTableWidgetItem(f"{tx.total_eur:,.2f} €"); ti2.setForeground(QColor(color)); tbl.setItem(i, 5, ti2)

    def _load_alerts(self):
        holdings_map = {h.id: h for h in self._holdings}
        alerts = get_alerts()
        self._alerts_table.setRowCount(len(alerts))
        self._alert_holding_combo.clear()
        for h in self._holdings:
            self._alert_holding_combo.addItem(f"{h.name} ({h.symbol})", h.id)

        for i, a in enumerate(alerts):
            h = holdings_map.get(a.holding_id)
            name = f"{h.name} ({h.symbol})" if h else "—"
            cond = "▲ Au-dessus de" if a.alert_type == "above" else "▼ En-dessous de"
            price_info = self._prices.get(h.coingecko_id if h else "", {})
            current    = price_info.get("price", 0)

            self._alerts_table.setItem(i, 0, QTableWidgetItem(name))
            self._alerts_table.setItem(i, 1, QTableWidgetItem(cond))
            self._alerts_table.setItem(i, 2, QTableWidgetItem(f"{a.target_price:,.2f} €"))
            self._alerts_table.setItem(i, 3, QTableWidgetItem(f"{current:,.2f} €" if current else "—"))

            btn_del = QPushButton("Supprimer")
            btn_del.setFixedHeight(28)
            btn_del.setStyleSheet("background:#2e2020; color:#e89090; border:1px solid #503030; border-radius:6px; font-size:11px;")
            btn_del.clicked.connect(lambda _, aid=a.id: self._delete_alert(aid))
            self._alerts_table.setCellWidget(i, 4, btn_del)

    def _on_portfolio_selection(self):
        has_sel = bool(self._portfolio_table.selectedItems())
        self._btn_sell.setEnabled(has_sel)
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

        vl.addWidget(lbl("Quantité :")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix d'achat unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(lbl("Note :")); vl.addWidget(note_edit)

        # Pré-remplir le prix depuis l'API
        def _on_coin_selected(idx):
            cid = result_combo.itemData(idx)
            if cid:
                prices = get_prices([cid])
                p = prices.get(cid, {}).get("price", 0)
                if p > 0:
                    price_spin.setValue(p)

        result_combo.currentIndexChanged.connect(_on_coin_selected)

        def _do_search():
            q = search_edit.text().strip()
            if not q:
                return
            results = search_coins(q)
            result_combo.clear()
            for r in results:
                result_combo.addItem(f"{r['name']} ({r['symbol']})", r["id"])
            result_combo.setProperty("_results", results)

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
            add_holding(coin["symbol"], coin["name"], coin["id"], qty, price)
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

        vl.addWidget(lbl(f"Quantité disponible : {h.quantity}")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix de vente unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(lbl("Note :")); vl.addWidget(note_edit)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("  Vendre"); btn_ok.setMinimumHeight(36); btn_ok.setStyleSheet("background:#ef4444; color:#fff; border:none; border-radius:8px; font-weight:700;")
        btn_cancel = QPushButton("Annuler"); btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do_sell():
            ok = sell_holding(h.id, qty_spin.value(), price_spin.value(), note_edit.text())
            if not ok:
                Toast.show(self, "✕  Quantité insuffisante", kind="error"); return
            dlg.accept(); self.load()
            Toast.show(self, f"✓  Vente enregistrée", kind="success")

        btn_ok.clicked.connect(_do_sell)
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

    def _check_alerts_now(self):
        triggered = check_alerts(self._prices)
        for t in triggered:
            direction = "au-dessus" if t["alert_type"] == "above" else "en-dessous"
            msg = (f"{t['name']} ({t['symbol']}) est passé {direction} de "
                   f"{t['target_price']:,.2f} € → Prix actuel : {t['current_price']:,.2f} €")
            Toast.show(self, f"🔔  {msg}", kind="info")
        if triggered:
            self._load_alerts()

    # ── Simulateur DCA ────────────────────────────────────────────────────────
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
        chart.setBackgroundVisible(False)
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
            chart.setBackgroundVisible(False)
            chart.legend().setVisible(False)
            chart.createDefaultAxes()
            self._wi_chart.setChart(chart)
            self._wi_chart.setVisible(True)
