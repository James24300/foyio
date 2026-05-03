"""
Vue Prévisions budgétaires.

Projette revenus, dépenses et solde cumulé sur 3, 6 ou 12 mois
en combinant les récurrentes actives et les tendances historiques.
"""
import logging
import os

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame, QSizePolicy, QButtonGroup,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QAreaSeries,
    QValueAxis, QBarCategoryAxis,
)

from utils.formatters import format_money
from ui.dashboard_widgets import CounterAnimation

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLOR_INCOME  = "#22c55e"
COLOR_EXPENSE = "#ef4444"
COLOR_BALANCE = "#3b82f6"
COLOR_HIST    = "#5a6472"


# ── Helpers UI ──────────────────────────────────────────────────────────────────

def _sep():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
    return line


def _kpi_card(title: str, color: str) -> dict:
    widget = QWidget()
    widget.setMinimumHeight(100)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    outer = QHBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    bar = QFrame()
    bar.setFixedWidth(5)
    bar.setStyleSheet(f"background:{color}; border-radius:4px 0 0 4px; border:none;")
    outer.addWidget(bar)

    inner_w = QWidget()
    inner_w.setStyleSheet("background:transparent; border:none;")
    inner = QVBoxLayout(inner_w)
    inner.setContentsMargins(16, 12, 16, 12)
    inner.setSpacing(4)

    title_lbl = QLabel(title.upper())
    title_lbl.setStyleSheet(
        "font-size:10px; font-weight:600; color:#848c94; "
        "letter-spacing:1px; background:transparent; border:none;"
    )
    value_lbl = QLabel("—")
    value_lbl.setStyleSheet(
        f"font-size:22px; font-weight:700; color:{color}; "
        "background:transparent; border:none;"
    )
    sub_lbl = QLabel("")
    sub_lbl.setStyleSheet("font-size:11px; color:#5a6472; background:transparent; border:none;")

    inner.addWidget(title_lbl)
    inner.addWidget(value_lbl)
    inner.addWidget(sub_lbl)
    inner.addStretch()
    outer.addWidget(inner_w, 1)

    widget.setStyleSheet("""
        QWidget { background:#292d32; border-radius:12px; border:1px solid #3d4248; }
        QWidget:hover { background:#2e3238; border:1px solid #5a6068; }
    """)
    return {"widget": widget, "value": value_lbl, "sub": sub_lbl}


def _toggle_btn(label: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setFixedHeight(32)
    btn.setMinimumWidth(48)
    btn.setStyleSheet("""
        QPushButton {
            background:#23272b; border:1px solid #3a3f47;
            border-radius:8px; color:#7a8494; font-size:13px;
            font-weight:600; padding:0 12px;
        }
        QPushButton:checked {
            background:#3b82f6; border-color:#3b82f6; color:#ffffff;
        }
        QPushButton:hover:!checked { background:#2e3238; color:#c8cdd4; }
    """)
    return btn


# ── Vue principale ──────────────────────────────────────────────────────────────

class ForecastView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._months_ahead = 6
        self._counters = []
        self._build_ui()

    # ── Construction ────────────────────────────────────────────────────────────

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

        lbl_title = QLabel("Prévisions budgétaires")
        lbl_title.setStyleSheet(
            "font-size:22px; font-weight:700; color:#e0e4ea; background:transparent;"
        )
        lbl_sub = QLabel(
            "Projection basée sur les récurrentes actives + tendance des 3 derniers mois"
        )
        lbl_sub.setStyleSheet("font-size:12px; color:#5a6472; background:transparent;")
        title_col.addWidget(lbl_title)
        title_col.addWidget(lbl_sub)

        header.addLayout(title_col, 1)

        # Sélecteur de période
        period_group = QButtonGroup(self)
        period_row = QHBoxLayout()
        period_row.setSpacing(6)

        self._btn_3  = _toggle_btn("3 mois")
        self._btn_6  = _toggle_btn("6 mois")
        self._btn_12 = _toggle_btn("12 mois")
        self._btn_6.setChecked(True)

        for btn, months in [(self._btn_3, 3), (self._btn_6, 6), (self._btn_12, 12)]:
            period_group.addButton(btn)
            period_row.addWidget(btn)
            btn.clicked.connect(lambda _, m=months: self._set_horizon(m))

        header.addLayout(period_row)
        main.addLayout(header)
        main.addWidget(_sep())

        # ── 4 cartes KPI ─────────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)

        self._card_income   = _kpi_card("Revenu mensuel moyen", COLOR_INCOME)
        self._card_expense  = _kpi_card("Dépenses mensuelles",  COLOR_EXPENSE)
        self._card_savings  = _kpi_card("Épargne nette",         COLOR_BALANCE)
        self._card_rate     = _kpi_card("Taux d'épargne",        "#f59e0b")

        for card in (self._card_income, self._card_expense,
                     self._card_savings, self._card_rate):
            kpi_row.addWidget(card["widget"])

        main.addLayout(kpi_row)

        # ── Graphique principal ───────────────────────────────────────────────
        self._chart_view = self._build_chart()
        main.addWidget(self._chart_view)

        # ── Légende ──────────────────────────────────────────────────────────
        legend_row = QHBoxLayout()
        legend_row.setSpacing(20)
        legend_row.addStretch()

        for color, label in [
            (COLOR_INCOME,  "Revenus"),
            (COLOR_EXPENSE, "Dépenses"),
            (COLOR_BALANCE, "Solde cumulé"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{color}; font-size:12px; background:transparent; border:none;"
            )
            txt = QLabel(label)
            txt.setStyleSheet("color:#848c94; font-size:12px; background:transparent; border:none;")
            lh = QHBoxLayout()
            lh.setSpacing(4)
            lh.addWidget(dot)
            lh.addWidget(txt)
            legend_row.addLayout(lh)

        # Indicateur prévision
        dot_f = QLabel("╌╌")
        dot_f.setStyleSheet("color:#5a6472; font-size:12px; background:transparent; border:none;")
        txt_f = QLabel("Prévision")
        txt_f.setStyleSheet("color:#5a6472; font-size:12px; background:transparent; border:none;")
        lh_f = QHBoxLayout()
        lh_f.setSpacing(4)
        lh_f.addWidget(dot_f)
        lh_f.addWidget(txt_f)
        legend_row.addLayout(lh_f)
        legend_row.addStretch()
        main.addLayout(legend_row)

        # ── Tableau mensuel ───────────────────────────────────────────────────
        self._table_container = QVBoxLayout()
        self._table_container.setSpacing(4)

        table_header_lbl = QLabel("DÉTAIL MENSUEL")
        table_header_lbl.setStyleSheet(
            "font-size:10px; font-weight:700; color:#5a6472; "
            "letter-spacing:2px; background:transparent;"
        )
        main.addWidget(table_header_lbl)

        # En-têtes colonnes
        header_row = self._table_header_row()
        main.addWidget(header_row)
        main.addWidget(_sep())

        self._table_widget = QWidget()
        self._table_widget.setStyleSheet("background:transparent;")
        table_layout = QVBoxLayout(self._table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(2)
        self._table_layout = table_layout

        main.addWidget(self._table_widget)

        self._info_lbl = QLabel(
            "💡 Les prévisions combinent vos récurrentes actives et la moyenne "
            "de vos 3 derniers mois de transactions variables."
        )
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet(
            "color:#5a6472; font-size:11px; background:#1e2124; "
            "border:1px solid #2e3238; border-radius:8px; padding:10px;"
        )
        main.addWidget(self._info_lbl)
        main.addStretch()

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _build_chart(self) -> QChartView:
        self._series_income_hist  = QLineSeries()
        self._series_income_fcast = QLineSeries()
        self._series_expense_hist = QLineSeries()
        self._series_expense_fcast= QLineSeries()
        self._series_balance      = QLineSeries()

        # Styles
        pen_income_h  = QPen(QColor(COLOR_INCOME),  2)
        pen_income_f  = QPen(QColor(COLOR_INCOME),  2, Qt.DashLine)
        pen_expense_h = QPen(QColor(COLOR_EXPENSE), 2)
        pen_expense_f = QPen(QColor(COLOR_EXPENSE), 2, Qt.DashLine)
        pen_balance   = QPen(QColor(COLOR_BALANCE), 2)

        self._series_income_hist.setPen(pen_income_h)
        self._series_income_fcast.setPen(pen_income_f)
        self._series_expense_hist.setPen(pen_expense_h)
        self._series_expense_fcast.setPen(pen_expense_f)
        self._series_balance.setPen(pen_balance)

        self._chart = QChart()
        for s in (self._series_income_hist, self._series_income_fcast,
                  self._series_expense_hist, self._series_expense_fcast,
                  self._series_balance):
            self._chart.addSeries(s)

        self._axis_x = QBarCategoryAxis()
        self._axis_y = QValueAxis()
        self._axis_y.setLabelFormat("%.0f €")
        self._axis_y.setGridLineColor(QColor("#2e3238"))
        self._axis_y.setLabelsColor(QColor("#5a6472"))

        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)

        for s in (self._series_income_hist, self._series_income_fcast,
                  self._series_expense_hist, self._series_expense_fcast,
                  self._series_balance):
            s.attachAxis(self._axis_x)
            s.attachAxis(self._axis_y)

        self._chart.setBackgroundBrush(QColor("#1e2124"))
        self._chart.layout().setContentsMargins(0, 0, 0, 0)
        self._chart.setBackgroundRoundness(0)
        self._chart.legend().setVisible(False)
        self._chart.setMargins(self._chart.margins().__class__(16, 8, 16, 8))

        self._axis_x.setLabelsColor(QColor("#5a6472"))
        self._axis_x.setGridLineVisible(False)
        self._axis_x.setLinePen(QPen(QColor("#2e3238")))

        chart_view = QChartView(self._chart)
        chart_view.setFixedHeight(300)
        chart_view.setStyleSheet(
            "background:#1e2124; border-radius:12px; border:1px solid #2e3238;"
        )
        chart_view.setRenderHint(QPainter.Antialiasing)
        return chart_view

    def _table_header_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 4, 12, 4)
        rl.setSpacing(0)

        def _h(text, stretch=1, align=Qt.AlignLeft):
            lbl = QLabel(text.upper())
            lbl.setStyleSheet(
                "font-size:10px; font-weight:600; color:#5a6472; "
                "letter-spacing:1px; background:transparent; border:none;"
            )
            lbl.setAlignment(align)
            rl.addWidget(lbl, stretch)

        _h("Mois", 2)
        _h("Revenus",  1, Qt.AlignRight)
        _h("Dépenses", 1, Qt.AlignRight)
        _h("Solde",    1, Qt.AlignRight)
        _h("Cumulé",   1, Qt.AlignRight)
        return row

    # ── Logique ─────────────────────────────────────────────────────────────────

    def _set_horizon(self, months: int):
        self._months_ahead = months
        self.refresh()

    def refresh(self):
        import account_state
        from services.forecast_service import get_forecast

        acc_id = account_state.get_id()
        data = get_forecast(
            months_ahead=self._months_ahead,
            history_months=4,
            account_id=acc_id,
        )
        self._populate(data)

    def _populate(self, data: dict):
        months    = data["months"]
        avg_inc   = data["avg_income"]
        avg_exp   = data["avg_expense"]
        avg_sav   = data["avg_savings"]
        sav_rate  = data["savings_rate"]

        # ── KPI ──────────────────────────────────────────────────────────────
        self._anim(self._card_income["value"],  avg_inc, COLOR_INCOME)
        self._anim(self._card_expense["value"], avg_exp, COLOR_EXPENSE)
        self._anim(self._card_savings["value"], avg_sav,
                   COLOR_BALANCE if avg_sav >= 0 else COLOR_EXPENSE)
        self._card_rate["value"].setText(f"{sav_rate:.1f} %")
        self._card_rate["value"].setStyleSheet(
            f"font-size:22px; font-weight:700; "
            f"color:{'#f59e0b' if sav_rate >= 0 else COLOR_EXPENSE}; "
            "background:transparent; border:none;"
        )

        forecast_months = [m for m in months if m["is_forecast"]]
        if forecast_months:
            total_sav = sum(m["balance"] for m in forecast_months)
            self._card_savings["sub"].setText(
                f"Total prévu sur {len(forecast_months)} mois : {format_money(total_sav)}"
            )

        # ── Graphique ────────────────────────────────────────────────────────
        for s in (self._series_income_hist, self._series_income_fcast,
                  self._series_expense_hist, self._series_expense_fcast,
                  self._series_balance):
            s.clear()

        labels = [m["label"] for m in months]
        self._axis_x.setCategories(labels)

        all_vals = []
        hist_idx = -1  # dernier index historique

        for i, m in enumerate(months):
            x = float(i)
            if not m["is_forecast"]:
                self._series_income_hist.append(x, m["income"])
                self._series_expense_hist.append(x, m["expense"])
                hist_idx = i
            else:
                # Relier au point précédent (jointure historique → prévision)
                if i == hist_idx + 1 and hist_idx >= 0:
                    prev = months[hist_idx]
                    self._series_income_fcast.append(float(hist_idx), prev["income"])
                    self._series_expense_fcast.append(float(hist_idx), prev["expense"])
                self._series_income_fcast.append(x, m["income"])
                self._series_expense_fcast.append(x, m["expense"])

            self._series_balance.append(x, m["cumulative"] or 0)
            all_vals += [m["income"], m["expense"], abs(m["cumulative"] or 0)]

        if all_vals:
            lo = min(min(m["cumulative"] or 0 for m in months), 0)
            hi = max(all_vals) * 1.1
            self._axis_y.setRange(lo * 1.1 if lo < 0 else 0, hi)

        # ── Tableau ───────────────────────────────────────────────────────────
        while self._table_layout.count():
            item = self._table_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for m in months:
            row = self._table_row(m)
            self._table_layout.addWidget(row)

    def _table_row(self, m: dict) -> QWidget:
        is_f = m["is_forecast"]
        balance = m["balance"]

        row = QWidget()
        bg = "#1e2124" if not is_f else "#1a1d21"
        row.setStyleSheet(
            f"QWidget {{ background:{bg}; border-radius:8px; border:1px solid #2e3238; }}"
            "QWidget:hover { background:#23272b; border-color:#3d4248; }"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 8, 12, 8)
        rl.setSpacing(0)

        def _cell(text, stretch=1, color="#c8cdd4", align=Qt.AlignLeft, bold=False):
            lbl = QLabel(text)
            style = f"color:{color}; font-size:12px; background:transparent; border:none;"
            if bold:
                style += " font-weight:700;"
            if is_f:
                style += " font-style:italic;"
            lbl.setStyleSheet(style)
            lbl.setAlignment(align | Qt.AlignVCenter)
            rl.addWidget(lbl, stretch)

        # Icône prévision
        icon = "⟩" if is_f else " "
        label_text = f"{icon} {m['label']}"
        _cell(label_text, 2, "#7aaee8" if is_f else "#c8cdd4")

        _cell(format_money(m["income"]),  1, COLOR_INCOME,
              Qt.AlignRight)
        _cell(format_money(m["expense"]), 1, COLOR_EXPENSE,
              Qt.AlignRight)
        _cell(format_money(balance), 1,
              COLOR_BALANCE if balance >= 0 else COLOR_EXPENSE,
              Qt.AlignRight, bold=True)
        _cell(format_money(m["cumulative"] or 0), 1,
              COLOR_BALANCE if (m["cumulative"] or 0) >= 0 else COLOR_EXPENSE,
              Qt.AlignRight)

        return row

    def _anim(self, label: QLabel, value: float, color: str):
        label.setStyleSheet(
            f"font-size:22px; font-weight:700; color:{color}; "
            "background:transparent; border:none;"
        )
        anim = CounterAnimation(label, value, duration_ms=600)
        anim.start()
        self._counters.append(anim)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self.refresh)
