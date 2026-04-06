from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QProgressBar, QSizePolicy, QScrollArea,
    QFrame, QGraphicsTextItem, QLayout
)
from PySide6.QtCore import Qt, QRect, QSize, QMargins, QThread, QDateTime
from PySide6.QtCore import Signal
from PySide6.QtCharts import QLineSeries, QAreaSeries, QValueAxis, QChart, QChartView
from PySide6.QtGui import QColor, QFont

from utils.formatters import format_money
from utils.icons import get_icon
from ui.dashboard_widgets import create_card, create_category_chart, CounterAnimation
from services.transaction_service import get_month_summary
from services.stats_service import expenses_by_category
from services.dashboard_service import (
    top_expenses, forecast_balance, biggest_category,
    compare_with_previous, recent_transactions, budget_alerts,
    forecast_income
)
import period_state

DONUT_COLORS = [
    "#22c55e", "#7a8494", "#f59e0b", "#ef4444",
    "#8b5cf6", "#06b6d4", "#f97316", "#ec4899",
    "#14b8a6", "#6366f1", "#84cc16", "#a855f7",
]


class _CryptoPriceFetcher(QThread):
    """Récupère les prix crypto en arrière-plan pour le dashboard."""
    done = Signal(dict)

    def __init__(self, ids):
        super().__init__()
        self._ids = ids

    def run(self):
        try:
            from services.crypto_service import get_prices
            self.done.emit(get_prices(self._ids))
        except Exception:
            self.done.emit({})


class _FlowLayout(QLayout):
    """Layout qui revient à la ligne automatiquement (wrap)."""
    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        if parent:
            self.setContentsMargins(4, 2, 4, 2)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        from PySide6.QtCore import Qt
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test):
        from PySide6.QtCore import QPoint
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        row_h = 0
        for item in self._items:
            w = item.widget()
            if not w:
                continue
            hint = w.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > rect.right() - m.right() and row_h > 0:
                x = rect.x() + m.left()
                y += row_h + self._spacing
                next_x = x + hint.width() + self._spacing
                row_h = 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y() + m.bottom()


class DashboardView(QWidget):

    def __init__(self):
        super().__init__()
        self._total_expense = 0

        main_layout = QVBoxLayout()
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ── Carte solde global tous comptes ──
        self.global_card = create_card("Solde tous comptes", "#22c55e", "wallet.png")
        main_layout.addWidget(self.global_card["widget"])

        # ── Sous-label : nombre de transactions du mois ──
        self._tx_count_label = QLabel()
        self._tx_count_label.setAlignment(Qt.AlignRight)
        self._tx_count_label.setStyleSheet(
            "font-size:11px; color:#5a6472; background:transparent; margin-top:-8px;"
        )
        main_layout.addWidget(self._tx_count_label)

        # ── Cartes KPI (ligne 2 : revenus / dépenses / solde) ──
        cards_layout = QGridLayout()
        cards_layout.setHorizontalSpacing(12)
        self.income_card  = create_card("Revenus",  "#22c55e", "income.png")
        self.expense_card = create_card("Dépenses", "#ef4444", "expense.png")
        self.balance_card = create_card("Solde",    "#7a8494", "balance.png")
        cards_layout.addWidget(self.income_card["widget"],  0, 0)
        cards_layout.addWidget(self.expense_card["widget"], 0, 1)
        cards_layout.addWidget(self.balance_card["widget"], 0, 2)
        main_layout.addLayout(cards_layout)

        # Sous-labels comparaison mois précédent
        cmp_layout = QHBoxLayout()
        cmp_layout.setSpacing(12)
        self._income_cmp  = QLabel()
        self._expense_cmp = QLabel()
        for lbl in (self._income_cmp, self._expense_cmp):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size:11px; color:#6b7280; background:transparent;")
            lbl.setVisible(False)
        cmp_layout.addWidget(self._income_cmp,  1)
        cmp_layout.addWidget(self._expense_cmp, 1)
        cmp_layout.addStretch(1)
        main_layout.addLayout(cmp_layout)

        # ── Santé financière ──
        self.health_label = QLabel()
        self.health_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.health_label)

        self.health_bar = QProgressBar()
        self.health_bar.setMaximum(100)
        self.health_bar.setTextVisible(False)
        self.health_bar.setFixedHeight(10)
        main_layout.addWidget(self.health_bar)

        # ── Mini-widget épargne ──
        self._savings_widget = self._build_savings_widget()
        main_layout.addWidget(self._savings_widget)

        # ── Mini-widget crypto ──
        self._crypto_widget = self._build_crypto_widget()
        self._crypto_widget.setVisible(False)  # masqué si aucun holding
        main_layout.addWidget(self._crypto_widget)

        # ── Projection des revenus ──
        self._income_proj_widget = self._build_income_projection_widget()
        main_layout.addWidget(self._income_proj_widget)

        # ── Graphique évolution du solde ──
        self._balance_chart_title = QLabel("Evolution du solde")
        self._balance_chart_title.setStyleSheet(
            "font-size:12px; font-weight:600; color:#848c94; "
            "background:transparent; letter-spacing:0.5px;"
        )
        main_layout.addWidget(self._balance_chart_title)
        self._balance_chart_view = self._create_balance_chart()
        main_layout.addWidget(self._balance_chart_view)

        # ── Graphique revenus vs dépenses (6 mois) ──
        self._rev_dep_title = QLabel("Revenus vs Dépenses — 6 prochains mois")
        self._rev_dep_title.setStyleSheet(
            "font-size:12px; font-weight:600; color:#848c94; "
            "background:transparent; letter-spacing:0.5px;"
        )
        main_layout.addWidget(self._rev_dep_title)
        self._rev_dep_view = self._create_rev_dep_chart()
        main_layout.addWidget(self._rev_dep_view)
        self._refresh_rev_dep_chart()

        # ── Ligne inférieure : donut + panneau droite ──
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(16)

        # -- Donut (gauche) --
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        self._chart_title = QLabel("Répartition des dépenses")
        self._chart_title.setStyleSheet("font-size:14px; font-weight:600; color:#c8cdd4;")
        self._chart_title.setAlignment(Qt.AlignCenter)
        left_col.addWidget(self._chart_title)

        self.category_chart, self.series = create_category_chart(self.open_category)
        self.category_chart.chart().legend().setVisible(False)
        self.category_chart.setMinimumHeight(260)
        self.category_chart.setMaximumHeight(300)
        left_col.addWidget(self.category_chart)

        self._donut_label = QGraphicsTextItem()
        self._donut_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._donut_label.setDefaultTextColor(QColor("#c8cdd4"))
        self._donut_label.setZValue(10)
        self.category_chart.scene().addItem(self._donut_label)

        # Légende donut
        self._legend_container = QWidget()
        self._legend_container.setStyleSheet("background:transparent;")
        self._legend_flow = _FlowLayout(self._legend_container, spacing=4)

        legend_scroll = QScrollArea()
        legend_scroll.setWidgetResizable(True)
        legend_scroll.setWidget(self._legend_container)
        legend_scroll.setMinimumHeight(52)
        legend_scroll.setMaximumHeight(80)
        legend_scroll.setFrameShape(QFrame.NoFrame)
        legend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        legend_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        legend_scroll.setStyleSheet(
            "QScrollArea { background:transparent; border:none; }"
            "QScrollBar:horizontal { height:4px; background:#191c20; }"
            "QScrollBar::handle:horizontal { background:#3d4248; border-radius:2px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }"
        )
        left_col.addWidget(legend_scroll)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        bottom_layout.addWidget(left_widget, 3)

        # -- Panneau droit : alertes budgets + dernières transactions --
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # · Alertes budgets
        alerts_title = QLabel("⚠  Alertes budgets")
        alerts_title.setStyleSheet("font-size:13px; font-weight:600; color:#f59e0b;")
        right_col.addWidget(alerts_title)

        self._alerts_widget = QWidget()
        self._alerts_layout = QVBoxLayout(self._alerts_widget)
        self._alerts_layout.setContentsMargins(0, 0, 0, 0)
        self._alerts_layout.setSpacing(6)
        right_col.addWidget(self._alerts_widget)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#3a3f47;")
        right_col.addWidget(sep)

        # · Rappels de paiement
        self._reminders_title = QLabel("  Rappels de paiement")
        self._reminders_title.setStyleSheet("font-size:13px; font-weight:600; color:#f59e0b;")
        right_col.addWidget(self._reminders_title)

        self._reminders_widget = QWidget()
        self._reminders_layout = QVBoxLayout(self._reminders_widget)
        self._reminders_layout.setContentsMargins(0, 0, 0, 0)
        self._reminders_layout.setSpacing(4)
        right_col.addWidget(self._reminders_widget)

        sep2_rem = QFrame()
        sep2_rem.setFrameShape(QFrame.HLine)
        sep2_rem.setStyleSheet("color:#3a3f47;")
        right_col.addWidget(sep2_rem)

        # · Dernières transactions
        recent_title = QLabel("Dernières transactions")
        recent_title.setStyleSheet("font-size:13px; font-weight:600; color:#c8cdd4;")
        right_col.addWidget(recent_title)

        self._recent_widget = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_widget)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(4)
        right_col.addWidget(self._recent_widget)

        right_col.addStretch()

        # Lien "Voir toutes"
        btn_all = QPushButton("Voir toutes les transactions →")
        btn_all.setStyleSheet(
            "background:transparent; color:#7a8494; "
            "font-size:12px; border:none; text-align:left; padding:0;"
        )
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.clicked.connect(lambda: self.window().set_active(1) if hasattr(self.window(), "set_active") else None)
        right_col.addWidget(btn_all)

        right_widget = QWidget()
        right_widget.setLayout(right_col)
        right_widget.setMinimumWidth(280)
        bottom_layout.addWidget(right_widget, 2)

        main_layout.addLayout(bottom_layout)

        # ── Analyse financière ──
        # ── Prévisions améliorées ──
        self._forecast_widget = QWidget()
        self._forecast_widget.setStyleSheet(
            "background:#2e3238; border-radius:10px; border:none;"
        )
        fw = QHBoxLayout(self._forecast_widget)
        fw.setContentsMargins(16, 12, 16, 12)
        fw.setSpacing(24)

        # Prévision solde
        col1 = QVBoxLayout(); col1.setSpacing(2)
        self._forecast_label = QLabel("Prévision fin de mois")
        self._forecast_label.setStyleSheet("font-size:11px; color:#7a8494; font-weight:600; letter-spacing:1px;")
        self._forecast_value = QLabel("—")
        self._forecast_value.setStyleSheet("font-size:20px; font-weight:700; color:#c8cdd4;")
        self._forecast_sub   = QLabel("")
        self._forecast_sub.setStyleSheet("font-size:11px; color:#7a8494;")
        col1.addWidget(self._forecast_label)
        col1.addWidget(self._forecast_value)
        col1.addWidget(self._forecast_sub)

        # Séparateur
        sep1 = QFrame(); sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("background:#3d4248; max-width:1px;")

        # Catégorie principale
        col2 = QVBoxLayout(); col2.setSpacing(2)
        lbl2 = QLabel("CATÉGORIE PRINCIPALE")
        lbl2.setStyleSheet("font-size:11px; color:#7a8494; font-weight:600; letter-spacing:1px;")
        self._cat_value = QLabel("—")
        self._cat_value.setStyleSheet("font-size:16px; font-weight:700; color:#f59e0b;")
        col2.addWidget(lbl2)
        col2.addWidget(self._cat_value)

        # Séparateur
        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("background:#3d4248; max-width:1px;")

        # Top dépenses
        col3 = QVBoxLayout(); col3.setSpacing(2)
        lbl3 = QLabel("TOP DÉPENSES")
        lbl3.setStyleSheet("font-size:11px; color:#7a8494; font-weight:600; letter-spacing:1px;")
        self._top_value = QLabel("—")
        self._top_value.setStyleSheet("font-size:12px; color:#c8cdd4;")
        self._top_value.setWordWrap(True)
        col3.addWidget(lbl3)
        col3.addWidget(self._top_value)

        fw.addLayout(col1)
        fw.addWidget(sep1)
        fw.addLayout(col2)
        fw.addWidget(sep2)
        fw.addLayout(col3, 1)

        # Garder analysis_box pour compatibilité
        self.analysis_box = QLabel()
        self.analysis_box.setVisible(False)
        main_layout.addWidget(self._forecast_widget)

        self.setLayout(main_layout)
        self.refresh()

    # ------------------------------------------------------------------
    def open_category(self, category):
        main = self.window()
        if hasattr(main, "transactions"):
            main.set_active(1)
            main.transactions.search.setText(category)

    def _center_donut_label(self):
        chart = self.category_chart.chart()
        plot  = chart.plotArea()
        rect  = self._donut_label.boundingRect()
        self._donut_label.setPos(
            plot.center().x() - rect.width()  / 2,
            plot.center().y() - rect.height() / 2
        )

    def slice_hover(self, state):
        sl = self.sender()
        if not sl:
            return
        if state:
            sl.setExploded(True)
            sl.setBrush(QColor(sl.base_color).lighter(135))
            pct = (sl.amount_value / self._total_expense * 100) if self._total_expense else 0
            self._donut_label.setPlainText(
                f"{sl.category_name}\n{format_money(sl.amount_value)}\n{pct:.1f}%"
            )
        else:
            sl.setExploded(False)
            sl.setBrush(sl.base_color)
            self._donut_label.setPlainText(
                f"{format_money(self._total_expense)}\nDépenses"
            )
        self._center_donut_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_donut_label()

    # ------------------------------------------------------------------
    def _rebuild_legend(self, data, total):
        while self._legend_flow.count():
            child = self._legend_flow.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for i, (name, value) in enumerate(data):
            color = DONUT_COLORS[i % len(DONUT_COLORS)]
            pct   = (value / total * 100) if total else 0

            item_w = QWidget()
            item_w.setStyleSheet("background:transparent;")
            row = QHBoxLayout(item_w)
            row.setContentsMargins(8, 0, 8, 0)
            row.setSpacing(5)

            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background:{color}; border-radius:5px;")

            lbl = QLabel(f"{name}  {pct:.0f}%")
            lbl.setStyleSheet("font-size:11px; color:#cbd5e1;")
            lbl.setToolTip(f"{name} : {format_money(value)} ({pct:.1f}%)")

            row.addWidget(dot)
            row.addWidget(lbl)
            self._legend_flow.addWidget(item_w)

    def _rebuild_alerts(self):
        """Reconstruit le widget alertes budgets."""
        while self._alerts_layout.count():
            child = self._alerts_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        alerts = budget_alerts()

        if not alerts:
            lbl = QLabel("Aucun budget en alerte ✓")
            lbl.setStyleSheet("font-size:12px; color:#22c55e; padding:4px 0;")
            self._alerts_layout.addWidget(lbl)
            return

        for name, limit, spent, pct in alerts:
            row = QWidget()
            row.setStyleSheet(
                "background:#292d32; border-radius:8px;"
                "border:1px solid #3a3f47;"
            )
            rl = QVBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)
            rl.setSpacing(4)

            header = QHBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#c8cdd4;")
            pct_color = "#ef4444" if pct >= 100 else "#f59e0b"
            pct_lbl = QLabel(f"{pct:.0f}%")
            pct_lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{pct_color};")
            header.addWidget(name_lbl)
            header.addStretch()
            header.addWidget(pct_lbl)
            rl.addLayout(header)

            bar = QProgressBar()
            bar.setMaximum(100)
            bar.setValue(min(int(pct), 100))
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet(f"""
                QProgressBar {{ background:#191c20; border-radius:3px; }}
                QProgressBar::chunk {{ background:{pct_color}; border-radius:3px; }}
            """)
            rl.addWidget(bar)

            amounts_lbl = QLabel(f"{format_money(spent)} / {format_money(limit)}")
            amounts_lbl.setStyleSheet("font-size:11px; color:#6b7280;")
            rl.addWidget(amounts_lbl)

            self._alerts_layout.addWidget(row)

    def _rebuild_reminders(self):
        """Reconstruit le widget rappels de paiement."""
        while self._reminders_layout.count():
            child = self._reminders_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        from services.reminder_service import get_upcoming_reminders
        reminders = get_upcoming_reminders()

        if not reminders:
            self._reminders_title.setVisible(False)
            self._reminders_widget.setVisible(False)
            return

        self._reminders_title.setVisible(True)
        self._reminders_widget.setVisible(True)
        self._reminders_title.setText(
            f"  Rappels de paiement ({len(reminders)})"
        )

        for r in reminders:
            row = QWidget()
            row.setStyleSheet(
                "background:#2a2010; border-radius:8px; "
                "border:1px solid #5a4010;"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)
            rl.setSpacing(8)

            day_text = "Aujourd'hui" if r['days_until'] == 0 else f"J-{r['days_until']}"
            name_lbl = QLabel(f"  {r['label']}  —  {day_text}")
            name_lbl.setStyleSheet(
                "font-size:12px; font-weight:600; color:#f59e0b; "
                "background:transparent; border:none;"
            )

            color = "#ef4444" if r['type'] == 'expense' else "#22c55e"
            sign = "-" if r['type'] == 'expense' else "+"
            amt_lbl = QLabel(f"{sign}{format_money(r['amount'])}")
            amt_lbl.setStyleSheet(
                f"font-size:12px; font-weight:600; color:{color}; "
                "background:transparent; border:none;"
            )
            amt_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            rl.addWidget(name_lbl, 1)
            rl.addWidget(amt_lbl)
            self._reminders_layout.addWidget(row)

    def _rebuild_recent(self):
        """Reconstruit le widget dernières transactions."""
        while self._recent_layout.count():
            child = self._recent_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        from db import Session
        from models import Category
        transactions = recent_transactions(5)

        if not transactions:
            lbl = QLabel("Aucune transaction ce mois")
            lbl.setStyleSheet("font-size:12px; color:#6b7280; padding:4px 0;")
            self._recent_layout.addWidget(lbl)
            return

        with Session() as session:
            cats = {c.id: c for c in session.query(Category).all()}

        for t in transactions:
            cat   = cats.get(t.category_id)
            color = "#22c55e" if t.type == "income" else "#ef4444"
            sign  = "+" if t.type == "income" else "-"

            row = QWidget()
            row.setStyleSheet(
                "background:#292d32; border-radius:8px;"
                "border:1px solid #3a3f47;"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)
            rl.setSpacing(8)

            # Icône catégorie
            if cat:
                from utils.category_icons import get_category_icon
                raw = cat.icon or ""
                icon_file = raw if raw.endswith(".png") else get_category_icon(cat.name)
                icon_lbl = QLabel()
                icon_lbl.setPixmap(get_icon(icon_file, 20).pixmap(20, 20))
                icon_lbl.setFixedSize(24, 24)
                rl.addWidget(icon_lbl)

            # Description + date
            info = QVBoxLayout()
            info.setSpacing(1)
            desc = t.note or (cat.name if cat else "—")
            desc_lbl = QLabel(desc[:28] + ("…" if len(desc) > 28 else ""))
            desc_lbl.setStyleSheet("font-size:12px; color:#c8cdd4;")
            date_lbl = QLabel(t.date.strftime("%d/%m/%Y"))
            date_lbl.setStyleSheet("font-size:10px; color:#6b7280;")
            info.addWidget(desc_lbl)
            info.addWidget(date_lbl)
            rl.addLayout(info)
            rl.addStretch()

            # Montant
            amt_lbl = QLabel(f"{sign}{format_money(t.amount)}")
            amt_lbl.setStyleSheet(
                f"font-size:12px; font-weight:600; color:{color};"
            )
            amt_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rl.addWidget(amt_lbl)

            self._recent_layout.addWidget(row)

    # ------------------------------------------------------------------
    def generate_test_data(self):
        from services.dev_data import generate_transactions
        generate_transactions(300)
        self.refresh()
        main = self.window()
        if hasattr(main, "transactions"):
            main.transactions.load()

    def clear_data(self):
        from services.dev_data import clear_transactions
        clear_transactions()
        main = self.window()
        if hasattr(main, "refresh_all"):
            main.refresh_all()

    # ------------------------------------------------------------------
    def _create_rev_dep_chart(self):
        """Graphique barres groupées revenus vs dépenses sur 6 mois."""
        from PySide6.QtCharts import (QChart, QChartView, QBarSeries,
            QBarSet, QBarCategoryAxis, QValueAxis)
        from PySide6.QtGui import QPainter, QColor, QFont

        chart = QChart()
        chart.setBackgroundBrush(QColor("#1e2124"))
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(QColor("#848c94"))
        chart.setMargins(QMargins(8, 4, 8, 4))
        chart.setAnimationOptions(QChart.SeriesAnimations)

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setFixedHeight(140)
        view.setStyleSheet("background:transparent; border:none;")
        self._rev_dep_chart = chart
        return view

    def _refresh_rev_dep_chart(self):
        """Met à jour le graphique revenus vs dépenses."""
        from PySide6.QtCharts import (QBarSeries, QBarSet,
            QBarCategoryAxis, QValueAxis)
        from PySide6.QtGui import QColor, QFont
        import account_state

        chart = self._rev_dep_chart
        chart.removeAllSeries()
        for ax in chart.axes():
            chart.removeAxis(ax)

        from services.stats_service import monthly_income_expense
        import period_state as _ps
        _p = _ps.get()
        data = monthly_income_expense(6, ref_month=_p.month, ref_year=_p.year)

        MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                     "Juil","Août","Sep","Oct","Nov","Déc"]

        bar_rev = QBarSet("Revenus")
        bar_dep = QBarSet("Dépenses")
        bar_rev.setColor(QColor("#22c55e"))
        bar_dep.setColor(QColor("#ef4444"))
        categories = []

        for row in data[-6:]:
            # row = (label_str, income, expense)
            categories.append(row[0].split()[0])
            bar_rev.append(round(row[1], 2))
            bar_dep.append(round(row[2], 2))

        series = QBarSeries()
        series.append(bar_rev)
        series.append(bar_dep)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor("#848c94"))
        axis_x.setLabelsFont(QFont("", 9))
        axis_x.setGridLineVisible(False)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(
            [r[1] for r in data[-6:]] + [r[2] for r in data[-6:]] + [1]
        )
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.2)
        axis_y.setLabelsColor(QColor("#c8cdd4"))
        axis_y.setLabelsFont(QFont("", 10))
        axis_y.setGridLineColor(QColor("#2e3238"))
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(4)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def _create_balance_chart(self):
        """Crée le graphique linéaire d'évolution du solde."""
        from PySide6.QtCharts import QLineSeries, QAreaSeries, QChart, QChartView
        from PySide6.QtCore import QMargins

        self._balance_series = QLineSeries()
        self._balance_series.setColor(QColor("#5a6472"))

        self._balance_area = QAreaSeries(self._balance_series)
        self._balance_area.setColor(QColor("#3a3f47"))
        self._balance_area.setBorderColor(QColor("#5a6472"))
        pen = self._balance_area.pen()
        pen.setWidth(2)
        self._balance_area.setPen(pen)

        chart = QChart()
        chart.addSeries(self._balance_area)
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        chart.layout().setContentsMargins(0, 0, 0, 0)
        chart.legend().setVisible(False)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setAnimationDuration(600)

        self._balance_axis_x = QValueAxis()
        self._balance_axis_x.setLabelsColor(QColor("#6b7280"))
        self._balance_axis_x.setGridLineColor(QColor("#292d32"))
        self._balance_axis_x.setLabelFormat("%d")
        self._balance_axis_x.setTitleText("")
        chart.addAxis(self._balance_axis_x, Qt.AlignBottom)
        self._balance_area.attachAxis(self._balance_axis_x)

        self._balance_axis_y = QValueAxis()
        self._balance_axis_y.setLabelsColor(QColor("#6b7280"))
        self._balance_axis_y.setGridLineColor(QColor("#292d32"))
        self._balance_axis_y.setLabelFormat("%d")
        chart.addAxis(self._balance_axis_y, Qt.AlignLeft)
        self._balance_area.attachAxis(self._balance_axis_y)

        view = QChartView(chart)
        view.setRenderHint(view.renderHints().__class__.Antialiasing)
        view.setFixedHeight(130)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return view

    def _update_balance_chart(self):
        """Met à jour le graphique avec les données du mois courant."""
        from collections import defaultdict
        from db import Session
        from models import Transaction
        from sqlalchemy import func
        import account_state

        p      = period_state.get()
        acc_id = account_state.get_id()

        with Session() as session:
            q = (session.query(
                    func.extract("day", Transaction.date).label("day"),
                    Transaction.type,
                    func.sum(Transaction.amount).label("total")
                )
                .filter(func.extract("year",  Transaction.date) == p.year)
                .filter(func.extract("month", Transaction.date) == p.month)
            )
            if acc_id is not None:
                q = q.filter(Transaction.account_id == acc_id)
            rows = q.group_by("day", Transaction.type).order_by("day").all()

        # Agréger par jour
        daily = defaultdict(float)
        for day, ttype, total in rows:
            d = int(day)
            if ttype == "income":
                daily[d] += float(total)
            else:
                daily[d] -= float(total)

        if not daily:
            self._balance_series.clear()
            return

        # Calculer le solde cumulatif
        import calendar
        max_day = calendar.monthrange(p.year, p.month)[1]
        cumul = 0.0
        points = []
        for d in range(1, max_day + 1):
            cumul += daily.get(d, 0)
            points.append((d, cumul))

        # Mettre à jour la série
        self._balance_series.clear()
        for d, val in points:
            self._balance_series.append(d, val)

        # Ajuster les axes
        values = [v for _, v in points]
        min_v, max_v = min(values), max(values)
        padding = max(abs(max_v - min_v) * 0.15, 50)
        self._balance_axis_x.setRange(1, max_day)
        self._balance_axis_y.setRange(min_v - padding, max_v + padding)

        # Couleur selon solde final
        final = points[-1][1]
        color = QColor("#22c55e") if final >= 0 else QColor("#ef4444")
        area_color = QColor("#1a2e1a") if final >= 0 else QColor("#2e1a1a")
        self._balance_series.setColor(color)
        self._balance_area.setColor(area_color)
        self._balance_area.setBorderColor(color)

    # ------------------------------------------------------------------
    def _go_to_savings(self):
        """Navigue vers la vue Épargne."""
        main = self.window()
        if hasattr(main, 'set_active'):
            main.set_active(6)  # index Épargne

    def _go_to_crypto(self):
        """Navigue vers la vue Crypto."""
        main = self.window()
        if hasattr(main, 'set_active'):
            main.set_active(13)  # index Crypto

    def _build_crypto_widget(self) -> QWidget:
        """Mini-widget résumé portefeuille crypto pour le dashboard."""
        w = QWidget()
        w.setCursor(Qt.PointingHandCursor)
        w.setStyleSheet("""
            QWidget {
                background:#292d32; border-radius:12px; border:1px solid #3d4248;
            }
            QWidget:hover {
                background:#2e3238; border:1px solid #5a6068;
            }
        """)
        w.mousePressEvent = lambda e: self._go_to_crypto()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        icon_lbl = QLabel("₿")
        icon_lbl.setStyleSheet(
            "font-size:22px; color:#f59e0b; background:transparent; border:none;"
        )

        title_lbl = QLabel("CRYPTO")
        title_lbl.setStyleSheet(
            "font-size:11px; font-weight:600; color:#848c94; "
            "letter-spacing:1px; background:transparent; border:none;"
        )

        self._crypto_val_lbl = QLabel("—")
        self._crypto_val_lbl.setStyleSheet(
            "font-size:18px; font-weight:700; color:#f59e0b; "
            "background:transparent; border:none;"
        )

        self._crypto_pnl_lbl = QLabel("")
        self._crypto_pnl_lbl.setStyleSheet(
            "font-size:11px; color:#7a8494; background:transparent; border:none;"
        )

        self._crypto_chg_lbl = QLabel("")
        self._crypto_chg_lbl.setStyleSheet(
            "font-size:11px; color:#7a8494; background:transparent; border:none;"
        )

        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(title_lbl)
        left.addWidget(self._crypto_val_lbl)

        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignRight)
        right.addWidget(self._crypto_pnl_lbl)
        right.addWidget(self._crypto_chg_lbl)

        row = QHBoxLayout()
        row.addWidget(icon_lbl)
        row.addLayout(left)
        row.addStretch()
        row.addLayout(right)
        layout.addLayout(row)

        return w

    def _build_savings_widget(self) -> QWidget:
        """Mini-widget résumé épargne pour le dashboard."""
        w = QWidget()
        w.setCursor(Qt.PointingHandCursor)
        w.setStyleSheet("""
            QWidget {
                background:#292d32; border-radius:12px; border:1px solid #3d4248;
            }
            QWidget:hover {
                background:#2e3238; border:1px solid #5a6068;
            }
        """)
        w.mousePressEvent = lambda e: self._go_to_savings()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            __import__("utils.icons", fromlist=["get_icon"]).get_icon("epargne.png", 28).pixmap(28, 28)
        )
        icon_lbl.setStyleSheet("background:transparent; border:none;")

        title_lbl = QLabel("Épargne")
        title_lbl.setStyleSheet(
            "font-size:11px; font-weight:600; color:#848c94; "
            "letter-spacing:1px; background:transparent; border:none;"
        )

        self._sav_total_lbl = QLabel("—")
        self._sav_total_lbl.setStyleSheet(
            "font-size:18px; font-weight:700; color:#22c55e; "
            "background:transparent; border:none;"
        )

        self._sav_goal_lbl = QLabel("")
        self._sav_goal_lbl.setStyleSheet(
            "font-size:11px; color:#7a8494; background:transparent; border:none;"
        )

        self._sav_bar = QProgressBar()
        self._sav_bar.setFixedHeight(6)
        self._sav_bar.setTextVisible(False)
        self._sav_bar.setStyleSheet("""
            QProgressBar { background:#3d4248; border-radius:3px; border:none; }
            QProgressBar::chunk { background:#22c55e; border-radius:3px; }
        """)
        self._sav_bar.setValue(0)

        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(title_lbl)
        left.addWidget(self._sav_total_lbl)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(self._sav_goal_lbl)
        right.addWidget(self._sav_bar)

        row = QHBoxLayout()
        row.addWidget(icon_lbl)
        row.addLayout(left)
        row.addStretch()
        row.addLayout(right)
        layout.addLayout(row)

        return w

    def _build_income_projection_widget(self) -> QWidget:
        """Mini-widget projection des revenus pour le dashboard."""
        w = QWidget()
        w.setStyleSheet(
            "QWidget { background:#292d32; border-radius:12px; border:1px solid #3d4248; }"
        )
        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # Icône
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("income.png", 28).pixmap(28, 28))
        icon_lbl.setStyleSheet("background:transparent; border:none;")

        # Colonne gauche : titre + projection
        left = QVBoxLayout()
        left.setSpacing(2)

        title_lbl = QLabel("PROJECTION REVENUS")
        title_lbl.setStyleSheet(
            "font-size:11px; font-weight:600; color:#848c94; "
            "letter-spacing:1px; background:transparent; border:none;"
        )

        self._inc_proj_value = QLabel("—")
        self._inc_proj_value.setStyleSheet(
            "font-size:18px; font-weight:700; color:#22c55e; "
            "background:transparent; border:none;"
        )

        left.addWidget(title_lbl)
        left.addWidget(self._inc_proj_value)

        # Colonne droite : moyenne + tendance
        right = QVBoxLayout()
        right.setSpacing(4)

        self._inc_proj_avg = QLabel("")
        self._inc_proj_avg.setStyleSheet(
            "font-size:11px; color:#7a8494; background:transparent; border:none;"
        )

        self._inc_proj_trend = QLabel("")
        self._inc_proj_trend.setStyleSheet(
            "font-size:12px; font-weight:600; background:transparent; border:none;"
        )

        right.addWidget(self._inc_proj_avg)
        right.addWidget(self._inc_proj_trend)

        row = QHBoxLayout()
        row.addWidget(icon_lbl)
        row.addLayout(left)
        row.addStretch()
        row.addLayout(right)
        layout.addLayout(row)

        return w

    def _refresh_income_projection(self):
        """Met à jour le widget projection des revenus."""
        try:
            data = forecast_income()
            projected = data["projected_current_month"]
            avg       = data["average_monthly"]
            trend     = data["trend"]
            current   = data["current_income"]

            self._inc_proj_value.setText(format_money(projected))

            self._inc_proj_avg.setText(f"Moyenne : {format_money(avg)}")

            if trend == "up":
                arrow, color, text = "▲", "#22c55e", "Tendance haussière"
            elif trend == "down":
                arrow, color, text = "▼", "#ef4444", "Tendance baissière"
            else:
                arrow, color, text = "●", "#f59e0b", "Tendance stable"

            self._inc_proj_trend.setText(f"{arrow} {text}")
            self._inc_proj_trend.setStyleSheet(
                f"font-size:12px; font-weight:600; color:{color}; "
                "background:transparent; border:none;"
            )
        except Exception:
            self._inc_proj_value.setText("—")
            self._inc_proj_avg.setText("")
            self._inc_proj_trend.setText("")

    def _apply_dashboard_order(self):
        """Réorganise les widgets selon l'ordre sauvegardé."""
        try:
            from services.settings_service import get as _gs
            order = _gs('dashboard_order')
            if not order:
                return
            widget_map = {
                'balance_chart':  self._balance_chart_view,
                'rev_dep_chart':  self._rev_dep_view,
                'savings_widget': self._savings_widget,
            }
            layout = self.layout()
            for key in order:
                if key in widget_map:
                    w = widget_map[key]
                    layout.removeWidget(w)
                    layout.addWidget(w)
        except Exception:
            pass

    def _refresh_savings_widget(self):
        """Met à jour le mini-widget épargne."""
        try:
            from services.savings_service import get_goals
            goals = get_goals()
            if not goals:
                self._sav_total_lbl.setText("0,00 €")
                self._sav_total_lbl.setStyleSheet(
                    "font-size:18px; font-weight:700; color:#848c94; "
                    "background:transparent; border:none;"
                )
                self._sav_goal_lbl.setText("  Créer un objectif d'épargne")
                self._sav_goal_lbl.setStyleSheet(
                    "font-size:12px; color:#7aaee8; text-decoration:underline; "
                    "background:transparent; border:none; cursor:pointer;"
                )
                self._sav_bar.setValue(0)
                return

            total_current = sum(g.current_amount for g in goals)
            total_target  = sum(g.target_amount  for g in goals)
            pct = int(total_current / total_target * 100) if total_target > 0 else 0

            from utils.formatters import format_money
            self._sav_total_lbl.setText(format_money(total_current))

            # Objectif le plus proche de l'échéance
            from datetime import date
            goals_with_deadline = [g for g in goals if g.deadline]
            if goals_with_deadline:
                nearest = min(goals_with_deadline,
                              key=lambda g: (g.deadline - date.today()).days)
                reste = nearest.target_amount - nearest.current_amount
                self._sav_goal_lbl.setText(
                    f"{nearest.name} — reste {format_money(reste)}"
                )
            else:
                self._sav_goal_lbl.setText(
                    f"{len(goals)} objectif(s) — {pct}% atteint"
                )

            self._sav_bar.setMaximum(100)
            self._sav_bar.setValue(pct)
        except Exception:
            pass

    def refresh(self):
        income, expense, balance = get_month_summary()
        self._total_expense = expense

        # ── Solde tous comptes ──
        try:
            from services.account_service import get_accounts, get_account_balance
            all_balance = sum(get_account_balance(a.id)[2] for a in get_accounts())
        except Exception:
            all_balance = balance

        # ── Nombre de transactions du mois ──
        try:
            from services.transaction_service import get_transactions_for_period
            tx_count = len(get_transactions_for_period(limit=9999))
            self._tx_count_label.setText(f"{tx_count} transaction(s) ce mois")
        except Exception:
            self._tx_count_label.setText("")

        # ── Graphique solde ──
        self._update_balance_chart()

        # ── Cartes KPI ──
        global_color  = "#22c55e" if all_balance >= 0 else "#ef4444"
        balance_color = "#22c55e" if balance >= 0 else "#ef4444"
        bar_style = "border-radius:4px 0 0 4px; border:none; background:{c};"

        self.global_card["value"].setStyleSheet(
            f"font-size:24px; font-weight:700; color:{global_color}; background:transparent; border:none;"
        )
        if "bar" in self.global_card:
            self.global_card["bar"].setStyleSheet(bar_style.format(c=global_color))
        self.balance_card["value"].setStyleSheet(
            f"font-size:24px; font-weight:700; color:{balance_color}; background:transparent; border:none;"
        )
        if "bar" in self.balance_card:
            self.balance_card["bar"].setStyleSheet(bar_style.format(c=balance_color))

        # Compteurs animés
        sign_g = "+" if all_balance >= 0 else "-"
        sign_b = "+" if balance >= 0 else ""
        self._anim_global  = CounterAnimation(self.global_card["value"],  abs(all_balance), prefix="" if all_balance >= 0 else "-")
        self._anim_income  = CounterAnimation(self.income_card["value"],  income)
        self._anim_expense = CounterAnimation(self.expense_card["value"], expense)
        self._anim_balance = CounterAnimation(self.balance_card["value"], abs(balance), prefix=sign_b if balance >= 0 else "-")
        for anim in [self._anim_global, self._anim_income, self._anim_expense, self._anim_balance]:
            anim.start()

        # ── Comparaison mois précédent ──
        try:
            inc_diff, exp_diff = compare_with_previous()
        except Exception:
            inc_diff, exp_diff = None, None

        def diff_label(diff):
            if diff is None:
                return ""
            arrow = "▲" if diff >= 0 else "▼"
            color = "#22c55e" if diff >= 0 else "#ef4444"
            return f'<span style="color:{color}">{arrow} {abs(diff):.1f}% vs mois préc.</span>'

        inc_text = diff_label(inc_diff)
        exp_text = diff_label(exp_diff)
        self._income_cmp.setText(inc_text)
        self._income_cmp.setTextFormat(Qt.RichText)
        self._income_cmp.setVisible(bool(inc_text))
        self._expense_cmp.setText(exp_text)
        self._expense_cmp.setTextFormat(Qt.RichText)
        self._expense_cmp.setVisible(bool(exp_text))

        # ── Santé financière ──
        percent = int((expense / income) * 100) if income > 0 else 0
        if percent < 50:
            health_text, health_color = "Situation financière saine", "#22c55e"
        elif percent < 80:
            health_text, health_color = "Attention aux dépenses",     "#f59e0b"
        else:
            health_text, health_color = "Dépenses élevées",           "#ef4444"

        self.health_label.setText(
            f'<span style="color:{health_color}; font-size:18px;">●</span> '
            f'{health_text} — Taux de dépense : {percent}%'
        )
        self.health_label.setStyleSheet(
            f"font-size:15px; font-weight:600; color:{health_color};"
        )
        self.health_bar.setValue(min(percent, 100))
        self.health_bar.setStyleSheet(
            f"QProgressBar {{ background:#191c20; border-radius:5px; }}"
            f"QProgressBar::chunk {{ background:{health_color}; border-radius:5px; }}"
        )

        # ── Donut ──
        data = expenses_by_category()
        self.series.clear()
        total = sum(v for _, v in data)
        self._total_expense = total

        if total == 0:
            self._donut_label.setPlainText("")
            self._rebuild_legend([], 0)
        else:
            self._donut_label.setPlainText(f"{format_money(total)}\nDépenses")
            self._chart_title.setText(f"Dépenses — {period_state.label()}")

            for i, (name, value) in enumerate(data):
                sl = self.series.append(name, value)
                color = QColor(DONUT_COLORS[i % len(DONUT_COLORS)])
                sl.setBrush(color)
                sl.setLabelVisible(False)
                sl.setExplodeDistanceFactor(0.06)
                sl.category_name = name
                sl.amount_value  = value
                sl.base_color    = color
                sl.hovered.connect(self.slice_hover)

            self._center_donut_label()
            self._rebuild_legend(data, total)

        # ── Nouveaux widgets ──
        self._rebuild_alerts()
        self._rebuild_reminders()
        self._rebuild_recent()
        self._refresh_rev_dep_chart()
        self._refresh_savings_widget()
        self._refresh_income_projection()

        self._update_analysis(income, expense, balance)
        self._refresh_crypto_widget()

    def _refresh_crypto_widget(self):
        """Met à jour le mini-widget crypto. Lance un fetch si le cache est vide."""
        try:
            from services.crypto_service import get_holdings, _price_cache
            holdings = get_holdings()
            if not holdings:
                self._crypto_widget.setVisible(False)
                return

            self._crypto_widget.setVisible(True)
            ids = [h.coingecko_id for h in holdings]

            import time as _t
            from services.crypto_service import _CACHE_TTL
            now = _t.time()
            cache_fresh = all(
                cg in _price_cache and now - _price_cache[cg].get("ts", 0) < _CACHE_TTL
                for cg in ids
            )

            if cache_fresh:
                # Cache frais → affichage immédiat, aucun appel réseau
                self._apply_crypto_prices(holdings, _price_cache)
            else:
                # Cache absent ou périmé → afficher valeurs d'achat + fetch en background
                self._apply_crypto_prices(holdings, {})
                self._crypto_fetcher = _CryptoPriceFetcher(ids)
                self._crypto_fetcher.done.connect(
                    lambda prices: self._apply_crypto_prices(holdings, prices)
                )
                self._crypto_fetcher.start()
        except Exception:
            self._crypto_widget.setVisible(False)

    def _apply_crypto_prices(self, holdings, prices: dict):
        """Calcule et affiche les métriques crypto dans le widget dashboard."""
        try:
            total_value  = 0.0
            total_invest = 0.0
            chg_weighted = 0.0
            has_live = bool(prices)

            for h in holdings:
                entry = prices.get(h.coingecko_id)
                price = entry["price"] if entry else h.avg_buy_price
                chg   = entry.get("change_24h", 0.0) if entry else 0.0
                value = h.quantity * price
                total_value  += value
                total_invest += h.quantity * h.avg_buy_price
                chg_weighted += value * chg

            pnl     = total_value - total_invest
            pnl_pct = (pnl / total_invest * 100) if total_invest > 0 else 0
            chg24   = (chg_weighted / total_value) if total_value > 0 else 0

            pnl_sign  = "+" if pnl  >= 0 else ""
            chg_sign  = "+" if chg24 >= 0 else ""
            pnl_color = "#22c55e" if pnl  >= 0 else "#ef4444"
            chg_color = "#22c55e" if chg24 >= 0 else "#ef4444"

            self._crypto_val_lbl.setText(format_money(total_value))

            if has_live:
                self._crypto_pnl_lbl.setText(
                    f'<span style="color:{pnl_color}">'
                    f'{pnl_sign}{format_money(pnl)} ({pnl_sign}{pnl_pct:.1f}%)</span>'
                )
                self._crypto_pnl_lbl.setTextFormat(Qt.RichText)
                self._crypto_chg_lbl.setText(
                    f'<span style="color:{chg_color}">24h : {chg_sign}{chg24:.2f}%</span>'
                )
                self._crypto_chg_lbl.setTextFormat(Qt.RichText)
            else:
                self._crypto_pnl_lbl.setText("Chargement des prix…")
                self._crypto_pnl_lbl.setStyleSheet(
                    "font-size:11px; color:#5a6472; background:transparent; border:none;"
                )
                self._crypto_chg_lbl.setText("")
        except Exception:
            pass

    def _update_analysis(self, income, expense, balance):
        from datetime import date
        import calendar
        forecast  = forecast_balance()
        cat       = biggest_category()
        cat_name  = cat[0] if cat else "Aucune"
        top       = top_expenses()

        sign_f = "+" if forecast >= 0 else ""
        color_f = "#22c55e" if forecast >= 0 else "#ef4444"
        is_current = period_state.is_current_month()

        self._forecast_label.setText(
            "Solde réel" if not is_current else "Prévision fin de mois"
        )
        self._forecast_value.setText(f"{sign_f}{format_money(forecast)}")
        self._forecast_value.setStyleSheet(
            f"font-size:20px; font-weight:700; color:{color_f};"
        )
        if is_current:
            p = period_state.get()
            days_left = calendar.monthrange(p.year, p.month)[1] - date.today().day
            self._forecast_sub.setText(f"J-{days_left} jours restants ce mois")
        else:
            self._forecast_sub.setText("")

        self._cat_value.setText(cat_name)

        top_lines = "\n".join(f"• {n} : {format_money(a)}" for n, a in top) \
                    or "Aucune dépense"
        self._top_value.setText(top_lines)
