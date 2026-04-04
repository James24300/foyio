"""
Vue Épargne — Foyio
4 sections :
  1. Objectifs d'épargne avec barres de progression
  2. Taux d'épargne mensuel (12 mois)
  3. Évolution de l'épargne cumulée
  4. Simulateur
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QDialog, QFormLayout,
    QLineEdit, QDoubleSpinBox, QDateEdit, QComboBox,
    QDialogButtonBox, QProgressBar, QTabWidget, QSpinBox,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QBarSeries, QBarSet,
    QBarCategoryAxis, QValueAxis, QAreaSeries
)
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import Qt, QDate, QMargins

from utils.formatters import format_money
from utils.icons import get_icon

GOAL_COLORS = [
    "#22c55e", "#3b82f6", "#f59e0b", "#8b5cf6",
    "#ef4444", "#06b6d4", "#f97316", "#ec4899",
]


class SavingsView(QWidget):

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Onglets
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #3d4248; border-radius:10px;
                background:#1e2124;
            }
            QTabBar::tab {
                background:#292d32; color:#7a8494;
                padding:8px 18px; border-radius:8px 8px 0 0;
                font-size:12px; font-weight:600;
            }
            QTabBar::tab:selected { background:#3e4550; color:#c8cdd4; }
            QTabBar::tab:hover    { background:#2e3238; color:#c8cdd4; }
        """)

        self._tab_goals    = self._build_goals_tab()
        self._tab_txn      = self._build_txn_tab()
        self._tab_rate     = self._build_rate_tab()
        self._tab_sim      = self._build_sim_tab()

        self._tabs.addTab(self._tab_goals, "  Objectifs")
        self._tabs.addTab(self._tab_txn,   "  Transactions")
        self._tabs.addTab(self._tab_rate,  "  Taux d'épargne")
        self._tabs.addTab(self._tab_sim,   "  Simulateur")

        # ── Barre titre + aide ──
        _HELP = {
            0: ("Objectifs d'épargne",
                "Créez des objectifs (voyage, voiture, urgences…) avec un montant cible.\n\n"
                "• La barre de progression indique l'avancement.\n"
                "• Cliquez sur «  Transactions » puis sur une ligne pour y ventiler de l'argent.\n"
                "• Le bouton « Synchroniser » met à jour le total depuis vos transactions catégorisées Épargne."),
            1: ("Transactions épargne",
                "Liste de toutes vos transactions dont la catégorie est « Épargne ».\n\n"
                "• Cliquez sur une ligne pour ouvrir la fenêtre de ventilation.\n"
                "• La ventilation permet de répartir une transaction sur un ou plusieurs objectifs.\n"
                "• La colonne « Reste » indique la part non encore affectée à un objectif."),
            2: ("Taux d'épargne mensuel",
                "Visualisez votre effort d'épargne mois par mois sur les 12 derniers mois.\n\n"
                "• Le taux = dépenses épargne ÷ revenus totaux × 100.\n"
                "• La ligne verte indique un objectif de 10 % (recommandation courante).\n"
                "• Un taux négatif signifie qu'aucun revenu n'a été enregistré ce mois-là."),
            3: ("Simulateur d'épargne",
                "Estimez combien vous accumulerez selon votre versement mensuel et un taux d'intérêt annuel.\n\n"
                "• Entrez un capital de départ, un versement mensuel et une durée.\n"
                "• Le taux annuel tient compte des intérêts composés (ex. livret, assurance-vie).\n"
                "• Les résultats sont indicatifs et ne constituent pas un conseil financier."),
        }
        from PySide6.QtWidgets import QMessageBox as _QMB
        top_row = QHBoxLayout()
        top_row.addStretch()
        _help_btn = QPushButton(" ? Aide")
        _help_btn.setFixedHeight(26)
        _help_btn.setToolTip("Aide sur cet onglet")
        _help_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#5a6472; border:1px solid #3d4248; "
            "border-radius:6px; font-size:11px; font-weight:600; padding:0 8px; }"
            "QPushButton:hover { color:#c8cdd4; border-color:#6b7280; }"
        )
        def _show_help():
            idx = self._tabs.currentIndex()
            title, text = _HELP.get(idx, ("Aide", ""))
            _QMB.information(self, title, text)
        _help_btn.clicked.connect(_show_help)
        top_row.addWidget(_help_btn)
        layout.addLayout(top_row)

        layout.addWidget(self._tabs)
        self.refresh()

    # ─────────────────────────────────────────────
    # ONGLET 1 : Objectifs
    # ─────────────────────────────────────────────
    def _build_txn_tab(self):
        """Onglet : liste des transactions épargne avec ventilation."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QLabel(
            "Cliquez sur une transaction pour la ventiler sur un ou plusieurs objectifs."
        )
        info.setStyleSheet("font-size:11px; color:#7a8494;")
        layout.addWidget(info)

        self._txn_table = QTableWidget()
        self._txn_table.setColumnCount(6)
        self._txn_table.setHorizontalHeaderLabels(
            ["Date", "Catégorie", "Description", "Montant", "Ventilé", "Reste"]
        )
        self._txn_table.verticalHeader().setVisible(False)
        self._txn_table.setShowGrid(False)
        self._txn_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._txn_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._txn_table.setAlternatingRowColors(True)
        self._txn_table.setFocusPolicy(Qt.NoFocus)
        self._txn_table.verticalHeader().setDefaultSectionSize(34)
        self._txn_table.itemDoubleClicked.connect(self._ventiler_transaction)
        hdr = self._txn_table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView
        hdr.setSectionResizeMode(0, QHeaderView.Fixed);  self._txn_table.setColumnWidth(0, 95)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed);  self._txn_table.setColumnWidth(1, 110)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed);  self._txn_table.setColumnWidth(3, 95)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed);  self._txn_table.setColumnWidth(4, 95)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._txn_table.setColumnWidth(5, 90)
        self._txn_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#2e3238; }
            QTableWidget::item:alternate { background:#202428; }
            QHeaderView::section {
                background:#292d32; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:4px 8px;
            }
        """)
        layout.addWidget(self._txn_table, 1)

        hint = QLabel("Double-clic sur une ligne pour ventiler")
        hint.setStyleSheet("font-size:10px; color:#4b5563;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        return tab

    def _reload_txn_table(self):
        from services.savings_service import get_savings_transactions
        from PySide6.QtGui import QColor
        from PySide6.QtCore import Qt

        rows = get_savings_transactions()
        self._txn_table.setSortingEnabled(False)
        self._txn_table.setRowCount(len(rows))

        if not rows:
            self._txn_table.setRowCount(1)
            _ei = QTableWidgetItem("Aucune transaction épargne — ajoutez des transactions avec la catégorie Épargne.")
            _ei.setTextAlignment(Qt.AlignCenter)
            _ei.setForeground(QColor("#5a6472"))
            _ei.setFlags(Qt.ItemIsEnabled)
            self._txn_table.setItem(0, 0, _ei)
            self._txn_table.setSpan(0, 0, 1, self._txn_table.columnCount())
            return

        for i, r in enumerate(rows):
            date_item = QTableWidgetItem(r["date"].strftime("%d/%m/%Y"))
            date_item.setData(Qt.UserRole, r["id"])
            self._txn_table.setItem(i, 0, date_item)
            self._txn_table.setItem(i, 1, QTableWidgetItem(r["cat_name"]))
            self._txn_table.setItem(i, 2, QTableWidgetItem(r["note"]))

            amt = QTableWidgetItem(format_money(r["amount"]))
            amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt.setForeground(QColor("#22c55e"))
            self._txn_table.setItem(i, 3, amt)

            alloc = QTableWidgetItem(format_money(r["allocated"]))
            alloc.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            alloc.setForeground(QColor("#c8cdd4"))
            self._txn_table.setItem(i, 4, alloc)

            remain = r["remaining"]
            rem_item = QTableWidgetItem(format_money(remain))
            rem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if remain <= 0:
                rem_item.setForeground(QColor("#22c55e"))
            elif remain < r["amount"]:
                rem_item.setForeground(QColor("#f59e0b"))
            else:
                rem_item.setForeground(QColor("#848c94"))
            self._txn_table.setItem(i, 5, rem_item)

        self._txn_table.setSortingEnabled(True)

    def _ventiler_transaction(self, item):
        """Dialogue de ventilation d'une transaction sur les objectifs."""
        row = item.row()
        txn_id = self._txn_table.item(row, 0).data(Qt.UserRole)
        if not txn_id:
            return

        from services.savings_service import (
            get_savings_transactions, get_goals, get_allocations,
            add_allocation, delete_allocation
        )
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QLabel, QDoubleSpinBox, QPushButton, QComboBox, QTableWidget,
            QTableWidgetItem, QHeaderView)
        from PySide6.QtGui import QColor

        # Infos transaction
        txns = get_savings_transactions()
        txn = next((t for t in txns if t["id"] == txn_id), None)
        if not txn:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Ventiler la transaction")
        dlg.setMinimumWidth(520)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        # En-tête
        header = QLabel(
            f"{txn['date'].strftime('%d/%m/%Y')}  •  {txn['cat_name']}  •  "
            f"{format_money(txn['amount'])}"
        )
        header.setStyleSheet(
            "font-size:14px; font-weight:700; color:#c8cdd4; "
            "background:#292d32; border-radius:8px; padding:10px;"
        )
        vl.addWidget(header)

        # Reste à ventiler
        self._ventil_remain_lbl = QLabel()
        self._ventil_remain_lbl.setStyleSheet(
            "font-size:12px; color:#f59e0b; font-weight:600;"
        )
        vl.addWidget(self._ventil_remain_lbl)

        # Tableau ventilations existantes
        alloc_tbl = QTableWidget(0, 3)
        alloc_tbl.setHorizontalHeaderLabels(["Objectif", "Montant", ""])
        alloc_tbl.verticalHeader().setVisible(False)
        alloc_tbl.setShowGrid(False)
        alloc_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        alloc_tbl.setMaximumHeight(150)
        alloc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        alloc_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        alloc_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        alloc_tbl.setColumnWidth(2, 32)
        alloc_tbl.setStyleSheet(
            "QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }"
            "QHeaderView::section { background:#292d32; color:#7a8494; border:none; "
            "border-bottom:1px solid #3a3f47; padding:4px 8px; }"
        )
        vl.addWidget(alloc_tbl)

        def reload_allocs():
            allocs = get_allocations(txn_id)
            total_alloc = sum(a["amount"] for a in allocs)
            remain = txn["amount"] - total_alloc
            self._ventil_remain_lbl.setText(
                f"Reste à ventiler : {format_money(remain)}"
            )
            self._ventil_remain_lbl.setStyleSheet(
                f"font-size:12px; font-weight:600; "
                f"color:{'#22c55e' if remain <= 0 else '#f59e0b'};"
            )
            alloc_tbl.setRowCount(len(allocs))
            for i, a in enumerate(allocs):
                alloc_tbl.setItem(i, 0, QTableWidgetItem(a["goal_name"]))
                amt_i = QTableWidgetItem(format_money(a["amount"]))
                amt_i.setForeground(QColor("#22c55e"))
                alloc_tbl.setItem(i, 1, amt_i)
                btn_del = QPushButton("✕")
                btn_del.setFixedSize(28, 28)
                btn_del.setStyleSheet("background:#3a1a1a; color:#ef4444; border-radius:6px; border:none;")
                def _confirm_del(_, aid=a["id"]):
                    from PySide6.QtWidgets import QMessageBox
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Confirmer la suppression")
                    msg.setText("Supprimer cette ventilation ?")
                    btn_yes = msg.addButton("Oui", QMessageBox.AcceptRole)
                    msg.addButton("Non", QMessageBox.RejectRole)
                    msg.exec()
                    if msg.clickedButton() != btn_yes:
                        return
                    delete_allocation(aid)
                    reload_allocs()
                    self._reload_txn_table()
                    self._reload_goals()
                btn_del.clicked.connect(_confirm_del)
                alloc_tbl.setCellWidget(i, 2, btn_del)

        reload_allocs()

        # Formulaire ajout ventilation
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#3d4248; max-height:1px;")
        vl.addWidget(sep)

        add_lbl = QLabel("Ajouter une ventilation :")
        add_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#848c94;")
        vl.addWidget(add_lbl)

        row_add = QHBoxLayout()
        goal_combo = QComboBox()
        goal_combo.setMinimumHeight(34)
        goals = get_goals()
        for g in goals:
            goal_combo.addItem(g.name, g.id)

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0.01, txn["amount"])
        amount_spin.setValue(txn["remaining"] if txn["remaining"] > 0 else txn["amount"])
        amount_spin.setSuffix(" €")
        amount_spin.setMinimumHeight(34)
        amount_spin.setFixedWidth(110)

        btn_add = QPushButton("Ajouter")
        btn_add.setMinimumHeight(34)
        btn_add.setFixedWidth(90)

        row_add.addWidget(goal_combo, 1)
        row_add.addWidget(amount_spin)
        row_add.addWidget(btn_add)
        vl.addLayout(row_add)

        msg_lbl = QLabel()
        msg_lbl.setStyleSheet("font-size:11px; color:#ef4444;")
        vl.addWidget(msg_lbl)

        def do_add():
            ok = add_allocation(txn_id, goal_combo.currentData(), amount_spin.value())
            if ok:
                msg_lbl.setText("")
                reload_allocs()
                self._reload_txn_table()
                self._reload_goals()
            else:
                msg_lbl.setText("⚠ Montant dépasse le reste disponible.")

        btn_add.clicked.connect(do_add)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)

        dlg.exec()

    def _build_goals_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Bouton ajouter
        # ── Indicateur global ──
        self._global_indicator = QWidget()
        self._global_indicator.setStyleSheet(
            "background:#292d32; border-radius:10px; border:1px solid #3d4248;"
        )
        gi_layout = QHBoxLayout(self._global_indicator)
        gi_layout.setContentsMargins(16, 10, 16, 10)
        gi_layout.setSpacing(12)

        self._gi_label = QLabel("Total épargné")
        self._gi_label.setStyleSheet("color:#848c94; font-size:12px; background:transparent; border:none;")
        self._gi_total = QLabel("0 €")
        self._gi_total.setStyleSheet("color:#22c55e; font-size:16px; font-weight:700; background:transparent; border:none;")
        self._gi_bar = QProgressBar()
        self._gi_bar.setFixedHeight(8)
        self._gi_bar.setTextVisible(False)
        self._gi_bar.setStyleSheet("""
            QProgressBar { background:#3d4248; border-radius:4px; border:none; }
            QProgressBar::chunk { background:#22c55e; border-radius:4px; }
        """)
        self._gi_pct = QLabel("0%")
        self._gi_pct.setStyleSheet("color:#7a8494; font-size:12px; background:transparent; border:none;")

        self._btn_sync = QPushButton("  Synchroniser")
        self._btn_sync.setIcon(get_icon("transactions.png"))
        self._btn_sync.setMinimumHeight(30)
        self._btn_sync.setStyleSheet("background:#2e3238; color:#848c94; border:1px solid #3d4248; border-radius:8px; font-size:11px;")
        self._btn_sync.setToolTip("Synchroniser avec les transactions épargne")
        self._btn_sync.clicked.connect(self._sync_savings)

        gi_layout.addWidget(self._gi_label)
        gi_layout.addWidget(self._gi_total)
        gi_layout.addWidget(self._gi_bar, 1)
        gi_layout.addWidget(self._gi_pct)
        gi_layout.addWidget(self._btn_sync)
        layout.addWidget(self._global_indicator)

        # ── Boutons action ──
        btn_row = QHBoxLayout()
        btn_add = QPushButton("  Nouvel objectif")
        btn_add.setIcon(get_icon("add.png"))
        btn_add.setMinimumHeight(36)
        btn_add.clicked.connect(self._add_goal)
        btn_row.addWidget(btn_add)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Zone de scroll pour les cartes objectifs
        self._goals_scroll = QScrollArea()
        self._goals_scroll.setWidgetResizable(True)
        self._goals_scroll.setFrameShape(QFrame.NoFrame)
        self._goals_scroll.setStyleSheet("background:transparent; border:none;")

        self._goals_container = QWidget()
        self._goals_container.setStyleSheet("background:transparent;")
        self._goals_layout = QVBoxLayout(self._goals_container)
        self._goals_layout.setSpacing(10)
        self._goals_layout.addStretch()

        self._goals_scroll.setWidget(self._goals_container)
        layout.addWidget(self._goals_scroll, 1)

        return tab

    def _build_goal_card(self, goal) -> QWidget:
        """Construit une carte objectif avec indicateur visuel et détails."""
        pct = min((goal.current_amount / goal.target_amount * 100)
                  if goal.target_amount > 0 else 0, 100)

        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background:#292d32;
                border-radius:12px;
                border-left:4px solid {goal.color};
            }}
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(16)

        # ── Indicateur pourcentage (gauche) ──
        pct_widget = QWidget()
        pct_widget.setFixedSize(72, 72)
        pct_widget.setStyleSheet(f"""
            QWidget {{
                background:#1e2124;
                border:3px solid {goal.color};
                border-radius:36px;
            }}
        """)
        pct_inner = QVBoxLayout(pct_widget)
        pct_inner.setContentsMargins(0, 0, 0, 0)
        pct_inner.setAlignment(Qt.AlignCenter)
        pct_label = QLabel(f"{pct:.0f}%")
        pct_label.setAlignment(Qt.AlignCenter)
        pct_label.setStyleSheet(
            f"font-size:16px; font-weight:700; color:{goal.color}; "
            "background:transparent; border:none;"
        )
        pct_inner.addWidget(pct_label)
        card_layout.addWidget(pct_widget)

        # ── Contenu principal (droite) ──
        right = QVBoxLayout()
        right.setSpacing(6)

        # Ligne 1 : nom + deadline + boutons
        top = QHBoxLayout()
        top.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(goal.icon, 20).pixmap(20, 20))
        icon_lbl.setStyleSheet("background:transparent; border:none;")

        name_lbl = QLabel(goal.name)
        name_lbl.setStyleSheet(
            "font-size:14px; font-weight:700; color:#c8cdd4; "
            "background:transparent; border:none;"
        )

        # Deadline badge
        deadline_lbl = QLabel()
        deadline_lbl.setStyleSheet("font-size:10px; color:#7a8494; background:transparent; border:none;")
        if goal.deadline:
            from datetime import date
            today = date.today()
            delta = (goal.deadline - today).days
            if delta < 0:
                deadline_lbl.setText("Échéance dépassée")
                deadline_lbl.setStyleSheet(
                    "font-size:10px; color:#ef4444; font-weight:600; "
                    "background:#3a1a1a; border-radius:4px; padding:2px 6px; border:none;"
                )
            elif delta <= 30:
                deadline_lbl.setText(f"J-{delta}")
                deadline_lbl.setStyleSheet(
                    "font-size:10px; color:#f59e0b; font-weight:600; "
                    "background:#2e2415; border-radius:4px; padding:2px 6px; border:none;"
                )
            else:
                deadline_lbl.setText(goal.deadline.strftime("%d/%m/%Y"))

        top.addWidget(icon_lbl)
        top.addWidget(name_lbl)
        top.addWidget(deadline_lbl)

        # Badge catégorie liée
        if getattr(goal, 'category_id', None):
            from db import Session as _S2
            from models import Category as _C2
            with _S2() as s:
                cat = s.query(_C2).filter_by(id=goal.category_id).first()
                cat_name = cat.name if cat else ''
            if cat_name:
                cat_badge = QLabel(cat_name)
                cat_badge.setStyleSheet(
                    'font-size:10px; color:#848c94; background:#2e3238; '
                    'border-radius:4px; padding:1px 6px; border:none;'
                )
                top.addWidget(cat_badge)

        top.addStretch()

        # Boutons action
        for btn_text, btn_style, btn_action in [
            ("+ Versement",
             f"background:{goal.color}22; color:{goal.color}; border:1px solid {goal.color}55;",
             lambda checked=False, gid=goal.id: self._add_contribution(gid)),
            ("- Retrait",
             "background:#3a1a1a; color:#ef4444; border:1px solid #7a2a2a;",
             lambda checked=False, gid=goal.id: self._withdraw_contribution(gid)),
        ]:
            b = QPushButton(btn_text)
            b.setFixedHeight(26)
            b.setStyleSheet(
                f"{btn_style} border-radius:6px; font-size:10px; font-weight:600; padding:0 8px;"
            )
            b.clicked.connect(btn_action)
            top.addWidget(b)

        for btn_icon, btn_tip, btn_action in [
            ("stats.png", "Historique", lambda checked=False, gid=goal.id, gname=goal.name: self._show_movements(gid, gname)),
            ("budget.png", "Modifier", lambda checked=False, gid=goal.id: self._edit_goal(gid)),
            ("delete.png", "Supprimer", lambda checked=False, gid=goal.id: self._delete_goal(gid)),
        ]:
            b = QPushButton()
            b.setIcon(get_icon(btn_icon, 14))
            b.setFixedSize(26, 26)
            b.setStyleSheet("background:#3e4550; border-radius:6px; border:none;")
            b.setToolTip(btn_tip)
            b.clicked.connect(btn_action)
            top.addWidget(b)

        right.addLayout(top)

        # Ligne 2 : montants + barre linéaire
        amounts_row = QHBoxLayout()
        amounts_lbl = QLabel(
            f"{format_money(goal.current_amount)}  /  {format_money(goal.target_amount)}"
        )
        amounts_lbl.setStyleSheet(
            "font-size:12px; color:#c8cdd4; background:transparent; border:none;"
        )

        reste = goal.target_amount - goal.current_amount
        reste_lbl = QLabel(
            f"Reste : {format_money(reste)}" if reste > 0 else "Objectif atteint !"
        )
        reste_lbl.setAlignment(Qt.AlignRight)
        reste_lbl.setStyleSheet(
            "font-size:11px; color:#7a8494; background:transparent; border:none;"
            if reste > 0 else
            "font-size:11px; color:#22c55e; font-weight:600; background:transparent; border:none;"
        )
        amounts_row.addWidget(amounts_lbl)
        amounts_row.addStretch()
        amounts_row.addWidget(reste_lbl)
        right.addLayout(amounts_row)

        # Barre de progression linéaire fine
        bar = QProgressBar()
        bar.setMinimum(0)
        bar.setMaximum(100)
        bar.setValue(int(pct))
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        bar.setStyleSheet(f"""
            QProgressBar {{ background:#3d4248; border-radius:3px; border:none; }}
            QProgressBar::chunk {{ background:{goal.color}; border-radius:3px; }}
        """)
        right.addWidget(bar)

        # Ligne 3 : estimation + versement mensuel
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        monthly_t = getattr(goal, "monthly_target", 0) or 0
        if monthly_t > 0 and reste > 0:
            monthly_badge = QLabel(f"↗ {format_money(monthly_t)}/mois")
            monthly_badge.setStyleSheet(
                f"font-size:10px; color:{goal.color}; font-weight:600; "
                f"background:{goal.color}22; border-radius:4px; padding:1px 6px; "
                "border:none;"
            )
            bottom.addWidget(monthly_badge)

        from services.savings_service import estimate_months_to_goal
        est = estimate_months_to_goal(goal)
        if est["months"] is not None and reste > 0:
            on_track = est.get("on_track", True)
            est_color = "#22c55e" if on_track else "#f59e0b"
            est_text = f"Atteint en {est['date']}" if on_track else f"En retard → {est['date']}"
            est_lbl = QLabel(est_text)
            est_lbl.setStyleSheet(
                f"font-size:10px; color:{est_color}; font-weight:600; "
                "background:transparent; border:none;"
            )
            bottom.addWidget(est_lbl)

        bottom.addStretch()
        right.addLayout(bottom)

        card_layout.addLayout(right, 1)
        return card

    # ─────────────────────────────────────────────
    # ONGLET 2 : Taux d'épargne
    # ─────────────────────────────────────────────
    def _save_rate_target(self):
        from services.savings_service import savings_rate_target, monthly_savings_rate
        savings_rate_target(self._rate_target_spin.value())
        self._build_rate_chart(monthly_savings_rate(12))
        from ui.toast import Toast
        Toast.show(self, 'Objectif de taux enregistré', kind='success')

    def _build_rate_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "Le taux d'épargne est calculé à partir des transactions "
            "dans les catégories Épargne, Livret, etc."
        )
        info.setStyleSheet("font-size:11px; color:#7a8494;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Objectif de taux personnel
        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        target_lbl = QLabel("Objectif de taux :")
        target_lbl.setStyleSheet("color:#848c94; font-size:12px;")
        self._rate_target_spin = QDoubleSpinBox()
        self._rate_target_spin.setRange(0, 100)
        self._rate_target_spin.setSuffix(" %")
        self._rate_target_spin.setDecimals(1)
        self._rate_target_spin.setFixedWidth(100)
        self._rate_target_spin.setFixedHeight(30)
        from services.savings_service import savings_rate_target
        self._rate_target_spin.setValue(savings_rate_target().get("target_rate", 10.0))
        btn_save_rate = QPushButton("Enregistrer")
        btn_save_rate.setFixedHeight(30)
        btn_save_rate.setStyleSheet("background:#2e3238; color:#c8cdd4; border:1px solid #3d4248; border-radius:6px; padding:0 10px;")
        btn_save_rate.clicked.connect(self._save_rate_target)
        target_row.addWidget(target_lbl)
        target_row.addWidget(self._rate_target_spin)
        target_row.addWidget(btn_save_rate)
        target_row.addStretch()
        layout.addLayout(target_row)

        # Graphique barres taux
        self._rate_chart_view = QChartView()
        self._rate_chart_view.setRenderHint(QPainter.Antialiasing)
        self._rate_chart_view.setMinimumHeight(220)
        self._rate_chart_view.setStyleSheet("background:transparent; border:none;")
        layout.addWidget(self._rate_chart_view, 1)

        # Récap taux moyen
        self._rate_avg_lbl = QLabel()
        self._rate_avg_lbl.setAlignment(Qt.AlignCenter)
        self._rate_avg_lbl.setStyleSheet(
            "font-size:14px; font-weight:700; color:#22c55e; "
            "background:#1a2a1a; border-radius:8px; padding:8px;"
        )
        layout.addWidget(self._rate_avg_lbl)

        return tab

    def _build_rate_chart(self, data):
        labels  = [d[0] for d in data]
        rates   = [d[3] for d in data]
        savings = [d[2] for d in data]

        bar_set = QBarSet("Épargne (€)")
        bar_set.setColor(QColor("#22c55e"))
        for v in savings:
            bar_set.append(v)

        series = QBarSeries()
        series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setBackgroundVisible(False)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setAnimationDuration(500)
        chart.setMargins(QMargins(0, 8, 0, 0))
        chart.legend().setVisible(False)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsFont(QFont("Segoe UI", 8))
        axis_x.setLabelsColor(QColor("#7a8494"))
        axis_x.setGridLineVisible(False)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(savings) if savings else 1
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.2)
        axis_y.setLabelsFont(QFont("Segoe UI", 8))
        axis_y.setLabelsColor(QColor("#7a8494"))
        axis_y.setGridLineColor(QColor("#3a3f47"))
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(5)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        # Ligne de tendance (moyenne mobile 3 mois)
        from PySide6.QtCharts import QLineSeries
        if len(savings) >= 3:
            trend = QLineSeries()
            trend.setColor(QColor("#f59e0b"))
            pen = trend.pen(); pen.setWidth(2); pen.setStyle(Qt.DashLine)
            trend.setPen(pen)
            for i in range(len(savings)):
                window = savings[max(0, i-2):i+1]
                avg = sum(window) / len(window)
                trend.append(i, avg)
            chart.addSeries(trend)
            trend.attachAxis(axis_x)
            trend.attachAxis(axis_y)

        # Ligne objectif de taux (en €)
        from services.savings_service import savings_rate_target
        target_rate = savings_rate_target().get("target_rate", 10.0)
        incomes = [d[1] for d in data]
        if incomes:
            avg_income = sum(incomes) / len(incomes)
            target_monthly = avg_income * target_rate / 100
            target_line = QLineSeries()
            target_line.setColor(QColor("#22c55e"))
            pen2 = target_line.pen(); pen2.setWidth(1); pen2.setStyle(Qt.DotLine)
            target_line.setPen(pen2)
            target_line.append(0, target_monthly)
            target_line.append(len(savings) - 1, target_monthly)
            chart.addSeries(target_line)
            target_line.attachAxis(axis_x)
            target_line.attachAxis(axis_y)

        self._rate_chart_view.setChart(chart)

        # Taux moyen + alerte si sous l'objectif
        avg_rate = sum(rates) / len(rates) if rates else 0
        target_rate = savings_rate_target().get("target_rate", 10.0)
        color = "#22c55e" if avg_rate >= target_rate else "#ef4444"
        icon  = "✓" if avg_rate >= target_rate else "⚠"
        self._rate_avg_lbl.setStyleSheet(
            f"font-size:14px; font-weight:700; color:{color}; "
            f"background:{'#1a2a1a' if avg_rate >= target_rate else '#2a1a1a'}; "
            "border-radius:8px; padding:8px;"
        )
        self._rate_avg_lbl.setText(
            f"{icon} Taux moyen : {avg_rate:.1f}% "
            f"(objectif : {target_rate:.0f}%)"
        )

    # ─────────────────────────────────────────────
    # ONGLET 3 : Simulateur
    # ─────────────────────────────────────────────
    def _on_sim_goal_changed(self):
        from services.savings_service import get_goals
        goal_id = self._sim_goal_combo.currentData()
        if goal_id is None:
            return
        goals = get_goals()
        goal = next((g for g in goals if g.id == goal_id), None)
        if goal:
            self._sim_target.setValue(goal.target_amount)
            self._sim_current.setValue(goal.current_amount)

    def _run_comparison(self):
        from services.savings_service import simulate
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QLabel, QDoubleSpinBox, QPushButton)
        dlg = QDialog(self)
        dlg.setWindowTitle("Comparer 2 scenarios")
        dlg.setMinimumWidth(480)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)
        target  = self._sim_target.value()
        current = self._sim_current.value()
        rate    = self._sim_rate.value()
        row = QHBoxLayout()
        spins = []
        for label, default in [("Scénario A (euros/mois)", 100), ("Scénario B (euros/mois)", 200)]:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight:600; color:#c8cdd4;")
            spin = QDoubleSpinBox()
            spin.setRange(1, 99999)
            spin.setValue(default)
            spin.setSuffix(" euros")
            spin.setMinimumHeight(34)
            spins.append(spin)
            col.addWidget(lbl)
            col.addWidget(spin)
            row.addLayout(col)
        vl.addLayout(row)
        result_lbl = QLabel()
        result_lbl.setWordWrap(True)
        result_lbl.setStyleSheet("color:#c8cdd4; font-size:12px; background:#292d32; border-radius:8px; padding:12px;")
        result_lbl.setVisible(False)
        vl.addWidget(result_lbl)
        def compare():
            lines = []
            for i, monthly in enumerate([s.value() for s in spins]):
                r = simulate(monthly, target, current, rate)
                months = r["months"]
                if months:
                    y, m = months // 12, months % 12
                    parts = []
                    if y: parts.append(f"{y} an{'s' if y > 1 else ''}")
                    if m: parts.append(f"{m} mois")
                    duration = " et ".join(parts)
                    sc = "AB"[i]
                    lines.append(f"Scénario {sc} - {monthly:.0f} euros/mois :\n  Atteint en {duration} ({r['target_date']})")
            result_lbl.setText("\n\n".join(lines))
            result_lbl.setVisible(True)
        btn = QPushButton("Comparer")
        btn.setMinimumHeight(36)
        btn.clicked.connect(compare)
        vl.addWidget(btn)
        close = QPushButton("Fermer")
        close.setMinimumHeight(34)
        close.setStyleSheet("background:#2e3238; color:#848c94;")
        close.clicked.connect(dlg.accept)
        vl.addWidget(close)
        dlg.exec()

    def _run_reverse_sim(self):
        from PySide6.QtWidgets import (QDialog, QFormLayout, QLabel, QSpinBox, QPushButton)
        dlg = QDialog(self)
        dlg.setWindowTitle("Combien dois-je épargner par mois ?")
        dlg.setMinimumWidth(380)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)
        months_spin = QSpinBox()
        months_spin.setRange(1, 600)
        months_spin.setValue(24)
        months_spin.setSuffix(" mois")
        months_spin.setMinimumHeight(34)
        form.addRow(QLabel("Delai souhaite :"), months_spin)
        result_lbl = QLabel()
        result_lbl.setStyleSheet(
            "font-size:15px; font-weight:700; color:#22c55e; "
            "background:#1a2a1a; border-radius:8px; padding:12px;"
        )
        result_lbl.setAlignment(Qt.AlignCenter)
        result_lbl.setWordWrap(True)
        result_lbl.setVisible(False)
        form.addRow(result_lbl)
        def calc():
            target  = self._sim_target.value()
            current = self._sim_current.value()
            rate    = self._sim_rate.value()
            months  = months_spin.value()
            reste   = target - current
            if reste <= 0:
                result_lbl.setText("Objectif deja atteint !")
                result_lbl.setVisible(True)
                return
            monthly_rate = rate / 100 / 12
            if monthly_rate > 0:
                                needed = reste * monthly_rate / ((1 + monthly_rate) ** months - 1)
            else:
                needed = reste / months
            result_lbl.setText(
                f"Il vous faut épargner\n{format_money(needed)} par mois\n"
                f"pour atteindre {format_money(target)}\nen {months} mois"
            )
            result_lbl.setVisible(True)
        btn_calc = QPushButton("Calculer")
        btn_calc.setMinimumHeight(36)
        btn_calc.clicked.connect(calc)
        form.addRow(btn_calc)
        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.setStyleSheet("background:#2e3238; color:#848c94;")
        btn_close.clicked.connect(dlg.accept)
        form.addRow(btn_close)
        dlg.exec()

    def _save_simulation(self):
        """Sauvegarde la simulation en cours dans un fichier JSON."""
        import json, os
        from PySide6.QtWidgets import QFileDialog
        from config import APP_DIR
        data = {
            'monthly': self._sim_monthly.value(),
            'target':  self._sim_target.value(),
            'current': self._sim_current.value(),
            'rate':    self._sim_rate.value(),
            'result':  self._sim_result.text(),
        }
        path, _ = QFileDialog.getSaveFileName(
            self, 'Sauvegarder la simulation',
            os.path.join(APP_DIR, 'simulation.json'),
            'Fichiers JSON (*.json)'
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            from ui.toast import Toast
            Toast.show(self, 'Simulation sauvegardée', kind='success')

    def _build_sim_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Formulaire
        form_widget = QWidget()
        form_widget.setStyleSheet(
            "background:#292d32; border-radius:12px; border:1px solid #3d4248;"
        )
        form = QFormLayout(form_widget)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color:#848c94; font-size:12px; background:transparent; border:none;")
            return l

        # Choisir un objectif existant
        self._sim_goal_combo = QComboBox()
        self._sim_goal_combo.setMinimumHeight(34)
        self._sim_goal_combo.addItem("— Aucun objectif sélectionné —", None)
        self._sim_goal_combo.currentIndexChanged.connect(self._on_sim_goal_changed)
        form.addRow(lbl("Objectif existant :"), self._sim_goal_combo)

        self._sim_monthly = QDoubleSpinBox()
        self._sim_monthly.setRange(1, 99999)
        self._sim_monthly.setValue(200)
        self._sim_monthly.setSuffix(" €/mois")
        self._sim_monthly.setMinimumHeight(34)

        self._sim_target = QDoubleSpinBox()
        self._sim_target.setRange(1, 9999999)
        self._sim_target.setValue(5000)
        self._sim_target.setSuffix(" €")
        self._sim_target.setMinimumHeight(34)

        self._sim_current = QDoubleSpinBox()
        self._sim_current.setRange(0, 9999999)
        self._sim_current.setValue(0)
        self._sim_current.setSuffix(" €")
        self._sim_current.setMinimumHeight(34)

        self._sim_rate = QDoubleSpinBox()
        self._sim_rate.setRange(0, 20)
        self._sim_rate.setValue(0)
        self._sim_rate.setSuffix(" % / an")
        self._sim_rate.setDecimals(2)
        self._sim_rate.setSingleStep(0.1)
        self._sim_rate.setMinimumHeight(34)

        self._sim_inflation = QDoubleSpinBox()
        self._sim_inflation.setRange(0, 20)
        self._sim_inflation.setValue(0)
        self._sim_inflation.setSuffix(" % / an")
        self._sim_inflation.setDecimals(2)
        self._sim_inflation.setSingleStep(0.1)
        self._sim_inflation.setMinimumHeight(34)

        form.addRow(lbl("Épargne mensuelle :"),  self._sim_monthly)
        form.addRow(lbl("Objectif :"),           self._sim_target)
        form.addRow(lbl("Épargne actuelle :"),   self._sim_current)
        form.addRow(lbl("Taux d'intérêt :"),     self._sim_rate)
        form.addRow(lbl("Inflation :"),           self._sim_inflation)

        btn_row_sim = QHBoxLayout()
        btn_sim = QPushButton("  Simuler")
        btn_sim.setIcon(get_icon("stats.png"))
        btn_sim.setMinimumHeight(36)
        btn_sim.clicked.connect(self._run_simulation)

        btn_compare = QPushButton("  Comparer 2 scénarios")
        btn_compare.setIcon(get_icon("balance.png"))
        btn_compare.setMinimumHeight(36)
        btn_compare.setStyleSheet("background:#2e3238; color:#848c94; border:1px solid #3d4248; border-radius:8px;")
        btn_compare.clicked.connect(self._run_comparison)

        btn_reverse = QPushButton("  Combien par mois ?")
        btn_reverse.setIcon(get_icon("budget.png"))
        btn_reverse.setMinimumHeight(36)
        btn_reverse.setStyleSheet("background:#2e3238; color:#848c94; border:1px solid #3d4248; border-radius:8px;")
        btn_reverse.clicked.connect(self._run_reverse_sim)

        btn_row_sim.addWidget(btn_sim)
        btn_row_sim.addWidget(btn_compare)
        btn_row_sim.addWidget(btn_reverse)
        form.addRow("", btn_row_sim)

        layout.addWidget(form_widget)

        # Résultat texte
        self._sim_result = QLabel()
        self._sim_result.setAlignment(Qt.AlignCenter)
        self._sim_result.setWordWrap(True)
        self._sim_result.setStyleSheet(
            "font-size:13px; font-weight:600; color:#22c55e; "
            "background:#1a2a1a; border-radius:8px; padding:10px;"
        )
        self._sim_result.setVisible(False)
        layout.addWidget(self._sim_result)

        # Graphique évolution
        self._sim_chart_view = QChartView()
        self._sim_chart_view.setRenderHint(QPainter.Antialiasing)
        self._sim_chart_view.setMinimumHeight(200)
        self._sim_chart_view.setVisible(False)
        layout.addWidget(self._sim_chart_view, 1)

        self._btn_save_sim = QPushButton('  Sauvegarder cette simulation')
        self._btn_save_sim.setIcon(get_icon('money.png'))
        self._btn_save_sim.setMinimumHeight(34)
        self._btn_save_sim.setStyleSheet('background:#2e3238; color:#848c94; border:1px solid #3d4248; border-radius:8px;')
        self._btn_save_sim.setVisible(False)
        self._btn_save_sim.clicked.connect(self._save_simulation)
        layout.addWidget(self._btn_save_sim)

        return tab

    def _run_simulation(self):
        from services.savings_service import simulate
        monthly = self._sim_monthly.value()
        target  = self._sim_target.value()
        current = self._sim_current.value()
        rate    = self._sim_rate.value()

        result = simulate(monthly, target, current, rate)
        months = result["months"]

        if months is None:
            self._sim_result.setText("Montant mensuel invalide.")
            self._sim_result.setVisible(True)
            return

        years  = months // 12
        rem    = months % 12

        parts = []
        if years > 0:
            parts.append(f"{years} an{'s' if years > 1 else ''}")
        if rem > 0:
            parts.append(f"{rem} mois")
        duration = " et ".join(parts) or "moins d'un mois"

        interest_info = ""
        if rate > 0:
            total_saved  = monthly * months + current
            total_gained = target - total_saved
            if total_gained > 0:
                interest_info = f"\n(dont {format_money(total_gained)} d'intérêts)"

        self._sim_result.setText(
            f"Objectif atteint en {duration}\n"
            f"Date estimée : {result['target_date']}{interest_info}"
        )
        self._sim_result.setVisible(True)

        # Graphique évolution
        evolution = result["evolution"]
        if not evolution or len(evolution) < 2:
            self._sim_chart_view.setVisible(False)
            self._btn_save_sim.setVisible(True)
            return

        self._sim_upper = QLineSeries()  # référence gardée sur self pour éviter GC/crash
        self._sim_upper.setColor(QColor("#22c55e"))

        for i, v in enumerate(evolution):
            self._sim_upper.append(i, v)

        # Ligne objectif
        self._sim_target_line = QLineSeries()
        self._sim_target_line.setColor(QColor("#ef4444"))
        pen = self._sim_target_line.pen()
        pen.setStyle(Qt.DashLine)
        pen.setWidth(1)
        self._sim_target_line.setPen(pen)
        self._sim_target_line.append(0, target)
        self._sim_target_line.append(len(evolution) - 1, target)

        area = QAreaSeries(self._sim_upper)
        area.setColor(QColor(34, 197, 94, 40))
        area.setBorderColor(QColor("#22c55e"))

        chart = QChart()
        chart.addSeries(area)
        chart.addSeries(self._sim_target_line)
        chart.setBackgroundVisible(False)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setAnimationDuration(600)
        chart.setMargins(QMargins(0, 8, 0, 0))
        chart.legend().setVisible(False)

        axis_x = QValueAxis()
        axis_x.setRange(0, len(evolution) - 1)
        axis_x.setLabelFormat("%d")
        axis_x.setLabelsFont(QFont("Segoe UI", 8))
        axis_x.setLabelsColor(QColor("#7a8494"))
        axis_x.setGridLineColor(QColor("#3a3f47"))
        axis_x.setTitleText("Mois")
        axis_x.setTitleFont(QFont("Segoe UI", 8))
        axis_x.setTitleBrush(QColor("#7a8494"))
        chart.addAxis(axis_x, Qt.AlignBottom)
        area.attachAxis(axis_x)
        self._sim_target_line.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, target * 1.1)
        axis_y.setLabelFormat("%d")
        axis_y.setLabelsFont(QFont("Segoe UI", 8))
        axis_y.setLabelsColor(QColor("#7a8494"))
        axis_y.setGridLineColor(QColor("#3a3f47"))
        chart.addAxis(axis_y, Qt.AlignLeft)
        area.attachAxis(axis_y)
        self._sim_target_line.attachAxis(axis_y)

        self._sim_chart_view.setChart(chart)
        self._sim_chart_view.setVisible(True)

    # ─────────────────────────────────────────────
    # CRUD Objectifs
    # ─────────────────────────────────────────────
    def _add_goal(self):
        dlg = self._goal_dialog()
        if dlg.exec() == QDialog.Accepted:
            from services.savings_service import add_goal
            data = dlg.get_data()
            add_goal(
                name=data["name"],
                target=data["target_amount"],
                current=data["current_amount"],
                color=data["color"],
                deadline=data.get("deadline"),
                monthly_target=data.get("monthly_target", 0),
                category_id=data.get("category_id"),
            )
            self._reload_goals()
            from ui.toast import Toast
            Toast.show(self, "Objectif ajouté", kind="success")

    def _edit_goal(self, goal_id: int):
        from services.savings_service import get_goals, update_goal
        goals = get_goals()
        goal  = next((g for g in goals if g.id == goal_id), None)
        if not goal:
            return
        dlg = self._goal_dialog(goal)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            update_goal(goal_id, **data)
            self._reload_goals()
            from ui.toast import Toast
            Toast.show(self, "Objectif modifié", kind="success")

    def _delete_goal(self, goal_id: int):
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer l'objectif")
        msg.setText("Supprimer cet objectif d'épargne ?")
        btn_ok = msg.addButton("Supprimer", QMessageBox.AcceptRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_ok:
            from services.savings_service import delete_goal
            delete_goal(goal_id)
            self._reload_goals()

    def _goal_dialog(self, goal=None) -> QDialog:
        dlg = QDialog(self)
        dlg.setWindowTitle("Objectif d'épargne")
        dlg.setMinimumWidth(360)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("color:#848c94; font-size:12px;")
            return l

        name_inp = QLineEdit()
        name_inp.setPlaceholderText("ex: Vacances, Voiture...")
        name_inp.setMinimumHeight(34)
        if goal:
            name_inp.setText(goal.name)

        target_spin = QDoubleSpinBox()
        target_spin.setRange(1, 9999999)
        target_spin.setSuffix(" €")
        target_spin.setMinimumHeight(34)
        target_spin.setValue(goal.target_amount if goal else 1000)

        current_spin = QDoubleSpinBox()
        current_spin.setRange(0, 9999999)
        current_spin.setSuffix(" €")
        current_spin.setMinimumHeight(34)
        current_spin.setValue(goal.current_amount if goal else 0)

        color_combo = QComboBox()
        color_combo.setMinimumHeight(34)
        color_names = ["Vert","Bleu","Orange","Violet","Rouge","Cyan","Orange foncé","Rose"]
        for c, n in zip(GOAL_COLORS, color_names):
            color_combo.addItem(n, c)
        if goal:
            idx = GOAL_COLORS.index(goal.color) if goal.color in GOAL_COLORS else 0
            color_combo.setCurrentIndex(idx)

        from PySide6.QtWidgets import QCheckBox
        deadline_check = QCheckBox("Fixer une echeance")
        deadline_check.setStyleSheet("color:#c8cdd4; font-size:12px;")
        deadline_check.setChecked(bool(goal and goal.deadline))

        deadline_edit = QDateEdit()
        deadline_edit.setCalendarPopup(True)
        deadline_edit.setMinimumHeight(34)
        if goal and goal.deadline:
            deadline_edit.setDate(QDate(goal.deadline.year,
                                        goal.deadline.month,
                                        goal.deadline.day))
        else:
            deadline_edit.setDate(QDate.currentDate().addYears(1))
        deadline_edit.setEnabled(deadline_check.isChecked())
        deadline_check.toggled.connect(deadline_edit.setEnabled)

        monthly_spin = QDoubleSpinBox()
        monthly_spin.setRange(0, 99999)
        monthly_spin.setValue(getattr(goal, "monthly_target", 0) if goal else 0)
        monthly_spin.setSuffix(" €/mois")
        monthly_spin.setMinimumHeight(34)
        monthly_spin.setSpecialValueText("Aucun")

        form.addRow(lbl("Nom :"),                  name_inp)
        form.addRow(lbl("Objectif :"),             target_spin)
        form.addRow(lbl("Épargne actuelle :"),     current_spin)
        form.addRow(lbl("Versement mensuel :"),    monthly_spin)

        # Sélecteur de catégorie liée
        from db import Session as _S
        from models import Category as _Cat
        from utils.icons import get_icon as _gi
        from utils.category_icons import get_category_icon
        cat_combo = QComboBox()
        cat_combo.setMinimumHeight(34)
        cat_combo.addItem("— Aucune catégorie liée —", None)
        with _S() as s:
            cats = s.query(_Cat).all()
            cats = sorted(cats, key=lambda c: c.name.lower()
                          .replace('é','e').replace('è','e')
                          .replace('ê','e').replace('à','a')
                          .replace('â','a').replace('ô','o')
                          .replace('û','u').replace('ù','u')
                          .replace('î','i').replace('ï','i'))
            s.expunge_all()
        for c in cats:
            icon_f = c.icon if c.icon and c.icon.endswith('.png') else get_category_icon(c.name)
            cat_combo.addItem(_gi(icon_f, 18), c.name, c.id)
            if goal and goal.category_id == c.id:
                cat_combo.setCurrentIndex(cat_combo.count() - 1)
        form.addRow(lbl("Catégorie liée :"),        cat_combo)

        form.addRow(lbl("Couleur :"),              color_combo)
        form.addRow("", deadline_check)
        form.addRow(lbl("Echeance :"),              deadline_edit)

        btns = QDialogButtonBox()
        btns.addButton("Enregistrer", QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler",     QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        def get_data():
            from datetime import date
            qd = deadline_edit.date()
            return {
                "name":           name_inp.text().strip(),
                "target_amount":  target_spin.value(),
                "current_amount": current_spin.value(),
                "monthly_target": monthly_spin.value(),
                "category_id":    cat_combo.currentData(),
                "color":          color_combo.currentData(),
                "deadline":       date(qd.year(), qd.month(), qd.day()) if deadline_check.isChecked() else None,
            }

        dlg.get_data = get_data
        return dlg

    # ─────────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────────
    def _show_movements(self, goal_id: int, goal_name: str):
        """Affiche l'historique des mouvements d'un objectif."""
        from services.savings_service import get_movements
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
        from PySide6.QtGui import QColor

        movements = get_movements(goal_id)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Historique — {goal_name}")
        dlg.setMinimumSize(460, 360)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        if not movements:
            lbl = QLabel("Aucun mouvement enregistré.")
            lbl.setStyleSheet("color:#7a8494; font-size:12px;")
            lbl.setAlignment(Qt.AlignCenter)
            vl.addWidget(lbl)
        else:
            tbl = QTableWidget(len(movements), 3)
            tbl.setHorizontalHeaderLabels(["Date", "Libellé", "Montant"])
            tbl.verticalHeader().setVisible(False)
            tbl.setShowGrid(False)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            tbl.setAlternatingRowColors(True)
            tbl.verticalHeader().setDefaultSectionSize(32)
            hdr = tbl.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.Fixed); tbl.setColumnWidth(0, 120)
            hdr.setSectionResizeMode(1, QHeaderView.Stretch)
            hdr.setSectionResizeMode(2, QHeaderView.Fixed); tbl.setColumnWidth(2, 110)
            tbl.setStyleSheet(
                "QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }"
                "QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }"
                "QTableWidget::item:alternate { background:#202428; }"
                "QHeaderView::section { background:#292d32; color:#7a8494; border:none; "
                "border-bottom:1px solid #3a3f47; padding:4px 8px; }"
            )
            total = 0
            for i, m in enumerate(movements):
                tbl.setItem(i, 0, QTableWidgetItem(
                    m["moved_at"].strftime("%d/%m/%Y %H:%M")
                ))
                tbl.setItem(i, 1, QTableWidgetItem(m["label"]))
                sign  = "+" if m["amount"] >= 0 else ""
                color = QColor("#22c55e") if m["amount"] >= 0 else QColor("#ef4444")
                amt_item = QTableWidgetItem(f"{sign}{format_money(abs(m['amount']))}")
                amt_item.setForeground(color)
                amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tbl.setItem(i, 2, amt_item)
                total += m["amount"]
            vl.addWidget(tbl, 1)

            # Total
            sign  = "+" if total >= 0 else ""
            color = "#22c55e" if total >= 0 else "#ef4444"
            total_lbl = QLabel(f"Total net : {sign}{format_money(abs(total))}")
            total_lbl.setStyleSheet(
                f"font-size:13px; font-weight:700; color:{color}; "
                "background:#292d32; border-radius:8px; padding:8px 14px;"
            )
            total_lbl.setAlignment(Qt.AlignRight)
            vl.addWidget(total_lbl)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)
        dlg.exec()

    def _withdraw_contribution(self, goal_id: int):
        """Dialogue pour retirer un montant d'un objectif."""
        from services.savings_service import get_goals
        goals = get_goals()
        goal = next((g for g in goals if g.id == goal_id), None)
        if not goal:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Retirer un montant")
        dlg.setFixedWidth(320)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)

        info = QLabel(f"Disponible : {format_money(goal.current_amount)}")
        info.setStyleSheet("color:#848c94; font-size:12px;")
        form.addRow(info)

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0.01, max(0.01, goal.current_amount))
        amount_spin.setValue(min(100, goal.current_amount))
        amount_spin.setSuffix(" €")
        amount_spin.setMinimumHeight(36)
        form.addRow(QLabel("Montant :"), amount_spin)

        btns = QDialogButtonBox()
        btns.addButton("Retirer", QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler", QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.Accepted:
            from services.savings_service import withdraw_contribution
            withdraw_contribution(goal_id, amount_spin.value())
            self._reload_goals()
            from ui.toast import Toast
            Toast.show(self, f"Retrait de {amount_spin.value():.2f} euros effectué", kind="success")

    def _add_contribution(self, goal_id: int):
        """Dialogue rapide pour ajouter un versement."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajouter un versement")
        dlg.setFixedWidth(320)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0.01, 99999)
        amount_spin.setValue(50)
        amount_spin.setSuffix(" €")
        amount_spin.setMinimumHeight(36)
        form.addRow(QLabel("Montant :"), amount_spin)

        label_input = QLineEdit()
        label_input.setPlaceholderText("ex: Virement mensuel, Prime...")
        label_input.setMinimumHeight(36)
        form.addRow(QLabel("Libellé (optionnel) :"), label_input)

        btns = QDialogButtonBox()
        btns.addButton("Ajouter", QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler", QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.Accepted:
            from services.savings_service import add_contribution
            lbl = label_input.text().strip() or 'Versement'
            add_contribution(goal_id, amount_spin.value(), label=lbl)
            self._reload_goals()
            from ui.toast import Toast
            Toast.show(self, f"Versement de {amount_spin.value():.2f} euros ajouté", kind="success")

    def _sync_savings(self):
        """Affiche le total des transactions épargne détectées."""
        from services.savings_service import sync_savings_from_transactions
        total = sync_savings_from_transactions()
        from ui.toast import Toast
        Toast.show(self, f"{total:.2f} euros d'épargne détectés dans les transactions", kind="success")

    def _update_global_indicator(self, goals):
        """Met à jour l'indicateur global en haut."""
        if not goals:
            self._gi_total.setText("0 €")
            self._gi_bar.setValue(0)
            self._gi_pct.setText("0%")
            return
        total_current = sum(g.current_amount for g in goals)
        total_target  = sum(g.target_amount  for g in goals)
        pct = int(total_current / total_target * 100) if total_target > 0 else 0
        self._gi_total.setText(format_money(total_current))
        self._gi_bar.setMaximum(100)
        self._gi_bar.setValue(pct)
        self._gi_pct.setText(f"{pct}%")

    def _reload_goals(self):
        from services.savings_service import get_goals
        # Vider
        while self._goals_layout.count() > 1:
            item = self._goals_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        goals = get_goals()
        self._update_global_indicator(goals)

        # Trier par urgence (échéance la plus proche en premier)
        from datetime import date
        def sort_key(g):
            if g.deadline:
                return (g.deadline - date.today()).days
            return 9999
        goals_sorted = sorted(goals, key=sort_key)

        if not goals_sorted:
            empty = QLabel("Aucun objectif — cliquez sur \"Nouvel objectif\" pour commencer.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:#7a8494; font-size:12px;")
            self._goals_layout.insertWidget(0, empty)
        else:
            for i, goal in enumerate(goals_sorted):
                card = self._build_goal_card(goal)
                self._goals_layout.insertWidget(i, card)

    def refresh(self):
        self._reload_goals()
        if hasattr(self, '_txn_table'):
            self._reload_txn_table()

        from services.savings_service import monthly_savings_rate
        data = monthly_savings_rate(12)
        self._build_rate_chart(data)
