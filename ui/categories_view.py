from PySide6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QColorDialog, QHeaderView, QDialog, QFormLayout, QComboBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor

from models import Category, Transaction, AccountCategory
import account_state
from ui.toast import Toast
from db import Session
from sqlalchemy import func

from utils.icons import get_icon
from ui.spellcheck_lineedit import SpellCheckLineEdit
from utils.formatters import format_money
from utils.category_icons import get_category_icon, get_category_color


class CategoryView(QWidget):

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        main_layout = QHBoxLayout()
        main_layout.setSpacing(24)

        # ── Panneau gauche (formulaire) ──
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignTop)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Nouvelle catégorie")
        title.setStyleSheet("font-size:15px; font-weight:600; color:#c8cdd4;")
        left_layout.addWidget(title)

        self.name = SpellCheckLineEdit()
        self.name.setPlaceholderText("Ex: Gaz, Électricité, Assurance...")
        self.name.setMinimumHeight(36)
        self.name.textChanged.connect(self.update_preview)
        self.name.returnPressed.connect(self.add_category)
        left_layout.addWidget(self.name)

        # Sélecteur d'icône
        icon_label = QLabel("Icône :")
        icon_label.setStyleSheet("font-size:12px; color:#7a8494;")
        left_layout.addWidget(icon_label)

        self.icon_combo = QComboBox()
        self.icon_combo.setMinimumHeight(36)
        self.icon_combo.setIconSize(QSize(22, 22))
        self.icon_combo.setPlaceholderText("— Choisir une icône —")
        self._fill_icon_combo()
        self.icon_combo.currentIndexChanged.connect(self.update_preview)
        left_layout.addWidget(self.icon_combo)

        self.preview = QLabel("💰 Nouvelle catégorie")
        self.preview.setTextFormat(Qt.RichText)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(42)
        self.preview.setStyleSheet("""
            QLabel {
                background:#1e2023; border:1px solid #3a3f47;
                border-radius:8px; font-size:13px; padding:2px; color:#c8cdd4;
            }
        """)
        left_layout.addWidget(self.preview)
        left_layout.addSpacing(6)

        # Couleur — juste après icône
        color_label = QLabel("Couleur :")
        color_label.setStyleSheet("font-size:12px; color:#7a8494;")
        left_layout.addWidget(color_label)

        self.color = "#7a8494"
        self.color_btn = QPushButton("  Choisir une couleur")
        self.color_btn.setMinimumHeight(36)
        self.color_btn.setStyleSheet(
            "background:#1e2124; color:#7aaee8; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; padding:0 12px; text-align:left;"
        )
        self.color_btn.clicked.connect(self.choose_color)
        left_layout.addWidget(self.color_btn)
        left_layout.addSpacing(10)

        self.btn = QPushButton("  + Ajouter la catégorie")
        self.btn.setMinimumHeight(38)
        self.btn.setStyleSheet(
            "background:#1e2124; color:#22c55e; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; font-weight:600; padding:0 12px; text-align:left;"
        )
        self.btn.clicked.connect(self.add_category)

        self.delete_btn = QPushButton("  Masquer sur ce compte")
        self.delete_btn.setMinimumHeight(38)
        self.delete_btn.setStyleSheet(
            "background:#1e2124; color:#f59e0b; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; font-weight:600; padding:0 12px; text-align:left;"
        )
        self.delete_btn.clicked.connect(self.delete_category)

        self.suppress_btn = QPushButton("  Supprimer la catégorie")
        self.suppress_btn.setMinimumHeight(38)
        self.suppress_btn.setStyleSheet(
            "background:#1e2124; color:#ef4444; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; font-weight:600; padding:0 12px; text-align:left;"
        )
        self.suppress_btn.clicked.connect(self.suppress_category)

        self.restore_btn = QPushButton("  Restaurer masquées")
        self.restore_btn.setMinimumHeight(38)
        self.restore_btn.setStyleSheet(
            "background:#1e2124; color:#a0b4c8; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; font-weight:600; padding:0 12px; text-align:left;"
        )
        self.restore_btn.clicked.connect(self.restore_hidden)

        left_layout.addWidget(self.btn)
        left_layout.addWidget(self.delete_btn)
        left_layout.addWidget(self.suppress_btn)
        left_layout.addWidget(self.restore_btn)
        left_layout.addStretch()

        # ── Panneau droit (liste) ──
        right_layout = QVBoxLayout()

        self.list = QTableWidget()
        self.list.setColumnCount(4)
        self.list.setHorizontalHeaderLabels(["", "Catégorie", "Transactions", "Dépenses"])
        self.list.setColumnWidth(0, 40)
        self.list.setColumnWidth(2, 100)
        self.list.setColumnWidth(3, 120)
        self.list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.list.horizontalHeader().setStretchLastSection(False)
        self.list.verticalHeader().setDefaultSectionSize(40)
        self.list.setEditTriggers(QTableWidget.NoEditTriggers)
        self.list.setSelectionBehavior(QTableWidget.SelectRows)
        self.list.setSelectionMode(QTableWidget.SingleSelection)
        self.list.itemDoubleClicked.connect(self.edit_category)
        right_layout.addWidget(self.list)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setMaximumWidth(420)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(right_widget, 2)
        self.setLayout(main_layout)
        self.load()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color))
        if color.isValid():
            self.color = color.name()
            self.color_btn.setText(f"  {self.color}")
            self.color_btn.setStyleSheet(
                f"background:#1e2124; color:{self.color}; "
                "border:1px solid #3d4248; "
                "border-radius:8px; font-size:12px; padding:0 12px; text-align:left;"
            )
        self.update_preview()

    def _fill_icon_combo(self):
        """Remplit le combo avec toutes les icônes disponibles."""
        import os
        import os as _os; _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        icons_dir = os.path.join(_base, "icons")
        self.icon_combo.clear()
        self.icon_combo.addItem("— Choisir une icône —", None)
        # Icônes triées, noms lisibles
        ICON_LABELS = {
            "assurance.png": "Assurance",
            "bank.png":      "Banque",
            "bike.png":      "Vélo / Moto",
            "bus.png":       "Bus",
            "car.png":       "Voiture",
            "coffee.png":    "Café",
            "divers.png":    "Divers",
            "doctor.png":    "Médecin",
            "electricity.png": "Électricité",
            "entertainment.png": "Loisirs",
            "epargne.png":   "Épargne",
            "fuel.png":      "Carburant",
            "gas.png":       "Gaz",
            "groceries.png": "Courses",
            "hotel.png":     "Hôtel",
            "house.png":     "Maison / Loyer",
            "internet.png":  "Internet",
            "lld.png":       "LLD",
            "money.png":     "Argent",
            "movie.png":     "Cinéma",
            "music.png":     "Musique",
            "other.png":     "Autre",
            "paypal.png":    "PayPal",
            "pharmacy.png":  "Pharmacie",
            "phone.png":     "Téléphone",
            "plane.png":     "Avion",
            "restaurant.png": "Restaurant",
            "shopping.png":  "Shopping",
            "train.png":     "Train",
            "transport.png": "Transport",
            "travel.png":    "Voyage",
            "wallet.png":    "Portefeuille",
            "water.png":     "Eau",
            "scissors.svg":  "Coiffeur / Beauté",
        }
        # Ajouter les icônes disponibles dans le dossier
        SKIP_FILES = {
            "add.png","delete.png","balance.png","budget.png",
            "categories.png","depenses.png","expense.png","income.png",
            "moon.png","revenus.png","stats.png","sun.png",
            "transactions.png","home.png","wallet.png",
        }
        if os.path.isdir(icons_dir):
            entries = []
            for filename in os.listdir(icons_dir):
                if (filename.endswith(".png") or filename.endswith(".svg")) and filename not in SKIP_FILES:
                    label = ICON_LABELS.get(filename, filename.replace(".png","").replace(".svg","").capitalize())
                    entries.append((label, filename))
            import unicodedata as _ud
            for label, filename in sorted(entries, key=lambda x: _ud.normalize("NFD", x[0].lower())):
                self.icon_combo.addItem(get_icon(filename, 22), label, filename)
        # Fallback si dossier vide
        if self.icon_combo.count() == 0:
            self.icon_combo.addItem("other.png")

    def update_preview(self):
        name  = self.name.text().strip() or "Nouvelle catégorie"
        color = self.color
        icon_file = self.icon_combo.currentData() or "other.png"
        pixmap = get_icon(icon_file, 18).pixmap(18, 18)
        self.preview.setText(f'<span style="color:{color}; font-size:14px;">●</span> {name}')

    def load(self):
        acc_id = account_state.get_id()
        with Session() as session:
            all_cats = session.query(Category).all()

            # Catégories masquées sur ce compte
            hidden_ids = set()
            if acc_id is not None:
                hidden_ids = {
                    row.category_id
                    for row in session.query(AccountCategory)
                    .filter_by(account_id=acc_id, hidden=True).all()
                }

            # Ne montrer que les catégories visibles, triées alphabétiquement (accents inclus)
            import unicodedata
            def _sort_key(c):
                return unicodedata.normalize("NFD", c.name.lower())
            categories = sorted(
                [c for c in all_cats if c.id not in hidden_ids],
                key=_sort_key
            )

            # Filtrer counts et amounts par compte actif
            q_counts  = session.query(Transaction.category_id, func.count(Transaction.id))
            q_amounts = (session.query(Transaction.category_id, func.sum(Transaction.amount))
                                .filter(Transaction.type == "expense"))
            if acc_id is not None:
                q_counts  = q_counts.filter(Transaction.account_id == acc_id)
                q_amounts = q_amounts.filter(Transaction.account_id == acc_id)

            counts  = dict(q_counts.group_by(Transaction.category_id).all())
            amounts = dict(q_amounts.group_by(Transaction.category_id).all())

        self.list.setRowCount(len(categories))

        if not categories:
            self.list.setRowCount(1)
            _ei = QTableWidgetItem("Aucune catégorie — créez-en une ci-dessus.")
            _ei.setTextAlignment(Qt.AlignCenter)
            _ei.setForeground(QColor("#5a6472"))
            _ei.setFlags(Qt.ItemIsEnabled)
            self.list.setItem(0, 0, _ei)
            self.list.setSpan(0, 0, 1, self.list.columnCount())
            return

        for i, c in enumerate(categories):
            count  = counts.get(c.id, 0)
            amount = amounts.get(c.id, 0)
            color  = c.color or "#888888"

            # Pastille couleur
            dot = QLabel()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(f"QLabel {{ background:{color}; border-radius:8px; }}")
            container_dot = QWidget()
            hl = QHBoxLayout(container_dot)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addStretch(); hl.addWidget(dot); hl.addStretch()
            self.list.setCellWidget(i, 0, container_dot)

            # Nom
            raw_icon = c.icon or ""
            icon_file = raw_icon if (raw_icon.endswith(".png") or raw_icon.endswith(".svg")) else get_category_icon(c.name)
            item = QTableWidgetItem(f"  {c.name}")
            item.setIcon(get_icon(icon_file, 20))
            item.setData(Qt.UserRole, c.id)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.list.setItem(i, 1, item)

            # Badge transactions
            badge = QLabel(str(count))
            badge.setAlignment(Qt.AlignCenter)
            badge_color = "#374151" if count == 0 else "#6a7484" if count <= 3 else "#16a34a" if count <= 7 else "#ea580c"
            badge.setStyleSheet(f"""
                QLabel {{ background:{badge_color}; border-radius:8px;
                          padding:1px 6px; color:white; font-weight:600; font-size:11px; }}
            """)
            container = QWidget()
            hl2 = QHBoxLayout(container)
            hl2.setContentsMargins(0, 0, 0, 0)
            hl2.addStretch(); hl2.addWidget(badge); hl2.addStretch()
            self.list.setCellWidget(i, 2, container)

            # Montant
            amount_item = QTableWidgetItem(format_money(amount))
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.list.setItem(i, 3, amount_item)

    def add_category(self):
        # Corriger l'orthographe avant validation
        if hasattr(self.name, 'correct_current'):
            self.name.correct_current()
        name = self.name.text().strip()
        if not name:
            return

        icon  = self.icon_combo.currentData() or get_category_icon(name)
        color = self.color if self.color != "#7a8494" else get_category_color(name)

        with Session() as session:
            if session.query(Category).filter_by(name=name).first():
                Toast.show(self, "✕  Cette catégorie existe déjà", kind="error")
                return
            session.add(Category(name=name, icon=icon, color=color))
            session.commit()

        added_name = self.name.text().strip()
        self.name.clear()
        self.icon_combo.setCurrentIndex(0)
        self.color = "#7a8494"
        self.color_btn.setText("🎨 Choisir une couleur")
        self.load()
        self.refresh_all()
        Toast.show(self, f"✓  Catégorie '{added_name}' ajoutée", kind="success")

    def edit_category(self, item):
        """Ouvre un dialogue pour renommer/recolorer la catégorie."""
        category_id = item.data(Qt.UserRole)
        if not category_id:
            return

        with Session() as session:
            cat = session.query(Category).filter_by(id=category_id).first()
            if not cat:
                return
            old_name  = cat.name
            old_color = cat.color or "#7a8494"
            old_icon  = cat.icon or "other.png"

        dialog = QDialog(self)
        dialog.setWindowTitle("Modifier la catégorie")
        dialog.setMinimumWidth(340)
        form = QFormLayout(dialog)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        name_input   = QLineEdit(old_name)
        name_input.setMinimumHeight(34)
        chosen_color = [old_color]
        color_btn    = QPushButton(f"🎨 {old_color}")
        color_btn.setMinimumHeight(34)

        # Sélecteur d'icône
        icon_combo = QComboBox()
        icon_combo.setMinimumHeight(34)
        icon_combo.setIconSize(QSize(22, 22))
        import os as _os
        icons_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "icons"
        )
        ICON_LABELS = {
            "assurance.png": "Assurance", "bank.png": "Banque",
            "bike.png": "Vélo / Moto", "bus.png": "Bus", "car.png": "Voiture",
            "coffee.png": "Café", "divers.png": "Divers", "doctor.png": "Médecin",
            "electricity.png": "Électricité", "entertainment.png": "Loisirs",
            "epargne.png": "Épargne", "fuel.png": "Carburant", "gas.png": "Gaz",
            "groceries.png": "Courses", "hotel.png": "Hôtel",
            "house.png": "Maison / Loyer", "internet.png": "Internet",
            "lld.png": "LLD", "money.png": "Argent", "movie.png": "Cinéma",
            "music.png": "Musique", "other.png": "Autre", "paypal.png": "PayPal",
            "pharmacy.png": "Pharmacie", "phone.png": "Téléphone",
            "plane.png": "Avion", "restaurant.png": "Restaurant",
            "shopping.png": "Shopping", "train.png": "Train",
            "transport.png": "Transport", "travel.png": "Voyage",
            "wallet.png": "Portefeuille", "water.png": "Eau",
            "scissors.svg": "Coiffeur / Beauté",
        }
        SKIP = {"add.png","delete.png","balance.png","budget.png","categories.png",
                "depenses.png","expense.png","income.png","moon.png","revenus.png",
                "stats.png","sun.png","transactions.png","home.png"}
        if _os.path.isdir(icons_dir):
            import unicodedata as _ud2
            entries = []
            for fname in _os.listdir(icons_dir):
                if (fname.endswith(".png") or fname.endswith(".svg")) and fname not in SKIP:
                    label = ICON_LABELS.get(fname, fname.replace(".png","").replace(".svg","").capitalize())
                    entries.append((label, fname))
            for label, fname in sorted(entries, key=lambda x: _ud2.normalize("NFD", x[0].lower())):
                icon_combo.addItem(get_icon(fname, 22), label, fname)
                if fname == old_icon:
                    icon_combo.setCurrentIndex(icon_combo.count() - 1)

        def pick_color():
            c = QColorDialog.getColor(QColor(chosen_color[0]))
            if c.isValid():
                chosen_color[0] = c.name()
                color_btn.setText(f"🎨 {chosen_color[0]}")

        color_btn.clicked.connect(pick_color)

        save_btn = QPushButton("Enregistrer")
        save_btn.setMinimumHeight(36)

        def save():
            new_name = name_input.text().strip()
            if not new_name:
                return
            new_icon = icon_combo.currentData() or old_icon
            with Session() as s:
                c = s.query(Category).filter_by(id=category_id).first()
                if c:
                    c.name  = new_name
                    c.color = chosen_color[0]
                    c.icon  = new_icon
                    s.commit()
            dialog.accept()
            self.load()
            self.refresh_all()
            Toast.show(self, f"✓  Catégorie modifiée", kind="success")

        save_btn.clicked.connect(save)
        form.addRow("Nom :", name_input)
        form.addRow("Icône :", icon_combo)
        form.addRow("Couleur :", color_btn)
        form.addRow(save_btn)
        dialog.exec()

    def delete_category(self):
        row = self.list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Erreur", "Sélectionnez une catégorie.")
            return

        item = self.list.item(row, 1)
        category_id = item.data(Qt.UserRole)
        acc_id = account_state.get_id()

        with Session() as session:
            # Vérifier si utilisée sur ce compte
            q_used = session.query(Transaction).filter_by(category_id=category_id)
            if acc_id is not None:
                q_used = q_used.filter(Transaction.account_id == acc_id)
            if q_used.first():
                Toast.show(self, "✕  Catégorie utilisée — réassignez d'abord les transactions", kind="error")
                return

            if acc_id is not None:
                # Masquer sur ce compte uniquement (ne pas supprimer globalement)
                existing = session.query(AccountCategory).filter_by(
                    account_id=acc_id, category_id=category_id
                ).first()
                if existing:
                    existing.hidden = True
                else:
                    session.add(AccountCategory(
                        account_id=acc_id,
                        category_id=category_id,
                        hidden=True
                    ))
                session.commit()
            else:
                # Pas de compte actif → suppression globale réelle
                cat = session.query(Category).filter_by(id=category_id).first()
                if cat:
                    session.delete(cat)
                    session.commit()

        self.load()
        self.refresh_all()

    def suppress_category(self):
        """Supprime définitivement la catégorie sélectionnée."""
        from PySide6.QtWidgets import QMessageBox
        rows = self.list.selectedItems()
        if not rows:
            Toast.show(self, "Sélectionnez une catégorie à supprimer", kind="warning")
            return
        row = self.list.currentRow()
        cat_id = self.list.item(row, 1)
        if not cat_id:
            return
        cid = cat_id.data(Qt.UserRole)
        cname = cat_id.text()

        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer définitivement")
        msg.setText(f"Supprimer définitivement la catégorie « {cname} » ?")
        msg.setInformativeText(
            "Les transactions associées conserveront leur montant mais perdront leur catégorie."
        )
        btn_yes = msg.addButton("Supprimer", QMessageBox.DestructiveRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() != btn_yes:
            return

        try:
            from db import safe_session
            from models import Category, Transaction
            with safe_session() as session:
                # Détacher les transactions
                session.query(Transaction).filter(
                    Transaction.category_id == cid
                ).update({"category_id": None})
                # Supprimer la catégorie
                cat = session.query(Category).filter_by(id=cid).first()
                if cat:
                    session.delete(cat)
            self.load()
            self.refresh_all()
            Toast.show(self, f"Catégorie « {cname} » supprimée", kind="success")
        except Exception as e:
            Toast.show(self, f"Erreur : {e}", kind="warning")

    def restore_hidden(self):
        """Réaffiche toutes les catégories masquées sur le compte actif."""
        acc_id = account_state.get_id()
        if acc_id is None:
            return
        with Session() as session:
            session.query(AccountCategory).filter_by(
                account_id=acc_id, hidden=True
            ).delete()
            session.commit()
        self.load()
        self.refresh_all()

    def refresh(self):
        self.load()

    def refresh_all(self):
        if hasattr(self.main_window, "transactions"):
            self.main_window.transactions.load_categories()
            self.main_window.transactions.load()
        if hasattr(self.main_window, "budget"):
            self.main_window.budget.load_categories()
        if hasattr(self.main_window, "accueil"):
            self.main_window.accueil.refresh()
