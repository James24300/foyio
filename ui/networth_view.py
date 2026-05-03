"""
Vue Patrimoine Net — actifs (comptes + épargne + crypto) moins passifs (prêts).
"""
import logging
import os

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QColor
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries, QPieSlice,
)

from utils.formatters import format_money
from ui.dashboard_widgets import CounterAnimation

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Palette cohérente avec le reste de l'app
COLOR_ASSETS      = "#22c55e"   # vert
COLOR_LIABILITIES = "#ef4444"   # rouge
COLOR_NET         = "#3b82f6"   # bleu
COLOR_ACCOUNTS    = "#6366f1"   # indigo
COLOR_SAVINGS     = "#14b8a6"   # teal
COLOR_CRYPTO      = "#f59e0b"   # ambre
COLOR_LOANS       = "#ef4444"   # rouge


# ── Thread de récupération des prix crypto ─────────────────────────────────────

class _CryptoPriceFetcher(QThread):
    done = Signal(dict)

    def __init__(self, coingecko_ids: list[str]):
        super().__init__()
        self._ids = coingecko_ids

    def run(self):
        try:
            from services.crypto_service import get_prices
            self.done.emit(get_prices(self._ids))
        except Exception:
            self.done.emit({})


# ── Widgets helpers ─────────────────────────────────────────────────────────────

def _sep():
    """Séparateur horizontal léger."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
    return line


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "font-size:10px; font-weight:700; color:#5a6472; "
        "letter-spacing:2px; background:transparent;"
    )
    return lbl


def _kpi_card(title: str, color: str) -> dict:
    """Carte KPI (titre + grande valeur)."""
    widget = QWidget()
    widget.setMinimumHeight(110)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    outer = QHBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    bar = QFrame()
    bar.setFixedWidth(5)
    bar.setStyleSheet(f"background:{color}; border-radius:4px 0 0 4px; border:none;")
    outer.addWidget(bar)

    content = QWidget()
    content.setStyleSheet("background:transparent; border:none;")
    inner = QVBoxLayout(content)
    inner.setContentsMargins(16, 14, 16, 14)
    inner.setSpacing(6)

    title_lbl = QLabel(title.upper())
    title_lbl.setStyleSheet(
        "font-size:10px; font-weight:600; color:#848c94; "
        "letter-spacing:1px; background:transparent; border:none;"
    )

    value_lbl = QLabel("0 €")
    value_lbl.setStyleSheet(
        f"font-size:26px; font-weight:700; color:{color}; "
        "background:transparent; border:none;"
    )

    inner.addWidget(title_lbl)
    inner.addWidget(value_lbl)
    inner.addStretch()
    outer.addWidget(content, 1)

    widget.setStyleSheet("""
        QWidget {
            background:#292d32;
            border-radius:12px;
            border:1px solid #3d4248;
        }
        QWidget:hover {
            background:#2e3238;
            border:1px solid #5a6068;
        }
    """)
    return {"widget": widget, "value": value_lbl}


def _row_item(label: str, amount: float, color: str, sub: str = "") -> QWidget:
    """Ligne d'un poste patrimonial (label + montant)."""
    row = QWidget()
    row.setStyleSheet(
        "QWidget { background:#23272b; border-radius:8px; border:1px solid #2e3238; }"
        "QWidget:hover { background:#292d32; border:1px solid #3d4248; }"
    )
    rl = QHBoxLayout(row)
    rl.setContentsMargins(12, 8, 12, 8)
    rl.setSpacing(8)

    dot = QLabel("●")
    dot.setFixedWidth(14)
    dot.setStyleSheet(f"color:{color}; font-size:10px; background:transparent; border:none;")

    name_lbl = QLabel(label)
    name_lbl.setStyleSheet("color:#c8cdd4; font-size:13px; background:transparent; border:none;")
    if sub:
        name_lbl.setToolTip(sub)

    amt_lbl = QLabel(format_money(abs(amount)))
    sign = "-" if amount < 0 else ""
    amt_lbl.setText(f"{sign}{format_money(abs(amount))}")
    amt_lbl.setStyleSheet(
        f"color:{color}; font-size:13px; font-weight:600; "
        "background:transparent; border:none;"
    )
    amt_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    rl.addWidget(dot)
    rl.addWidget(name_lbl, 1)
    rl.addWidget(amt_lbl)
    return row


def _section_card(title: str, color: str) -> dict:
    """Bloc section avec titre et zone d'items."""
    outer = QWidget()
    outer.setStyleSheet(
        "QWidget { background:#1e2124; border-radius:12px; border:1px solid #2e3238; }"
    )
    vl = QVBoxLayout(outer)
    vl.setContentsMargins(14, 14, 14, 14)
    vl.setSpacing(8)

    header = QHBoxLayout()
    dot = QLabel("●")
    dot.setStyleSheet(f"color:{color}; font-size:12px; background:transparent; border:none;")
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"font-size:13px; font-weight:700; color:{color}; "
        "background:transparent; border:none;"
    )
    total_lbl = QLabel("0 €")
    total_lbl.setStyleSheet(
        f"font-size:13px; font-weight:700; color:{color}; "
        "background:transparent; border:none;"
    )
    total_lbl.setAlignment(Qt.AlignRight)

    header.addWidget(dot)
    header.addSpacing(4)
    header.addWidget(title_lbl, 1)
    header.addWidget(total_lbl)
    vl.addLayout(header)
    vl.addWidget(_sep())

    items_widget = QWidget()
    items_widget.setStyleSheet("background:transparent; border:none;")
    items_layout = QVBoxLayout(items_widget)
    items_layout.setContentsMargins(0, 0, 0, 0)
    items_layout.setSpacing(4)
    vl.addWidget(items_widget)

    return {
        "widget":        outer,
        "items_layout":  items_layout,
        "total_lbl":     total_lbl,
    }


# ── Vue principale ──────────────────────────────────────────────────────────────

class NetWorthView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._crypto_fetcher = None
        self._data = {}
        self._counters = []
        self._build_ui()

    # ── Construction de l'UI ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("background:#1a1d21;")

        container = QWidget()
        container.setStyleSheet("background:#1a1d21;")
        main = QVBoxLayout(container)
        main.setContentsMargins(24, 24, 24, 24)
        main.setSpacing(20)

        # ── En-tête ──────────────────────────────────────────────────────────
        header = QHBoxLayout()

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        lbl_title = QLabel("Patrimoine Net")
        lbl_title.setStyleSheet(
            "font-size:22px; font-weight:700; color:#e0e4ea; background:transparent;"
        )

        self._lbl_networth = QLabel("— €")
        self._lbl_networth.setStyleSheet(
            "font-size:38px; font-weight:800; color:#3b82f6; background:transparent;"
        )

        self._lbl_subtitle = QLabel("Actifs − Passifs · Mise à jour à chaque ouverture")
        self._lbl_subtitle.setStyleSheet(
            "font-size:12px; color:#5a6472; background:transparent;"
        )

        title_col.addWidget(lbl_title)
        title_col.addWidget(self._lbl_networth)
        title_col.addWidget(self._lbl_subtitle)

        header.addLayout(title_col, 1)

        btn_refresh = QPushButton("  Actualiser")
        btn_refresh.setIcon(QIcon(os.path.join(BASE_DIR, "icons", "stats.png")))
        btn_refresh.setFixedHeight(36)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background:#23272b; border:1px solid #3a3f47;
                border-radius:8px; color:#c8cdd4; font-size:13px;
                padding:0 14px;
            }
            QPushButton:hover { background:#2e3238; border-color:#5a6068; }
        """)
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh, 0, Qt.AlignTop)

        main.addLayout(header)
        main.addWidget(_sep())

        # ── 3 cartes KPI ─────────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        self._card_assets      = _kpi_card("Total Actifs",       COLOR_ASSETS)
        self._card_liabilities = _kpi_card("Total Passifs",      COLOR_LIABILITIES)
        self._card_net         = _kpi_card("Patrimoine Net",      COLOR_NET)

        for card in (self._card_assets, self._card_liabilities, self._card_net):
            kpi_row.addWidget(card["widget"])

        main.addLayout(kpi_row)

        # ── 2 colonnes : Actifs | Passifs ─────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.setAlignment(Qt.AlignTop)

        # Colonne Actifs
        self._col_assets = QVBoxLayout()
        self._col_assets.setSpacing(12)
        self._col_assets.setAlignment(Qt.AlignTop)

        lbl_assets = QLabel("ACTIFS")
        lbl_assets.setStyleSheet(
            "font-size:11px; font-weight:700; color:#22c55e; "
            "letter-spacing:2px; background:transparent;"
        )
        self._col_assets.addWidget(lbl_assets)

        self._sec_accounts = _section_card("Comptes bancaires", COLOR_ACCOUNTS)
        self._sec_savings   = _section_card("Objectifs d'épargne", COLOR_SAVINGS)
        self._sec_crypto    = _section_card("Crypto-monnaies", COLOR_CRYPTO)

        self._col_assets.addWidget(self._sec_accounts["widget"])
        self._col_assets.addWidget(self._sec_savings["widget"])
        self._col_assets.addWidget(self._sec_crypto["widget"])

        assets_wrap = QWidget()
        assets_wrap.setStyleSheet("background:transparent;")
        assets_wrap.setLayout(self._col_assets)

        # Colonne Passifs
        self._col_liabilities = QVBoxLayout()
        self._col_liabilities.setSpacing(12)
        self._col_liabilities.setAlignment(Qt.AlignTop)

        lbl_liab = QLabel("PASSIFS")
        lbl_liab.setStyleSheet(
            "font-size:11px; font-weight:700; color:#ef4444; "
            "letter-spacing:2px; background:transparent;"
        )
        self._col_liabilities.addWidget(lbl_liab)

        self._sec_loans = _section_card("Prêts & Crédits", COLOR_LOANS)
        self._col_liabilities.addWidget(self._sec_loans["widget"])

        # Graphique de répartition
        self._chart_view = self._build_pie_chart()
        self._col_liabilities.addWidget(self._chart_view)
        self._col_liabilities.addStretch()

        liab_wrap = QWidget()
        liab_wrap.setStyleSheet("background:transparent;")
        liab_wrap.setLayout(self._col_liabilities)

        cols.addWidget(assets_wrap, 3)
        cols.addWidget(liab_wrap, 2)

        main.addLayout(cols)
        main.addStretch()

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _build_pie_chart(self) -> QChartView:
        self._pie_series = QPieSeries()
        self._pie_series.setHoleSize(0.45)

        chart = QChart()
        chart.addSeries(self._pie_series)
        chart.setBackgroundBrush(QColor("#1e2124"))
        chart.setMargins(QChart.margins(chart) if False else chart.margins())
        chart.layout().setContentsMargins(0, 0, 0, 0)
        chart.setBackgroundRoundness(0)
        chart.legend().setVisible(False)
        chart.setTitle("Répartition des actifs")
        chart.setTitleFont(chart.titleFont())
        chart.titleFont().setPixelSize(12)

        # Correction du titre via stylesheet
        chart_view = QChartView(chart)
        chart_view.setFixedHeight(240)
        chart_view.setStyleSheet("background:#1e2124; border-radius:12px; border:1px solid #2e3238;")
        chart_view.setRenderHint(chart_view.renderHints().value if False else __import__('PySide6.QtGui', fromlist=['QPainter']).QPainter.Antialiasing)

        self._pie_chart = chart
        return chart_view

    # ── Données ─────────────────────────────────────────────────────────────────

    def refresh(self):
        from services.networth_service import get_net_worth_data
        self._data = get_net_worth_data()
        self._populate(crypto_value=0.0, prices={}, loading=True)

        ids = [h["coingecko_id"] for h in self._data.get("holdings", [])]
        if ids:
            if self._crypto_fetcher and self._crypto_fetcher.isRunning():
                self._crypto_fetcher.quit()
            self._crypto_fetcher = _CryptoPriceFetcher(ids)
            self._crypto_fetcher.done.connect(self._on_crypto_prices)
            self._crypto_fetcher.start()
        else:
            self._populate(crypto_value=0.0, prices={}, loading=False)

    def _on_crypto_prices(self, prices: dict):
        holdings = self._data.get("holdings", [])
        crypto_value = sum(
            h["quantity"] * prices.get(h["coingecko_id"], {}).get("price", 0)
            for h in holdings
        )
        self._data["crypto_prices"] = prices
        self._data["crypto_value"]  = round(crypto_value, 2)
        self._populate(crypto_value=crypto_value, prices=prices, loading=False)

    def _populate(self, crypto_value: float, prices: dict, loading: bool):
        data = self._data
        accounts = data.get("accounts", [])
        savings  = data.get("savings",  [])
        loans    = data.get("loans",    [])
        holdings = data.get("holdings", [])

        total_accounts = data.get("total_accounts", 0.0)
        total_savings  = data.get("total_savings",  0.0)
        total_loans    = data.get("total_loans",    0.0)
        total_assets   = round(total_accounts + total_savings + crypto_value, 2)
        net_worth      = round(total_assets - total_loans, 2)

        # ── KPI cards ────────────────────────────────────────────────────────
        self._animate_value(self._card_assets["value"],      total_assets, COLOR_ASSETS)
        self._animate_value(self._card_liabilities["value"], -total_loans, COLOR_LIABILITIES)
        self._animate_value(self._card_net["value"],          net_worth,   COLOR_NET)
        self._animate_value(self._lbl_networth,               net_worth,   COLOR_NET,
                            font_size="38px")

        # ── Comptes ───────────────────────────────────────────────────────────
        self._fill_section(
            self._sec_accounts,
            [(a["name"], a["balance"], a["color"]) for a in accounts],
            total_accounts,
            COLOR_ACCOUNTS,
        )

        # ── Épargne ───────────────────────────────────────────────────────────
        self._fill_section(
            self._sec_savings,
            [(s["name"], s["amount"], COLOR_SAVINGS) for s in savings],
            total_savings,
            COLOR_SAVINGS,
        )

        # ── Crypto ────────────────────────────────────────────────────────────
        if loading:
            crypto_items = [("Chargement des prix…", 0.0, "#5a6472")]
        else:
            crypto_items = []
            for h in holdings:
                price = prices.get(h["coingecko_id"], {}).get("price", 0)
                value = h["quantity"] * price
                crypto_items.append((
                    f"{h['name']} ({h['symbol'].upper()})",
                    value,
                    COLOR_CRYPTO,
                ))

        self._fill_section(
            self._sec_crypto,
            crypto_items,
            crypto_value if not loading else None,
            COLOR_CRYPTO,
        )

        # ── Prêts ─────────────────────────────────────────────────────────────
        self._fill_section(
            self._sec_loans,
            [(l["name"], -l["remaining"], COLOR_LOANS) for l in loans],
            -total_loans if loans else 0.0,
            COLOR_LOANS,
        )

        # ── Graphique ─────────────────────────────────────────────────────────
        self._update_pie(total_accounts, total_savings, crypto_value)

    def _fill_section(self, sec: dict, items: list, total, color: str):
        layout = sec["items_layout"]
        # Vider les items existants
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            empty = QLabel("Aucun élément")
            empty.setStyleSheet("color:#5a6472; font-size:12px; background:transparent; border:none;")
            layout.addWidget(empty)
        else:
            for label, amount, c in items:
                layout.addWidget(_row_item(label, amount, c))

        if total is not None:
            sign = "-" if total < 0 else ""
            sec["total_lbl"].setText(f"{sign}{format_money(abs(total))}")
        else:
            sec["total_lbl"].setText("…")

    def _animate_value(self, label: QLabel, value: float, color: str,
                       font_size: str = "26px"):
        label.setStyleSheet(
            f"font-size:{font_size}; font-weight:{'800' if font_size == '38px' else '700'}; "
            f"color:{color}; background:transparent; border:none;"
        )
        anim = CounterAnimation(label, value, duration_ms=700)
        anim.start()
        self._counters.append(anim)

    def _update_pie(self, accounts: float, savings: float, crypto: float):
        self._pie_series.clear()

        slices_data = [
            ("Comptes",  max(accounts, 0), COLOR_ACCOUNTS),
            ("Épargne",  max(savings,  0), COLOR_SAVINGS),
            ("Crypto",   max(crypto,   0), COLOR_CRYPTO),
        ]
        total = sum(v for _, v, _ in slices_data)

        if total <= 0:
            sl = self._pie_series.append("Aucun actif", 1)
            sl.setColor(QColor("#2e3238"))
            sl.setLabelVisible(False)
            return

        for name, value, color in slices_data:
            if value <= 0:
                continue
            sl = self._pie_series.append(name, value)
            sl.setColor(QColor(color))
            sl.setBorderColor(QColor("#1e2124"))
            sl.setBorderWidth(2)
            pct = value / total * 100
            sl.setLabel(f"{name}  {pct:.0f}%")
            sl.setLabelVisible(pct >= 5)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self.refresh)
