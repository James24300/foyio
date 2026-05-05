import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QComboBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QDoubleValidator

from db import Session
from models import Category
from utils.icons import get_icon
from utils.formatters import format_money

from ui.toast import Toast
from ui.spellcheck_lineedit import SpellCheckLineEdit
from services.recurring_service import (
    get_recurring, add_recurring, toggle_recurring, delete_recurring
)

logger = logging.getLogger(__name__)

DAYS_FR = [
    "1er", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "23", "24", "25", "26", "27", "28"
]


class RecurringView(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── En-tête ──
        header = QLabel("Gérez vos transactions qui se répètent chaque mois.")
        header.setStyleSheet("font-size:13px; color:#7a8494;")
        layout.addWidget(header)

        # ── Formulaire d'ajout ──
        form_card = QWidget()
        form_card.setStyleSheet("""
            QWidget {
                background:#26292e; border-radius:12px;
                border:1px solid #3a3f47;
            }
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(10)

        form_title = QLabel("Nouvelle transaction récurrente")
        form_title.setStyleSheet(
            "font-size:13px; font-weight:600; color:#c8cdd4; background:transparent; border:none;"
        )
        form_layout.addWidget(form_title)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Dépense", "Revenu"])
        self.type_combo.setMinimumHeight(34)
        self.type_combo.setFixedWidth(110)

        self.label_input = SpellCheckLineEdit()
        self.label_input.setPlaceholderText("Libellé (ex: Loyer, Netflix, Salaire...)")
        self.label_input.setMinimumHeight(34)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Montant (€)")
        self.amount_input.setValidator(QDoubleValidator(0.01, 100_000_000, 2))
        self.amount_input.setMinimumHeight(34)
        self.amount_input.setFixedWidth(120)

        row1.addWidget(self.type_combo)
        row1.addWidget(self.label_input, 1)
        row1.addWidget(self.amount_input)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.category_combo = QComboBox()
        self.category_combo.setIconSize(QSize(16, 16))
        self.category_combo.setMinimumHeight(34)

        day_label = QLabel("Le")
        day_label.setStyleSheet(
            "color:#7a8494; font-size:13px; background:transparent; border:none;"
        )
        day_label.setFixedWidth(20)

        self.day_combo = QComboBox()
        self.day_combo.setMinimumHeight(34)
        self.day_combo.setFixedWidth(80)
        for d in DAYS_FR:
            self.day_combo.addItem(d)

        du_mois = QLabel("du mois")
        du_mois.setStyleSheet(
            "color:#7a8494; font-size:13px; background:transparent; border:none;"
        )

        # Rappel avant échéance
        rappel_label = QLabel("Rappel")
        rappel_label.setStyleSheet(
            "color:#7a8494; font-size:13px; background:transparent; border:none;"
        )
        self.reminder_spin = QSpinBox()
        self.reminder_spin.setRange(0, 30)
        self.reminder_spin.setValue(3)
        self.reminder_spin.setSuffix(" jours avant")
        self.reminder_spin.setToolTip("Nombre de jours avant l'échéance pour recevoir un rappel (0 = désactivé)")
        self.reminder_spin.setMinimumHeight(34)
        self.reminder_spin.setFixedWidth(165)

        self.add_btn = QPushButton("  Ajouter")
        self.add_btn.setIcon(get_icon("add.png"))
        self.add_btn.setMinimumHeight(34)
        self.add_btn.clicked.connect(self._add)

        row2.addWidget(self.category_combo, 1)
        row2.addWidget(day_label)
        row2.addWidget(self.day_combo)
        row2.addWidget(du_mois)
        row2.addSpacing(8)
        row2.addWidget(rappel_label)
        row2.addWidget(self.reminder_spin)
        row2.addStretch()
        row2.addWidget(self.add_btn)
        form_layout.addLayout(row2)

        layout.addWidget(form_card)

        # ── Séparateur ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none; margin:4px 0;")
        layout.addWidget(sep)

        # ── Tableau des règles ──
        list_title = QLabel("Transactions récurrentes enregistrées")
        list_title.setStyleSheet("font-size:13px; font-weight:600; color:#c8cdd4;")
        layout.addWidget(list_title)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Statut", "Libellé", "Type", "Montant", "Jour", "Rappel", "Actions"
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setIconSize(QSize(16, 16))

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 200)

        self.table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item {
                border-bottom:1px solid #3a3f47; padding:4px 8px;
            }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section {
                background:#26292e; border:none;
                padding:6px 8px; font-weight:600; color:#7a8494;
            }
        """)

        layout.addWidget(self.table, 1)

        # ── Note bas de page ──
        note = QLabel(
            "Les transactions récurrentes sont générées automatiquement "
            "au démarrage de l'application."
        )
        note.setStyleSheet("font-size:11px; color:#6b7280;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.setLayout(layout)
        self._load_categories()
        self.load()

    # ------------------------------------------------------------------
    def _load_categories(self):
        from utils.category_icons import get_category_icon
        with Session() as session:
            cats = session.query(Category).order_by(Category.name).all()
        self.category_combo.clear()
        self.category_combo.addItem("— Catégorie —", None)
        for c in cats:
            raw = c.icon or ""
            icon_file = raw if raw.endswith(".png") else get_category_icon(c.name)
            self.category_combo.addItem(get_icon(icon_file, 16), c.name, c.id)
        self.category_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------
    def _add(self):
        label = self.label_input.text().strip()
        if not label:
            Toast.show(self, "✕  Saisissez un libellé", kind="error")
            self.label_input.setFocus()
            return

        try:
            amount = float(self.amount_input.text().replace(",", "."))
            if amount <= 0:
                raise ValueError
        except ValueError:
            Toast.show(self, "✕  Montant invalide", kind="error")
            self.amount_input.setFocus()
            return

        category_id = self.category_combo.currentData()
        if not category_id:
            Toast.show(self, "✕  Choisissez une catégorie", kind="error")
            self.category_combo.showPopup()
            return

        ttype = "income" if self.type_combo.currentText() == "Revenu" else "expense"
        day   = self.day_combo.currentIndex() + 1
        reminder = self.reminder_spin.value()

        add_recurring(label, amount, ttype, category_id, day, reminder_days=reminder)

        self.label_input.clear()
        self.amount_input.clear()
        self.day_combo.setCurrentIndex(0)
        self.reminder_spin.setValue(3)
        self._load_categories()  # remet à l'entrée neutre
        self.load()
        Toast.show(self, f"✓  {label} — généré chaque mois", kind="success")

    # ------------------------------------------------------------------
    def load(self):
        rules = get_recurring()

        with Session() as session:
            categories = {c.id: c.name for c in session.query(Category).all()}

        self.table.setRowCount(len(rules))

        if not rules:
            self.table.setRowCount(1)
            empty = QTableWidgetItem("Aucune transaction récurrente — ajoutez-en une ci-dessus.")
            empty.setForeground(QColor("#6b7280"))
            self.table.setItem(0, 1, empty)
            return

        for i, rule in enumerate(rules):
            # ── Statut (pastille) ──
            dot = QLabel("●")
            dot.setAlignment(Qt.AlignCenter)
            dot.setStyleSheet(
                f"color:{'#22c55e' if rule.active else '#6b7280'};"
                "font-size:18px; background:transparent;"
            )
            dot.setToolTip("Activée" if rule.active else "Désactivée")
            self.table.setCellWidget(i, 0, dot)

            # ── Libellé ──
            cat_name = categories.get(rule.category_id, "")
            lbl_item = QTableWidgetItem(f"  {rule.label}")
            lbl_item.setData(Qt.UserRole, rule.id)
            if cat_name:
                lbl_item.setToolTip(f"Catégorie : {cat_name}")
            if not rule.active:
                lbl_item.setForeground(QColor("#6b7280"))
            self.table.setItem(i, 1, lbl_item)

            # ── Type ──
            type_text = "Revenu" if rule.type == "income" else "Dépense"
            type_color = "#22c55e" if rule.type == "income" else "#ef4444"
            type_item = QTableWidgetItem(type_text)
            type_item.setForeground(QColor(type_color))
            type_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.table.setItem(i, 2, type_item)

            # ── Montant ──
            amt_item = QTableWidgetItem(format_money(rule.amount))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fnt = amt_item.font(); fnt.setBold(True); amt_item.setFont(fnt)
            self.table.setItem(i, 3, amt_item)

            # ── Jour ──
            day_item = QTableWidgetItem(f"le {rule.day_of_month}")
            day_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            day_item.setForeground(QColor("#7a8494"))
            self.table.setItem(i, 4, day_item)

            # ── Rappel ──
            r_days = rule.reminder_days if rule.reminder_days is not None else 3
            rappel_text = f"J-{r_days}" if r_days > 0 else "—"
            rappel_item = QTableWidgetItem(rappel_text)
            rappel_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            rappel_item.setForeground(QColor("#f59e0b" if r_days > 0 else "#6b7280"))
            rappel_item.setToolTip(
                f"Rappel {r_days} jour(s) avant" if r_days > 0 else "Rappel désactivé"
            )
            self.table.setItem(i, 5, rappel_item)

            # ── Boutons actions ──
            btn_widget = QWidget()
            btn_widget.setStyleSheet("background:transparent;")
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)

            toggle_btn = QPushButton(
                "Désactiver" if rule.active else "Activer"
            )
            toggle_btn.setFixedHeight(28)
            toggle_btn.setStyleSheet(
                "QPushButton { background:#3e4550; color:#b8c0c8; border-radius:6px; "
                "font-size:11px; padding:0 8px; }"
                "QPushButton:hover { background:#1e40af; }"
            )
            toggle_btn.clicked.connect(
                lambda _, rid=rule.id: self._toggle(rid)
            )

            del_btn = QPushButton("Supprimer")
            del_btn.setFixedHeight(28)
            del_btn.setStyleSheet(
                "QPushButton { background:#3d1010; color:#fca5a5; border-radius:6px; "
                "font-size:11px; padding:0 8px; }"
                "QPushButton:hover { background:#7f1d1d; }"
            )
            del_btn.clicked.connect(
                lambda _, rid=rule.id: self._delete(rid)
            )

            btn_layout.addWidget(toggle_btn)
            btn_layout.addWidget(del_btn)
            self.table.setCellWidget(i, 6, btn_widget)

    # ------------------------------------------------------------------
    def _toggle(self, rule_id):
        toggle_recurring(rule_id)
        self.load()

    def _delete(self, rule_id):
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirmer la suppression")
        msg.setText(
            "Supprimer cette règle récurrente ?\n"
            "Les transactions déjà générées seront conservées."
        )
        btn_yes = msg.addButton("Supprimer", QMessageBox.DestructiveRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_yes:
            delete_recurring(rule_id)
            self.load()
