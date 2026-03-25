import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QStackedWidget,
    QDialog, QDateEdit, QFileDialog
)
from PySide6.QtCore import Qt, QSize, QDate
from PySide6.QtGui import QColor, QDoubleValidator

from db import Session
from models import Transaction, Category, Budget

from utils.category_icons import get_category_icon
from utils.icons import get_icon
from utils.formatters import format_money

from services.transaction_recognition import find_rule
from ui.toast import Toast
from ui.spellcheck_lineedit import SpellCheckLineEdit
from services.transaction_filter_service import match_transaction
from services.transaction_service import (
    find_monthly_duplicates, get_duplicate_count,
    add_transaction,
    get_transactions,
    get_transactions_for_period,
    delete_transaction,
    save_tags,
    get_tags_for_transactions,
)


_SORT_ROLE = Qt.UserRole + 1


class _SortItem(QTableWidgetItem):
    """QTableWidgetItem dont le tri utilise une clé numérique dédiée."""
    def __lt__(self, other):
        a = self.data(_SORT_ROLE)
        b = other.data(_SORT_ROLE)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return super().__lt__(other)


class Transactions(QWidget):

    def __init__(self, accueil):
        super().__init__()
        self.accueil = accueil
        self.page_size = 200
        self.current_offset = 0

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Barre de totaux ──
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size:14px; font-weight:600;")
        self.total_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.total_label)

        # ── Formulaire d'ajout ──
        form_card = QWidget()
        form_card.setStyleSheet("""
            QWidget {
                background:#26292e; border-radius:12px;
                border:1px solid #3a3f47;
            }
        """)
        form_card_layout = QVBoxLayout(form_card)
        form_card_layout.setContentsMargins(16, 12, 16, 12)
        form_card_layout.setSpacing(8)

        form_title = QLabel("Nouvelle transaction")
        form_title.setStyleSheet(
            "font-size:13px; font-weight:600; color:#c8cdd4; "
            "background:transparent; border:none;"
        )
        form_card_layout.addWidget(form_title)

        # Ligne 1 : Type + Montant + Catégorie + Description
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.type = QComboBox()
        self.type.addItems(["Dépense", "Revenu"])
        self.type.setMinimumHeight(36)
        self.type.setMinimumWidth(100)

        self.amount = QLineEdit()
        validator = QDoubleValidator(0.01, 100_000_000, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.amount.setValidator(validator)
        self.amount.setMinimumHeight(36)
        self.amount.setFixedWidth(130)
        self.amount.setPlaceholderText("Montant (€)")
        self.amount.returnPressed.connect(self.add)

        self.category = QComboBox()
        self.category.setIconSize(QSize(18, 18))
        self.category.setMinimumHeight(34)
        self.load_categories()

        self.note = QLineEdit()
        self.note.setPlaceholderText("Description (ex: Carrefour, Netflix...)")
        self.note.setMinimumHeight(36)
        self.note.returnPressed.connect(self.add)
        self.note.textChanged.connect(self._auto_category)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("Tags (ex: vacances, remboursable)")
        self.tags_input.setMinimumHeight(36)
        self.tags_input.returnPressed.connect(self.add)

        row1.addWidget(self.type)
        row1.addWidget(self.amount)
        row1.addWidget(self.category, 1)
        row1.addWidget(self.note, 2)
        row1.addWidget(self.tags_input, 1)
        form_card_layout.addLayout(row1)

        # Ligne 2 : Date + Ajouter + Supprimer + Exporter + Importer
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        date_lbl = QLabel("Date :")
        date_lbl.setStyleSheet(
            "color:#7a8494; font-size:12px; background:transparent; border:none;"
        )
        self._add_date = QDateEdit()
        self._add_date.setCalendarPopup(True)
        self._add_date.setDate(QDate.currentDate())
        self._add_date.setDisplayFormat("dd/MM/yyyy")
        self._add_date.setMinimumHeight(34)
        self._add_date.setFixedWidth(130)

        self.btn = QPushButton("  Ajouter")
        self.btn.setIcon(get_icon("add.png"))
        self.btn.setMinimumHeight(34)
        self.btn.clicked.connect(self.add)

        self.delete_btn = QPushButton("  Supprimer")
        self.delete_btn.setIcon(get_icon("delete.png"))
        self.delete_btn.setMinimumHeight(34)
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self.delete_selected)

        self.export_btn = QPushButton("  Exporter")
        self.export_btn.setIcon(get_icon("expense.png"))
        self.export_btn.setMinimumHeight(34)
        self.export_btn.setObjectName("export")
        self.export_btn.clicked.connect(self.export_choose)

        self.import_btn = QPushButton("  Importer")
        self.import_btn.setIcon(get_icon("income.png"))
        self.import_btn.setMinimumHeight(34)
        self.import_btn.setObjectName("import")
        self.import_btn.clicked.connect(self.import_csv)

        row2.addWidget(date_lbl)
        row2.addWidget(self._add_date)
        row2.addStretch()
        row2.addWidget(self.btn)
        row2.addWidget(self.delete_btn)
        row2.addWidget(self.export_btn)
        row2.addWidget(self.import_btn)
        form_card_layout.addLayout(row2)

        layout.addWidget(form_card)

        # ── Barre de recherche ──
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 Rechercher : courses, revenu, >100, <50, 50-200, 03/2026...")
        self.search.setMinimumHeight(34)
        self.search.textChanged.connect(self.filter_table)
        search_row.addWidget(self.search, 1)

        from PySide6.QtWidgets import QCheckBox
        self._all_periods_check = QCheckBox("Toutes périodes")
        self._all_periods_check.setToolTip("Rechercher dans toutes les transactions, pas seulement le mois affiché")
        self._all_periods_check.setStyleSheet("""
            QCheckBox { color:#f59e0b; font-size:12px; font-weight:600; }
            QCheckBox::indicator { width:16px; height:16px; border:2px solid #f59e0b;
                border-radius:4px; background:#1e2124; }
            QCheckBox::indicator:checked { background:#f59e0b; }
        """)
        self._all_periods_check.toggled.connect(self._on_global_search_toggled)
        search_row.addWidget(self._all_periods_check)

        layout.addLayout(search_row)

        # Indicateur de doublons (invisible par défaut)
        self._dup_btn = QPushButton("")
        self._dup_btn.setVisible(False)
        self._dup_btn.setStyleSheet(
            "background:#2e2415; color:#f59e0b; border:1px solid #78450a;"
            "border-radius:6px; padding:4px 12px; font-size:12px;"
        )
        self._dup_btn.clicked.connect(self._show_duplicates)
        layout.addWidget(self._dup_btn)

        # ── Tableau ──
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "Date", "Type", "Montant", "Catégorie", "Description", "Tags"]
        )
        self.table.setMinimumHeight(350)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.itemDoubleClicked.connect(self._edit_transaction)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setIconSize(QSize(18, 18))
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)

        header = self.table.horizontalHeader()

        # ── Largeurs de colonnes ──
        # Col 0 : barre couleur — fixe, très étroite
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 4)

        # Col 1 : Date — fixe, juste assez pour jj/mm/aaaa
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 100)

        # Col 2 : Type — fixe
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 115)

        # Col 3 : Montant — fixe (aligné à droite)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 120)

        # Col 4 : Catégorie — fixe, généreuse pour noms longs
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 200)

        # Col 5 : Description — prend tout l'espace restant
        header.setSectionResizeMode(5, QHeaderView.Stretch)

        # Col 6 : Tags — taille fixe
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(6, 180)

        self.table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item {
                background:#1e2023;
                border-bottom:1px solid #3a3f47;
                padding:0px 8px;
            }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section {
                background:#26292e; border:none;
                padding:6px 8px; font-weight:600;
            }
        """)

        # Widget message "aucune transaction"
        self._empty_widget = QWidget()
        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_icon = QLabel("📭")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_icon.setStyleSheet("font-size:48px; background:transparent;")
        self._empty_label = QLabel("Aucune transaction pour cette période")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            "font-size:15px; color:#4b5563; font-weight:500; background:transparent;"
        )
        self._empty_sub = QLabel("Ajoutez une transaction ou changez de période / compte")
        self._empty_sub.setAlignment(Qt.AlignCenter)
        self._empty_sub.setStyleSheet("font-size:12px; color:#374151; background:transparent;")
        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(self._empty_label)
        empty_layout.addWidget(self._empty_sub)
        self._empty_widget.setStyleSheet("background:#1e2023; border-radius:10px;")

        # ── Filtre période personnalisée ──
        from PySide6.QtWidgets import QCheckBox
        period_row = QHBoxLayout()
        period_row.setSpacing(8)

        self._custom_period_check = QCheckBox("  Période personnalisée")
        self._custom_period_check.setStyleSheet("""
            QCheckBox { color:#f59e0b; font-size:12px; font-weight:700; }
            QCheckBox::indicator { width:16px; height:16px; border:2px solid #f59e0b;
                border-radius:4px; background:#1e2124; }
            QCheckBox::indicator:checked { background:#f59e0b; }
        """)

        # Sélecteurs avec calendrier QDateEdit natif Windows
        prev  = QDate.currentDate().addMonths(-1)
        today = QDate.currentDate()

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate(prev.year(), prev.month(), 1))
        self._date_from.setDisplayFormat('dd/MM/yyyy')
        self._date_from.setMinimumHeight(34)
        self._date_from.setMinimumWidth(130)
        self._date_from.setEnabled(False)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(today)
        self._date_to.setDisplayFormat('dd/MM/yyyy')
        self._date_to.setMinimumHeight(34)
        self._date_to.setMinimumWidth(130)
        self._date_to.setEnabled(False)

        self._btn_period = QPushButton("Appliquer")
        self._btn_period.setMinimumHeight(34)
        self._btn_period.setMinimumWidth(110)
        self._btn_period.setEnabled(False)
        self._btn_period.clicked.connect(self._apply_period_filter)

        self._custom_date_range = None
        self._custom_period_check.toggled.connect(self._toggle_period_filter)

        period_row.addWidget(self._custom_period_check)
        period_row.addWidget(self._date_from)
        period_row.addWidget(QLabel(" au "))
        period_row.addWidget(self._date_to)
        period_row.addWidget(self._btn_period)
        period_row.addStretch()
        layout.addLayout(period_row)

        self._table_stack = QStackedWidget()
        self._table_stack.addWidget(self.table)        # index 0 = tableau
        self._table_stack.addWidget(self._empty_widget) # index 1 = message vide
        layout.addWidget(self._table_stack, 1)

        # ── Bouton "charger plus" ──
        self.load_more_btn = QPushButton("Charger plus de transactions...")
        self.load_more_btn.setStyleSheet(
            "background:#26292e; color:#7a8494; border-radius:6px;"
        )
        self.load_more_btn.clicked.connect(self.load_more)
        layout.addWidget(self.load_more_btn)

        self.setLayout(layout)
        self.load()

    # ------------------------------------------------------------------
    def _auto_category(self):
        note = self.note.text()
        category_id = find_rule(note)
        if category_id:
            for i in range(self.category.count()):
                if self.category.itemData(i) == category_id:
                    self.category.setCurrentIndex(i)
                    break

    def load_categories(self):
        with Session() as session:
            categories = session.query(Category).order_by(Category.name).all()
        self.category.clear()
        self.category.addItem("— Catégorie —", None)
        for c in categories:
            raw = c.icon or ""
            from utils.category_icons import get_category_icon as _gci
            icon_file = raw if (raw.endswith(".png") or raw.endswith(".svg")) else _gci(c.name)
            self.category.addItem(get_icon(icon_file, 18), c.name, c.id)
        self.category.setCurrentIndex(0)

    # ------------------------------------------------------------------
    def add(self):
        try:
            amount = float(self.amount.text().replace(",", "."))
        except ValueError:
            Toast.show(self, "✕  Montant invalide", kind="error")
            self.amount.setFocus()
            return

        if amount <= 0:
            Toast.show(self, "✕  Le montant doit être positif", kind="error")
            self.amount.setFocus()
            return

        category_id = self.category.currentData()
        if not category_id:
            Toast.show(self, "✕  Choisissez une catégorie", kind="error")
            self.category.showPopup()
            return

        ttype = "income" if self.type.currentText() == "Revenu" else "expense"
        if hasattr(self.note, 'correct_current'):
            self.note.correct_current()
        # Récupérer la date depuis le sélecteur
        from datetime import datetime as _dt
        qd = self._add_date.date()
        tx_date = _dt(qd.year(), qd.month(), qd.day())
        # Parser les tags
        raw_tags = self.tags_input.text().strip()
        tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else None
        try:
            add_transaction(amount, ttype, category_id, self.note.text().strip(), date=tx_date, tags=tag_list)
        except Exception as e:
            Toast.show(self, f"✕  Erreur : {e}", kind="error")
            return

        main = self.window()
        if hasattr(main, "refresh_all"):
            main.refresh_all()

        # Mémoriser les infos avant de vider les champs
        added_type   = self.type.currentText()
        added_note   = self.note.text().strip()
        added_amount = amount

        self.amount.clear()
        self.note.clear()
        self.tags_input.clear()
        self._add_date.setDate(QDate.currentDate())  # remettre à aujourd'hui
        self.load_categories()   # recharge et remet à l'entrée neutre
        self.amount.setFocus()
        self.table.scrollToTop()

        # Confirmation visuelle
        from utils.formatters import format_money as _fmt
        label = added_note if added_note else added_type
        sign  = "+" if added_type == "Revenu" else "-"
        Toast.show(self, f"✓  {label}  {sign}{_fmt(added_amount)}", kind="success")
        self._check_duplicates()
        self._flash_row(0, added_type)

        # Transfert automatique épargne
        if ttype == "expense":
            self._check_auto_transfer(category_id, added_amount, tx_date, added_note)

        # Alerte dépassement de budget
        if ttype == "expense" and category_id:
            self._check_budget_alert(category_id, added_amount)

    # ------------------------------------------------------------------
    def _check_auto_transfer(self, category_id, amount, tx_date, note):
        """Propose un transfert automatique si la catégorie est liée à un compte épargne."""
        from services.transfer_service import get_transfer_account, create_mirror_transaction
        from utils.formatters import format_money as _fmt

        acc_id, acc_name = get_transfer_account(category_id)
        if not acc_id:
            return

        # Popup de confirmation avec montant modifiable
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QLabel, QDoubleSpinBox, QDialogButtonBox)

        dlg = QDialog(self)
        dlg.setWindowTitle("Transfert épargne")
        dlg.setMinimumWidth(380)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        info = QLabel(
            f"Cette dépense est liée au compte <b>{acc_name}</b>.<br>"
            f"Voulez-vous créditer ce compte ?"
        )
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet("font-size:13px; color:#c8cdd4;")
        info.setWordWrap(True)
        vl.addWidget(info)

        # Montant modifiable
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel("Montant à créditer :")
        lbl.setStyleSheet("font-size:12px; color:#848c94;")
        spin = QDoubleSpinBox()
        spin.setRange(0.01, 999999.99)
        spin.setValue(amount)
        spin.setSuffix(" €")
        spin.setMinimumHeight(36)
        spin.setFixedWidth(150)
        row.addWidget(lbl)
        row.addWidget(spin)
        row.addStretch()
        vl.addLayout(row)

        # Résumé
        summary = QLabel(
            f"→ +{_fmt(amount)} sur {acc_name}"
        )
        summary.setStyleSheet(
            "font-size:12px; font-weight:600; color:#22c55e; "
            "background:#1a2a1a; border-radius:8px; padding:8px 12px;"
        )
        vl.addWidget(summary)

        # Mettre à jour le résumé quand le montant change
        def _update_summary():
            summary.setText(f"→ +{_fmt(spin.value())} sur {acc_name}")
        spin.valueChanged.connect(_update_summary)

        btns = QDialogButtonBox()
        btns.addButton("Transférer", QDialogButtonBox.AcceptRole)
        btns.addButton("Ignorer", QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() == QDialog.Accepted:
            transfer_amount = spin.value()
            create_mirror_transaction(
                source_date=tx_date,
                amount=transfer_amount,
                category_id=category_id,
                destination_account_id=acc_id,
                note=note or "Transfert épargne"
            )
            Toast.show(self,
                f"✓  +{_fmt(transfer_amount)} crédité sur {acc_name}",
                kind="success"
            )
            main = self.window()
            if hasattr(main, "refresh_all"):
                main.refresh_all()

    # ------------------------------------------------------------------
    def _check_budget_alert(self, category_id: int, added_amount: float):
        """Affiche un avertissement si le budget de la catégorie est dépassé ce mois-ci."""
        from services.transaction_service import get_budget_status
        from db import Session
        from models import Category

        status = get_budget_status()
        for cat_id, limit, spent in status:
            if cat_id != category_id:
                continue
            if spent >= limit:
                with Session() as session:
                    cat = session.query(Category).filter_by(id=cat_id).first()
                    cat_name = cat.name if cat else "cette catégorie"
                Toast.show(
                    self,
                    f"⚠  Budget « {cat_name} » dépassé ({spent:.0f} € / {limit:.0f} €)",
                    kind="warning"
                )
            elif spent >= limit * 0.9:
                with Session() as session:
                    cat = session.query(Category).filter_by(id=cat_id).first()
                    cat_name = cat.name if cat else "cette catégorie"
                Toast.show(
                    self,
                    f"⚠  Budget « {cat_name} » bientôt atteint ({spent:.0f} € / {limit:.0f} €)",
                    kind="warning"
                )
            break

    # ------------------------------------------------------------------
    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Confirmer la suppression")
        msg.setText("Supprimer cette transaction ?")
        btn_yes = msg.addButton("Oui", QMessageBox.AcceptRole)
        msg.addButton("Non", QMessageBox.RejectRole)
        msg.exec()

        if msg.clickedButton() != btn_yes:
            return

        item = self.table.item(row, 1)
        if not item:
            return

        try:
            delete_transaction(item.data(Qt.UserRole))
        except Exception as e:
            Toast.show(self, f"✕  Erreur suppression : {e}", kind="error")
            return
        self.load()
        self.accueil.refresh()
        Toast.show(self, "Transaction supprimée", kind="warning")
        self._check_duplicates()

    # ------------------------------------------------------------------
    def edit_transaction(self, item):
        row = item.row()
        id_item = self.table.item(row, 1)
        if not id_item:
            return
        transaction_id = id_item.data(Qt.UserRole)

        with Session() as session:
            t = session.query(Transaction).filter_by(id=transaction_id).first()
            if not t:
                return
            t_id, t_amount, t_type = t.id, t.amount, t.type
            t_note, t_date, t_cat_id = t.note or "", t.date, t.category_id
            cats_data = [
                (c.id, c.name,
                 c.icon if c.icon and c.icon.endswith(".png") else None)
                for c in session.query(Category).order_by(Category.name).all()
            ]

        dialog = QDialog(self)
        dialog.setWindowTitle("Modifier la transaction")
        dialog.setMinimumWidth(340)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setSpacing(8)

        type_input = QComboBox()
        type_input.addItems(["Dépense", "Revenu"])
        type_input.setCurrentIndex(0 if t_type == "expense" else 1)

        amount_input = QLineEdit(str(t_amount))
        note_input   = QLineEdit(t_note)

        date_input = QDateEdit()
        date_input.setCalendarPopup(True)
        date_input.setDate(QDate(t_date.year, t_date.month, t_date.day))

        cat_input = QComboBox()
        from utils.icons import get_icon as _get_icon
        for cid, clabel, cicon in cats_data:
            icon_widget = _get_icon(cicon, 18) if cicon else _get_icon("other.png", 18)
            cat_input.addItem(icon_widget, clabel, cid)
            if cid == t_cat_id:
                cat_input.setCurrentIndex(cat_input.count() - 1)

        save_btn = QPushButton("Enregistrer")

        def save():
            try:
                new_amount = float(amount_input.text().replace(",", "."))
            except ValueError:
                return
            with Session() as s:
                tr = s.query(Transaction).filter_by(id=t_id).first()
                if tr:
                    tr.amount      = new_amount
                    tr.note        = note_input.text().strip()
                    tr.type        = "income" if type_input.currentText() == "Revenu" else "expense"
                    tr.category_id = cat_input.currentData()
                    tr.date        = date_input.date().toPython()
                    s.commit()
            dialog.accept()
            self.load()
            self.accueil.refresh()

        save_btn.clicked.connect(save)

        for label_txt, widget in [
            ("Type", type_input), ("Montant (€)", amount_input),
            ("Description", note_input), ("Date", date_input), ("Catégorie", cat_input)
        ]:
            dlg_layout.addWidget(QLabel(label_txt))
            dlg_layout.addWidget(widget)
        dlg_layout.addWidget(save_btn)
        dialog.exec()

    # ------------------------------------------------------------------
    def _show_share_dialog(self, filepath: str, count: int):
        """Fenêtre de partage : Email, WhatsApp, Enregistrer sous, Fermer."""
        import os, subprocess, urllib.parse
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        dlg = QDialog(self)
        dlg.setWindowTitle("Partager le fichier")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        info = QLabel(f"{count} transaction(s) exportée(s)")
        info.setStyleSheet("font-size:13px; font-weight:600; color:#c8cdd4;")
        layout.addWidget(info)

        fname = os.path.basename(filepath)
        path_lbl = QLabel(fname)
        path_lbl.setStyleSheet("font-size:11px; color:#848c94;")
        layout.addWidget(path_lbl)

        def make_btn(label, color="#2e3238", text_color="#c8cdd4"):
            b = QPushButton(label)
            b.setMinimumHeight(40)
            b.setStyleSheet(
                f"background:{color}; color:{text_color};"
                "border:1px solid #3d4248; border-radius:8px;"
                "font-size:13px; padding:0 14px;"
            )
            return b

        # ── Envoyer par email ──
        btn_mail = make_btn("  @   Envoyer par email")
        def open_mail():
            try:
                import win32com.client
                outlook = win32com.client.Dispatch("Outlook.Application")
                mail = outlook.CreateItem(0)
                mail.Subject = "Export Foyio"
                mail.Body = f"Veuillez trouver ci-joint l'export Foyio.\n\nFichier : {fname}"
                mail.Attachments.Add(filepath)
                mail.Display(True)
            except ImportError:
                subject = urllib.parse.quote("Export Foyio")
                body    = urllib.parse.quote(f"Fichier : {fname}")
                QDesktopServices.openUrl(QUrl(f"mailto:?subject={subject}&body={body}"))
            dlg.accept()
        btn_mail.clicked.connect(open_mail)
        layout.addWidget(btn_mail)

        # ── WhatsApp Web ──
        btn_wa = make_btn("  💬   WhatsApp")
        def open_whatsapp():
            text = urllib.parse.quote(f"Voici mon export Foyio : {fname}")
            QDesktopServices.openUrl(QUrl(f"https://web.whatsapp.com/send?text={text}"))
            dlg.accept()
        btn_wa.clicked.connect(open_whatsapp)
        layout.addWidget(btn_wa)

        # ── Enregistrer sous ──
        btn_save = make_btn("  💾   Enregistrer sous...")
        def save_as():
            from PySide6.QtWidgets import QFileDialog as _QFD
            ext  = os.path.splitext(filepath)[1]
            if ext == ".csv":
                filt = "Fichiers CSV (*.csv)"
            else:
                filt = "Fichiers PDF (*.pdf)"
            dest, _ = _QFD.getSaveFileName(dlg, "Enregistrer sous", fname, filt)
            if dest:
                import shutil
                shutil.copy2(filepath, dest)
                Toast.show(self, f"Fichier enregistré", kind="success")
            dlg.accept()
        btn_save.clicked.connect(save_as)
        layout.addWidget(btn_save)

        # ── Imprimer ──
        btn_print = make_btn("  🖨   Imprimer")
        def do_print():
            import subprocess, os
            try:
                if os.name == "nt":
                    # Windows : ouvrir le PDF avec l'application par défaut en mode impression
                    os.startfile(filepath, "print")
                else:
                    subprocess.Popen(["lp", filepath])
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(dlg, "Impression", f"Impossible d'imprimer : {e}")
            dlg.accept()
        btn_print.clicked.connect(do_print)
        layout.addWidget(btn_print)

        # ── Fermer ──
        btn_close = make_btn("  ✕   Fermer", "#1e2124", "#848c94")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)

        dlg.exec()


    def export_choose(self):
        """Propose le choix CSV ou PDF."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Exporter")
        msg.setText("Choisissez le format d'export :")
        btn_csv = msg.addButton("CSV (tableur)", QMessageBox.AcceptRole)
        btn_pdf = msg.addButton("PDF (rapport)", QMessageBox.ActionRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_csv:
            self.export_csv()
        elif clicked == btn_pdf:
            self.export_pdf()

    def export_csv(self):
        """Export CSV avancé avec filtres période et catégorie."""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QLabel, QComboBox, QPushButton, QCheckBox)
        from PySide6.QtCore import QDate
        import period_state

        dlg = QDialog(self)
        dlg.setWindowTitle("Exporter en CSV")
        dlg.setMinimumWidth(380)
        vl = QVBoxLayout(dlg)
        vl.setSpacing(12)
        vl.setContentsMargins(20, 20, 20, 20)

        # Période
        vl.addWidget(QLabel("Période :"))
        MONTHS = ['Jan','Fev','Mar','Avr','Mai','Juin',
                  'Juil','Aout','Sep','Oct','Nov','Dec']
        years = [str(y) for y in range(2020, QDate.currentDate().year()+1)]
        p = period_state.get()

        row_from = QHBoxLayout()
        row_from.addWidget(QLabel("Du :"))
        m_from = QComboBox(); m_from.addItems(MONTHS)
        m_from.setCurrentIndex(0); m_from.setFixedWidth(70)
        y_from = QComboBox(); y_from.addItems(years)
        y_from.setCurrentText(str(p.year)); y_from.setFixedWidth(80)
        row_from.addWidget(m_from); row_from.addWidget(y_from); row_from.addStretch()
        vl.addLayout(row_from)

        row_to = QHBoxLayout()
        row_to.addWidget(QLabel("Au :"))
        m_to = QComboBox(); m_to.addItems(MONTHS)
        m_to.setCurrentIndex(p.month-1); m_to.setFixedWidth(70)
        y_to = QComboBox(); y_to.addItems(years)
        y_to.setCurrentText(str(p.year)); y_to.setFixedWidth(80)
        row_to.addWidget(m_to); row_to.addWidget(y_to); row_to.addStretch()
        vl.addLayout(row_to)

        # Catégorie
        vl.addWidget(QLabel("Catégorie :"))
        cat_combo = QComboBox()
        cat_combo.setMinimumHeight(32)
        cat_combo.addItem("Toutes les catégories", None)
        from db import Session
        from models import Category
        with Session() as session:
            cats = session.query(Category).order_by(Category.name).all()
            for c in cats:
                cat_combo.addItem(c.name, c.id)
        vl.addWidget(cat_combo)

        # Type
        chk_inc = QCheckBox("Revenus"); chk_inc.setChecked(True)
        chk_exp = QCheckBox("Dépenses"); chk_exp.setChecked(True)
        type_row = QHBoxLayout()
        type_row.addWidget(chk_inc); type_row.addWidget(chk_exp)
        type_row.addStretch()
        vl.addLayout(type_row)

        # Boutons
        btn_row = QHBoxLayout()
        btn_exp = QPushButton("  Exporter")
        btn_exp.setMinimumHeight(36)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addStretch(); btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_exp)
        vl.addLayout(btn_row)

        def _do_export():
            import calendar, tempfile, os
            from datetime import date
            from services.transaction_service import get_transactions_for_date_range
            from services.export_service import export_transactions_csv_filtered

            mf = m_from.currentIndex()+1; yf = int(y_from.currentText())
            mt = m_to.currentIndex()+1;   yt = int(y_to.currentText())
            d_from = date(yf, mf, 1)
            d_to   = date(yt, mt, calendar.monthrange(yt, mt)[1])
            cat_id = cat_combo.currentData()
            types  = []
            if chk_inc.isChecked(): types.append('income')
            if chk_exp.isChecked(): types.append('expense')

            tmp = os.path.join(tempfile.gettempdir(),
                f'foyio_export_{yf}{mf:02d}_{yt}{mt:02d}.csv')
            try:
                count = export_transactions_csv_filtered(tmp, d_from, d_to, cat_id, types)
                dlg.accept()
                self._show_share_dialog(tmp, count)
            except Exception as e:
                Toast.show(self, f'Erreur export : {e}', kind='error')

        btn_exp.clicked.connect(_do_export)
        dlg.exec()

    # ------------------------------------------------------------------
    def export_pdf(self):
        import period_state
        from PySide6.QtWidgets import QFileDialog

        default_name = (
            f"foyio_{period_state.get().year}"
            f"_{period_state.get().month:02d}.pdf"
        )
        import tempfile, os
        tmp_path = os.path.join(tempfile.gettempdir(), default_name)
        try:
            from services.pdf_export_service import export_pdf
            p = period_state.get()
            count = export_pdf(tmp_path, p.year, p.month)
            self._show_share_dialog(tmp_path, count)
        except ImportError:
            Toast.show(self,
                "reportlab non installe. Lancez : python -m pip install reportlab",
                kind="error")
        except Exception as e:
            Toast.show(self, f"Erreur PDF : {e}", kind="error")

    # ------------------------------------------------------------------
    def import_csv(self):
        """Import CSV ou PDF — détection automatique du format."""
        from PySide6.QtWidgets import QFileDialog

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un relevé bancaire",
            "",
            "Relevés bancaires (*.csv *.pdf);;Fichiers CSV (*.csv);;Fichiers PDF (*.pdf)"
        )
        if not filepath:
            return

        # Déterminer le type et ouvrir le bon dialogue
        from ui.import_view import ImportDialog
        dialog = ImportDialog(self, filepath=filepath)
        if dialog.exec() == ImportDialog.Accepted:
            count = dialog.imported_count()
            main = self.window()
            if hasattr(main, "refresh_all"):
                main.refresh_all()
            from ui.toast import Toast
            Toast.show(self, f"✓  {count} transaction(s) importée(s)", kind="success")

    # ------------------------------------------------------------------
    def load(self):
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        self.current_offset = 0

        # Les transactions arrivent triées par date DESC (plus récentes en haut).
        # Pour calculer le solde cumulatif correct ligne par ligne (de haut en bas),
        # on calcule d'abord le solde total puis on le décrémente.
        if getattr(self, '_custom_date_range', None):
            from services.transaction_service import get_transactions_for_date_range
            d_from, d_to = self._custom_date_range
            data = get_transactions_for_date_range(d_from, d_to)
        else:
            data = get_transactions_for_period(self.page_size, 0)

        self.table.clearContents()
        self.table.setRowCount(len(data))

        if not data:
            self.table.setRowCount(1)
            _ei = QTableWidgetItem("Aucune transaction trouvée pour cette période.")
            _ei.setTextAlignment(Qt.AlignCenter)
            _ei.setForeground(QColor("#5a6472"))
            _ei.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(0, 0, _ei)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            self.update_totals()
            return

        with Session() as session:
            categories = {c.id: c for c in session.query(Category).all()}
            budgets    = {b.category_id: b.monthly_limit for b in session.query(Budget).all()}

        # Charger tous les tags en un seul batch
        all_tx_ids = [t.id for t in data]
        tags_map = get_tags_for_transactions(all_tx_ids)

        # Charger les IDs de transactions ayant des pièces jointes
        from services.attachment_service import get_transaction_ids_with_attachments
        ids_with_attachments = get_transaction_ids_with_attachments(all_tx_ids)

        category_spent = {}

        for i, t in enumerate(data):
            category  = categories.get(t.category_id)
            cat_color = category.color if category and category.color else "#888888"

            if t.type == "expense":
                category_spent[t.category_id] = category_spent.get(t.category_id, 0) + t.amount

            limit         = budgets.get(t.category_id)
            spent         = category_spent.get(t.category_id, 0)
            warning_color = None

            if limit and limit > 0:
                ratio = spent / limit
                if ratio >= 1.0:
                    warning_color = QColor("#3d1010")
                elif ratio >= 0.8:
                    warning_color = QColor("#3d2e10")

            # ── Col 0 : barre couleur catégorie (4px) ──
            bar = QWidget()
            bar.setStyleSheet(f"background-color:{cat_color};")
            bar.setFixedWidth(4)
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)
            hl.addWidget(bar)
            hl.addStretch()
            self.table.setCellWidget(i, 0, container)

            # ── Col 1 : Date ──
            date_item = _SortItem(t.date.strftime("%d/%m/%Y"))
            date_item.setData(Qt.UserRole, t.id)
            date_item.setData(_SORT_ROLE, t.date.toordinal())
            date_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.table.setItem(i, 1, date_item)

            # ── Col 2 : Type ──
            if t.type == "income":
                type_label, icon_name, color = "Revenu",  "revenus.png",  QColor("#22c55e")
            else:
                type_label, icon_name, color = "Dépense", "depenses.png", QColor("#ef4444")

            type_item = QTableWidgetItem(get_icon(icon_name), f"  {type_label}")
            type_item.setForeground(color)
            type_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(i, 2, type_item)

            # ── Col 3 : Montant ──
            prefix = "▲ " if t.type == "income" else "▼ "
            amount_item = _SortItem(prefix + format_money(t.amount))
            amount_item.setData(Qt.UserRole, t.amount)
            amount_item.setData(_SORT_ROLE, t.amount)
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amount_item.setForeground(color)
            fnt = amount_item.font(); fnt.setBold(True); amount_item.setFont(fnt)
            self.table.setItem(i, 3, amount_item)

            # ── Col 4 : Catégorie (icône + nom) ──
            if category:
                raw_icon = category.icon or ""
                icon_file = raw_icon if raw_icon.endswith(".png") else get_category_icon(category.name)
                cat_item  = QTableWidgetItem(get_icon(icon_file, 18), f"  {category.name}")
            else:
                cat_item  = QTableWidgetItem(get_icon("other.png", 18), "  Inconnu")
            cat_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(i, 4, cat_item)

            # ── Col 5 : Description ──
            note_text = (t.note or "").replace('\xa0', ' ').replace('\ufffd', '').strip()
            if t.id in ids_with_attachments:
                note_text = "\U0001F4CE " + note_text
            note_item = QTableWidgetItem(note_text)
            note_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            note_item.setForeground(QColor("#7a8494"))
            self.table.setItem(i, 5, note_item)

            # ── Col 6 : Tags ──
            tx_tags = tags_map.get(t.id, [])
            tag_item = QTableWidgetItem(", ".join(tx_tags))
            tag_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tag_item.setForeground(QColor("#6366f1"))
            self.table.setItem(i, 6, tag_item)

            # ── Alerte budget ──
            if warning_color:
                for col in range(1, 7):
                    cell = self.table.item(i, col)
                    if cell:
                        cell.setBackground(warning_color)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)
        self.filter_table()
        # Afficher le message vide si aucune donnée
        self._update_empty_state(len(data))

    # ------------------------------------------------------------------
    def _toggle_period_filter(self, checked):
        """Active/désactive le filtre période personnalisée."""
        for w in [self._date_from, self._date_to, self._btn_period]:
            w.setEnabled(checked)
        if not checked:
            self._custom_date_range = None
            self.load()

    def _apply_period_filter(self):
        """Applique le filtre période personnalisée au jour près."""
        qf = self._date_from.date()
        qt = self._date_to.date()
        from datetime import date
        self._custom_date_range = (
            date(qf.year(), qf.month(), qf.day()),
            date(qt.year(), qt.month(), qt.day())
        )
        self.load()

    def _show_context_menu(self, pos):
        """Menu contextuel clic droit sur une transaction."""
        from PySide6.QtWidgets import QMenu
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        txn_id = self.table.item(row, 1)  # colonne 1 = Date, qui porte l'ID en UserRole
        if not txn_id:
            return
        tid = txn_id.data(Qt.UserRole)
        if not tid:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#292d32; color:#c8cdd4; border:1px solid #3d4248;
                    border-radius:8px; padding:4px; }
            QMenu::item { padding:8px 20px; border-radius:6px; font-size:12px; }
            QMenu::item:selected { background:#3e4550; }
        """)
        act_edit = menu.addAction("  Modifier")
        act_dup  = menu.addAction("  Dupliquer")
        act_attach = menu.addAction("  Pièces jointes")
        menu.addSeparator()
        act_del  = menu.addAction("  Supprimer")
        act_del.setProperty("danger", True)

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_edit:
            self._edit_transaction(self.table.item(row, 1))
        elif action == act_dup:
            self._duplicate_transaction(tid)
        elif action == act_attach:
            self._show_attachments(tid)
        elif action == act_del:
            self.table.selectRow(row)
            self.delete_selected()

    def _duplicate_transaction(self, txn_id: int):
        """Duplique une transaction sur la période courante."""
        from db import Session
        from models import Transaction
        from services.transaction_service import add_transaction
        import period_state, account_state
        from datetime import date

        with Session() as session:
            t = session.query(Transaction).filter_by(id=txn_id).first()
            if not t:
                return
            amount     = t.amount
            ttype      = t.type
            cat_id     = t.category_id
            note       = (t.note or "") + " (copie)"

        p = period_state.get()
        today = date.today()
        # Utiliser aujourd'hui si dans la période, sinon le 1er du mois
        if today.year == p.year and today.month == p.month:
            tx_date = today
        else:
            tx_date = date(p.year, p.month, 1)

        add_transaction(amount, ttype, cat_id, note, date=tx_date)
        self.load()
        from ui.toast import Toast
        Toast.show(self, "Transaction dupliquée", kind="success")

    def _edit_transaction(self, item):
        """Ouvre un dialogue pour modifier une transaction existante."""
        row = item.row()
        date_item = self.table.item(row, 1)
        if not date_item:
            return
        transaction_id = date_item.data(Qt.UserRole)
        if not transaction_id:
            return

        from PySide6.QtWidgets import (
            QDialog, QFormLayout, QDialogButtonBox,
            QDateEdit, QDoubleSpinBox
        )
        from PySide6.QtCore import QDate
        from db import Session
        from models import Transaction, Category
        from utils.category_icons import get_category_icon

        from services.transaction_service import get_tags_for_transaction, save_tags as _save_tags

        with Session() as session:
            t = session.query(Transaction).filter_by(id=transaction_id).first()
            if not t:
                return
            cats = session.query(Category).order_by(Category.name).all()
            t_date     = t.date
            t_amount   = t.amount
            t_type     = t.type
            t_note     = t.note or ""
            t_cat_id   = t.category_id
            session.expunge_all()

        t_tags = get_tags_for_transaction(transaction_id)

        dlg = QDialog(self)
        dlg.setWindowTitle("Modifier la transaction")
        dlg.setMinimumWidth(380)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(10)

        # Type
        type_combo = QComboBox()
        type_combo.addItem("Dépense",  "expense")
        type_combo.addItem("Revenu",   "income")
        type_combo.setCurrentIndex(0 if t_type == "expense" else 1)
        type_combo.setMinimumHeight(34)
        form.addRow("Type :", type_combo)

        # Montant
        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0.01, 999999.99)
        amount_spin.setDecimals(2)
        amount_spin.setSingleStep(1.0)
        amount_spin.setValue(t_amount)
        amount_spin.setMinimumHeight(34)
        form.addRow("Montant :", amount_spin)

        # Catégorie
        cat_combo = QComboBox()
        cat_combo.setMinimumHeight(34)
        cat_combo.setIconSize(QSize(18, 18))
        cat_combo.addItem("— Aucune —", None)
        for c in cats:
            icon_file = c.icon if c.icon and c.icon.endswith(".png") else get_category_icon(c.name)
            cat_combo.addItem(get_icon(icon_file, 18), c.name, c.id)
            if c.id == t_cat_id:
                cat_combo.setCurrentIndex(cat_combo.count() - 1)
        form.addRow("Catégorie :", cat_combo)

        # Description
        from ui.spellcheck_lineedit import SpellCheckLineEdit
        note_input = SpellCheckLineEdit()
        note_input.setText(t_note)
        note_input.setPlaceholderText("Description (optionnel)")
        note_input.setMinimumHeight(34)
        form.addRow("Description :", note_input)

        # Tags
        tags_edit = QLineEdit()
        tags_edit.setText(", ".join(t_tags))
        tags_edit.setPlaceholderText("Tags (ex: vacances, remboursable)")
        tags_edit.setMinimumHeight(34)
        form.addRow("Tags :", tags_edit)

        # Date
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate(t_date.year, t_date.month, t_date.day))
        date_edit.setMinimumHeight(34)
        form.addRow("Date :", date_edit)

        # ── Pièces jointes ──
        from services.attachment_service import (
            get_attachments as _get_attachments,
            save_attachment as _save_attachment,
            delete_attachment as _delete_attachment,
            open_attachment as _open_attachment,
        )

        att_container = QWidget()
        att_layout = QVBoxLayout(att_container)
        att_layout.setContentsMargins(0, 0, 0, 0)
        att_layout.setSpacing(4)

        def _refresh_attachments():
            # Vider le layout sauf le bouton d'ajout
            while att_layout.count() > 1:
                child = att_layout.takeAt(1)
                if child.widget():
                    child.widget().deleteLater()
            attachments = _get_attachments(transaction_id)
            for att in attachments:
                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 0, 0, 0)
                row_l.setSpacing(6)
                lbl = QLabel(f"📄 {att.filename}")
                lbl.setStyleSheet("color:#c8cdd4; font-size:12px; background:transparent; border:none;")
                row_l.addWidget(lbl, 1)
                btn_open = QPushButton("Ouvrir")
                btn_open.setMinimumHeight(28)
                btn_open.setFixedWidth(70)
                btn_open.setStyleSheet(
                    "background:#2a4a7f; color:#93c5fd; border:1px solid #3b6fb5;"
                    "border-radius:4px; padding:2px 8px; font-size:11px;"
                )
                btn_open.clicked.connect(lambda checked, a=att: _open_attachment(a))
                row_l.addWidget(btn_open)
                btn_del = QPushButton("Supprimer")
                btn_del.setMinimumHeight(28)
                btn_del.setFixedWidth(80)
                btn_del.setStyleSheet(
                    "background:#4a1a1a; color:#f87171; border:1px solid #7f1d1d;"
                    "border-radius:4px; padding:2px 8px; font-size:11px;"
                )
                btn_del.clicked.connect(lambda checked, a=att: (_delete_attachment(a.id), _refresh_attachments()))
                row_l.addWidget(btn_del)
                att_layout.addWidget(row_w)

        add_att_btn = QPushButton("  Ajouter un justificatif")
        add_att_btn.setMinimumHeight(32)
        add_att_btn.setStyleSheet(
            "background:#26292e; color:#c8cdd4; border:1px solid #3a3f47;"
            "border-radius:6px; padding:4px 12px; font-size:12px;"
        )

        def _add_attachment():
            files, _ = QFileDialog.getOpenFileNames(
                dlg,
                "Ajouter un justificatif",
                "",
                "Images et PDF (*.png *.jpg *.jpeg *.pdf *.bmp)",
            )
            for f in files:
                _save_attachment(transaction_id, f)
            _refresh_attachments()

        add_att_btn.clicked.connect(_add_attachment)
        att_layout.insertWidget(0, add_att_btn)
        _refresh_attachments()
        form.addRow("Justificatifs :", att_container)

        btns = QDialogButtonBox()
        btns.addButton("Enregistrer", QDialogButtonBox.AcceptRole)
        btn_hist = btns.addButton("Historique", QDialogButtonBox.ActionRole)
        btns.addButton("Annuler",      QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        def show_history():
            from models import TransactionHistory
            from db import Session as _S
            with _S() as s:
                rows = s.query(TransactionHistory)                    .filter_by(transaction_id=transaction_id)                    .order_by(TransactionHistory.changed_at.desc()).all()
                s.expunge_all()
            hist_dlg = QDialog(dlg)
            hist_dlg.setWindowTitle("Historique des modifications")
            hist_dlg.setMinimumWidth(500)
            vl = QVBoxLayout(hist_dlg)
            vl.setContentsMargins(16,16,16,16)
            if not rows:
                vl.addWidget(QLabel("Aucune modification enregistrée."))
            else:
                tbl = QTableWidget(len(rows), 4)
                tbl.setHorizontalHeaderLabels(["Date", "Champ", "Avant", "Après"])
                tbl.verticalHeader().setVisible(False)
                tbl.setShowGrid(False)
                tbl.setEditTriggers(QTableWidget.NoEditTriggers)
                tbl.horizontalHeader().setStretchLastSection(True)
                for i, r in enumerate(rows):
                    tbl.setItem(i,0,QTableWidgetItem(r.changed_at.strftime("%d/%m/%Y %H:%M")))
                    tbl.setItem(i,1,QTableWidgetItem(r.field_name))
                    tbl.setItem(i,2,QTableWidgetItem(r.old_value or ""))
                    tbl.setItem(i,3,QTableWidgetItem(r.new_value or ""))
                vl.addWidget(tbl)
            close_btn = QPushButton("Fermer")
            close_btn.clicked.connect(hist_dlg.accept)
            vl.addWidget(close_btn)
            hist_dlg.exec()

        btn_hist.clicked.connect(show_history)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        # Sauvegarder
        from datetime import datetime as _dt, date as _date_type
        from db import safe_session
        qd = date_edit.date()
        # t_date peut être un date ou un datetime
        if hasattr(t_date, 'hour'):
            new_date = _dt(qd.year(), qd.month(), qd.day(),
                           t_date.hour, t_date.minute, t_date.second)
        else:
            new_date = _dt(qd.year(), qd.month(), qd.day())

        from models import TransactionHistory
        from datetime import datetime as _now
        try:
            with safe_session() as session:
                t = session.query(Transaction).filter_by(id=transaction_id).first()
                if t:
                    new_amount = round(amount_spin.value(), 2)
                    new_type   = type_combo.currentData()
                    new_cat    = cat_combo.currentData()
                    new_note   = note_input.text().strip() or None

                    # Historique des changements
                    changes = []
                    if t.amount      != new_amount: changes.append(("amount",      str(t.amount),      str(new_amount)))
                    if t.type        != new_type:   changes.append(("type",        t.type,             new_type))
                    if t.category_id != new_cat:    changes.append(("category_id", str(t.category_id), str(new_cat)))
                    if (t.note or "") != (new_note or ""): changes.append(("note", t.note or "", new_note or ""))
                    old_date = t.date if isinstance(t.date, _date_type) else t.date.date()
                    if old_date != new_date.date(): changes.append(("date", str(old_date), str(new_date.date())))

                    t.amount      = new_amount
                    t.type        = new_type
                    t.category_id = new_cat
                    t.note        = new_note
                    t.date        = new_date

                    for field, old_v, new_v in changes:
                        session.add(TransactionHistory(
                            transaction_id=transaction_id,
                            changed_at=_now.now(),
                            field_name=field,
                            old_value=old_v,
                            new_value=new_v,
                            account_id=t.account_id,
                        ))

            # Sauvegarder les tags
            raw_tags = tags_edit.text().strip()
            new_tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []
            _save_tags(transaction_id, new_tags)
        except Exception as e:
            from ui.toast import Toast
            Toast.show(self, f"Erreur sauvegarde : {e}", kind="error")
            return

        self.load()
        main = self.window()
        if hasattr(main, "refresh_all"):
            main.refresh_all()
        from ui.toast import Toast
        Toast.show(self, "Transaction modifiée", kind="success")

        # Transfert automatique si catégorie épargne changée vers une catégorie liée
        if new_type == "expense" and new_cat != t_cat_id:
            self._check_auto_transfer(new_cat, new_amount, new_date, new_note or "")

    def _flash_row(self, row: int, ttype: str):
        """Flash vert ou rouge sur la ligne ajoutée."""
        from PySide6.QtCore import QTimer
        flash_color = "#1a3a1a" if ttype == "income" else "#3a1a1a"
        normal_color = ""
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(QColor(flash_color))
        def reset():
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QColor(0, 0, 0, 0))
        QTimer.singleShot(800, reset)

    def _check_duplicates(self):
        """Vérifie silencieusement les doublons du mois courant."""
        import period_state as _ps
        try:
            p = _ps.get()
            from services.transaction_service import find_monthly_duplicates
            pairs = find_monthly_duplicates(p.year, p.month)
            if len(pairs) > 0:
                self._dup_btn.setText(f"  {len(pairs)} doublon(s) probable(s) ce mois")
                self._dup_btn.setVisible(True)
            else:
                self._dup_btn.setVisible(False)
        except Exception:
            self._dup_btn.setVisible(False)

    def _show_duplicates(self):
        """Affiche la liste des doublons dans un dialogue."""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QTableWidget,
            QTableWidgetItem, QDialogButtonBox, QHeaderView
        )
        from PySide6.QtGui import QColor
        import period_state as _ps

        p = _ps.get()
        pairs = find_monthly_duplicates(p.year, p.month)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Doublons probables — {_ps.label()}")
        dlg.setMinimumWidth(700)
        dlg.setMinimumHeight(340)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        msg = (f"{len(pairs)} paire(s) de transactions potentiellement en doublon. "
               "Vérifiez et supprimez manuellement si nécessaire.")
        info = QLabel(msg)
        info.setStyleSheet("font-size:12px; color:#848c94;")
        info.setWordWrap(True)
        layout.addWidget(info)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Date A", "Date B", "Montant", "Libellé A", "Libellé B"])
        table.setRowCount(len(pairs))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.setStyleSheet("""
            QTableWidget { background:#191c20; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:4px 8px; }
            QHeaderView::section {
                background:#292d32; color:#848c94; border:none;
                border-bottom:1px solid #3d4248; padding:6px 8px; font-size:11px;
            }
        """)

        for row, (t1, t2, raison) in enumerate(pairs):
            for col, text in enumerate([
                t1.date.strftime("%d/%m/%Y"),
                t2.date.strftime("%d/%m/%Y"),
                f"{t1.amount:.2f} EUR",
                t1.note or "—",
                t2.note or "—",
            ]):
                item = QTableWidgetItem(text)
                item.setForeground(QColor("#f59e0b") if col == 2 else QColor("#c8cdd4"))
                table.setItem(row, col, item)

        layout.addWidget(table)
        btns = QDialogButtonBox()
        btns.addButton("Fermer", QDialogButtonBox.RejectRole)
        btns.rejected.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()

    def _update_empty_state(self, total_rows: int):
        """Bascule entre le tableau et le message 'aucune transaction'."""
        import period_state as _ps
        import account_state as _as
        if total_rows == 0:
            acc = _as.get_name()
            period = _ps.label()
            self._empty_label.setText(
                f"Aucune transaction — {acc} — {period}"
            )
            self._table_stack.setCurrentIndex(1)
        else:
            self._table_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    def _on_global_search_toggled(self, checked: bool):
        """Recharge toutes les transactions ou revient à la période."""
        if checked:
            self._load_all_transactions()
        else:
            self.load()

    def _load_all_transactions(self):
        """Charge toutes les transactions (toutes périodes, tous comptes) dans le tableau."""
        from services.transaction_service import get_transactions
        from services.attachment_service import get_transaction_ids_with_attachments

        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        data = get_transactions(limit=10000, offset=0)
        self.table.clearContents()
        self.table.setRowCount(len(data))

        if not data:
            self.table.setRowCount(1)
            _ei = QTableWidgetItem("Aucune transaction enregistrée.")
            _ei.setTextAlignment(Qt.AlignCenter)
            _ei.setForeground(QColor("#5a6472"))
            _ei.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(0, 0, _ei)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            self.table.setUpdatesEnabled(True)
            return

        with Session() as session:
            categories = {c.id: c for c in session.query(Category).all()}

        all_tx_ids = [t.id for t in data]
        tags_map = get_tags_for_transactions(all_tx_ids)
        ids_with_attachments = get_transaction_ids_with_attachments(all_tx_ids)

        for i, t in enumerate(data):
            category  = categories.get(t.category_id)
            cat_color = category.color if category and category.color else "#888888"

            bar = QWidget()
            bar.setStyleSheet(f"background-color:{cat_color};")
            bar.setFixedWidth(4)
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)
            hl.addWidget(bar)
            hl.addStretch()
            self.table.setCellWidget(i, 0, container)

            date_item = _SortItem(t.date.strftime("%d/%m/%Y"))
            date_item.setData(Qt.UserRole, t.id)
            date_item.setData(_SORT_ROLE, t.date.toordinal())
            date_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.table.setItem(i, 1, date_item)

            if t.type == "income":
                type_label, icon_name, color = "Revenu",  "revenus.png",  QColor("#22c55e")
            else:
                type_label, icon_name, color = "Dépense", "depenses.png", QColor("#ef4444")

            type_item = QTableWidgetItem(get_icon(icon_name), f"  {type_label}")
            type_item.setForeground(color)
            type_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(i, 2, type_item)

            prefix = "▲ " if t.type == "income" else "▼ "
            amount_item = _SortItem(prefix + format_money(t.amount))
            amount_item.setData(Qt.UserRole, t.amount)
            amount_item.setData(_SORT_ROLE, t.amount)
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amount_item.setForeground(color)
            fnt = amount_item.font(); fnt.setBold(True); amount_item.setFont(fnt)
            self.table.setItem(i, 3, amount_item)

            if category:
                raw_icon = category.icon or ""
                icon_file = raw_icon if raw_icon.endswith(".png") else get_category_icon(category.name)
                cat_item = QTableWidgetItem(get_icon(icon_file, 18), f"  {category.name}")
            else:
                cat_item = QTableWidgetItem(get_icon("other.png", 18), "  Inconnu")
            cat_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(i, 4, cat_item)

            note_text = (t.note or "").replace('\xa0', ' ').replace('\ufffd', '').strip()
            if t.id in ids_with_attachments:
                note_text = "\U0001F4CE " + note_text
            note_item = QTableWidgetItem(note_text)
            note_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            note_item.setForeground(QColor("#7a8494"))
            self.table.setItem(i, 5, note_item)

            tx_tags = tags_map.get(t.id, [])
            tag_item = QTableWidgetItem(", ".join(tx_tags))
            tag_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tag_item.setForeground(QColor("#6366f1"))
            self.table.setItem(i, 6, tag_item)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)
        self.filter_table()

    # ------------------------------------------------------------------
    def filter_table(self):
        text = self.search.text().strip().lower()

        if not text:
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)
            self.update_totals()
            return

        tokens = text.split()

        for row in range(self.table.rowCount()):
            type_item     = self.table.item(row, 2)
            amount_item   = self.table.item(row, 3)
            category_item = self.table.item(row, 4)
            note_item     = self.table.item(row, 5)
            tag_item      = self.table.item(row, 6)

            type_text     = type_item.text().lower()     if type_item     else ""
            category_text = category_item.text().lower() if category_item else ""
            note_text     = note_item.text().lower()     if note_item     else ""
            tag_text_val  = tag_item.text().lower()      if tag_item      else ""
            amount        = amount_item.data(Qt.UserRole) if amount_item  else 0

            # Récupérer la date de la ligne pour le filtre par date
            date_item = self.table.item(row, 1)
            row_date  = None
            if date_item:
                try:
                    from datetime import datetime as _dt
                    row_date = _dt.strptime(date_item.text(), "%d/%m/%Y").date()
                except ValueError:
                    pass

            show = match_transaction(
                type_text, category_text, note_text, amount, tokens,
                transaction_date=row_date, tag_text=tag_text_val
            )
            self.table.setRowHidden(row, not show)

        # Basculer vers message vide si le filtre masque tout
        visible = sum(
            1 for r in range(self.table.rowCount())
            if not self.table.isRowHidden(r)
        )
        if self.table.rowCount() > 0 and visible == 0:
            self._empty_label.setText('Aucun résultat pour cette recherche')
            self._empty_sub.setText('Essayez d\'autres mots-clés')
            self._table_stack.setCurrentIndex(1)
        elif self.table.rowCount() > 0:
            self._table_stack.setCurrentIndex(0)
            self._empty_sub.setText(
                'Ajoutez une transaction ou changez de période / compte'
            )

        self.update_totals()

    # ------------------------------------------------------------------
    def update_totals(self):
        income = expense = 0

        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            type_item   = self.table.item(row, 2)
            amount_item = self.table.item(row, 3)
            if not type_item or not amount_item:
                continue
            amount = amount_item.data(Qt.UserRole)
            if "Revenu" in type_item.text():
                income += amount
            else:
                expense += amount

        BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        income_icon  = os.path.join(BASE_DIR, "icons", "income.png")
        expense_icon = os.path.join(BASE_DIR, "icons", "expense.png")
        balance_icon = os.path.join(BASE_DIR, "icons", "balance.png")

        # Animation compteur : interpolation depuis les valeurs précédentes
        from PySide6.QtCore import QTimer as _QTimer
        prev_income  = getattr(self, '_prev_income',  0.0)
        prev_expense = getattr(self, '_prev_expense', 0.0)
        self._prev_income  = income
        self._prev_expense = expense

        STEPS    = 24
        INTERVAL = 16  # ~60 fps

        step_ref = [0]
        if hasattr(self, '_totals_timer') and self._totals_timer.isActive():
            self._totals_timer.stop()

        def _render(cur_i, cur_e):
            bal  = cur_i - cur_e
            sign = "+" if bal >= 0 else ""
            self.total_label.setText(
                f'<img src="{income_icon}" width="20"> '
                f'<span style="color:#22c55e">+{format_money(cur_i)}</span>'
                f'&nbsp;&nbsp;&nbsp;'
                f'<img src="{expense_icon}" width="20"> '
                f'<span style="color:#ef4444">-{format_money(cur_e)}</span>'
                f'&nbsp;&nbsp;&nbsp;'
                f'<img src="{balance_icon}" width="20"> '
                f'<span style="color:#{"22c55e" if bal >= 0 else "ef4444"}">'
                f'{sign}{format_money(bal)}</span>'
            )

        def _tick():
            s = step_ref[0]
            if s >= STEPS:
                self._totals_timer.stop()
                _render(income, expense)
                return
            t = s / STEPS
            t = 1 - (1 - t) ** 3          # ease-out cubic
            _render(
                prev_income  + (income  - prev_income)  * t,
                prev_expense + (expense - prev_expense) * t,
            )
            step_ref[0] += 1

        self._totals_timer = _QTimer(self)
        self._totals_timer.setInterval(INTERVAL)
        self._totals_timer.timeout.connect(_tick)
        self._totals_timer.start()

    # ------------------------------------------------------------------
    def load_more(self):
        self.current_offset += self.page_size
        new_data = get_transactions_for_period(self.page_size, self.current_offset)

        if not new_data:
            self.load_more_btn.setText("Tout est chargé")
            self.load_more_btn.setEnabled(False)
            return

        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)

        with Session() as session:
            categories = {c.id: c for c in session.query(Category).all()}

        # Charger les tags pour les nouvelles transactions
        more_ids = [t.id for t in new_data]
        tags_map = get_tags_for_transactions(more_ids)

        start_row = self.table.rowCount()
        self.table.setRowCount(start_row + len(new_data))

        for i, t in enumerate(new_data):
            row      = start_row + i
            category = categories.get(t.category_id)
            cat_color = category.color if category and category.color else "#888888"

            bar = QWidget()
            bar.setStyleSheet(f"background-color:{cat_color};")
            bar.setFixedWidth(4)
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(bar)
            hl.addStretch()
            self.table.setCellWidget(row, 0, container)

            date_item = _SortItem(t.date.strftime("%d/%m/%Y"))
            date_item.setData(Qt.UserRole, t.id)
            date_item.setData(_SORT_ROLE, t.date.toordinal())
            date_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.table.setItem(row, 1, date_item)

            if t.type == "income":
                type_label, icon_name, color = "Revenu",  "revenus.png",  QColor("#22c55e")
            else:
                type_label, icon_name, color = "Dépense", "depenses.png", QColor("#ef4444")

            type_item = QTableWidgetItem(get_icon(icon_name), f"  {type_label}")
            type_item.setForeground(color)
            self.table.setItem(row, 2, type_item)

            prefix = "▲ " if t.type == "income" else "▼ "
            amount_item = _SortItem(prefix + format_money(t.amount))
            amount_item.setData(Qt.UserRole, t.amount)
            amount_item.setData(_SORT_ROLE, t.amount)
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amount_item.setForeground(color)
            self.table.setItem(row, 3, amount_item)

            cat_item = QTableWidgetItem(
                get_icon(category.icon or "other.png", 18) if category else get_icon("other.png", 18),
                f"  {category.name}" if category else "  Inconnu"
            )
            cat_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 4, cat_item)

            note_item = QTableWidgetItem(t.note or "")
            note_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            note_item.setForeground(QColor("#7a8494"))
            self.table.setItem(row, 5, note_item)

            tx_tags = tags_map.get(t.id, [])
            tag_item = QTableWidgetItem(", ".join(tx_tags))
            tag_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tag_item.setForeground(QColor("#6366f1"))
            self.table.setItem(row, 6, tag_item)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

    # ------------------------------------------------------------------
    def _show_attachments(self, txn_id: int):
        """Fenêtre de gestion des pièces jointes d'une transaction."""
        from services.attachment_service import (
            get_attachments, save_attachment, delete_attachment, open_attachment,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Pièces jointes")
        dlg.setMinimumSize(480, 340)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        title = QLabel("Pièces jointes (tickets, factures...)")
        title.setStyleSheet(
            "font-size:14px; font-weight:700; color:#c8cdd4; "
            "background:#292d32; border-radius:8px; padding:10px;"
        )
        vl.addWidget(title)

        # Liste des fichiers
        att_list = QVBoxLayout()
        att_list.setSpacing(6)
        att_container = QWidget()
        att_container.setLayout(att_list)

        def refresh_list():
            while att_list.count():
                child = att_list.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            attachments = get_attachments(txn_id)
            if not attachments:
                empty = QLabel("Aucune pièce jointe.")
                empty.setStyleSheet("color:#6b7280; font-size:12px; padding:8px;")
                att_list.addWidget(empty)
            else:
                for att in attachments:
                    row_w = QWidget()
                    row_w.setStyleSheet(
                        "background:#26292e; border-radius:8px; border:1px solid #3a3f47;"
                    )
                    row_l = QHBoxLayout(row_w)
                    row_l.setContentsMargins(12, 8, 12, 8)
                    row_l.setSpacing(10)

                    name_lbl = QLabel(att.filename)
                    name_lbl.setStyleSheet(
                        "color:#c8cdd4; font-size:12px; background:transparent; border:none;"
                    )
                    row_l.addWidget(name_lbl, 1)

                    btn_open = QPushButton("Ouvrir")
                    btn_open.setFixedHeight(26)
                    btn_open.setStyleSheet(
                        "background:#2e3238; color:#3b82f6; border:1px solid #3a3f47;"
                        "border-radius:6px; font-size:11px; padding:0 10px;"
                    )
                    btn_open.clicked.connect(
                        lambda checked, a=att: open_attachment(a)
                    )
                    row_l.addWidget(btn_open)

                    btn_del = QPushButton("Supprimer")
                    btn_del.setFixedHeight(26)
                    btn_del.setStyleSheet(
                        "background:#2e2020; color:#e89090; border:1px solid #503030;"
                        "border-radius:6px; font-size:11px; padding:0 10px;"
                    )
                    btn_del.clicked.connect(
                        lambda checked, a_id=att.id: (delete_attachment(a_id), refresh_list())
                    )
                    row_l.addWidget(btn_del)

                    att_list.addWidget(row_w)

        refresh_list()
        vl.addWidget(att_container, 1)

        # Boutons bas
        btn_row = QHBoxLayout()
        btn_add = QPushButton("  Ajouter un fichier")
        btn_add.setMinimumHeight(34)
        btn_add.setStyleSheet(
            "background:#2e3238; color:#22c55e; border:1px solid #3a3f47;"
            "border-radius:8px; font-size:12px; padding:0 16px;"
        )

        def add_file():
            path, _ = QFileDialog.getOpenFileName(
                dlg, "Choisir un fichier",
                "", "Tous les fichiers (*.*)"
            )
            if path:
                save_attachment(txn_id, path)
                refresh_list()
                Toast.show(self, "Pièce jointe ajoutée", kind="success")

        btn_add.clicked.connect(add_file)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_add)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        vl.addLayout(btn_row)

        dlg.exec()
