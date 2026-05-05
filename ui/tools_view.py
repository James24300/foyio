"""
Vue Outils — Foyio
4 onglets :
  1. Convertisseur de devises
  2. Calculateur TVA / remise
  3. Comparateur de prix (prix à l'unité/litre)
  4. Calculatrice taux de change
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QFormLayout, QComboBox,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QSizePolicy, QGridLayout, QSpinBox, QScrollArea
)
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from utils.formatters import format_money


def _sep():
    s = QFrame()
    s.setFrameShape(QFrame.HLine)
    s.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
    return s


def _lbl(text, bold=False, color="#848c94"):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{color}; font-size:12px; "
        f"{'font-weight:700;' if bold else ''} background:transparent; border:none;"
    )
    return l


def _result_box(text=""):
    l = QLabel(text)
    l.setAlignment(Qt.AlignCenter)
    l.setWordWrap(True)
    l.setStyleSheet(
        "font-size:20px; font-weight:700; color:#22c55e; "
        "background:#1a2a1a; border-radius:10px; padding:14px; border:none;"
    )
    l.setMinimumHeight(60)
    return l


DEVISES = [
    ("EUR", "Euro", "€"),
    ("USD", "Dollar US", "$"),
    ("GBP", "Livre Sterling", "£"),
    ("CHF", "Franc Suisse", "Fr"),
    ("JPY", "Yen", "¥"),
    ("CAD", "Dollar Canadien", "CA$"),
    ("AUD", "Dollar Australien", "A$"),
    ("CNY", "Yuan", "¥"),
    ("MAD", "Dirham Marocain", "DH"),
    ("TND", "Dinar Tunisien", "DT"),
    ("DZD", "Dinar Algérien", "DA"),
]

# Taux de change de secours (mis à jour si connexion disponible)
_RATES_FALLBACK = {
    "EUR": 1.0, "USD": 1.08, "GBP": 0.86, "CHF": 0.96,
    "JPY": 162.0, "CAD": 1.47, "AUD": 1.65, "CNY": 7.82,
    "MAD": 10.85, "TND": 3.35, "DZD": 145.0,
}
RATES_EUR = dict(_RATES_FALLBACK)
_rates_updated = False
_rates_date = "taux indicatifs"


def _fetch_rates():
    """Récupère les taux en temps réel depuis exchangerate-api.com (gratuit)."""
    global RATES_EUR, _rates_updated, _rates_date
    try:
        import urllib.request, json
        url = "https://api.exchangerate-api.com/v4/latest/EUR"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        rates = data.get("rates", {})
        for code in _RATES_FALLBACK:
            if code in rates:
                RATES_EUR[code] = rates[code]
        _rates_updated = True
        _rates_date = data.get("date", "")
        import logging as _log
        _log.getLogger(__name__).info("Taux de change mis à jour : %s", _rates_date)
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("Taux de change : impossible de mettre à jour (%s), taux indicatifs utilisés", e)


# Mise à jour asynchrone au chargement du module
import threading
threading.Thread(target=_fetch_rates, daemon=True).start()


class ToolsView(QWidget):

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #3d4248; border-radius:10px;
                background:#1e2124;
            }
            QTabBar::tab {
                background:#292d32; color:#7a8494;
                padding:8px 16px; border-radius:8px 8px 0 0;
                font-size:12px; font-weight:600;
            }
            QTabBar::tab:selected { background:#3e4550; color:#c8cdd4; }
            QTabBar::tab:hover    { background:#2e3238; color:#c8cdd4; }
        """)

        self._tabs.addTab(self._build_currency_tab(),   "  Devises")
        self._tabs.addTab(self._build_tva_tab(),        "  TVA / Remise")
        self._tabs.addTab(self._build_exchange_tab(),   "  Taux de change")
        self._tabs.addTab(self._build_loan_tab(),       "  Prêt")
        self._tabs.addTab(self._build_budget_tab(),     "  Budget 50/30/20")
        self._tabs.addTab(self._build_compound_tab(),   "  Intérêts")
        self._tabs.addTab(self._build_fiscal_tab(),    "  Rapport fiscal")
        self._tabs.addTab(self._build_software_tab(),   "  Logiciels")

        layout.addWidget(self._tabs)

    # ─────────────────────────────────────────────
    # ONGLET 1 : Convertisseur de devises
    # ─────────────────────────────────────────────
    def _build_currency_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addWidget(_lbl("Convertisseur de devises", bold=True, color="#c8cdd4"))
        layout.addWidget(_lbl(
            "Taux indicatifs — pour des taux en temps réel, consultez votre banque.",
            color="#5a6472"
        ))
        layout.addWidget(_sep())

        form = QFormLayout()
        form.setSpacing(10)

        self._curr_amount = QLineEdit()
        self._curr_amount.setMinimumHeight(36)

        self._curr_from = QComboBox()
        self._curr_to   = QComboBox()
        for code, name, symbol in DEVISES:
            self._curr_from.addItem(f"{code} — {name}", code)
            self._curr_to.addItem(f"{code} — {name}", code)
        self._curr_to.setCurrentIndex(1)  # USD par défaut
        self._curr_from.setMinimumHeight(36)
        self._curr_to.setMinimumHeight(36)

        form.addRow(_lbl("Montant (€) :"),      self._curr_amount)
        form.addRow(_lbl("De :"),           self._curr_from)
        form.addRow(_lbl("Vers :"),         self._curr_to)
        layout.addLayout(form)

        btn = QPushButton("  Convertir")
        btn.setMinimumHeight(38)
        btn.clicked.connect(self._convert_currency)
        layout.addWidget(btn)

        self._curr_result = _result_box("—")
        layout.addWidget(self._curr_result)

        # Tableau des taux croisés
        layout.addWidget(_sep())
        self._rates_date_lbl = _lbl("Chargement des taux...", color="#5a6472")
        layout.addWidget(_lbl("Taux EUR", bold=True, color="#848c94"))
        layout.addWidget(self._rates_date_lbl)
        tbl = QTableWidget(len(DEVISES), 2)
        tbl.setHorizontalHeaderLabels(["Devise", "1 EUR ="])
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setMaximumHeight(220)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.setStyleSheet(
            "QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }"
            "QTableWidget::item { border-bottom:1px solid #292d32; padding:4px 8px; }"
            "QHeaderView::section { background:#292d32; color:#7a8494; border:none; "
            "border-bottom:1px solid #3a3f47; padding:4px 8px; }"
        )
        self._rates_tbl = tbl
        self._populate_rates_table()
        layout.addWidget(tbl)

        # Rafraîchir après chargement async
        from PySide6.QtCore import QTimer
        self._rates_timer = QTimer()
        self._rates_timer.setSingleShot(True)
        self._rates_timer.timeout.connect(self._refresh_rates_table)
        self._rates_timer.start(3000)
        layout.addStretch()
        return tab

    def _populate_rates_table(self):
        for i, (code, name, symbol) in enumerate(DEVISES):
            self._rates_tbl.setItem(i, 0, QTableWidgetItem(f"{symbol} {code} — {name}"))
            rate = RATES_EUR.get(code, 1.0)
            r_item = QTableWidgetItem(f"{rate:,.4f} {code}")
            r_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            r_item.setForeground(QColor("#22c55e"))
            self._rates_tbl.setItem(i, 1, r_item)

    def _refresh_rates_table(self):
        """Rafraîchit le tableau après mise à jour async des taux."""
        self._populate_rates_table()
        if _rates_updated and _rates_date:
            self._rates_date_lbl.setText(f"Taux mis à jour le {_rates_date}")
            self._rates_date_lbl.setStyleSheet(
                "color:#22c55e; font-size:11px; background:transparent; border:none;"
            )
        else:
            self._rates_date_lbl.setText("Taux indicatifs (pas de connexion)")
            self._rates_date_lbl.setStyleSheet(
                "color:#f59e0b; font-size:11px; background:transparent; border:none;"
            )

    def _convert_currency(self):
        amount   = float(self._curr_amount.text().replace(',', '.') or 0)
        code_from = self._curr_from.currentData()
        code_to   = self._curr_to.currentData()
        rate_from = RATES_EUR.get(code_from, 1.0)
        rate_to   = RATES_EUR.get(code_to,   1.0)
        # Convertir via EUR
        eur = amount / rate_from
        result = eur * rate_to
        sym_to = next((s for c,n,s in DEVISES if c == code_to), "")
        sym_from = next((s for c,n,s in DEVISES if c == code_from), "")
        self._curr_result.setText(
            f"{amount:,.2f} {sym_from} {code_from}\n"
            f"= {result:,.4f} {sym_to} {code_to}"
        )

    # ─────────────────────────────────────────────
    # ONGLET 2 : TVA / Remise
    # ─────────────────────────────────────────────
    def _build_tva_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addWidget(_lbl("Calculateur TVA & Remise", bold=True, color="#c8cdd4"))
        layout.addWidget(_sep())

        # ── TVA ──
        layout.addWidget(_lbl("TVA", bold=True, color="#848c94"))
        tva_form = QFormLayout()
        tva_form.setSpacing(10)

        self._tva_ht = QLineEdit()
        self._tva_ht.setMinimumHeight(36)

        self._tva_rate = QComboBox()
        for rate in ["20 % (taux normal)", "10 % (taux intermédiaire)",
                     "5,5 % (taux réduit)", "2,1 % (taux super réduit)"]:
            self._tva_rate.addItem(rate, float(rate.split()[0].replace(",",".")))
        self._tva_rate.setMinimumHeight(36)

        tva_form.addRow(_lbl("Prix HT (€) :"), self._tva_ht)
        tva_form.addRow(_lbl("Taux TVA :"), self._tva_rate)
        layout.addLayout(tva_form)

        btn_tva = QPushButton("  Calculer la TVA")
        btn_tva.setMinimumHeight(36)
        btn_tva.clicked.connect(self._calc_tva)
        layout.addWidget(btn_tva)

        self._tva_result = _result_box("—")
        layout.addWidget(self._tva_result)

        layout.addWidget(_sep())

        # ── Remise ──
        layout.addWidget(_lbl("Remise / Soldes", bold=True, color="#848c94"))
        rem_form = QFormLayout()
        rem_form.setSpacing(10)

        self._rem_price = QLineEdit()
        self._rem_price.setMinimumHeight(36)

        self._rem_pct = QLineEdit()
        self._rem_pct.setMinimumHeight(36)

        rem_form.addRow(_lbl("Prix initial (€) :"), self._rem_price)
        rem_form.addRow(_lbl("Remise (%) :"),       self._rem_pct)
        layout.addLayout(rem_form)

        btn_rem = QPushButton("  Calculer la remise")
        btn_rem.setMinimumHeight(36)
        btn_rem.clicked.connect(self._calc_remise)
        layout.addWidget(btn_rem)

        self._rem_result = _result_box("—")
        layout.addWidget(self._rem_result)
        layout.addStretch()
        return tab

    def _calc_tva(self):
        ht   = float(self._tva_ht.text().replace(',', '.') or 0)
        rate = self._tva_rate.currentData()
        tva  = ht * rate / 100
        ttc  = ht + tva
        self._tva_result.setText(
            f"HT : {ht:,.2f} €\n"
            f"TVA ({rate}%) : +{tva:,.2f} €\n"
            f"TTC : {ttc:,.2f} €"
        )
        self._tva_result.setStyleSheet(
            "font-size:15px; font-weight:700; color:#c8cdd4; "
            "background:#292d32; border-radius:10px; padding:14px; border:none;"
        )

    def _calc_remise(self):
        price   = float(self._rem_price.text().replace(',', '.') or 0)
        pct     = float(self._rem_pct.text().replace(',', '.') or 0)
        remise  = price * pct / 100
        final   = price - remise
        self._rem_result.setText(
            f"Prix initial : {price:,.2f} €\n"
            f"Remise ({pct}%) : -{remise:,.2f} €\n"
            f"Prix final : {final:,.2f} €"
        )
        self._rem_result.setStyleSheet(
            "font-size:15px; font-weight:700; color:#22c55e; "
            "background:#1a2a1a; border-radius:10px; padding:14px; border:none;"
        )

    # ─────────────────────────────────────────────
    # ONGLET 3 : Comparateur de prix
    # ─────────────────────────────────────────────
    def _build_price_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addWidget(_lbl("Comparateur de prix à l'unité", bold=True, color="#c8cdd4"))
        layout.addWidget(_lbl(
            "Comparez jusqu'à 4 produits — le moins cher est mis en évidence.",
            color="#5a6472"
        ))
        layout.addWidget(_sep())

        # Unité de référence
        unit_row = QHBoxLayout()
        unit_row.addWidget(_lbl("Unité de référence :"))
        self._price_unit = QComboBox()
        for u in ["100g", "1kg", "1L", "100mL", "1 unité", "1m", "1m²"]:
            self._price_unit.addItem(u, u)
        self._price_unit.setMinimumHeight(34)
        unit_row.addWidget(self._price_unit)
        unit_row.addStretch()
        layout.addLayout(unit_row)

        # Grille de produits
        self._price_rows = []
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.addWidget(_lbl("Produit", bold=True), 0, 0)
        grid.addWidget(_lbl("Prix (€)", bold=True), 0, 1)
        grid.addWidget(_lbl("Quantité", bold=True), 0, 2)
        grid.addWidget(_lbl("Unité", bold=True), 0, 3)

        units = ["g", "kg", "mL", "L", "unité(s)", "m", "m²"]
        for i in range(4):
            name = QLineEdit()
            name.setPlaceholderText(f"Produit {i+1}")
            name.setMinimumHeight(34)
            price = QLineEdit()
            price.setMinimumHeight(34)
            qty = QLineEdit()
            qty.setMinimumHeight(34)
            unit = QComboBox()
            for u in units:
                unit.addItem(u, u)
            unit.setMinimumHeight(34)
            grid.addWidget(name,  i+1, 0)
            grid.addWidget(price, i+1, 1)
            grid.addWidget(qty,   i+1, 2)
            grid.addWidget(unit,  i+1, 3)
            self._price_rows.append((name, price, qty, unit))

        layout.addLayout(grid)

        btn = QPushButton("  Comparer")
        btn.setMinimumHeight(38)
        btn.clicked.connect(self._compare_prices)
        layout.addWidget(btn)

        self._price_result_tbl = QTableWidget(0, 3)
        self._price_result_tbl.setHorizontalHeaderLabels(
            ["Produit", "Prix unitaire", ""]
        )
        self._price_result_tbl.verticalHeader().setVisible(False)
        self._price_result_tbl.setShowGrid(False)
        self._price_result_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._price_result_tbl.setMaximumHeight(160)
        self._price_result_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._price_result_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._price_result_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._price_result_tbl.setColumnWidth(2, 80)
        self._price_result_tbl.setStyleSheet(
            "QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }"
            "QTableWidget::item { border-bottom:1px solid #292d32; padding:4px 8px; }"
            "QHeaderView::section { background:#292d32; color:#7a8494; border:none; "
            "border-bottom:1px solid #3a3f47; padding:4px 8px; }"
        )
        layout.addWidget(self._price_result_tbl)
        layout.addStretch()
        return tab

    def _compare_prices(self):
        ref_unit = self._price_unit.currentData()

        # Facteurs de conversion vers l'unité de référence
        conversions = {
            ("g",       "100g"):  100,
            ("g",       "1kg"):   1000,
            ("kg",      "100g"):  0.1,
            ("kg",      "1kg"):   1,
            ("mL",      "100mL"): 100,
            ("mL",      "1L"):    1000,
            ("L",       "100mL"): 0.1,
            ("L",       "1L"):    1,
            ("unité(s)","1 unité"): 1,
            ("m",       "1m"):    1,
            ("m²",      "1m²"):   1,
        }

        results = []
        for name_w, price_w, qty_w, unit_w in self._price_rows:
            name  = name_w.text().strip() or "—"
            price = float(price_w.text().replace(',','.') or 0)
            qty   = float(qty_w.text().replace(',','.') or 0)
            unit  = unit_w.currentData()
            factor = conversions.get((unit, ref_unit))
            if factor and qty > 0:
                unit_price = price / qty * factor
                results.append((name, unit_price))

        if not results:
            return

        results.sort(key=lambda x: x[1])
        best = results[0][1]

        self._price_result_tbl.setRowCount(len(results))
        for i, (name, unit_price) in enumerate(results):
            self._price_result_tbl.setItem(i, 0, QTableWidgetItem(name))
            up_item = QTableWidgetItem(f"{unit_price:.4f} € / {ref_unit}")
            up_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            is_best = abs(unit_price - best) < 0.0001
            up_item.setForeground(QColor("#22c55e" if is_best else "#c8cdd4"))
            self._price_result_tbl.setItem(i, 1, up_item)
            badge = QTableWidgetItem("✓ Meilleur prix" if is_best else "")
            badge.setForeground(QColor("#22c55e"))
            badge.setTextAlignment(Qt.AlignCenter)
            self._price_result_tbl.setItem(i, 2, badge)

    # ─────────────────────────────────────────────
    # ONGLET 4 : Calculatrice taux de change
    # ─────────────────────────────────────────────
    def _build_exchange_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addWidget(_lbl("Calculatrice taux de change", bold=True, color="#c8cdd4"))
        layout.addWidget(_lbl(
            "Calculez le taux réel appliqué par votre banque et comparez.",
            color="#5a6472"
        ))
        layout.addWidget(_sep())

        form = QFormLayout()
        form.setSpacing(10)

        self._xr_sent = QLineEdit()
        self._xr_sent.setMinimumHeight(36)

        self._xr_received = QLineEdit()
        self._xr_received.setMinimumHeight(36)

        self._xr_currency = QComboBox()
        for code, name, symbol in DEVISES:
            self._xr_currency.addItem(f"{symbol} {code} — {name}", code)
        self._xr_currency.setCurrentIndex(1)
        self._xr_currency.setMinimumHeight(36)

        self._xr_fees = QLineEdit()
        self._xr_fees.setMinimumHeight(36)
        self._xr_fees.setToolTip("Frais bancaires prélevés")

        form.addRow(_lbl("Montant envoyé (€) :"),     self._xr_sent)
        form.addRow(_lbl("Montant reçu (devise) :"),             self._xr_received)
        form.addRow(_lbl("Devise reçue :"),             self._xr_currency)
        form.addRow(_lbl("Frais prélevés (€) :"),           self._xr_fees)
        layout.addLayout(form)

        btn = QPushButton("  Analyser le taux")
        btn.setMinimumHeight(38)
        btn.clicked.connect(self._analyze_rate)
        layout.addWidget(btn)

        self._xr_result = QLabel("—")
        self._xr_result.setAlignment(Qt.AlignLeft)
        self._xr_result.setWordWrap(True)
        self._xr_result.setStyleSheet(
            "font-size:13px; color:#c8cdd4; background:#292d32; "
            "border-radius:10px; padding:14px; border:none;"
        )
        self._xr_result.setMinimumHeight(120)
        layout.addWidget(self._xr_result)
        layout.addStretch()
        return tab

    def _analyze_rate(self):
        sent     = float(self._xr_sent.text().replace(',', '.') or 0)
        received = float(self._xr_received.text().replace(',', '.') or 0)
        code     = self._xr_currency.currentData()
        fees     = float(self._xr_fees.text().replace(',', '.') or 0)
        sym      = next((s for c,n,s in DEVISES if c == code), "")

        effective_sent = sent - fees
        applied_rate   = received / effective_sent if effective_sent > 0 else 0
        reference_rate = RATES_EUR.get(code, 1.0)
        diff_pct       = ((applied_rate - reference_rate) / reference_rate * 100) \
                         if reference_rate > 0 else 0
        cost_spread    = (reference_rate - applied_rate) / reference_rate * effective_sent \
                         if reference_rate > 0 else 0

        color  = "#22c55e" if diff_pct >= -1 else "#f59e0b" if diff_pct >= -3 else "#ef4444"
        rating = "Excellent" if diff_pct >= -1 else "Acceptable" if diff_pct >= -3 else "Mauvais"

        self._xr_result.setText(
            f"Taux appliqué :  {applied_rate:.4f} {code}/EUR\n"
            f"Taux de référence :  {reference_rate:.4f} {code}/EUR\n"
            f"Écart :  {diff_pct:+.2f}%  →  {rating}\n"
            f"Coût du spread :  ~{cost_spread:.2f} €\n"
            f"Frais totaux (spread + frais) :  ~{cost_spread + fees:.2f} €"
        )
        self._xr_result.setStyleSheet(
            f"font-size:13px; color:{color}; background:#292d32; "
            "border-radius:10px; padding:14px; border:none; line-height:1.6;"
        )

    # ── Simulateur de prêt ────────────────────────────────────────
    def _build_loan_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(_lbl("Simulateur de prêt", bold=True, color="#c8cdd4"))
        layout.addWidget(_sep())
        form = QFormLayout(); form.setSpacing(10)

        self._loan_amount = QLineEdit()
        self._loan_amount.setMinimumHeight(36)

        self._loan_rate = QLineEdit()
        self._loan_rate.setMinimumHeight(36)

        self._loan_duration = QLineEdit()
        self._loan_duration.setMinimumHeight(36)

        self._loan_insurance = QLineEdit()
        self._loan_insurance.setMinimumHeight(36)

        form.addRow(_lbl("Capital (€) :"),        self._loan_amount)
        form.addRow(_lbl("Taux (%) :"),           self._loan_rate)
        form.addRow(_lbl("Durée (mois) :"),          self._loan_duration)
        form.addRow(_lbl("Taux assurance (%) :"),      self._loan_insurance)
        layout.addLayout(form)

        btn = QPushButton("  Calculer"); btn.setMinimumHeight(38)
        btn.clicked.connect(self._calc_loan); layout.addWidget(btn)

        self._loan_result = QLabel("—")
        self._loan_result.setWordWrap(True)
        self._loan_result.setStyleSheet(
            "font-size:13px; color:#c8cdd4; background:#292d32; "
            "border-radius:10px; padding:14px; border:none;"
        )
        layout.addWidget(self._loan_result)
        layout.addWidget(_sep())
        layout.addWidget(_lbl("Tableau d'amortissement (12 premières lignes)", color="#848c94"))

        self._loan_tbl = QTableWidget(0, 5)
        self._loan_tbl.setHorizontalHeaderLabels(["Mois","Mensualité","Capital","Íntérêts","Restant"])
        self._loan_tbl.verticalHeader().setVisible(False)
        self._loan_tbl.setShowGrid(False)
        self._loan_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._loan_tbl.setMaximumHeight(200)
        for i in range(5):
            self._loan_tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        self._loan_tbl.setStyleSheet(
            "QTableWidget{background:#1e2023;color:#c8cdd4;border:none;}"
            "QTableWidget::item{border-bottom:1px solid #292d32;padding:3px 8px;}"
            "QHeaderView::section{background:#292d32;color:#7a8494;border:none;"
            "border-bottom:1px solid #3a3f47;padding:4px 8px;}")
        layout.addWidget(self._loan_tbl)
        layout.addStretch()
        return tab

    def _calc_loan(self):
        capital = float(self._loan_amount.text().replace(',','.') or 0)
        rate_m  = float(self._loan_rate.text().replace(',','.') or 0) / 100 / 12
        n       = int(self._loan_duration.text() or 0)
        ins_m   = capital * float(self._loan_insurance.text().replace(',','.') or 0) / 100 / 12
        mensualité = capital * rate_m / (1 - (1 + rate_m) ** -n) if rate_m > 0 else capital / n
        mensualité_totale = mensualité + ins_m
        cout_total = mensualité_totale * n
        lines = [
            f"Mensualité (hors assurance) : {mensualité:,.2f} euros",
            f"Assurance mensuelle :         {ins_m:,.2f} euros",
            f"Mensualité totale :           {mensualité_totale:,.2f} euros",
            f"Coût total :                  {cout_total:,.2f} euros",
            f"Dont intérêts :               {mensualité*n - capital:,.2f} euros",
            f"Dont assurance :              {ins_m*n:,.2f} euros",
        ]
        self._loan_result.setText("\n".join(lines))
        rows = min(12, n); self._loan_tbl.setRowCount(rows)
        remaining = capital
        for i in range(rows):
            interets = remaining * rate_m
            cap_r    = mensualité - interets
            remaining -= cap_r
            self._loan_tbl.setItem(i, 0, QTableWidgetItem(str(i+1)))
            for j, (val, color) in enumerate([
                (mensualité, "#c8cdd4"), (cap_r, "#22c55e"),
                (interets, "#ef4444"), (max(0, remaining), "#c8cdd4")
            ]):
                item = QTableWidgetItem(f"{val:,.2f}")
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setForeground(QColor(color))
                self._loan_tbl.setItem(i, j+1, item)

    # ── Budget 50/30/20 ───────────────────────────────────────────
    def _build_budget_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(_lbl("Règle budgétaire 50 / 30 / 20", bold=True, color="#c8cdd4"))
        layout.addWidget(_lbl("50% besoins · 30% envies · 20% épargne", color="#5a6472"))
        layout.addWidget(_sep())
        form = QFormLayout(); form.setSpacing(10)

        self._budget_income = QLineEdit()
        self._budget_income.setMinimumHeight(36)

        self._budget_charges = QLineEdit()
        self._budget_charges.setMinimumHeight(36)

        form.addRow(_lbl("Revenu net (€) :"),        self._budget_income)
        form.addRow(_lbl("Charges actuelles (€) :"), self._budget_charges)
        layout.addLayout(form)

        btn = QPushButton("  Calculer mon budget"); btn.setMinimumHeight(38)
        btn.clicked.connect(self._calc_budget); layout.addWidget(btn)

        self._budget_result = QLabel("—")
        self._budget_result.setWordWrap(True)
        self._budget_result.setStyleSheet(
            "font-size:13px; color:#c8cdd4; background:#292d32; "
            "border-radius:10px; padding:16px; border:none;"
        )
        layout.addWidget(self._budget_result)
        layout.addStretch()
        return tab

    def _calc_budget(self):
        income  = float(self._budget_income.text().replace(',','.') or 0)
        charges = float(self._budget_charges.text().replace(',','.') or 0)
        b50 = income * 0.50; b30 = income * 0.30; b20 = income * 0.20
        warn = ""
        if charges > b50:
            warn = f"\n\nATTENTION : Charges trop élevées de {charges - b50:,.0f} euros !"
        lines = [
            f"Besoins essentiels (50%) :  {b50:,.0f} euros",
            f"  Loyer, alimentation, transport, santé",
            f"  Charges actuelles : {charges:,.0f} euros{warn}",
            "",
            f"Envies & loisirs (30%) :    {b30:,.0f} euros",
            f"  Sorties, abonnements, shopping, vacances",
            "",
            f"Épargne & remboursements (20%) : {b20:,.0f} euros",
            f"  Livret, investissements, remboursement dettes",
        ]
        self._budget_result.setText("\n".join(lines))

    # ── Intérêts composés ─────────────────────────────────────────
    def _build_compound_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(_lbl("Calculateur d'intérêts composés", bold=True, color="#c8cdd4"))
        layout.addWidget(_sep())
        form = QFormLayout(); form.setSpacing(10)

        self._cmp_capital = QLineEdit()
        self._cmp_capital.setMinimumHeight(36)

        self._cmp_monthly = QLineEdit()
        self._cmp_monthly.setMinimumHeight(36)

        self._cmp_rate = QLineEdit()
        self._cmp_rate.setMinimumHeight(36)

        self._cmp_years = QLineEdit()
        self._cmp_years.setMinimumHeight(36)

        form.addRow(_lbl("Capital initial (€) :"),   self._cmp_capital)
        form.addRow(_lbl("Versement mensuel :"), self._cmp_monthly)
        form.addRow(_lbl("Taux annuel (%) :"),       self._cmp_rate)
        form.addRow(_lbl("Durée (mois) :"),             self._cmp_years)
        layout.addLayout(form)

        btn = QPushButton("  Calculer"); btn.setMinimumHeight(38)
        btn.clicked.connect(self._calc_compound); layout.addWidget(btn)

        self._cmp_result = QLabel("—")
        self._cmp_result.setWordWrap(True)
        self._cmp_result.setStyleSheet(
            "font-size:13px; color:#22c55e; background:#1a2a1a; "
            "border-radius:10px; padding:16px; border:none;"
        )
        layout.addWidget(self._cmp_result)

        layout.addWidget(_sep())
        layout.addWidget(_lbl("Progression par année", color="#848c94"))
        self._cmp_tbl = QTableWidget(0, 4)
        self._cmp_tbl.setHorizontalHeaderLabels(["Année","Capital total","Versé","Íntérêts"])
        self._cmp_tbl.verticalHeader().setVisible(False)
        self._cmp_tbl.setShowGrid(False)
        self._cmp_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._cmp_tbl.setMaximumHeight(200)
        for i in range(4):
            self._cmp_tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        self._cmp_tbl.setStyleSheet(
            "QTableWidget{background:#1e2023;color:#c8cdd4;border:none;}"
            "QTableWidget::item{border-bottom:1px solid #292d32;padding:3px 8px;}"
            "QHeaderView::section{background:#292d32;color:#7a8494;border:none;"
            "border-bottom:1px solid #3a3f47;padding:4px 8px;}")
        layout.addWidget(self._cmp_tbl)
        layout.addStretch()
        return tab

    def _calc_compound(self):
        capital = float(self._cmp_capital.text().replace(',','.') or 0)
        monthly = float(self._cmp_monthly.text().replace(',','.') or 0)
        rate_m  = float(self._cmp_rate.text().replace(',','.') or 0) / 100 / 12
        years   = int(self._cmp_years.text() or 0)
        bal     = capital
        for m in range(years * 12):
            bal += monthly
            bal *= (1 + rate_m)
        total_verséd   = capital + monthly * years * 12
        total_interests = bal - total_verséd
        gain_pct = (bal / total_verséd - 1) * 100 if total_verséd > 0 else 0
        lines = [
            f"Capital final :      {bal:,.2f} euros",
            f"Total versé :        {total_verséd:,.2f} euros",
            f"Íntérêts generes :   +{total_interests:,.2f} euros",
            f"Gain :               +{gain_pct:.1f}%",
            f"Multiplicateur :     x{bal/total_verséd:.2f}",
        ]
        self._cmp_result.setText("\n".join(lines))
        rows = min(max(years, 0), 20); self._cmp_tbl.setRowCount(rows)
        bal2 = capital
        for yr in range(rows):
            for m in range(12):
                bal2 += monthly; bal2 *= (1 + rate_m)
            verséd = capital + monthly * 12 * (yr + 1)
            inter  = bal2 - verséd
            self._cmp_tbl.setItem(yr, 0, QTableWidgetItem(f"An {yr+1}"))
            for j, (val, col) in enumerate([
                (bal2,"#c8cdd4"), (verséd,"#7a8494"), (max(0,inter),"#22c55e")
            ]):
                item = QTableWidgetItem(f"{val:,.0f} euros")
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setForeground(QColor(col))
                self._cmp_tbl.setItem(yr, j+1, item)


    # ── Logiciels gratuits ────────────────────────────────────────
    def _build_software_tab(self):
        from PySide6.QtWidgets import QScrollArea, QGridLayout
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        outer.addWidget(_lbl("Logiciels gratuits recommandés", bold=True, color="#c8cdd4"))
        outer.addWidget(_lbl(
            "Cliquez sur un bouton pour ouvrir le site officiel de téléchargement.",
            color="#5a6472"
        ))
        outer.addWidget(_sep())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent; border:none;")

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        SOFTWARE = [
            # (catégorie, nom, description, url, couleur)
            ("Intelligence Artificielle",
             "Claude.ai", "Assistant IA par Anthropic — votre assistant Foyio !",
             "https://claude.ai", "#c8cdd4"),

            ("Bureautique",
             "LibreOffice", "Suite bureautique complète (Writer, Calc, Impress...)",
             "https://www.libreoffice.org/download/libreoffice/", "#22c55e"),
            ("Bureautique",
             "OpenOffice", "Traitement de texte, tableur, présentation",
             "https://www.openoffice.org/fr/Telecharger/", "#22c55e"),
            ("Bureautique",
             "Notepad++", "Éditeur de texte avancé",
             "https://notepad-plus-plus.org/downloads/", "#22c55e"),

            ("PDF",
             "Adobe Acrobat Reader", "Lecteur PDF officiel Adobe",
             "https://get.adobe.com/fr/reader/", "#ef4444"),
            ("PDF",
             "Foxit PDF Reader", "Lecteur PDF rapide et léger",
             "https://www.foxit.com/fr/pdf-reader/", "#ef4444"),
            ("PDF",
             "PDF24 Creator", "Créer, fusionner et éditer des PDF",
             "https://tools.pdf24.org/fr/creator", "#ef4444"),

            ("Compression",
             "7-Zip", "Archiveur gratuit et open source (alternative à WinRAR)",
             "https://www.7-zip.org/download.html", "#f59e0b"),
            ("Compression",
             "WinRAR", "Gestionnaire d'archives (30 jours gratuit, puis fonctionnel)",
             "https://www.rarlab.com/download.htm", "#f59e0b"),
            ("Compression",
             "PeaZip", "Archiveur gratuit multi-formats",
             "https://peazip.github.io/", "#f59e0b"),

            ("Sécurité",
             "Avast Free", "Antivirus gratuit",
             "https://www.avast.com/fr-fr/free-antivirus-download", "#8b5cf6"),
            ("Sécurité",
             "Malwarebytes", "Anti-malware (version gratuite)",
             "https://fr.malwarebytes.com/mwb-download/", "#8b5cf6"),
            ("Sécurité",
             "Bitwarden", "Gestionnaire de mots de passe open source",
             "https://bitwarden.com/download/", "#8b5cf6"),

            ("Multimédia",
             "VLC Media Player", "Lecteur multimédia universel",
             "https://www.videolan.org/vlc/", "#06b6d4"),
            ("Multimédia",
             "GIMP", "Éditeur d'images professionnel",
             "https://www.gimp.org/downloads/", "#06b6d4"),
            ("Multimédia",
             "Audacity", "Éditeur audio gratuit",
             "https://www.audacityteam.org/download/", "#06b6d4"),

            ("Utilitaires",
             "CCleaner Free", "Nettoyage et optimisation du PC",
             "https://www.ccleaner.com/ccleaner/download", "#ec4899"),
            ("Utilitaires",
             "Everything", "Recherche de fichiers ultra-rapide",
             "https://www.voidtools.com/downloads/", "#ec4899"),
            ("Utilitaires",
             "TreeSize Free", "Analyse l'espace disque",
             "https://www.jam-software.com/treesize_free", "#ec4899"),
        ]

        # Grouper par catégorie
        categories = {}
        for cat, name, desc, url, color in SOFTWARE:
            categories.setdefault(cat, []).append((name, desc, url, color))

        for cat, items in categories.items():
            # Titre de catégorie
            cat_lbl = QLabel(f"  {cat}")
            cat_lbl.setStyleSheet(
                "font-size:12px; font-weight:700; color:#c8cdd4; "
                "background:#2e3238; border-radius:6px; padding:6px 10px; border:none;"
            )
            layout.addWidget(cat_lbl)

            for name, desc, url, color in items:
                card = QWidget()
                card.setStyleSheet(
                    "QWidget { background:#292d32; border-radius:10px; border:1px solid #3d4248; }"
                    "QWidget:hover { background:#2e3238; border:1px solid #5a6068; }"
                )
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(14, 10, 14, 10)
                card_layout.setSpacing(12)

                # Indicateur couleur
                dot = QLabel()
                dot.setFixedSize(10, 10)
                dot.setStyleSheet(
                    f"background:{color}; border-radius:5px; border:none;"
                )

                # Texte
                text_col = QVBoxLayout()
                text_col.setSpacing(2)
                name_lbl = QLabel(name)
                name_lbl.setStyleSheet(
                    "font-size:13px; font-weight:600; color:#c8cdd4; "
                    "background:transparent; border:none;"
                )
                desc_lbl = QLabel(desc)
                desc_lbl.setStyleSheet(
                    "font-size:11px; color:#7a8494; background:transparent; border:none;"
                )
                text_col.addWidget(name_lbl)
                text_col.addWidget(desc_lbl)

                # Bouton télécharger
                btn = QPushButton("  Télécharger")
                btn.setFixedHeight(30)
                btn.setFixedWidth(120)
                btn.setStyleSheet(
                    f"background:#3e4550; color:{color}; "
                    "border:none; border-radius:6px; "
                    "font-size:11px; font-weight:600;"
                )
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))

                card_layout.addWidget(dot)
                card_layout.addLayout(text_col, 1)
                card_layout.addWidget(btn)
                layout.addWidget(card)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)
        return tab

    # ─────────────────────────────────────────────
    # ONGLET 8 : Rapport fiscal annuel
    # ─────────────────────────────────────────────
    def _build_fiscal_tab(self):
        from datetime import datetime as _dt

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Titre + aide ──
        title_row = QHBoxLayout()
        title_row.addWidget(_lbl("Rapport fiscal annuel", bold=True, color="#c8cdd4"))
        title_row.addStretch()
        _help = QPushButton(" ? Aide")
        _help.setFixedHeight(26)
        _help.setStyleSheet(
            "QPushButton { background:transparent; color:#5a6472; border:1px solid #3d4248; "
            "border-radius:6px; font-size:11px; font-weight:600; padding:0 8px; }"
            "QPushButton:hover { color:#c8cdd4; border-color:#6b7280; }"
        )
        from PySide6.QtWidgets import QMessageBox as _QMB
        _help.clicked.connect(lambda: _QMB.information(
            tab, "Rapport fiscal annuel",
            "Calcule vos revenus, dépenses et solde net pour l'année choisie.\n\n"
            "Le rapport in-app affiche :\n"
            "• Synthèse (3 KPIs)\n"
            "• Ventilation mensuelle\n"
            "• Dépenses par catégorie\n"
            "• Top 10 dépenses\n\n"
            "L'export PDF nécessite reportlab :\n"
            "    python -m pip install reportlab"
        ))
        title_row.addWidget(_help)
        layout.addLayout(title_row)
        layout.addWidget(_sep())

        # ── Barre de contrôle ──
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        ctrl.addWidget(_lbl("Année :"))

        self._fiscal_year = QSpinBox()
        self._fiscal_year.setRange(2015, _dt.now().year + 1)
        self._fiscal_year.setValue(_dt.now().year)
        self._fiscal_year.setFixedHeight(36)
        self._fiscal_year.setFixedWidth(110)
        self._fiscal_year.setStyleSheet(
            "QSpinBox { background:#292d32; color:#c8cdd4; border:1px solid #3d4248; "
            "border-radius:8px; padding:4px 10px; font-size:13px; }"
            "QSpinBox::up-button, QSpinBox::down-button { background:#3e4550; border:none; width:20px; }"
        )
        ctrl.addWidget(self._fiscal_year)

        btn_calc = QPushButton("Calculer")
        btn_calc.setFixedHeight(36)
        btn_calc.setStyleSheet(
            "QPushButton { background:#3b82f6; color:#fff; border:none; "
            "border-radius:8px; font-size:13px; font-weight:700; padding:0 18px; }"
            "QPushButton:hover { background:#2563eb; }"
        )
        btn_calc.clicked.connect(self._generate_fiscal_report)
        ctrl.addWidget(btn_calc)

        self._btn_pdf = QPushButton("Exporter PDF")
        self._btn_pdf.setFixedHeight(36)
        self._btn_pdf.setEnabled(False)
        self._btn_pdf.setStyleSheet(
            "QPushButton { background:#26292e; color:#c8cdd4; border:1px solid #3d4248; "
            "border-radius:8px; font-size:12px; padding:0 14px; }"
            "QPushButton:hover { background:#2e3238; }"
            "QPushButton:disabled { color:#3d4248; border-color:#2e3238; }"
        )
        self._btn_pdf.clicked.connect(self._export_fiscal_pdf)
        ctrl.addWidget(self._btn_pdf)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ── Zone de résultats (scrollable) ──
        self._fiscal_scroll = QScrollArea()
        self._fiscal_scroll.setWidgetResizable(True)
        self._fiscal_scroll.setFrameShape(QFrame.NoFrame)
        self._fiscal_scroll.setStyleSheet("background:transparent;")

        placeholder = QLabel("Sélectionnez une année et cliquez sur Calculer.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color:#5a6472; font-size:13px; background:transparent;")
        self._fiscal_scroll.setWidget(placeholder)
        layout.addWidget(self._fiscal_scroll, 1)

        self._fiscal_report_data = None
        return tab

    def _generate_fiscal_report(self):
        from ui.toast import Toast
        year = self._fiscal_year.value()
        try:
            from services.fiscal_report_service import generate_fiscal_report
            data = generate_fiscal_report(year)
            self._fiscal_report_data = data
            self._show_fiscal_data(year, data)
            self._btn_pdf.setEnabled(True)
        except Exception as e:
            Toast.show(self, f"Erreur : {e}", kind="error")

    def _show_fiscal_data(self, year: int, data: dict):
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 16)
        vl.setSpacing(16)

        # ── KPIs ──
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        def _kpi(label, value, color):
            w = QWidget()
            w.setStyleSheet(
                f"background:#26292e; border-radius:10px; border:1px solid #3a3f47;"
            )
            wl = QVBoxLayout(w)
            wl.setContentsMargins(16, 12, 16, 12)
            wl.setSpacing(4)
            t = QLabel(label)
            t.setStyleSheet("font-size:10px; color:#5a6472; font-weight:600; background:transparent; border:none;")
            v = QLabel(value)
            v.setStyleSheet(f"font-size:18px; font-weight:700; color:{color}; background:transparent; border:none;")
            wl.addWidget(t)
            wl.addWidget(v)
            return w

        net = data["net_balance"]
        net_color = "#22c55e" if net >= 0 else "#ef4444"
        net_sign  = "+" if net >= 0 else ""
        kpi_row.addWidget(_kpi("REVENUS TOTAUX",  f"+{format_money(data['total_income'])}", "#22c55e"))
        kpi_row.addWidget(_kpi("DÉPENSES TOTALES", f"-{format_money(data['total_expense'])}", "#ef4444"))
        kpi_row.addWidget(_kpi("SOLDE NET",        f"{net_sign}{format_money(net)}", net_color))
        vl.addLayout(kpi_row)

        # ── Ventilation mensuelle ──
        vl.addWidget(_lbl("Ventilation mensuelle", bold=True, color="#c8cdd4"))
        tbl_m = QTableWidget(12, 4)
        tbl_m.setHorizontalHeaderLabels(["Mois", "Revenus", "Dépenses", "Solde"])
        tbl_m.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl_m.setShowGrid(False)
        tbl_m.setFrameShape(QFrame.NoFrame)
        tbl_m.verticalHeader().setVisible(False)
        tbl_m.verticalHeader().setDefaultSectionSize(34)
        tbl_m.setFixedHeight(34 * 12 + tbl_m.horizontalHeader().height() + 4)
        hdr = tbl_m.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in [1, 2, 3]:
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            tbl_m.setColumnWidth(c, 110)
        tbl_m.setStyleSheet(
            "QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }"
            "QTableWidget::item { border-bottom:1px solid #26292e; padding:0 8px; }"
            "QHeaderView::section { background:#26292e; color:#7a8494; border:none; "
            "border-bottom:1px solid #3a3f47; padding:5px 8px; font-size:11px; }"
        )
        for r, m in enumerate(data["monthly_breakdown"]):
            tbl_m.setItem(r, 0, QTableWidgetItem(m["month"]))
            inc_item = QTableWidgetItem(f"+{format_money(m['income'])}")
            inc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            inc_item.setForeground(QColor("#22c55e"))
            tbl_m.setItem(r, 1, inc_item)
            exp_item = QTableWidgetItem(f"-{format_money(m['expense'])}")
            exp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            exp_item.setForeground(QColor("#ef4444"))
            tbl_m.setItem(r, 2, exp_item)
            bal = m["balance"]
            bal_item = QTableWidgetItem(f"{'+'if bal>=0 else ''}{format_money(bal)}")
            bal_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bal_item.setForeground(QColor("#22c55e" if bal >= 0 else "#ef4444"))
            tbl_m.setItem(r, 3, bal_item)
        vl.addWidget(tbl_m)

        # ── Dépenses par catégorie ──
        cat_data = [(k, v["expense"]) for k, v in data["category_totals"].items() if v["expense"] > 0]
        if cat_data:
            vl.addWidget(_lbl("Dépenses par catégorie", bold=True, color="#c8cdd4"))
            total_exp = data["total_expense"] or 1
            tbl_c = QTableWidget(len(cat_data), 3)
            tbl_c.setHorizontalHeaderLabels(["Catégorie", "Montant", "% total"])
            tbl_c.setEditTriggers(QTableWidget.NoEditTriggers)
            tbl_c.setShowGrid(False)
            tbl_c.setFrameShape(QFrame.NoFrame)
            tbl_c.verticalHeader().setVisible(False)
            tbl_c.verticalHeader().setDefaultSectionSize(32)
            tbl_c.setFixedHeight(32 * len(cat_data) + tbl_c.horizontalHeader().height() + 4)
            ch = tbl_c.horizontalHeader()
            ch.setSectionResizeMode(0, QHeaderView.Stretch)
            ch.setSectionResizeMode(1, QHeaderView.Fixed); tbl_c.setColumnWidth(1, 120)
            ch.setSectionResizeMode(2, QHeaderView.Fixed); tbl_c.setColumnWidth(2, 80)
            tbl_c.setStyleSheet(tbl_m.styleSheet())
            for r, (cat, amt) in enumerate(cat_data):
                tbl_c.setItem(r, 0, QTableWidgetItem(cat))
                a_item = QTableWidgetItem(f"-{format_money(amt)}")
                a_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                a_item.setForeground(QColor("#ef4444"))
                tbl_c.setItem(r, 1, a_item)
                p_item = QTableWidgetItem(f"{amt / total_exp * 100:.1f}%")
                p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                p_item.setForeground(QColor("#848c94"))
                tbl_c.setItem(r, 2, p_item)
            vl.addWidget(tbl_c)

        # ── Top 10 dépenses ──
        top = data.get("top_expenses", [])
        if top:
            vl.addWidget(_lbl("Top 10 dépenses", bold=True, color="#c8cdd4"))
            tbl_t = QTableWidget(len(top), 4)
            tbl_t.setHorizontalHeaderLabels(["Date", "Description", "Montant", "Catégorie"])
            tbl_t.setEditTriggers(QTableWidget.NoEditTriggers)
            tbl_t.setShowGrid(False)
            tbl_t.setFrameShape(QFrame.NoFrame)
            tbl_t.verticalHeader().setVisible(False)
            tbl_t.verticalHeader().setDefaultSectionSize(32)
            tbl_t.setFixedHeight(32 * len(top) + tbl_t.horizontalHeader().height() + 4)
            th = tbl_t.horizontalHeader()
            th.setSectionResizeMode(1, QHeaderView.Stretch)
            for c_, w_ in [(0, 95), (2, 110), (3, 130)]:
                th.setSectionResizeMode(c_, QHeaderView.Fixed)
                tbl_t.setColumnWidth(c_, w_)
            tbl_t.setStyleSheet(tbl_m.styleSheet())
            for r, exp in enumerate(top):
                tbl_t.setItem(r, 0, QTableWidgetItem(exp["date"]))
                tbl_t.setItem(r, 1, QTableWidgetItem(exp["description"]))
                a_item = QTableWidgetItem(f"-{format_money(exp['amount'])}")
                a_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                a_item.setForeground(QColor("#ef4444"))
                tbl_t.setItem(r, 2, a_item)
                tbl_t.setItem(r, 3, QTableWidgetItem(exp["category"]))
            vl.addWidget(tbl_t)

        vl.addStretch()
        self._fiscal_scroll.setWidget(container)

    def _export_fiscal_pdf(self):
        from ui.toast import Toast
        import os
        if not self._fiscal_report_data:
            return
        year = self._fiscal_year.value()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = os.path.join(desktop, f"rapport_fiscal_{year}.pdf")
        try:
            from services.fiscal_report_service import export_fiscal_pdf
            export_fiscal_pdf(year, filepath=filepath)
            Toast.show(self, f"Rapport fiscal {year} enregistré sur le Bureau", kind="success")
        except ImportError:
            Toast.show(self,
                "reportlab non installé. Lancez : python -m pip install reportlab",
                kind="error")
        except Exception as e:
            Toast.show(self, f"Erreur export PDF : {e}", kind="error")
