import account_state
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QComboBox, QProgressBar, QFrame,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy, QScrollArea
)
from PySide6.QtCore import QSize, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor

from db import Session
from models import Category, Transaction, Budget
from sqlalchemy import func
from utils.icons import get_icon
from utils.formatters import format_money
import period_state

from services.transaction_service import set_budget, get_budget_status, delete_budget
from ui.toast import Toast


class BudgetView(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Titre ──
        self._form_label = QLabel("Budgets")
        self._form_label.setStyleSheet("font-size:15px; font-weight:600; color:#c8cdd4;")
        layout.addWidget(self._form_label)

        # ── Formulaire ajout en carte ──
        form_card = QWidget()
        form_card.setStyleSheet("""
            QWidget {
                background:#26292e; border-radius:12px;
                border:1px solid #3a3f47;
            }
        """)
        form_inner = QVBoxLayout(form_card)
        form_inner.setContentsMargins(16, 12, 16, 12)
        form_inner.setSpacing(8)

        form_title = QLabel("Définir un budget mensuel")
        form_title.setStyleSheet(
            "font-size:13px; font-weight:600; color:#c8cdd4; "
            "background:transparent; border:none;"
        )
        form_inner.addWidget(form_title)

        form_row = QHBoxLayout()
        form_row.setSpacing(8)

        self.category = QComboBox()
        self.category.setMinimumHeight(36)
        form_row.addWidget(self.category, 2)

        self.amount = QLineEdit()
        self.amount.setPlaceholderText("Limite mensuelle (€)")
        self.amount.setMinimumHeight(36)
        self.amount.setFixedWidth(160)
        self.amount.returnPressed.connect(self.save)
        form_row.addWidget(self.amount)

        btn = QPushButton("  Enregistrer")
        btn.setIcon(get_icon("budget.png"))
        btn.setIconSize(QSize(20, 20))
        btn.setMinimumHeight(36)
        btn.clicked.connect(self.save)
        form_row.addWidget(btn)

        form_inner.addLayout(form_row)
        layout.addWidget(form_card)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none; margin:4px 0;")
        layout.addWidget(sep)

        # ── Onglets ──
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #3a3f47;
                border-radius:8px;
                background:#1e2023;
            }
            QTabBar::tab {
                background:#26292e;
                color:#7a8494;
                padding:8px 20px;
                border:1px solid #3a3f47;
                border-bottom:none;
                border-radius:6px 6px 0 0;
                font-size:12px;
                font-weight:600;
            }
            QTabBar::tab:selected {
                background:#1e2023;
                color:#c8cdd4;
                border-bottom:1px solid #1e2023;
            }
            QTabBar::tab:hover { color:#c8cdd4; }
        """)

        # Tab 1 : Mois courant
        self._tab_current = QWidget()
        tab1_layout = QVBoxLayout(self._tab_current)
        tab1_layout.setSpacing(10)
        tab1_layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")

        self._budgets_widget = QWidget()
        self._budgets_widget.setStyleSheet("background:transparent;")
        self.results_layout = QVBoxLayout(self._budgets_widget)
        self.results_layout.setSpacing(10)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.addStretch()

        scroll.setWidget(self._budgets_widget)
        tab1_layout.addWidget(scroll)

        # Tab 2 : Historique
        self._tab_history = QWidget()
        tab2_layout = QVBoxLayout(self._tab_history)
        tab2_layout.setSpacing(8)
        tab2_layout.setContentsMargins(12, 12, 12, 12)

        self._history_table = QTableWidget()
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._history_table.setShowGrid(False)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.verticalHeader().setDefaultSectionSize(34)
        self._history_table.setAlternatingRowColors(False)
        self._history_table.setFocusPolicy(Qt.NoFocus)
        self._history_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #3a3f47; padding:4px 10px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section {
                background:#26292e; border:none;
                padding:6px 10px; font-weight:600; color:#7a8494;
                font-size:11px; border-bottom:1px solid #3a3f47;
            }
        """)
        tab2_layout.addWidget(self._history_table)

        self._tabs.addTab(self._tab_current, "Mois courant")
        self._tabs.addTab(self._tab_history, "Historique")
        self._tab_chart = QWidget()
        QVBoxLayout(self._tab_chart)
        self._tabs.addTab(self._tab_chart, "Graphique")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tabs, 1)
        self.setLayout(layout)

        self._bar_anims = []
        self.load_categories()
        self.refresh()

    # ------------------------------------------------------------------
    def showEvent(self, event):
        """Rejoue l'animation dès que la page Budget devient visible."""
        super().showEvent(event)
        self.refresh()

    def _animate_bar(self, bar: QProgressBar, target: int):
        """Anime une QProgressBar de 0 à target avec un effet ease-out.
        Si la vue n'est pas encore visible, applique directement la valeur finale."""
        if not self.isVisible():
            bar.setValue(target)
            return

        from PySide6.QtCore import QTimer
        STEPS = 50
        step  = [0]
        timer = QTimer(self)
        timer.setInterval(22)

        def _tick():
            s = step[0]
            if s >= STEPS:
                bar.setValue(target)
                timer.stop()
                return
            ease = 1 - (1 - s / STEPS) ** 3
            bar.setValue(int(target * ease))
            step[0] += 1

        timer.timeout.connect(_tick)
        timer.start()
        self._bar_anims.append(timer)

    def load_categories(self):
        from utils.category_icons import get_category_icon
        with Session() as session:
            categories = session.query(Category).order_by(Category.name).all()
        self.category.clear()
        self.category.setIconSize(QSize(18, 18))
        self.category.addItem("— Choisir une catégorie —", None)
        for c in categories:
            raw_icon = c.icon or ""
            icon_file = raw_icon if raw_icon.endswith(".png") else get_category_icon(c.name)
            self.category.addItem(get_icon(icon_file, 18), c.name, c.id)
        self.category.setCurrentIndex(0)

    def save(self):
        try:
            amount = float(self.amount.text().replace(",", "."))
            if amount <= 0:
                Toast.show(self, "✕  Le montant doit être positif", kind="error")
                return
        except ValueError:
            Toast.show(self, "✕  Montant invalide", kind="error")
            self.amount.setFocus()
            return

        category_id = self.category.currentData()
        if not category_id:
            Toast.show(self, "✕  Choisissez une catégorie", kind="error")
            self.category.showPopup()
            return

        # Vérifier si la catégorie est plutôt un revenu
        from db import Session as _S
        from models import Transaction as _T
        from sqlalchemy import func as _f
        with _S() as s:
            income_count = s.query(_f.count(_T.id)).filter(
                _T.category_id == category_id,
                _T.type == "income"
            ).scalar() or 0
            expense_count = s.query(_f.count(_T.id)).filter(
                _T.category_id == category_id,
                _T.type == "expense"
            ).scalar() or 0

        set_budget(category_id, amount)
        self.amount.clear()
        self.category.setCurrentIndex(0)
        self.refresh()

        if income_count > expense_count:
            Toast.show(self, "Budget enregistré — attention : cette catégorie est surtout utilisée pour des revenus", kind="warning")
        else:
            Toast.show(self, "✓  Budget enregistré", kind="success")

    def _on_tab_changed(self, index):
        if index == 1:
            self._build_history()

    # ------------------------------------------------------------------
    def refresh(self):
        acc = account_state.get_name()
        self._form_label.setText(f"Budgets — {acc}" if acc else "Budgets")

        self._bar_anims.clear()

        # Vider
        while self.results_layout.count() > 1:
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        data = get_budget_status()

        with Session() as session:
            categories = {c.id: c for c in session.query(Category).all()}

        if not data:
            empty = QLabel("Aucun budget défini. Ajoutez-en un ci-dessus.")
            empty.setStyleSheet("color:#6b7280; font-style:italic; padding:12px 0;")
            self.results_layout.insertWidget(0, empty)
            return

        # Calculer les dépenses du mois précédent pour la tendance
        p = period_state.get()
        pm, py = p.month - 1, p.year
        if pm <= 0:
            pm += 12
            py -= 1
        prev_spent = {}
        with Session() as session:
            for cat_id, limit, spent in data:
                q = session.query(func.sum(Transaction.amount)).filter(
                    Transaction.category_id == cat_id,
                    Transaction.type == "expense",
                    func.extract("year",  Transaction.date) == py,
                    func.extract("month", Transaction.date) == pm,
                )
                acc_id = account_state.get_id()
                if acc_id is not None:
                    q = q.filter(Transaction.account_id == acc_id)
                prev_spent[cat_id] = q.scalar() or 0

        for cat_id, limit, spent in data:
            cat   = categories.get(cat_id)
            name  = cat.name if cat else "Inconnu"
            color = cat.color if cat and cat.color else "#7a8494"

            row_widget = QWidget()
            row_widget.setStyleSheet(
                "background:#26292e; border-radius:10px; border:1px solid #3a3f47;"
            )
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(6)

            # Ligne 1 : nom + tendance + montants + supprimer
            header = QHBoxLayout()
            name_label = QLabel(name)
            name_label.setStyleSheet(
                "font-weight:600; font-size:13px; background:transparent; border:none;"
            )

            # Indicateur de tendance vs mois précédent
            prev = prev_spent.get(cat_id, 0)
            if prev > 0:
                diff_pct = ((spent - prev) / prev) * 100
                if diff_pct > 5:
                    trend_text = f"▲ {diff_pct:.0f}%"
                    trend_color = "#ef4444"
                elif diff_pct < -5:
                    trend_text = f"▼ {abs(diff_pct):.0f}%"
                    trend_color = "#22c55e"
                else:
                    trend_text = "≈"
                    trend_color = "#7a8494"
                trend_label = QLabel(trend_text)
                trend_label.setStyleSheet(
                    f"font-size:11px; font-weight:600; color:{trend_color}; "
                    "background:transparent; border:none;"
                )
                trend_label.setToolTip(
                    f"Mois précédent : {format_money(prev)}"
                )
            else:
                trend_label = None

            percent = min((spent / limit) * 100, 100) if limit > 0 else 0
            reste = max(limit - spent, 0)
            amounts_label = QLabel(f"{format_money(spent)} / {format_money(limit)}")
            amounts_label.setAlignment(Qt.AlignRight)
            amounts_label.setStyleSheet(
                "color:#7a8494; font-size:12px; background:transparent; border:none;"
            )
            btn_edit = QPushButton("Modifier")
            btn_edit.setFixedHeight(26)
            btn_edit.setStyleSheet(
                "background:#1a2a3a; color:#60a5fa; border:1px solid #2a4a6a;"
                "border-radius:5px; font-size:11px; padding:0 8px;"
            )
            btn_edit.clicked.connect(lambda _, cid=cat_id, lim=limit: self._edit_budget(cid, lim))
            btn_del = QPushButton("Supprimer")
            btn_del.setFixedHeight(26)
            btn_del.setStyleSheet(
                "background:#2e2020; color:#e89090; border:1px solid #503030;"
                "border-radius:5px; font-size:11px; padding:0 8px;"
            )
            btn_del.clicked.connect(lambda _, cid=cat_id: self._delete_budget(cid))
            header.addWidget(name_label)
            if trend_label:
                header.addWidget(trend_label)
            header.addStretch()
            header.addWidget(amounts_label)
            header.addSpacing(8)
            header.addWidget(btn_edit)
            header.addWidget(btn_del)
            row_layout.addLayout(header)

            # Barre de progression
            bar = QProgressBar()
            bar.setMaximum(100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)

            if percent >= 100:
                bar_color = "#ef4444"
                status_text = f"⚠ Budget dépassé de {format_money(spent - limit)}"
                status_color = "#ef4444"
            elif percent >= 80:
                bar_color = "#f59e0b"
                status_text = f"Attention — reste {format_money(reste)}"
                status_color = "#f59e0b"
            else:
                bar_color = color
                status_text = f"Reste {format_money(reste)} disponible"
                status_color = "#22c55e"

            bar.setStyleSheet(f"""
                QProgressBar {{ background:#17191c; border-radius:4px; }}
                QProgressBar::chunk {{ background:{bar_color}; border-radius:4px; }}
            """)
            row_layout.addWidget(bar)

            # Animer la barre de 0 → valeur cible via QTimer
            self._animate_bar(bar, int(percent))

            # Ligne statut
            status_row = QHBoxLayout()
            status_label = QLabel(status_text)
            status_label.setStyleSheet(
                f"color:{status_color}; font-size:11px; "
                "background:transparent; border:none;"
            )
            pct_label = QLabel(f"{percent:.0f}%")
            pct_label.setAlignment(Qt.AlignRight)
            pct_label.setStyleSheet(
                f"color:{status_color}; font-size:11px; font-weight:600; "
                "background:transparent; border:none;"
            )
            status_row.addWidget(status_label)
            status_row.addStretch()
            status_row.addWidget(pct_label)
            row_layout.addLayout(status_row)

            self.results_layout.insertWidget(self.results_layout.count() - 1, row_widget)

        # Rafraîchir l'historique si visible
        if self._tabs.currentIndex() == 1:
            self._build_history()

    # ------------------------------------------------------------------
    def _edit_budget(self, category_id: int, current_limit: float):
        """Modifie le montant limite d'un budget existant."""
        from PySide6.QtWidgets import QDialog, QFormLayout, QDoubleSpinBox, QDialogButtonBox

        dlg = QDialog(self)
        dlg.setWindowTitle("Modifier le budget")
        dlg.setFixedWidth(320)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)

        spin = QDoubleSpinBox()
        spin.setRange(1, 999999)
        spin.setValue(current_limit)
        spin.setSuffix(" €")
        spin.setMinimumHeight(36)
        form.addRow(QLabel("Nouvelle limite :"), spin)

        btns = QDialogButtonBox()
        btns.addButton("Enregistrer", QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler", QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.Accepted:
            set_budget(category_id, spin.value())
            self.refresh()
            Toast.show(self, "Budget modifié", kind="success")

    # ------------------------------------------------------------------
    def _on_tab_changed(self, index):
        if index == 2:
            self._build_budget_chart()

    def _build_budget_chart(self):
        """Graphique en barres des budgets : dépensé vs limite."""
        from PySide6.QtCharts import (QChart, QChartView, QBarSeries, QBarSet,
            QBarCategoryAxis, QValueAxis)
        from PySide6.QtGui import QPainter, QColor
        from PySide6.QtCore import Qt
        import account_state, period_state

        # Vider le layout existant
        layout = self._tab_chart.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        from services.transaction_service import get_budget_status
        from db import Session
        from models import Category
        from PySide6.QtGui import QFont

        raw = get_budget_status()
        if not raw:
            lbl = QLabel("Aucun budget configuré.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#7a8494; font-size:13px;")
            layout.addWidget(lbl)
            return

        # Résoudre les noms de catégories
        with Session() as session:
            cat_names = {c.id: c.name for c in session.query(Category).all()}

        categories = []
        bar_spent  = QBarSet("Dépensé")
        bar_limit  = QBarSet("Limite")
        bar_spent.setColor(QColor("#3b82f6"))
        bar_limit.setColor(QColor("#3d4248"))
        max_val = 100

        for cat_id, limit, spent in raw:
            name = cat_names.get(cat_id, str(cat_id))[:12]
            categories.append(name)
            bar_spent.append(round(spent, 2))
            bar_limit.append(round(limit, 2))
            max_val = max(max_val, limit)

        series = QBarSeries()
        series.append(bar_limit)
        series.append(bar_spent)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(f"Budgets - {period_state.label()}")
        chart.setTitleFont(QFont("", 11, 700))
        chart.setBackgroundBrush(QColor("#1e2124"))
        chart.setTitleBrush(QColor("#c8cdd4"))
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(QColor("#848c94"))
        chart.setAnimationOptions(QChart.SeriesAnimations)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor("#848c94"))
        axis_x.setLabelsFont(QFont("", 8))
        axis_x.setGridLineVisible(False)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.15)
        axis_y.setLabelsColor(QColor("#848c94"))
        axis_y.setLabelsFont(QFont("", 8))
        axis_y.setGridLineColor(QColor("#2e3238"))
        axis_y.setLabelFormat("%d")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(320)
        layout.addWidget(view)

    def _delete_budget(self, category_id: int):
        """Supprime un budget après confirmation."""
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer le budget")
        msg.setText("Supprimer ce budget ?")
        btn_oui = msg.addButton("Supprimer", QMessageBox.AcceptRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_oui:
            delete_budget(category_id)
            self.refresh()
            Toast.show(self, "Budget supprimé", kind="warning")

    def _build_history(self):
        """Construit le tableau historique : catégories x mois."""
        from datetime import datetime

        MONTHS_FR = ["","Jan","Fév","Mar","Avr","Mai","Juin",
                     "Juil","Août","Sep","Oct","Nov","Déc"]

        acc_id = account_state.get_id()

        # Récupérer les budgets du compte actif
        with Session() as session:
            q_budgets = session.query(Budget)
            if acc_id is not None:
                q_budgets = q_budgets.filter(Budget.account_id == acc_id)
            budgets = {b.category_id: b.monthly_limit for b in q_budgets.all()}
            categories = {c.id: c for c in session.query(Category).all()}

        if not budgets:
            self._history_table.setRowCount(1)
            self._history_table.setColumnCount(1)
            self._history_table.setHorizontalHeaderLabels([""])
            item = QTableWidgetItem("Aucun budget défini")
            item.setForeground(QColor("#6b7280"))
            self._history_table.setItem(0, 0, item)
            return

        # Déterminer les mois disponibles (6 derniers mois avec données)
        today = datetime.now()
        months = []
        for i in range(5, -1, -1):
            m, y = today.month - i, today.year
            while m <= 0:
                m += 12; y -= 1
            months.append((y, m, f"{MONTHS_FR[m]} {y}"))

        # Filtrer : ne garder que les mois avec au moins une transaction
        months_with_data = []
        with Session() as session:
            for y, m, label in months:
                q = session.query(func.count(Transaction.id)).filter(
                    func.extract("year",  Transaction.date) == y,
                    func.extract("month", Transaction.date) == m,
                )
                if acc_id is not None:
                    q = q.filter(Transaction.account_id == acc_id)
                if q.scalar() > 0:
                    months_with_data.append((y, m, label))

        if not months_with_data:
            months_with_data = [(today.year, today.month,
                                 f"{MONTHS_FR[today.month]} {today.year}")]

        # Construire le tableau
        cat_ids = sorted(budgets.keys(),
                         key=lambda cid: categories[cid].name if cid in categories else "")

        # Colonnes : Catégorie | Limite | Mois1 | Mois2 | ...
        col_labels = ["Catégorie", "Limite"] + [m[2] for m in months_with_data]
        self._history_table.setColumnCount(len(col_labels))
        self._history_table.setHorizontalHeaderLabels(col_labels)
        self._history_table.setRowCount(len(cat_ids))

        hdr = self._history_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in range(2, len(col_labels)):
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)

        with Session() as session:
            for row, cat_id in enumerate(cat_ids):
                cat   = categories.get(cat_id)
                name  = cat.name if cat else "Inconnu"
                limit = budgets[cat_id]

                # Catégorie
                name_item = QTableWidgetItem(f"  {name}")
                name_item.setForeground(QColor("#c8cdd4"))
                self._history_table.setItem(row, 0, name_item)

                # Limite
                limit_item = QTableWidgetItem(format_money(limit))
                limit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                limit_item.setForeground(QColor("#7a8494"))
                self._history_table.setItem(row, 1, limit_item)

                # Dépenses par mois
                for col, (y, m, _) in enumerate(months_with_data, start=2):
                    q = session.query(func.sum(Transaction.amount)).filter(
                        Transaction.category_id == cat_id,
                        Transaction.type == "expense",
                        func.extract("year",  Transaction.date) == y,
                        func.extract("month", Transaction.date) == m,
                    )
                    if acc_id is not None:
                        q = q.filter(Transaction.account_id == acc_id)
                    spent = q.scalar() or 0

                    pct = (spent / limit * 100) if limit > 0 else 0
                    spent_item = QTableWidgetItem(format_money(spent))
                    spent_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                    if pct >= 100:
                        spent_item.setForeground(QColor("#ef4444"))
                        spent_item.setBackground(QColor("#2e1f1f"))
                    elif pct >= 80:
                        spent_item.setForeground(QColor("#f59e0b"))
                    elif spent > 0:
                        spent_item.setForeground(QColor("#22c55e"))
                    else:
                        spent_item.setForeground(QColor("#4a5060"))

                    self._history_table.setItem(row, col, spent_item)
