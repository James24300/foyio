"""
Fenêtre d'import CSV — prévisualisation + confirmation doublon par doublon.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QProgressBar, QWidget, QFrame
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor

from db import Session
from models import Category
from utils.icons import get_icon
from utils.formatters import format_money
from utils.category_icons import get_category_icon


class ImportDialog(QDialog):

    def __init__(self, parent=None, filepath=None):
        super().__init__(parent)
        self.setWindowTitle("Importer un relevé bancaire CSV / PDF")
        self.setMinimumSize(900, 620)
        self.resize(980, 680)

        self._rows      = []      # liste d'ImportRow
        self._cat_combos = []     # QComboBox par ligne
        self._categories = []     # [(id, name, icon_file)]
        self._imported   = 0
        self._preloaded_filepath = filepath

        self._load_categories()
        self._build_ui()

        # Charger automatiquement si filepath fourni
        if filepath:
            self._open_file(filepath)

    # ------------------------------------------------------------------
    def _load_categories(self):
        with Session() as session:
            cats = session.query(Category).order_by(Category.name).all()
        self._categories = []
        for c in cats:
            raw = c.icon or ""
            icon_file = raw if raw.endswith(".png") else get_category_icon(c.name)
            self._categories.append((c.id, c.name, icon_file))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── En-tête ──
        header = QHBoxLayout()

        info = QLabel(
            "Importez un relevé bancaire (.csv, .pdf, .ofx/.qfx, .qif).\n"
            "Banques supportées : Société Générale, BNP, Crédit Agricole, LCL, etc.\n"
            "Vérifiez les catégories détectées avant de valider."
        )
        info.setStyleSheet("color:#7a8494; font-size:12px;")
        info.setWordWrap(True)
        header.addWidget(info, 1)

        self._btn_open = QPushButton("  Choisir un fichier CSV")
        self._btn_open.setIcon(get_icon("money.png"))
        self._btn_open.setMinimumHeight(40)
        self._btn_open.setMinimumWidth(200)
        self._btn_open.setText("  Choisir un fichier CSV / PDF / OFX / QIF")
        self._btn_open.clicked.connect(self._open_file)
        header.addWidget(self._btn_open)

        layout.addLayout(header)

        # ── Bandeau statut ──
        self._status = QLabel("Aucun fichier sélectionné.")
        self._status.setStyleSheet(
            "background:#26292e; border-radius:8px; padding:8px 14px;"
            "font-size:12px; color:#7a8494;"
        )
        layout.addWidget(self._status)

        # ── Tableau de prévisualisation ──
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Date", "Libellé", "Type", "Montant", "Catégorie", "Statut"]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setAlternatingRowColors(False)
        self._table.setFocusPolicy(Qt.NoFocus)

        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed);    self._table.setColumnWidth(0, 100)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed);    self._table.setColumnWidth(2, 90)
        h.setSectionResizeMode(3, QHeaderView.Fixed);    self._table.setColumnWidth(3, 120)
        h.setSectionResizeMode(4, QHeaderView.Fixed);    self._table.setColumnWidth(4, 170)
        h.setSectionResizeMode(5, QHeaderView.Fixed);    self._table.setColumnWidth(5, 110)

        self._table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #3a3f47; padding:4px 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section {
                background:#26292e; border:none;
                padding:6px 8px; font-weight:600; color:#7a8494;
            }
        """)

        layout.addWidget(self._table, 1)

        # ── Barre de progression ──
        self._progress = QProgressBar()
        self._progress.setMaximum(100)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar { background:#26292e; border-radius:3px; }
            QProgressBar::chunk { background:#7a8494; border-radius:3px; }
        """)
        layout.addWidget(self._progress)

        # ── Boutons ──
        btn_row = QHBoxLayout()

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet("color:#6b7280; font-size:12px;")
        btn_row.addWidget(self._lbl_count)
        btn_row.addStretch()

        self._btn_cancel = QPushButton("Fermer")
        self._btn_cancel.setMinimumHeight(38)
        self._btn_cancel.setStyleSheet("background:#374151; color:#c8cdd4;")
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_import = QPushButton("  Importer les transactions")
        self._btn_import.setIcon(get_icon("add.png"))
        self._btn_import.setMinimumHeight(38)
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._do_import)

        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_import)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    def _open_file(self, filepath=None):
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Choisir un relevé bancaire",
                "", "Relevés bancaires (*.csv *.CSV *.pdf *.PDF *.ofx *.OFX *.qfx *.QFX *.qif *.QIF)"
            )
        if not filepath:
            return

        try:
            ext = filepath.lower().split(".")[-1]
            if ext == "pdf":
                from services.import_service import load_pdf
                fmt, rows = load_pdf(filepath)
            elif ext in ("ofx", "qfx"):
                from services.import_service import load_ofx
                fmt, rows = load_ofx(filepath)
            elif ext == "qif":
                from services.import_service import load_qif
                fmt, rows = load_qif(filepath)
            else:
                from services.import_service import load_csv
                fmt, rows = load_csv(filepath)
        except ValueError as e:
            QMessageBox.critical(self, "Format non reconnu", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Erreur de lecture", str(e))
            return

        self._rows = rows

        fmt_labels = {
            "sg_web":      "Société Générale (Web)",
            "sg_gdb":      "Société Générale (GDB)",
            "sg":          "Société Générale (CSV)",
            "sg_auto":     "Société Générale (CSV détecté)",
            "internal":    "Export Foyio",
            "pdf_sg":      "Société Générale (PDF)",
            "pdf_generic": "Relevé bancaire (PDF)",
            "ofx":         "OFX / QFX",
            "qif":         "QIF (Quicken)",
        }
        n_dup = sum(1 for r in rows if r.is_duplicate)
        n_ok  = len(rows) - n_dup

        self._status.setText(
            f"Fichier : {filepath.split('/')[-1].split(chr(92))[-1]}  •  "
            f"Format : {fmt_labels.get(fmt, fmt)}  •  "
            f"{len(rows)} transaction(s) trouvée(s)  •  "
            f"{n_dup} doublon(s) potentiel(s)"
        )
        self._status.setStyleSheet(
            "background:#3e4550; border-radius:8px; padding:8px 14px;"
            "font-size:12px; color:#b8c0c8;"
        )

        self._fill_table(rows)
        self._btn_import.setEnabled(len(rows) > 0)
        self._lbl_count.setText(
            f"{n_ok} à importer  •  {n_dup} doublon(s)"
        )

    def _fill_table(self, rows):
        self._table.setRowCount(len(rows))
        self._cat_combos = []

        for i, row in enumerate(rows):
            # Date
            date_item = QTableWidgetItem(row.date.strftime("%d/%m/%Y"))
            date_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self._table.setItem(i, 0, date_item)

            # Libellé
            label_item = QTableWidgetItem(row.label)
            self._table.setItem(i, 1, label_item)

            # Type
            if row.type == "income":
                type_item = QTableWidgetItem(get_icon("revenus.png"), "  Revenu")
                type_item.setForeground(QColor("#22c55e"))
            else:
                type_item = QTableWidgetItem(get_icon("depenses.png"), "  Dépense")
                type_item.setForeground(QColor("#ef4444"))
            self._table.setItem(i, 2, type_item)

            # Montant
            sign = "+" if row.type == "income" else "-"
            amt_item = QTableWidgetItem(f"{sign}{format_money(row.amount)}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            color = QColor("#22c55e") if row.type == "income" else QColor("#ef4444")
            amt_item.setForeground(color)
            fnt = amt_item.font(); fnt.setBold(True); amt_item.setFont(fnt)
            self._table.setItem(i, 3, amt_item)

            # Catégorie — QComboBox éditable
            combo = QComboBox()
            combo.setIconSize(QSize(16, 16))
            combo.addItem("— Non catégorisée —", None)
            for cat_id, cat_name, icon_file in self._categories:
                combo.addItem(get_icon(icon_file, 16), cat_name, cat_id)
                if cat_id == row.category_id:
                    combo.setCurrentIndex(combo.count() - 1)
            # Apprendre en temps réel quand l'utilisateur change la catégorie
            def _on_cat_changed(idx, r=row, c=combo):
                cid = c.currentData()
                if cid and r.label:
                    try:
                        from services.transaction_recognition import learn_from_import
                        learn_from_import([(r.label, cid)])
                        # Mettre à jour les autres lignes non catégorisées
                        self._auto_fill_similar(r.label, cid)
                    except Exception:
                        pass
            combo.currentIndexChanged.connect(_on_cat_changed)
            self._table.setCellWidget(i, 4, combo)
            self._cat_combos.append(combo)

            # Statut doublon
            if row.is_duplicate:
                status_item = QTableWidgetItem("⚠ Doublon possible")
                status_item.setForeground(QColor("#f59e0b"))
            else:
                status_item = QTableWidgetItem("✓ Nouveau")
                status_item.setForeground(QColor("#22c55e"))
            status_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self._table.setItem(i, 5, status_item)

            # Fond de ligne pour les doublons
            if row.is_duplicate:
                for col in range(5):
                    item = self._table.item(i, col)
                    if item:
                        item.setBackground(QColor("#2d2010"))

    # ------------------------------------------------------------------
    def _auto_fill_similar(self, label: str, cat_id: int):
        """Remplit automatiquement les lignes similaires non catégorisées."""
        from services.transaction_recognition import normalize
        label_n = normalize(label)
        # Extraire mots-clés significatifs
        import re
        SKIP = {"carte", "super", "sarl", "retrait", "frais", "x4832",
                "x3093", "paiement", "commerce", "electronique"}
        words = [w for w in re.split(r"\W+", label_n)
                 if len(w) >= 3 and w not in SKIP
                 and not re.match(r'^x?\d+$', w)]
        if not words:
            return
        keyword = max(words, key=len)
        for i, combo in enumerate(self._cat_combos):
            if combo.currentData() is not None:
                continue  # déjà catégorisé
            row_label = normalize(self._rows[i].label if i < len(self._rows) else '')
            if keyword in row_label:
                # Sélectionner la même catégorie
                for j in range(combo.count()):
                    if combo.itemData(j) == cat_id:
                        combo.blockSignals(True)
                        combo.setCurrentIndex(j)
                        combo.blockSignals(False)
                        break

    def _do_import(self):
        if not self._rows:
            return

        from services.import_service import insert_row
        import account_state

        acc_id   = account_state.get_id()
        imported = skipped = 0
        errors   = []

        self._progress.setVisible(True)
        self._progress.setMaximum(len(self._rows))

        skip_all_duplicates = False

        # Si tout est doublon, demander une seule fois
        n_dup = sum(1 for r in self._rows if r.is_duplicate)
        if n_dup == len(self._rows) and n_dup > 0:
            msg = QMessageBox(self)
            msg.setWindowTitle("Doublons détectés")
            msg.setText(
                f"Toutes les {n_dup} transactions semblent déjà exister.\n"
                "Voulez-vous les importer quand même ?"
            )
            btn_yes = msg.addButton("Importer quand même", QMessageBox.AcceptRole)
            btn_no  = msg.addButton("Annuler", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_no:
                return
            else:
                skip_all_duplicates = True
                for r in self._rows:
                    r.is_duplicate = False

        for i, row in enumerate(self._rows):
            self._progress.setValue(i + 1)
            cat_id = self._cat_combos[i].currentData() if i < len(self._cat_combos) else None

            # Doublon → demander confirmation
            if row.is_duplicate and not skip_all_duplicates:
                msg = QMessageBox(self)
                msg.setWindowTitle("Doublon détecté")
                msg.setText(
                    f"Cette transaction semble déjà exister :\n\n"
                    f"  {row.date.strftime('%d/%m/%Y')}  |  "
                    f"{row.label}  |  {format_money(row.amount)}\n\n"
                    f"Voulez-vous l'importer quand même ?"
                )
                btn_yes    = msg.addButton("Importer quand même",       QMessageBox.AcceptRole)
                btn_no     = msg.addButton("Ignorer",                   QMessageBox.RejectRole)
                btn_no_all = msg.addButton("Ignorer tous les doublons", QMessageBox.ActionRole)
                msg.exec()

                clicked = msg.clickedButton()
                if clicked == btn_no:
                    skipped += 1
                    continue
                elif clicked == btn_no_all:
                    skipped += 1
                    skip_all_duplicates = True
                    continue
                # btn_yes → on continue vers l'insertion

            elif row.is_duplicate and skip_all_duplicates:
                skipped += 1
                continue

            try:
                insert_row(row, cat_id, acc_id)
                imported += 1
                # Apprendre immédiatement pour les lignes suivantes
                if cat_id and row.label:
                    try:
                        from services.transaction_recognition import learn_from_import
                        learn_from_import([(row.label, cat_id)])
                    except Exception:
                        pass
            except Exception as e:
                errors.append(f"{row.label}: {e}")

        self._progress.setVisible(False)
        self._imported = imported

        summary = f"{imported} transaction(s) importée(s)"
        if skipped:
            summary += f"\n{skipped} doublon(s) ignoré(s)"
        if errors:
            summary += f"\n{len(errors)} erreur(s) :\n" + "\n".join(errors[:5])

        # Afficher le résumé
        if errors:
            QMessageBox.warning(self, "Import terminé avec erreurs", summary)
        else:
            QMessageBox.information(self, "Import terminé", summary)

        # Apprentissage des catégories
        if imported > 0:
            try:
                from services.transaction_recognition import learn_from_import
                associations = [
                    (self._rows[i].label, self._cat_combos[i].currentData())
                    for i in range(len(self._rows))
                    if i < len(self._cat_combos) and self._cat_combos[i].currentData()
                ]
                learn_from_import(associations)
            except Exception:
                pass

        # Proposer d'ajouter les récurrents détectés
        if imported > 0:
            try:
                from services.import_service import detect_recurring_candidates
                candidates = detect_recurring_candidates(self._rows)
                if candidates:
                    self._propose_recurring(candidates)
            except Exception:
                pass

        # Toujours fermer le dialogue
        self.accept()

    def _propose_recurring(self, candidates: list):
        """Propose d'ajouter les transactions récurrentes détectées."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QCheckBox, QPushButton, QScrollArea, QWidget
        from utils.formatters import format_money

        dlg = QDialog(self)
        dlg.setWindowTitle("Virements récurrents détectés")
        dlg.setMinimumWidth(420)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        vl.addWidget(QLabel(
            f"{len(candidates)} virement(s) récurrent(s) détecté(s).\n"
            "Cochez ceux à ajouter aux récurrentes :"
        ))

        checks = []
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        inner = QWidget(); il = QVBoxLayout(inner)
        for c in candidates:
            chk = QCheckBox(
                f"{c['label']}  —  {format_money(c['amount'])}  "
                f"({'Revenu' if c['type']=='income' else 'Dépense'})  x{c['count']}"
            )
            chk.setChecked(True)
            il.addWidget(chk)
            checks.append((chk, c))
        scroll.setWidget(inner)
        vl.addWidget(scroll)

        btn_row = __import__('PySide6.QtWidgets', fromlist=['QHBoxLayout']).QHBoxLayout()
        btn_add = QPushButton("  Ajouter les sélectionnées")
        btn_add.setMinimumHeight(34)
        btn_skip = QPushButton("Ignorer")
        btn_skip.setMinimumHeight(34)
        btn_skip.clicked.connect(dlg.reject)
        btn_row.addStretch(); btn_row.addWidget(btn_skip); btn_row.addWidget(btn_add)
        vl.addLayout(btn_row)

        def _add():
            from services.recurring_service import add_recurring
            import account_state
            added = 0
            for chk, c in checks:
                if chk.isChecked():
                    try:
                        from datetime import date
                        add_recurring(
                            label=c["label"],
                            amount=c["amount"],
                            ttype=c["type"],
                            category_id=None,
                            day_of_month=date.today().day,
                        )
                        added += 1
                    except Exception:
                        pass
            from ui.toast import Toast
            if added:
                Toast.show(self.parent() or self,
                           f"{added} récurrente(s) ajoutée(s)", kind="success")
            dlg.accept()

        btn_add.clicked.connect(_add)
        dlg.exec()

    def imported_count(self):
        return self._imported
