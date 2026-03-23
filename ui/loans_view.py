"""
Vue Prêts — Foyio
Gestion des prêts / crédits avec tableau d'amortissement.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame, QDialog, QProgressBar
)
from PySide6.QtCore import Qt, QDate, QSize
from PySide6.QtGui import QColor, QDoubleValidator

from utils.formatters import format_money
from utils.icons import get_icon
from ui.toast import Toast
from services.loan_service import (
    add_loan, get_loans, delete_loan,
    get_amortization_schedule, get_loan_summary,
)


class LoansView(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── En-tête ──
        header = QLabel("Suivez vos prêts et crédits en cours.")
        header.setStyleSheet("font-size:13px; color:#7a8494;")
        layout.addWidget(header)

        # ── Carte résumé ──
        self.summary_card = QWidget()
        self.summary_card.setStyleSheet("""
            QWidget {
                background:#26292e; border-radius:12px;
                border:1px solid #3a3f47;
            }
        """)
        summary_layout = QHBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(20, 16, 20, 16)
        summary_layout.setSpacing(30)

        # Total dette
        col1 = QVBoxLayout()
        lbl1_title = QLabel("Total dette restante")
        lbl1_title.setStyleSheet(
            "font-size:11px; color:#7a8494; font-weight:600; "
            "background:transparent; border:none;"
        )
        self.lbl_total_debt = QLabel("0,00 \u20ac")
        self.lbl_total_debt.setStyleSheet(
            "font-size:22px; font-weight:700; color:#ef4444; "
            "background:transparent; border:none;"
        )
        col1.addWidget(lbl1_title)
        col1.addWidget(self.lbl_total_debt)

        # Total mensualités
        col2 = QVBoxLayout()
        lbl2_title = QLabel("Total mensualit\u00e9s")
        lbl2_title.setStyleSheet(
            "font-size:11px; color:#7a8494; font-weight:600; "
            "background:transparent; border:none;"
        )
        self.lbl_total_monthly = QLabel("0,00 \u20ac")
        self.lbl_total_monthly.setStyleSheet(
            "font-size:22px; font-weight:700; color:#f59e0b; "
            "background:transparent; border:none;"
        )
        col2.addWidget(lbl2_title)
        col2.addWidget(self.lbl_total_monthly)

        # Date fin estimée
        col3 = QVBoxLayout()
        lbl3_title = QLabel("Fin estim\u00e9e")
        lbl3_title.setStyleSheet(
            "font-size:11px; color:#7a8494; font-weight:600; "
            "background:transparent; border:none;"
        )
        self.lbl_end_date = QLabel("\u2014")
        self.lbl_end_date.setStyleSheet(
            "font-size:22px; font-weight:700; color:#3b82f6; "
            "background:transparent; border:none;"
        )
        col3.addWidget(lbl3_title)
        col3.addWidget(self.lbl_end_date)

        summary_layout.addLayout(col1)
        summary_layout.addLayout(col2)
        summary_layout.addLayout(col3)
        summary_layout.addStretch()

        layout.addWidget(self.summary_card)

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

        form_title = QLabel("Nouveau pr\u00eat")
        form_title.setStyleSheet(
            "font-size:13px; font-weight:600; color:#c8cdd4; "
            "background:transparent; border:none;"
        )
        form_layout.addWidget(form_title)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nom du pr\u00eat (ex: Cr\u00e9dit auto, Hypoth\u00e8que...)")
        self.name_input.setMinimumHeight(34)

        self.total_input = QLineEdit()
        self.total_input.setPlaceholderText("Montant total (\u20ac)")
        self.total_input.setValidator(QDoubleValidator(0.01, 100_000_000, 2))
        self.total_input.setMinimumHeight(34)
        self.total_input.setFixedWidth(150)

        self.payment_input = QLineEdit()
        self.payment_input.setPlaceholderText("Mensualit\u00e9 (\u20ac)")
        self.payment_input.setValidator(QDoubleValidator(0.01, 100_000_000, 2))
        self.payment_input.setMinimumHeight(34)
        self.payment_input.setFixedWidth(130)

        row1.addWidget(self.name_input, 1)
        row1.addWidget(self.total_input)
        row1.addWidget(self.payment_input)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        rate_label = QLabel("Taux")
        rate_label.setStyleSheet(
            "color:#7a8494; font-size:13px; background:transparent; border:none;"
        )
        self.rate_input = QLineEdit()
        self.rate_input.setPlaceholderText("Taux (%)")
        self.rate_input.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.rate_input.setMinimumHeight(34)
        self.rate_input.setFixedWidth(90)

        start_label = QLabel("D\u00e9but")
        start_label.setStyleSheet(
            "color:#7a8494; font-size:13px; background:transparent; border:none;"
        )
        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDate(QDate.currentDate())
        self.start_date_input.setMinimumHeight(34)
        self.start_date_input.setFixedWidth(130)

        end_label = QLabel("Fin")
        end_label.setStyleSheet(
            "color:#7a8494; font-size:13px; background:transparent; border:none;"
        )
        self.end_date_input = QDateEdit()
        self.end_date_input.setCalendarPopup(True)
        self.end_date_input.setDate(QDate.currentDate().addYears(5))
        self.end_date_input.setMinimumHeight(34)
        self.end_date_input.setFixedWidth(130)

        self.add_btn = QPushButton("  Ajouter")
        self.add_btn.setIcon(get_icon("add.png"))
        self.add_btn.setMinimumHeight(34)
        self.add_btn.clicked.connect(self._add)

        row2.addWidget(rate_label)
        row2.addWidget(self.rate_input)
        row2.addSpacing(8)
        row2.addWidget(start_label)
        row2.addWidget(self.start_date_input)
        row2.addSpacing(8)
        row2.addWidget(end_label)
        row2.addWidget(self.end_date_input)
        row2.addStretch()
        row2.addWidget(self.add_btn)
        form_layout.addLayout(row2)

        layout.addWidget(form_card)

        # ── Séparateur ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            "background:#2e3238; max-height:1px; border:none; margin:4px 0;"
        )
        layout.addWidget(sep)

        # ── Tableau des prêts ──
        list_title = QLabel("Pr\u00eats en cours")
        list_title.setStyleSheet("font-size:13px; font-weight:600; color:#c8cdd4;")
        layout.addWidget(list_title)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Nom", "Montant total", "Restant", "Mensualit\u00e9",
            "Taux", "Progression", "Actions"
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setFocusPolicy(Qt.NoFocus)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 160)
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
            "Cliquez sur un pr\u00eat pour voir le tableau d\u2019amortissement d\u00e9taill\u00e9."
        )
        note.setStyleSheet("font-size:11px; color:#6b7280;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.setLayout(layout)
        self.load()

    # ------------------------------------------------------------------
    def _add(self):
        name = self.name_input.text().strip()
        if not name:
            Toast.show(self, "\u2715  Saisissez un nom", kind="error")
            self.name_input.setFocus()
            return

        try:
            total = float(self.total_input.text().replace(",", "."))
            if total <= 0:
                raise ValueError
        except ValueError:
            Toast.show(self, "\u2715  Montant total invalide", kind="error")
            self.total_input.setFocus()
            return

        try:
            payment = float(self.payment_input.text().replace(",", "."))
            if payment <= 0:
                raise ValueError
        except ValueError:
            Toast.show(self, "\u2715  Mensualit\u00e9 invalide", kind="error")
            self.payment_input.setFocus()
            return

        try:
            rate = float(self.rate_input.text().replace(",", "."))
            if rate < 0:
                raise ValueError
        except (ValueError, AttributeError):
            Toast.show(self, "\u2715  Taux invalide", kind="error")
            self.rate_input.setFocus()
            return

        start_d = self.start_date_input.date().toPython()
        end_d = self.end_date_input.date().toPython()

        if end_d <= start_d:
            Toast.show(self, "\u2715  La date de fin doit \u00eatre apr\u00e8s la date de d\u00e9but", kind="error")
            return

        add_loan(name, total, payment, rate, start_d, end_d)

        self.name_input.clear()
        self.total_input.clear()
        self.payment_input.clear()
        self.rate_input.clear()
        self.start_date_input.setDate(QDate.currentDate())
        self.end_date_input.setDate(QDate.currentDate().addYears(5))
        self.load()
        Toast.show(self, f"\u2713  Pr\u00eat \u00ab {name} \u00bb ajout\u00e9", kind="success")

    # ------------------------------------------------------------------
    def load(self):
        """Recharge le tableau et le r\u00e9sum\u00e9."""
        loans = get_loans()
        self._update_summary()

        self.table.setRowCount(len(loans))

        if not loans:
            self.table.setRowCount(1)
            empty = QTableWidgetItem(
                "Aucun pr\u00eat enregistr\u00e9 \u2014 ajoutez-en un ci-dessus."
            )
            empty.setForeground(QColor("#6b7280"))
            self.table.setItem(0, 0, empty)
            return

        for i, loan in enumerate(loans):
            # Nom
            name_item = QTableWidgetItem(f"  {loan.name}")
            name_item.setData(Qt.UserRole, loan.id)
            self.table.setItem(i, 0, name_item)

            # Montant total
            total_item = QTableWidgetItem(format_money(loan.total_amount))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, total_item)

            # Restant
            remaining_item = QTableWidgetItem(format_money(loan.remaining_amount))
            remaining_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            remaining_item.setForeground(QColor("#ef4444"))
            self.table.setItem(i, 2, remaining_item)

            # Mensualité
            payment_item = QTableWidgetItem(format_money(loan.monthly_payment))
            payment_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, payment_item)

            # Taux
            rate_item = QTableWidgetItem(f"{loan.interest_rate:.2f} %")
            rate_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.table.setItem(i, 4, rate_item)

            # Progression
            pct = 0
            if loan.total_amount > 0:
                pct = int(
                    ((loan.total_amount - loan.remaining_amount) / loan.total_amount) * 100
                )
            bar = QProgressBar()
            bar.setValue(pct)
            bar.setTextVisible(True)
            bar.setFormat(f"{pct} %")
            bar.setFixedHeight(22)
            bar.setStyleSheet("""
                QProgressBar {
                    background:#2e3238; border-radius:6px;
                    text-align:center; color:#c8cdd4;
                    font-size:11px; font-weight:600;
                    border:none;
                }
                QProgressBar::chunk {
                    background:#22c55e; border-radius:6px;
                }
            """)
            self.table.setCellWidget(i, 5, bar)

            # Actions
            actions_widget = QWidget()
            actions_widget.setStyleSheet("background:transparent; border:none;")
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            btn_schedule = QPushButton("Amortissement")
            btn_schedule.setFixedHeight(28)
            btn_schedule.setStyleSheet("""
                QPushButton {
                    background:#2e3238; color:#3b82f6;
                    border:1px solid #3a3f47; border-radius:6px;
                    font-size:11px; padding:0 10px;
                }
                QPushButton:hover { background:#3a3f47; color:#60a5fa; }
            """)
            btn_schedule.clicked.connect(
                lambda checked, lid=loan.id, lname=loan.name: self._show_schedule(lid, lname)
            )

            btn_delete = QPushButton("Supprimer")
            btn_delete.setFixedHeight(28)
            btn_delete.setStyleSheet("""
                QPushButton {
                    background:#2e2020; color:#e89090;
                    border:1px solid #503030; border-radius:6px;
                    font-size:11px; padding:0 10px;
                }
                QPushButton:hover { background:#3a2020; color:#ff6b6b; }
            """)
            btn_delete.clicked.connect(
                lambda checked, lid=loan.id, lname=loan.name: self._delete(lid, lname)
            )

            actions_layout.addWidget(btn_schedule)
            actions_layout.addWidget(btn_delete)
            actions_layout.addStretch()
            self.table.setCellWidget(i, 6, actions_widget)

    # ------------------------------------------------------------------
    def _update_summary(self):
        summary = get_loan_summary()
        self.lbl_total_debt.setText(format_money(summary["total_remaining"]))
        self.lbl_total_monthly.setText(format_money(summary["total_monthly"]))

        end = summary.get("estimated_end")
        if end:
            self.lbl_end_date.setText(end.strftime("%m/%Y"))
        else:
            self.lbl_end_date.setText("\u2014")

    # ------------------------------------------------------------------
    def _delete(self, loan_id, loan_name):
        reply = QMessageBox.question(
            self, "Supprimer",
            f"Supprimer le pr\u00eat \u00ab {loan_name} \u00bb ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_loan(loan_id)
            self.load()
            Toast.show(self, f"\u2713  Pr\u00eat supprim\u00e9", kind="success")

    # ------------------------------------------------------------------
    def _show_schedule(self, loan_id, loan_name):
        """Affiche le tableau d'amortissement dans un dialogue."""
        schedule = get_amortization_schedule(loan_id)
        if not schedule:
            Toast.show(self, "\u2715  Impossible de calculer l\u2019amortissement", kind="error")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Amortissement \u2014 {loan_name}")
        dlg.setMinimumSize(700, 500)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        title = QLabel(f"Tableau d\u2019amortissement \u2014 {loan_name}")
        title.setStyleSheet(
            "font-size:15px; font-weight:700; color:#c8cdd4; "
            "background:#292d32; border-radius:8px; padding:10px;"
        )
        vl.addWidget(title)

        # Résumé rapide
        total_interest = sum(row["interest"] for row in schedule)
        total_paid = sum(row["payment"] for row in schedule)
        info = QLabel(
            f"Dur\u00e9e : {len(schedule)} mois  \u2502  "
            f"Total rembours\u00e9 : {format_money(total_paid)}  \u2502  "
            f"Total int\u00e9r\u00eats : {format_money(total_interest)}"
        )
        info.setStyleSheet("font-size:12px; color:#7a8494;")
        vl.addWidget(info)

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Mois", "Date", "Mensualit\u00e9", "Capital", "Int\u00e9r\u00eats", "Restant"
        ])
        table.setRowCount(len(schedule))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setFocusPolicy(Qt.NoFocus)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        table.setColumnWidth(0, 60)
        table.setColumnWidth(1, 90)

        table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item {
                border-bottom:1px solid #3a3f47; padding:2px 6px;
            }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section {
                background:#26292e; border:none;
                padding:4px 6px; font-weight:600; color:#7a8494;
                font-size:11px;
            }
        """)

        for i, row in enumerate(schedule):
            num_item = QTableWidgetItem(str(row["month_num"]))
            num_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            table.setItem(i, 0, num_item)

            date_item = QTableWidgetItem(row["date"])
            date_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            table.setItem(i, 1, date_item)

            pay_item = QTableWidgetItem(format_money(row["payment"]))
            pay_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 2, pay_item)

            princ_item = QTableWidgetItem(format_money(row["principal"]))
            princ_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            princ_item.setForeground(QColor("#22c55e"))
            table.setItem(i, 3, princ_item)

            int_item = QTableWidgetItem(format_money(row["interest"]))
            int_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            int_item.setForeground(QColor("#f59e0b"))
            table.setItem(i, 4, int_item)

            rem_item = QTableWidgetItem(format_money(row["remaining"]))
            rem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 5, rem_item)

        vl.addWidget(table, 1)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)

        dlg.exec()
