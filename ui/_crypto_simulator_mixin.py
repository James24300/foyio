# No Qt parent needed — mixed into CryptoView which is a QWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QDoubleSpinBox, QSpinBox, QComboBox,
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QValueAxis,
    QDateTimeAxis, QStackedBarSeries, QBarSet, QBarCategoryAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen

from services.crypto_service import simulate_dca, simulate_what_if
from ui.toast import Toast
from ui.crypto_threads import _CompFetcher


class _CryptoSimulatorMixin:

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
