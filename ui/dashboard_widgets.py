import os

from PySide6.QtCharts import (
    QChart,
    QChartView,
    QPieSeries,
    QPieSlice,
    QBarSeries,
    QBarSet,
    QBarCategoryAxis,
    QValueAxis
)

from PySide6.QtGui import QColor, QPainter, QPixmap, QFont
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
    QSizePolicy,

)

from utils.formatters import format_money
from utils.theme import THEME
from utils.icons import get_icon

from PySide6.QtCore import Qt, QMargins, QTimer, QEasingCurve
from PySide6.QtWidgets import QGraphicsOpacityEffect

from services.stats_service import expenses_by_category, monthly_balance

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CounterAnimation:
    """Anime un QLabel de 0 vers une valeur cible (compteur progressif)."""

    def __init__(self, label, target: float, duration_ms: int = 800,
                 prefix: str = "", suffix: str = " €", decimals: int = 2):
        self._label    = label
        self._target   = target
        self._start    = 0.0
        self._current  = 0.0
        self._prefix   = prefix
        self._suffix   = suffix
        self._decimals = decimals
        self._steps    = max(30, duration_ms // 16)  # ~60fps
        self._step     = 0
        self._timer    = QTimer()
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._step = 0
        self._timer.start()

    def _tick(self):
        self._step += 1
        t = self._step / self._steps
        # Easing out cubic
        t = 1 - (1 - t) ** 3
        self._current = self._start + (self._target - self._start) * t
        val = f"{self._current:,.{self._decimals}f}".replace(",", " ").replace(".", ",")
        self._label.setText(f"{self._prefix}{val}{self._suffix}")
        if self._step >= self._steps:
            self._timer.stop()
            # Valeur finale exacte
            val = f"{self._target:,.{self._decimals}f}".replace(",", " ").replace(".", ",")
            self._label.setText(f"{self._prefix}{val}{self._suffix}")




# -------------------------------------------------
# CARD WIDGET
# -------------------------------------------------

def create_card(title, color, icon):
    """Carte KPI moderne avec icône, titre, valeur et barre de couleur latérale."""
    from PySide6.QtWidgets import QFrame

    widget = QWidget()
    widget.setMinimumHeight(110)
    widget.setMaximumHeight(130)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # Layout principal horizontal : barre colorée | contenu
    outer = QHBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    # Barre verticale colorée à gauche
    bar = QFrame()
    bar.setFixedWidth(5)
    bar.setStyleSheet(f"background:{color}; border-radius:4px 0 0 4px; border:none;")
    outer.addWidget(bar)

    # Zone contenu
    content = QWidget()
    content.setStyleSheet("background:transparent; border:none;")
    inner = QVBoxLayout(content)
    inner.setContentsMargins(16, 14, 16, 14)
    inner.setSpacing(8)

    # Ligne du haut : icône + titre
    header = QHBoxLayout()
    header.setSpacing(8)

    icon_label = QLabel()
    icon_label.setFixedSize(24, 24)
    icon_label.setAlignment(Qt.AlignCenter)
    icon_label.setPixmap(get_icon(icon, 20).pixmap(20, 20))
    icon_label.setStyleSheet("background:transparent; border:none;")

    title_label = QLabel(title.upper())
    title_label.setStyleSheet(
        "font-size:10px; font-weight:600; color:#848c94; "
        "letter-spacing:1px; background:transparent; border:none;"
    )

    header.addWidget(icon_label)
    header.addWidget(title_label)
    header.addStretch()
    inner.addLayout(header)

    # Valeur principale
    value_label = QLabel("0 €")
    value_label.setStyleSheet(
        f"font-size:24px; font-weight:700; color:{color}; "
        "background:transparent; border:none;"
    )
    inner.addWidget(value_label)
    inner.addStretch()

    outer.addWidget(content, 1)

    # Style global de la carte
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

    return {
        "widget": widget,
        "value": value_label,
        "bar":   bar,
    }

# -------------------------------------------------
# PIE CHART
# -------------------------------------------------

def create_category_chart(callback=None):

    series = QPieSeries()
    series.setHoleSize(0.60)

    chart = QChart()
    chart.addSeries(series)

    chart.setTitle("")
    chart.setMargins(QMargins(0, 0, 0, 0))
    chart.setTitleFont(QFont("Segoe UI", 11))
    chart.setTitleBrush(QColor("#ffffff"))

    chart.setAnimationOptions(QChart.SeriesAnimations)
    chart.setAnimationDuration(450)

    legend = chart.legend()

    legend.setVisible(True)
    legend.setAlignment(Qt.AlignBottom)
    legend.setLabelColor(QColor("#c8cdd4"))
    legend.setFont(QFont("Segoe UI", 9))

    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)

    chart_view = QChartView(chart)
    chart_view.setRenderHint(QPainter.Antialiasing)

    chart_view.setMinimumHeight(360)
    chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    return chart_view, series

# -------------------------------------------------
# MONTHLY BALANCE CHART
# -------------------------------------------------

def create_month_chart():

    data = monthly_balance()

    if not data:
        data = [("Aucun", 0)]

    set0 = QBarSet("")
    set0.setColor(QColor("#7a8494"))

    for month, value in data:
        set0.append(value)

    series = QBarSeries()
    series.append(set0)
    series.setBarWidth(0.6)

    chart = QChart()
    chart.addSeries(series)

    chart.setMargins(QMargins(2,2,2,2))
    chart.layout().setContentsMargins(10,10,10,10)

    chart.setTitle("Évolution mensuelle")

    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)

    chart.legend().setVisible(False)

    chart.setAnimationOptions(QChart.SeriesAnimations)
    chart.setAnimationDuration(800)

    # AXIS X
    axisX = QBarCategoryAxis()
    months = [month for month, _ in data]
    axisX.append(months)
    axisX.setLabelsColor(QColor("#7a8494"))

    chart.addAxis(axisX, Qt.AlignBottom)
    series.attachAxis(axisX)

    # AXIS Y
    axisY = QValueAxis()
    axisY.setLabelFormat("%d")
    axisY.setTitleText("€")
    axisY.setLabelsColor(QColor("#7a8494"))
    axisY.setGridLineColor(QColor("#3a3f47"))

    if not data:
        data = [("Aucun",0)]

    values = [v for _, v in data]

    max_value = max(values) if values else 0

    if max_value == 0:
        max_value = 1
    
    axisY.setRange(0, max_value * 1.2)

    chart.addAxis(axisY, Qt.AlignLeft)
    series.attachAxis(axisY)

    chart_view = QChartView(chart)
    chart_view.setRenderHint(QPainter.Antialiasing)

    chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    return chart_view

# -------------------------------------------------
# INCOME VS EXPENSE CHART
# -------------------------------------------------

def create_income_expense_chart():

    data = monthly_balance()

    months = []
    income_values = []
    expense_values = []

    for month, value in data:

        months.append(month)

        if value >= 0:
            income_values.append(value)
            expense_values.append(0)
        else:
            income_values.append(0)
            expense_values.append(abs(value))

    income_set = QBarSet("Revenus")
    expense_set = QBarSet("Dépenses")

    income_set.setColor(QColor("#22c55e"))
    expense_set.setColor(QColor("#ef4444"))

    for v in income_values:
        income_set.append(v)

    for v in expense_values:
        expense_set.append(v)

    series = QBarSeries()
    series.setBarWidth(0.6)
    series.append(income_set)
    series.append(expense_set)

    chart = QChart()
    chart.addSeries(series)

    chart.setMargins(QMargins(2,2,2,2))

    chart.setTitle("Revenus vs Dépenses")

    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)

    chart.setAnimationOptions(QChart.SeriesAnimations)
    chart.setAnimationDuration(800)

    axisX = QBarCategoryAxis()
    axisX.append(months)

    chart.addAxis(axisX, Qt.AlignBottom)
    series.attachAxis(axisX)

    axisY = QValueAxis()
    axisY.setLabelFormat("%d")
    axisY.setTitleText("€")

    axisY.setLabelsColor(QColor("#7a8494"))
    axisY.setGridLineColor(QColor("#3a3f47"))

    chart.addAxis(axisY, Qt.AlignLeft)
    series.attachAxis(axisY)

    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignBottom)

    chart_view = QChartView(chart)
    chart_view.setRenderHint(QPainter.Antialiasing)

    chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    return chart_view