from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget
)
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries,
    QBarSeries, QBarSet, QBarCategoryAxis, QCategoryAxis
)
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import Qt, QMargins

from utils.formatters import format_money
from services.stats_service import (
    expenses_by_category, expenses_by_category_annual,
    monthly_balance, monthly_income_expense
)
import account_state
import period_state

DONUT_COLORS = [
    "#22c55e", "#7a8494", "#f59e0b", "#ef4444",
    "#8b5cf6", "#06b6d4", "#f97316", "#ec4899",
    "#14b8a6", "#6366f1", "#84cc16", "#a855f7",
]


def _fmt_amount(v):
    """Formate un montant pour l'axe Y : abrège en k si >= 1000."""
    v = abs(v)
    if v >= 1000:
        return f"{v/1000:.1f}k€"
    return f"{int(v)}€"


def _make_y_axis(max_val: float, negative: bool = False):
    """
    Crée un QCategoryAxis avec des labels montant bien formatés.
    Utilise QCategoryAxis au lieu de QValueAxis pour contrôler
    exactement le texte affiché et éviter la troncature Qt.
    """
    TICKS = 5
    top   = max_val * (1.25 if negative else 1.15)
    step  = top / TICKS

    axis = QCategoryAxis()
    axis.setLabelsFont(QFont("Segoe UI", 8))
    axis.setLabelsColor(QColor("#7a8494"))
    axis.setGridLineColor(QColor("#3a3f47"))
    axis.setMin(-top if negative else 0)
    axis.setMax(top)
    axis.setStartValue(-top if negative else 0)

    if negative:
        for i in range(-TICKS, TICKS + 1):
            val = i * step
            axis.append(_fmt_amount(val), val)
    else:
        for i in range(0, TICKS + 1):
            val = i * step
            axis.append(_fmt_amount(val), val)

    return axis


class _NumericItem(QTableWidgetItem):
    """QTableWidgetItem qui trie numériquement via Qt.UserRole."""
    def __lt__(self, other):
        v1 = self.data(Qt.UserRole)
        v2 = other.data(Qt.UserRole)
        if v1 is not None and v2 is not None:
            return float(v1) < float(v2)
        return super().__lt__(other)


class StatisticsView(QWidget):

    def __init__(self):
        super().__init__()
        self._total = 0
        self._series = None

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        self.setLayout(layout)

        self._build_ui(layout)
        self._load_data()

    # ------------------------------------------------------------------
    def _build_ui(self, layout):
        # Onglets
        self._stat_tabs = QTabWidget()
        self._stat_tabs.setStyleSheet("""
            QTabWidget::pane { border:none; background:transparent; }
            QTabBar::tab { background:#292d32; color:#7a8494; padding:7px 16px;
                border-radius:8px 8px 0 0; font-size:12px; font-weight:600; }
            QTabBar::tab:selected { background:#3e4550; color:#c8cdd4; }
            QTabBar::tab:hover { color:#c8cdd4; }
        """)
        layout.addWidget(self._stat_tabs)

        # Onglet 1 : statistiques habituelles
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setSpacing(12)
        tab1_layout.setContentsMargins(0, 12, 0, 0)
        self._stat_tabs.addTab(tab1, "  Analyse")

        # Onglet 2 : comparaison mois
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setSpacing(12)
        tab2_layout.setContentsMargins(0, 12, 0, 0)
        self._stat_tabs.addTab(tab2, "  Comparaison mois")

        # Onglet 3 : Camembert
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.setSpacing(4)
        tab3_layout.setContentsMargins(0, 4, 0, 0)
        self._stat_tabs.addTab(tab3, "  Répartition")
        self._pie_tab_layout = tab3_layout

        self._pie_tab_built = False
        self._comp_tab_built = False

        def _on_tab_changed(i):
            if i == 1 and not self._comp_tab_built:
                self._build_comparison_tab(tab2_layout)
                self._comp_tab_built = True
            elif i == 2 and not self._pie_tab_built:
                self._build_pie_tab(self._pie_tab_layout)
                self._pie_tab_built = True

        self._stat_tabs.currentChanged.connect(_on_tab_changed)

        self._tab1_layout = tab1_layout
        layout = tab1_layout  # continuer à remplir tab1

        # ══════════════════════════════════════
        # SECTION 1 : Donut dépenses par catégorie
        # ══════════════════════════════════════
        self._title_pie = QLabel()
        self._title_pie.setStyleSheet("font-size:14px; font-weight:600; color:#c8cdd4;")
        self._title_pie.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_pie)

        self._series = QPieSeries()
        self._series.setHoleSize(0.50)  # Donut

        chart_pie = QChart()
        chart_pie.addSeries(self._series)
        chart_pie.setTitle("")
        chart_pie.setBackgroundVisible(False)
        chart_pie.setAnimationOptions(QChart.SeriesAnimations)
        chart_pie.setAnimationDuration(600)
        chart_pie.setMargins(QMargins(0, 0, 0, 0))
        chart_pie.legend().setVisible(False)

        self._pie_view = QChartView(chart_pie)
        self._pie_view.setRenderHint(QPainter.Antialiasing)
        self._pie_view.setMinimumHeight(340)
        self._pie_view.setMaximumHeight(400)
        self._pie_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._pie_view.setStyleSheet("background:transparent; border:none;")

        # Container empilé : chart + label overlay
        from PySide6.QtWidgets import QStackedLayout
        analysis_chart_container = QWidget()
        analysis_chart_container.setStyleSheet("background:transparent; border:none;")
        analysis_stack = QStackedLayout(analysis_chart_container)
        analysis_stack.setStackingMode(QStackedLayout.StackAll)
        analysis_stack.addWidget(self._pie_view)

        # Label central overlay (QLabel fiable)
        self._center_label = QLabel()
        self._center_label.setAlignment(Qt.AlignCenter)
        self._center_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._center_label.setFixedSize(160, 60)
        self._center_label.setStyleSheet(
            "background:transparent; border:none; "
            "color:#c8cdd4; font-size:12px; font-weight:700;"
        )
        center_wrapper = QWidget()
        center_wrapper.setAttribute(Qt.WA_TransparentForMouseEvents)
        center_wrapper.setStyleSheet("background:transparent; border:none;")
        cw_layout = QVBoxLayout(center_wrapper)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setAlignment(Qt.AlignCenter)
        cw_layout.addWidget(self._center_label)
        analysis_stack.addWidget(center_wrapper)

        layout.addWidget(analysis_chart_container)

        # Légende détaillée en tableau
        self._legend_table = QTableWidget()
        self._legend_table.setColumnCount(4)
        self._legend_table.setHorizontalHeaderLabels(
            ["", "Catégorie", "Montant", "%"]
        )
        self._legend_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._legend_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._legend_table.setShowGrid(False)
        self._legend_table.verticalHeader().setVisible(False)
        self._legend_table.verticalHeader().setDefaultSectionSize(34)
        self._legend_table.setAlternatingRowColors(False)
        self._legend_table.setFocusPolicy(Qt.NoFocus)
        self._legend_table.setMaximumHeight(240)
        hdr = self._legend_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self._legend_table.setColumnWidth(0, 36)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)   # Catégorie
        hdr.setMinimumSectionSize(80)                      # min pour éviter la coupure
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)     # Montant
        self._legend_table.setColumnWidth(2, 100)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)     # %
        self._legend_table.setColumnWidth(3, 56)
        self._legend_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:2px 8px; }
            QTableWidget::item:selected { background:#292d32; }
            QHeaderView::section {
                background:#292d32; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:4px 8px; font-size:11px;
            }
        """)
        layout.addWidget(self._legend_table)

        self._sep1 = QFrame()
        self._sep1.setFrameShape(QFrame.HLine)
        self._sep1.setStyleSheet("color:#3a3f47;")
        layout.addWidget(self._sep1)

        # ══════════════════════════════════════
        # SECTION 2 : Revenus vs Dépenses 12 mois
        # ══════════════════════════════════════
        self._title_rvd = QLabel("Revenus vs Dépenses — 12 derniers mois")
        self._title_rvd.setStyleSheet("font-size:14px; font-weight:600; color:#c8cdd4;")
        self._title_rvd.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_rvd)

        self._rvd_view = self._build_income_expense_chart()
        layout.addWidget(self._rvd_view, 2)

        self._sep2 = QFrame()
        self._sep2.setFrameShape(QFrame.HLine)
        self._sep2.setStyleSheet("color:#3a3f47;")
        layout.addWidget(self._sep2)

        # ══════════════════════════════════════
        # SECTION 3 : Tableau récapitulatif mensuel
        # ══════════════════════════════════════
        title_recap = QLabel("Récapitulatif mensuel")
        title_recap.setStyleSheet("font-size:14px; font-weight:600; color:#c8cdd4;")
        title_recap.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_recap)

        self._recap_table = self._build_recap_table()
        layout.addWidget(self._recap_table)

        # ══════════════════════════════════════
        # SECTION 4 : Projection des revenus — 6 mois
        # ══════════════════════════════════════
        self._sep3 = QFrame()
        self._sep3.setFrameShape(QFrame.HLine)
        self._sep3.setStyleSheet("color:#3a3f47;")
        layout.addWidget(self._sep3)

        self._title_proj = QLabel("Projection des revenus — 6 derniers mois")
        self._title_proj.setStyleSheet("font-size:14px; font-weight:600; color:#c8cdd4;")
        self._title_proj.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_proj)

        self._income_proj_view = self._build_income_projection_chart()
        layout.addWidget(self._income_proj_view, 2)

    # ------------------------------------------------------------------
    # Graphique 2 : Revenus vs Dépenses — barres groupées 12 mois
    # ------------------------------------------------------------------
    def _build_income_expense_chart(self):
        data = monthly_income_expense(12)
        # Ne garder que les mois avec des données
        data = [(l, i, e) for l, i, e in data if i > 0 or e > 0]
        if not data:
            data = monthly_income_expense(1)

        months  = [d[0] for d in data]
        incomes  = [d[1] for d in data]
        expenses = [d[2] for d in data]

        set_income = QBarSet("Revenus")
        set_income.setColor(QColor("#22c55e"))
        set_income.setBorderColor(QColor("#16a34a"))

        set_expense = QBarSet("Dépenses")
        set_expense.setColor(QColor("#ef4444"))
        set_expense.setBorderColor(QColor("#b91c1c"))

        for v in incomes:
            set_income.append(v)
        for v in expenses:
            set_expense.append(v)

        series = QBarSeries()
        series.append(set_income)
        series.append(set_expense)
        series.setBarWidth(0.7)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("")
        chart.setBackgroundVisible(False)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setAnimationDuration(600)
        chart.setMargins(QMargins(16, 4, 4, 4))

        # Légende native Qt — simple et efficace pour 2 séries seulement
        legend = chart.legend()
        legend.setVisible(True)
        legend.setAlignment(Qt.AlignBottom)
        legend.setLabelColor(QColor("#c8cdd4"))
        legend.setFont(QFont("Segoe UI", 9))

        axis_x = QBarCategoryAxis()
        axis_x.append(months)
        axis_x.setLabelsColor(QColor("#7a8494"))
        axis_x.setLabelsAngle(-45)
        axis_x.setGridLineColor(QColor("#3a3f47"))
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(max(incomes, default=0), max(expenses, default=0)) or 1
        axis_y = _make_y_axis(max_val, negative=False)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(240)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return view

    # ------------------------------------------------------------------
    # Tableau 3 : Récapitulatif mensuel (remplace le graphique solde net)
    # ------------------------------------------------------------------
    def _build_recap_table(self):
        from services.stats_service import monthly_income_expense
        # Récupérer tous les mois disponibles et trier du plus récent au plus ancien
        data = monthly_income_expense(12)
        # Inverser : mois le plus récent en premier
        data = list(reversed(data))
        # Ne garder que les mois avec au moins une transaction
        data = [(l, i, e) for l, i, e in data if i > 0 or e > 0]
        # Si aucune donnée, garder le mois courant quand même
        if not data:
            data = monthly_income_expense(1)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Mois", "Revenus", "Dépenses", "Solde"])
        table.setRowCount(len(data))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setFocusPolicy(Qt.NoFocus)
        table.verticalHeader().setDefaultSectionSize(34)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #3a3f47; padding:4px 10px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section {
                background:#26292e; border:none;
                padding:6px 10px; font-weight:600; color:#7a8494;
            }
        """)

        for i, (label, income, expense) in enumerate(data):
            solde = income - expense

            # Mois
            month_item = QTableWidgetItem(label)
            month_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            table.setItem(i, 0, month_item)

            # Revenus
            inc_item = QTableWidgetItem(format_money(income))
            inc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            inc_item.setForeground(QColor("#22c55e"))
            table.setItem(i, 1, inc_item)

            # Dépenses
            exp_item = QTableWidgetItem(format_money(expense))
            exp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            exp_item.setForeground(QColor("#ef4444"))
            table.setItem(i, 2, exp_item)

            # Solde + indicateur couleur
            sign = "+" if solde >= 0 else ""
            sol_item = QTableWidgetItem(f"{sign}{format_money(solde)}")
            sol_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sol_item.setForeground(QColor("#22c55e") if solde >= 0 else QColor("#ef4444"))
            fnt = sol_item.font(); fnt.setBold(True); sol_item.setFont(fnt)
            table.setItem(i, 3, sol_item)

        # Hauteur ajustée au contenu
        total_h = sum(table.rowHeight(r) for r in range(table.rowCount()))
        table.setFixedHeight(total_h + table.horizontalHeader().height() + 4)

        return table
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Données donut
    # ------------------------------------------------------------------
    def _load_data(self):
        data = expenses_by_category_annual(12)
        self._series.clear()

        total = sum(v for _, v in data)
        self._total = total

        # Titre dynamique avec la période
        self._title_pie.setText(
            "Dépenses par catégorie — 12 derniers mois"
        )

        if total == 0:
            self._rebuild_legend([])
            if hasattr(self, '_center_label'):
                self._update_center_label('Aucune', 'depense')
            return


        for i, (name, value) in enumerate(data):
            sl = self._series.append(name, value)
            color = QColor(DONUT_COLORS[i % len(DONUT_COLORS)])
            sl.setBrush(color)
            sl.setLabelVisible(False)
            sl.setExplodeDistanceFactor(0.06)
            sl.category_name = name
            sl.amount_value  = value
            sl.base_color    = color
            sl.hovered.connect(self._on_hover)
            sl.clicked.connect(
                lambda checked=False, cat=name: self._filter_category(cat)
            )

        self._rebuild_legend(data)
        if hasattr(self, "_center_label"):
            self._update_center_label(format_money(self._total), "D\u00e9penses")

    def _update_center_label(self, line1: str, line2: str = ""):
        text = f"{line1}\n{line2}" if line2 else line1
        self._center_label.setText(text)

    def _reposition_center_label(self):
        """Plus nécessaire avec QLabel overlay — gardé pour compatibilité."""
        pass

    def _force_center(self):
        """Plus nécessaire avec QLabel overlay — gardé pour compatibilité."""
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_center_label"):
            self._reposition_center_label()

    def _on_hover(self, state):
        sl = self.sender()
        if not sl or not hasattr(self, '_center_label'):
            return
        if state:
            sl.setExploded(True)
            sl.setBrush(QColor(sl.base_color).lighter(135))
            pct = (sl.amount_value / self._total * 100) if self._total else 0
            self._center_label.setText(
                f"{sl.category_name}\n{format_money(sl.amount_value)} · {pct:.1f}%"
            )
        else:
            sl.setExploded(False)
            sl.setBrush(sl.base_color)
            self._center_label.setText(
                f"{format_money(self._total)}\nDépenses"
            )

    def _rebuild_legend(self, data):
        """Construit la légende sous forme de tableau avec pastille, nom, montant, %."""
        self._legend_table.setSortingEnabled(False)
        self._legend_table.setRowCount(len(data))

        for i, (name, value) in enumerate(data):
            color = DONUT_COLORS[i % len(DONUT_COLORS)]
            pct   = (value / self._total * 100) if self._total else 0

            # Pastille couleur via QLabel
            dot_widget = QWidget()
            dot_widget.setStyleSheet("background:transparent;")
            dot_layout = QHBoxLayout(dot_widget)
            dot_layout.setContentsMargins(4, 0, 4, 0)
            dot_layout.setAlignment(Qt.AlignCenter)
            dot_lbl = QLabel()
            dot_lbl.setFixedSize(16, 16)
            dot_lbl.setStyleSheet(
                f"background:{color}; border-radius:8px; border:none;"
            )
            dot_layout.addWidget(dot_lbl)
            self._legend_table.setCellWidget(i, 0, dot_widget)

            # Catégorie
            name_item = QTableWidgetItem(f"  {name}")
            name_item.setForeground(QColor("#c8cdd4"))
            self._legend_table.setItem(i, 1, name_item)

            # Montant — valeur numérique dans UserRole pour tri correct
            amt_item = _NumericItem(format_money(value))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt_item.setForeground(QColor("#ef4444"))
            amt_item.setData(Qt.UserRole, float(value))
            font = amt_item.font(); font.setBold(True); amt_item.setFont(font)
            self._legend_table.setItem(i, 2, amt_item)

            # Pourcentage — valeur numérique dans UserRole pour tri correct
            pct_item = _NumericItem(f"{pct:.1f}%")
            pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct_item.setForeground(QColor("#7a8494"))
            pct_item.setData(Qt.UserRole, float(pct))
            self._legend_table.setItem(i, 3, pct_item)

        self._legend_table.setSortingEnabled(True)
        self._legend_table.horizontalHeader().setSortIndicatorShown(True)

    # ------------------------------------------------------------------
    def _build_comparison_tab(self, layout):
        """Compare le mois courant avec le mois précédent."""
        from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis
        from PySide6.QtGui import QPainter, QColor, QFont
        from datetime import date
        import calendar

        # Vider le layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        period = period_state.get()
        acc_id = account_state.get_id()
        y, m   = period.year, period.month

        # Mois précédent
        if m == 1:
            py, pm = y - 1, 12
        else:
            py, pm = y, m - 1

        MONTHS_FR = ["","Janvier","Février","Mars","Avril","Mai","Juin",
                     "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]

        from services.stats_service import monthly_income_expense
        cur_data  = monthly_income_expense(12)
        # Filtrer les 2 mois concernés
        def get_month(data, yy, mm):
            for row in data:
                if row[0] == yy and row[1] == mm:
                    return row
            return (yy, mm, 0, 0, 0)

        cur  = get_month(cur_data, y, m)
        prev = get_month(cur_data, py, pm)

        # ── Cartes de comparaison ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        for label, cur_val, prev_val, color in [
            ("Revenus",  cur[2], prev[2], "#22c55e"),
            ("Dépenses", cur[3], prev[3], "#ef4444"),
            ("Solde",    cur[4], prev[4], "#3b82f6"),
        ]:
            card = QWidget()
            card.setStyleSheet("background:#292d32; border-radius:10px; border:1px solid #3d4248;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(4)

            t = QLabel(label)
            t.setStyleSheet("font-size:11px; color:#7a8494; font-weight:600; letter-spacing:1px;")
            cur_lbl = QLabel(format_money(cur_val))
            cur_lbl.setStyleSheet(f"font-size:18px; font-weight:700; color:{color};")
            diff = cur_val - prev_val
            sign = "+" if diff >= 0 else ""
            diff_color = "#22c55e" if diff >= 0 else "#ef4444"
            if label == "Dépenses":
                diff_color = "#ef4444" if diff >= 0 else "#22c55e"
            diff_lbl = QLabel(f"{sign}{format_money(diff)} vs {MONTHS_FR[pm]}")
            diff_lbl.setStyleSheet(f"font-size:11px; color:{diff_color};")

            cl.addWidget(t)
            cl.addWidget(cur_lbl)
            cl.addWidget(diff_lbl)
            cards_row.addWidget(card)

        layout.addLayout(cards_row)

        # ── Graphique barres groupées ──
        bar_rev_cur  = QBarSet(MONTHS_FR[m])
        bar_rev_prev = QBarSet(MONTHS_FR[pm])
        bar_rev_cur.setColor(QColor("#22c55e"))
        bar_rev_prev.setColor(QColor("#3d4248"))

        bar_dep_cur  = QBarSet(f"{MONTHS_FR[m]} dép.")
        bar_dep_prev = QBarSet(f"{MONTHS_FR[pm]} dép.")
        bar_dep_cur.setColor(QColor("#ef4444"))
        bar_dep_prev.setColor(QColor("#7a3030"))

        bar_rev_cur.append(cur[2])
        bar_rev_prev.append(prev[2])
        bar_dep_cur.append(cur[3])
        bar_dep_prev.append(prev[3])

        series = QBarSeries()
        series.append(bar_rev_prev)
        series.append(bar_rev_cur)
        series.append(bar_dep_prev)
        series.append(bar_dep_cur)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(f"Comparaison {MONTHS_FR[pm]} vs {MONTHS_FR[m]} {y}")
        chart.setTitleFont(QFont("", 12, 700))
        chart.setBackgroundBrush(QColor("#1e2124"))
        chart.setTitleBrush(QColor("#c8cdd4"))
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(QColor("#848c94"))
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setMargins(QMargins(10, 10, 10, 10))

        axis_x = QBarCategoryAxis()
        axis_x.append(["Revenus / Dépenses"])
        axis_x.setLabelsColor(QColor("#848c94"))
        axis_x.setGridLineVisible(False)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(cur[2], cur[3], prev[2], prev[3], 1)
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.2)
        axis_y.setLabelsColor(QColor("#848c94"))
        axis_y.setGridLineColor(QColor("#2e3238"))
        axis_y.setLabelFormat("%.0f €")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(300)
        layout.addWidget(view)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Graphique 4 : Projection revenus — réel vs projeté sur 6 mois
    # ------------------------------------------------------------------
    def _build_income_projection_chart(self):
        from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis
        from PySide6.QtGui import QPainter, QColor, QFont
        from datetime import datetime
        from sqlalchemy import func as sqlfunc
        from db import Session
        from models import Transaction
        import account_state as acc_state

        now = datetime.now()
        MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                     "Juil","Août","Sep","Oct","Nov","Déc"]

        # Collecter les revenus réels des 6 derniers mois
        months_data = []
        with Session() as session:
            for i in range(5, -1, -1):
                m, y = now.month - i, now.year
                while m <= 0:
                    m += 12; y -= 1
                q = (
                    session.query(sqlfunc.sum(Transaction.amount))
                    .filter(Transaction.type == "income")
                    .filter(sqlfunc.extract("year",  Transaction.date) == y)
                    .filter(sqlfunc.extract("month", Transaction.date) == m)
                )
                aid = acc_state.get_id()
                if aid is not None:
                    q = q.filter(Transaction.account_id == aid)
                actual = q.scalar() or 0
                months_data.append((f"{MONTHS_FR[m]} {y}", actual))

        # Calculer la moyenne glissante (projection) pour chaque mois
        projected_data = []
        all_actuals = [d[1] for d in months_data]
        for idx in range(len(months_data)):
            # Moyenne des mois précédents disponibles (3 mois max)
            prev = [all_actuals[j] for j in range(max(0, idx - 3), idx) if all_actuals[j] > 0]
            if prev:
                projected_data.append(sum(prev) / len(prev))
            elif idx == 0:
                projected_data.append(all_actuals[0])
            else:
                projected_data.append(0)

        categories = [d[0] for d in months_data]
        actuals    = [d[1] for d in months_data]

        set_actual = QBarSet("Revenu réel")
        set_actual.setColor(QColor("#22c55e"))
        set_actual.setBorderColor(QColor("#16a34a"))

        set_proj = QBarSet("Projection (moyenne)")
        set_proj.setColor(QColor("#3b82f6"))
        set_proj.setBorderColor(QColor("#2563eb"))

        for v in actuals:
            set_actual.append(v)
        for v in projected_data:
            set_proj.append(v)

        series = QBarSeries()
        series.append(set_actual)
        series.append(set_proj)
        series.setBarWidth(0.7)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("")
        chart.setBackgroundVisible(False)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setAnimationDuration(600)
        chart.setMargins(QMargins(16, 4, 4, 4))

        legend = chart.legend()
        legend.setVisible(True)
        legend.setAlignment(Qt.AlignBottom)
        legend.setLabelColor(QColor("#c8cdd4"))
        legend.setFont(QFont("Segoe UI", 9))

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor("#7a8494"))
        axis_x.setLabelsAngle(-45)
        axis_x.setGridLineColor(QColor("#3a3f47"))
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(max(actuals, default=0), max(projected_data, default=0)) or 1
        axis_y = _make_y_axis(max_val, negative=False)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(240)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return view

    def refresh(self):
        """Rafraîchit toutes les sections."""
        self._load_data()
        self._replace_chart("_rvd_view", self._build_income_expense_chart(), 2)
        self._replace_chart("_income_proj_view", self._build_income_projection_chart(), 2)
        # Reconstruire le tableau récapitulatif
        old_table = self._recap_table
        self._recap_table = self._build_recap_table()
        tab1_layout = self._tab1_layout
        for i in range(tab1_layout.count()):
            item = tab1_layout.itemAt(i)
            if item and item.widget() == old_table:
                tab1_layout.removeWidget(old_table)
                old_table.deleteLater()
                tab1_layout.insertWidget(i, self._recap_table)
                break
        # Forcer la reconstruction des onglets au prochain clic
        self._pie_tab_built = False
        self._comp_tab_built = False

    def _replace_chart(self, attr: str, new_view, stretch: int):
        """Remplace un graphique dans le layout tab1 sans tout reconstruire."""
        old_view = getattr(self, attr)
        layout   = self._tab1_layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() == old_view:
                layout.removeWidget(old_view)
                old_view.deleteLater()
                layout.insertWidget(i, new_view, stretch)
                break
        setattr(self, attr, new_view)

    def _filter_category(self, category_name):
        main = self.window()
        if hasattr(main, "transactions"):
            main.set_active(1)
            main.transactions.search.setText(category_name)

    def _build_pie_tab(self, layout):
        """Onglet Répartition — donut interactif + barres proportionnelles."""
        from PySide6.QtCharts import QChart, QPieSeries, QChartView
        from PySide6.QtGui import QPainter, QColor, QFont
        from PySide6.QtCore import Qt, QMargins
        from PySide6.QtWidgets import (
            QLabel, QScrollArea, QWidget, QFrame,
            QHBoxLayout, QVBoxLayout,
            QProgressBar, QSizePolicy, QStackedLayout
        )

        # Vider le layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from services.stats_service import expenses_by_category_all
        from utils.formatters import format_money
        import period_state

        data  = expenses_by_category_all()
        total = sum(v for _, v in data) if data else 0

        if not data or total == 0:
            empty_w = QWidget()
            empty_w.setStyleSheet("background:transparent;")
            el = QVBoxLayout(empty_w)
            el.setAlignment(Qt.AlignCenter)
            el.setSpacing(12)
            icon_lbl = QLabel("📊")
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("font-size:48px; background:transparent; border:none;")
            msg = QLabel("Aucune dépense pour cette période")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("color:#5a6472; font-size:14px; background:transparent; border:none;")
            sub = QLabel(f"{period_state.label()}")
            sub.setAlignment(Qt.AlignCenter)
            sub.setStyleSheet("color:#3e4550; font-size:12px; background:transparent; border:none;")
            el.addWidget(icon_lbl)
            el.addWidget(msg)
            el.addWidget(sub)
            layout.addWidget(empty_w)
            layout.addStretch()
            return

        COLORS = [
            "#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#8b5cf6",
            "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
            "#14b8a6", "#a855f7", "#eab308", "#10b981", "#f43f5e",
        ]

        data = sorted(data, key=lambda x: x[1], reverse=True)
        max_val = data[0][1] if data else 1

        # ═══════════ BANDEAU KPI ═══════════
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        for kpi_title, kpi_value, kpi_color in [
            ("TOTAL DÉPENSES", format_money(total), "#ef4444"),
            ("CATÉGORIES", str(len(data)), "#3b82f6"),
            ("1ère CATÉGORIE", data[0][0] if data else "—", "#f59e0b"),
            ("PART DU 1er", f"{data[0][1] / total * 100:.0f} %" if data else "—", "#8b5cf6"),
        ]:
            kw = QWidget()
            kw.setStyleSheet("background:#292d32; border-radius:10px; border:1px solid #3d4248;")
            kl = QVBoxLayout(kw)
            kl.setContentsMargins(14, 10, 14, 10)
            kl.setSpacing(4)
            kt = QLabel(kpi_title)
            kt.setStyleSheet("font-size:9px; font-weight:700; color:#5a6472; letter-spacing:1.5px; background:transparent; border:none;")
            kv = QLabel(kpi_value)
            kv.setStyleSheet(f"font-size:17px; font-weight:700; color:{kpi_color}; background:transparent; border:none;")
            kl.addWidget(kt)
            kl.addWidget(kv)
            kpi_row.addWidget(kw, 1)
        layout.addLayout(kpi_row)

        # ═══════════ DONUT + BARRES ═══════════
        main_row = QHBoxLayout()
        main_row.setSpacing(16)

        # ── Donut (gauche) ──
        left_w = QWidget()
        left_w.setStyleSheet("background:transparent; border:none;")
        left_l = QVBoxLayout(left_w)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(2)
        left_l.setAlignment(Qt.AlignTop)

        period_lbl = QLabel(f"Répartition — {period_state.label()}")
        period_lbl.setAlignment(Qt.AlignCenter)
        period_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#848c94; background:transparent; border:none;")
        left_l.addWidget(period_lbl)

        series = QPieSeries()
        series.setHoleSize(0.58)
        series.setPieSize(0.85)
        self._pie_tab_series = series
        self._pie_tab_total  = total

        for i, (name, value) in enumerate(data):
            sl = series.append(name, value)
            color = QColor(COLORS[i % len(COLORS)])
            sl.setBrush(color)
            sl.setLabelVisible(False)
            sl.setExplodeDistanceFactor(0.04)
            sl.category_name = name
            sl.amount_value  = value
            sl.base_color    = color
            sl.hovered.connect(self._pie_tab_hover)
            sl.clicked.connect(lambda checked=False, cat=name: self._filter_category(cat))

        chart = QChart()
        chart.addSeries(series)
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.legend().setVisible(False)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setAnimationDuration(400)
        chart.setMargins(QMargins(0, 0, 0, 0))

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setStyleSheet("background:transparent; border:none;")
        view.setMinimumHeight(280)
        view.setMaximumHeight(310)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # QLabel positionné en absolu par-dessus le chart view
        self._pie_tab_center = QLabel(view)
        self._pie_tab_center.setAlignment(Qt.AlignCenter)
        self._pie_tab_center.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._pie_tab_center.setStyleSheet(
            "background:transparent; border:none; "
            "color:#c8cdd4; font-size:12px; font-weight:700;"
        )
        self._pie_tab_center.setText(f"{format_money(total)}\nDépenses")
        self._pie_tab_center.setFixedSize(160, 50)

        # Centrer le label quand le chart se redimensionne
        self._pie_tab_chart_view = view
        original_resize = view.resizeEvent
        def _on_resize(event):
            original_resize(event)
            self._center_pie_tab_label()
        view.resizeEvent = _on_resize

        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._center_pie_tab_label)

        left_l.addWidget(view)

        hint = QLabel("Survolez pour détailler — Cliquez pour filtrer")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:10px; color:#3e4550; background:transparent; border:none;")
        left_l.addWidget(hint)

        main_row.addWidget(left_w, 4)

        # ── Séparateur vertical ──
        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setStyleSheet("background:#2e3238; max-width:1px; border:none;")
        main_row.addWidget(vsep)

        # ── Barres proportionnelles (droite) ──
        right_w = QWidget()
        right_w.setStyleSheet("background:transparent; border:none;")
        right_l = QVBoxLayout(right_w)
        right_l.setContentsMargins(0, 4, 0, 0)
        right_l.setSpacing(0)

        bars_title = QLabel("DÉTAIL PAR CATÉGORIE")
        bars_title.setStyleSheet("font-size:10px; font-weight:700; color:#5a6472; letter-spacing:1.5px; background:transparent; border:none; margin-bottom:8px;")
        right_l.addWidget(bars_title)

        bars_scroll = QScrollArea()
        bars_scroll.setWidgetResizable(True)
        bars_scroll.setFrameShape(QFrame.NoFrame)
        bars_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bars_scroll.setStyleSheet("background:transparent; border:none;")

        bars_container = QWidget()
        bars_container.setStyleSheet("background:transparent; border:none;")
        bars_layout = QVBoxLayout(bars_container)
        bars_layout.setContentsMargins(0, 0, 4, 0)
        bars_layout.setSpacing(6)

        for i, (name, value) in enumerate(data):
            pct   = value / total * 100
            color = COLORS[i % len(COLORS)]

            row_w = QWidget()
            row_w.setCursor(Qt.PointingHandCursor)
            row_w.setStyleSheet(
                "QWidget { background:#23272b; border-radius:8px; border:none; }"
                "QWidget:hover { background:#292d32; }"
            )
            row_w.mousePressEvent = lambda e, cat=name: self._filter_category(cat)
            rl = QVBoxLayout(row_w)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(4)

            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background:{color}; border-radius:6px; border:none;")
            cat_lbl = QLabel(name)
            cat_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#c8cdd4; background:transparent; border:none;")
            amt_lbl = QLabel(format_money(value))
            amt_lbl.setAlignment(Qt.AlignRight)
            amt_lbl.setStyleSheet(f"font-size:12px; font-weight:700; color:{color}; background:transparent; border:none;")
            pct_lbl = QLabel(f"{pct:.1f}%")
            pct_lbl.setAlignment(Qt.AlignRight)
            pct_lbl.setFixedWidth(46)
            pct_lbl.setStyleSheet("font-size:11px; font-weight:600; color:#7a8494; background:transparent; border:none;")
            top_row.addWidget(dot)
            top_row.addWidget(cat_lbl, 1)
            top_row.addWidget(amt_lbl)
            top_row.addWidget(pct_lbl)
            rl.addLayout(top_row)

            bar = QProgressBar()
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            bar.setMaximum(1000)
            bar.setValue(int(value / max_val * 1000))
            bar.setStyleSheet(
                f"QProgressBar {{ background:#1e2124; border-radius:3px; border:none; }}"
                f"QProgressBar::chunk {{ background:{color}; border-radius:3px; }}"
            )
            rl.addWidget(bar)
            bars_layout.addWidget(row_w)

        bars_layout.addStretch()
        bars_scroll.setWidget(bars_container)
        right_l.addWidget(bars_scroll, 1)

        main_row.addWidget(right_w, 5)
        layout.addLayout(main_row, 1)

    def _pie_tab_hover(self, state):
        """Survol des tranches — met à jour le QLabel central."""
        from PySide6.QtGui import QColor
        from utils.formatters import format_money

        sl = self.sender()
        if not sl or not hasattr(self, '_pie_tab_center'):
            return

        if state:
            sl.setExploded(True)
            sl.setBrush(QColor(sl.base_color).lighter(130))
            pct = sl.amount_value / self._pie_tab_total * 100 if self._pie_tab_total else 0
            self._pie_tab_center.setText(
                f"{sl.category_name}\n{format_money(sl.amount_value)} · {pct:.1f}%"
            )
        else:
            sl.setExploded(False)
            sl.setBrush(sl.base_color)
            self._pie_tab_center.setText(
                f"{format_money(self._pie_tab_total)}\nDépenses"
            )

    def _center_pie_tab_label(self):
        """Positionne le label au centre du trou du donut."""
        if not hasattr(self, '_pie_tab_chart_view') or not hasattr(self, '_pie_tab_center'):
            return
        view = self._pie_tab_chart_view
        plot = view.chart().plotArea()
        if plot.width() < 10:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(200, self._center_pie_tab_label)
            return
        lbl = self._pie_tab_center
        cx = int(plot.center().x() - lbl.width() / 2)
        cy = int(plot.center().y() - lbl.height() / 2)
        lbl.move(cx, cy)
