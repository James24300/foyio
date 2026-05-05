# No Qt parent needed — mixed into CryptoView which is a QWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QSpinBox,
    QComboBox, QCheckBox, QMessageBox,
)
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QAreaSeries
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from services.crypto_service import (
    get_dca_plans, add_dca_plan, delete_dca_plan, toggle_dca_plan,
    get_due_dca_plans, execute_dca, update_dca_plan, get_holdings,
    simulate_dca,
)
from ui.toast import Toast
from ui.crypto_threads import _pixmap_cache


class _CryptoDcaMixin:

    # ── Onglet DCA ────────────────────────────────────────────────────────────
    def _build_dca_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        # En-tête explication
        info = QLabel(
            "Le DCA (Dollar Cost Averaging) consiste à investir un montant fixe "
            "régulièrement, quel que soit le prix. Foyio vous rappelle chaque mois "
            "et vous permet d'exécuter l'achat en un clic."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size:11px; color:#7a8494; padding:4px 0;")
        vl.addWidget(info)

        # Formulaire ajout plan
        form_card = QWidget()
        form_card.setStyleSheet(
            "background:#26292e; border-radius:10px; border:1px solid #3a3f47;"
        )
        form_vl = QVBoxLayout(form_card)
        form_vl.setContentsMargins(14, 12, 14, 12)
        form_vl.setSpacing(10)

        title_lbl = QLabel("Nouveau plan DCA")
        title_lbl.setStyleSheet(
            "font-size:13px; font-weight:700; color:#c8cdd4; background:transparent; border:none;"
        )
        form_vl.addWidget(title_lbl)

        row = QHBoxLayout()
        row.setSpacing(10)

        # Crypto
        col_crypto = QVBoxLayout()
        lbl_crypto = QLabel("Crypto")
        lbl_crypto.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_holding_combo = QComboBox()
        self._dca_holding_combo.setMinimumHeight(34)
        self._dca_holding_combo.setMinimumWidth(160)
        col_crypto.addWidget(lbl_crypto)
        col_crypto.addWidget(self._dca_holding_combo)
        row.addLayout(col_crypto)

        # Montant €
        col_amt = QVBoxLayout()
        lbl_amt = QLabel("Montant (€)")
        lbl_amt.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_amount = QDoubleSpinBox()
        self._dca_amount.setRange(1, 99_999)
        self._dca_amount.setDecimals(2)
        self._dca_amount.setSuffix(" €")
        self._dca_amount.setValue(50)
        self._dca_amount.setMinimumHeight(34)
        self._dca_amount.setMinimumWidth(120)
        col_amt.addWidget(lbl_amt)
        col_amt.addWidget(self._dca_amount)
        row.addLayout(col_amt)

        # Jour du mois
        col_day = QVBoxLayout()
        lbl_day = QLabel("Jour du mois")
        lbl_day.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_day = QSpinBox()
        self._dca_day.setRange(1, 28)
        self._dca_day.setValue(1)
        self._dca_day.setSuffix("e du mois")
        self._dca_day.setMinimumHeight(34)
        self._dca_day.setMinimumWidth(120)
        col_day.addWidget(lbl_day)
        col_day.addWidget(self._dca_day)
        row.addLayout(col_day)

        # Note
        col_note = QVBoxLayout()
        lbl_note = QLabel("Note (optionnelle)")
        lbl_note.setStyleSheet("font-size:11px; color:#7a8494; background:transparent; border:none;")
        self._dca_note = QLineEdit()
        self._dca_note.setPlaceholderText("Ex : Épargne long terme")
        self._dca_note.setMinimumHeight(34)
        col_note.addWidget(lbl_note)
        col_note.addWidget(self._dca_note)
        row.addLayout(col_note, 1)

        # Bouton
        btn_add_dca = QPushButton("Créer le plan")
        btn_add_dca.setMinimumHeight(34)
        btn_add_dca.setStyleSheet(
            "background:#22c55e; color:#000; border:none; border-radius:8px;"
            "font-weight:700; padding:0 14px; text-align:center;"
        )
        btn_add_dca.clicked.connect(self._add_dca_plan)
        row.addWidget(btn_add_dca)

        form_vl.addLayout(row)
        vl.addWidget(form_card)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
        vl.addWidget(sep)

        # Tableau des plans existants
        self._dca_table = QTableWidget(0, 7)
        self._dca_table.setHorizontalHeaderLabels([
            "Crypto", "Montant", "Jour", "Dernier achat", "Prochain", "Statut", "Actions"
        ])
        self._dca_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._dca_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._dca_table.setShowGrid(False)
        self._dca_table.verticalHeader().setVisible(False)
        self._dca_table.verticalHeader().setDefaultSectionSize(48)
        hdr = self._dca_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, w_ in [(1, 110), (2, 80), (3, 120), (4, 100), (5, 90), (6, 340)]:
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._dca_table.setColumnWidth(col, w_)
        self._dca_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._dca_table, 1)
        return w

    # ── Logique DCA ───────────────────────────────────────────────────────────
    def _load_dca(self):
        """Charge les plans DCA et les affiche dans le tableau."""
        from datetime import date
        # Mise à jour du combo de création
        self._dca_holding_combo.clear()
        for h in self._holdings:
            self._dca_holding_combo.addItem(f"{h.name} ({h.symbol.upper()})", h.id)

        plans = get_dca_plans()
        holdings_map = {h.id: h for h in self._holdings}

        self._dca_table.setRowCount(0)
        today = date.today()

        for plan in plans:
            holding = holdings_map.get(plan.holding_id)
            if not holding:
                continue

            row = self._dca_table.rowCount()
            self._dca_table.insertRow(row)

            name_txt = f"{holding.name} ({holding.symbol.upper()})"
            self._dca_table.setItem(row, 0, QTableWidgetItem(name_txt))

            amt_item = QTableWidgetItem(f"{plan.amount_eur:.2f} €")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._dca_table.setItem(row, 1, amt_item)

            day_item = QTableWidgetItem(f"{plan.day_of_month}")
            day_item.setTextAlignment(Qt.AlignCenter)
            self._dca_table.setItem(row, 2, day_item)

            last_txt = plan.last_executed.strftime("%d/%m/%Y") if plan.last_executed else "Jamais"
            self._dca_table.setItem(row, 3, QTableWidgetItem(last_txt))

            # Prochain achat
            from datetime import date as _d
            import calendar
            if today.day <= plan.day_of_month:
                next_month = today.month
                next_year  = today.year
            else:
                if today.month == 12:
                    next_month = 1
                    next_year  = today.year + 1
                else:
                    next_month = today.month + 1
                    next_year  = today.year
            max_day  = calendar.monthrange(next_year, next_month)[1]
            next_day = min(plan.day_of_month, max_day)
            next_date = _d(next_year, next_month, next_day)
            is_due = (next_date == today)
            next_txt = "Aujourd'hui !" if is_due else next_date.strftime("%d/%m/%Y")
            next_item = QTableWidgetItem(next_txt)
            if is_due:
                next_item.setForeground(QColor("#22c55e"))
            self._dca_table.setItem(row, 4, next_item)

            # Statut
            status_txt = "Actif" if plan.active else "Inactif"
            status_item = QTableWidgetItem(status_txt)
            status_item.setForeground(QColor("#22c55e") if plan.active else QColor("#ef4444"))
            status_item.setTextAlignment(Qt.AlignCenter)
            self._dca_table.setItem(row, 5, status_item)

            # Actions
            cell = QWidget()
            cell.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cell)
            hl.setContentsMargins(4, 4, 4, 4)
            hl.setSpacing(4)

            _btn_s = "border:none; border-radius:6px; font-size:11px; font-weight:600; text-align:center; padding:0 8px;"

            btn_edit = QPushButton("Modifier")
            btn_edit.setFixedHeight(28)
            btn_edit.setFixedWidth(70)
            btn_edit.setStyleSheet(f"background:#6366f1; color:#fff; {_btn_s}")
            btn_edit.clicked.connect(lambda checked, pid=plan.id: self._edit_dca(pid))

            btn_exec = QPushButton("Exécuter")
            btn_exec.setFixedHeight(28)
            btn_exec.setFixedWidth(70)
            btn_exec.setEnabled(plan.active)
            btn_exec.setStyleSheet(f"background:#3b82f6; color:#fff; {_btn_s}")
            btn_exec.clicked.connect(lambda checked, pid=plan.id: self._execute_dca(pid))

            btn_toggle = QPushButton("Désactiver" if plan.active else "Activer")
            btn_toggle.setFixedHeight(28)
            btn_toggle.setFixedWidth(80)
            btn_toggle.setStyleSheet(f"background:#f59e0b; color:#000; {_btn_s}")
            btn_toggle.clicked.connect(lambda checked, pid=plan.id: self._toggle_dca(pid))

            btn_del = QPushButton("Suppr.")
            btn_del.setFixedHeight(28)
            btn_del.setFixedWidth(56)
            btn_del.setStyleSheet(f"background:#ef4444; color:#fff; {_btn_s}")
            btn_del.clicked.connect(lambda checked, pid=plan.id: self._delete_dca(pid))

            hl.addWidget(btn_edit)
            hl.addWidget(btn_exec)
            hl.addWidget(btn_toggle)
            hl.addWidget(btn_del)
            hl.addStretch()
            self._dca_table.setCellWidget(row, 6, cell)

    def _add_dca_plan(self):
        holding_id = self._dca_holding_combo.currentData()
        if holding_id is None:
            Toast.show(self, "Aucune crypto sélectionnée.", "warning")
            return
        amount = self._dca_amount.value()
        day    = self._dca_day.value()
        note   = self._dca_note.text().strip()
        add_dca_plan(holding_id, amount, day, note)
        self._dca_note.clear()
        self._load_dca()
        Toast.show(self, "Plan DCA créé.", "success")

    def _execute_dca(self, plan_id: int):
        dlg = QDialog(self)
        dlg.setWindowTitle("Exécuter le DCA")
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet("background:#1e2023; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setSpacing(14)

        lbl = QLabel("Voulez-vous exécuter ce plan DCA maintenant ?\nL'achat sera enregistré au prix actuel du marché.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#c8cdd4; font-size:12px;")
        vl.addWidget(lbl)

        chk_link = QCheckBox("Lier à une transaction financière")
        chk_link.setStyleSheet("color:#a0a8b4; font-size:11px;")
        vl.addWidget(chk_link)

        row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet(
            "background:#2e3238; color:#7a8494; border:none; border-radius:8px; padding:0 14px;"
        )
        btn_cancel.clicked.connect(dlg.reject)

        btn_ok = QPushButton("Acheter maintenant")
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet(
            "background:#22c55e; color:#000; border:none; border-radius:8px;"
            "font-weight:700; padding:0 14px; text-align:center;"
        )
        btn_ok.clicked.connect(dlg.accept)

        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        vl.addLayout(row)

        if dlg.exec() != QDialog.Accepted:
            return

        result = execute_dca(plan_id, link_financial=chk_link.isChecked())
        if result is None:
            Toast.show(self, "Impossible de récupérer le prix actuel.", "error")
            return

        Toast.show(
            self,
            f"Acheté {result['qty']:.6f} {result['symbol'].upper()} "
            f"à {result['price']:.2f} € — Total : {result['total']:.2f} €",
            "success"
        )
        self._holdings = get_holdings()
        self._load_portfolio()
        self._load_transactions()
        self._load_dca()

    def _toggle_dca(self, plan_id: int):
        new_state = toggle_dca_plan(plan_id)
        self._load_dca()
        Toast.show(self, f"Plan {'activé' if new_state else 'désactivé'}.", "success")

    def _edit_dca(self, plan_id: int):
        from services.crypto_service import get_dca_plans
        plans = get_dca_plans()
        plan = next((p for p in plans if p.id == plan_id), None)
        if not plan:
            return

        holding = next((h for h in self._holdings if h.id == plan.holding_id), None)
        holding_name = f"{holding.name} ({holding.symbol.upper()})" if holding else f"ID {plan.holding_id}"

        dlg = QDialog(self)
        dlg.setWindowTitle("Modifier le plan DCA")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background:#1e2023; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        title = QLabel(f"Modifier — {holding_name}")
        title.setStyleSheet("font-size:13px; font-weight:700; color:#c8cdd4;")
        vl.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px; color:#7a8494;")
            return l

        amt_spin = QDoubleSpinBox()
        amt_spin.setRange(1, 99_999)
        amt_spin.setDecimals(2)
        amt_spin.setSuffix(" €")
        amt_spin.setValue(plan.amount_eur)
        amt_spin.setMinimumHeight(34)
        form.addRow(_lbl("Montant :"), amt_spin)

        day_spin = QSpinBox()
        day_spin.setRange(1, 28)
        day_spin.setSuffix("e du mois")
        day_spin.setValue(plan.day_of_month)
        day_spin.setMinimumHeight(34)
        form.addRow(_lbl("Jour du mois :"), day_spin)

        note_edit = QLineEdit()
        note_edit.setText(plan.note or "")
        note_edit.setPlaceholderText("Note optionnelle")
        note_edit.setMinimumHeight(34)
        form.addRow(_lbl("Note :"), note_edit)

        vl.addLayout(form)

        row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet("background:#2e3238; color:#7a8494; border:none; border-radius:8px; padding:0 14px;")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Enregistrer")
        btn_ok.setFixedHeight(34)
        btn_ok.setStyleSheet("background:#6366f1; color:#fff; border:none; border-radius:8px; font-weight:700; padding:0 14px; text-align:center;")
        btn_ok.clicked.connect(dlg.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        vl.addLayout(row)

        if dlg.exec() == QDialog.Accepted:
            update_dca_plan(plan_id, amt_spin.value(), day_spin.value(), note_edit.text().strip())
            self._load_dca()
            Toast.show(self, "Plan DCA modifié.", "success")

    def _delete_dca(self, plan_id: int):
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer le plan DCA")
        msg.setText("Voulez-vous vraiment supprimer ce plan DCA ?")
        btn_oui = msg.addButton("Oui", QMessageBox.DestructiveRole)
        msg.addButton("Non", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_oui:
            delete_dca_plan(plan_id)
            self._load_dca()
            Toast.show(self, "Plan supprimé.", "success")

    def _check_due_dca(self):
        """Vérifie les plans DCA dus aujourd'hui et envoie une notification systray."""
        due = get_due_dca_plans()
        if not due:
            return
        holdings_map = {h.id: h for h in self._holdings}
        for plan in due:
            h = holdings_map.get(plan.holding_id)
            if not h:
                continue
            msg = (
                f"DCA {h.name} ({h.symbol.upper()}) : "
                f"{plan.amount_eur:.0f} € prévu aujourd'hui !"
            )
            self._show_tray_msg("DCA récurrent", msg)

    def _refresh_dca_logos(self):
        """Met à jour les logos dans le tableau DCA."""
        from PySide6.QtGui import QPixmap
        holdings_map = {h.id: h for h in self._holdings}
        for row in range(self._dca_table.rowCount()):
            item = self._dca_table.item(row, 0)
            if not item:
                continue
            # Chercher le holding correspondant
            for h in self._holdings:
                if f"{h.name} ({h.symbol.upper()})" == item.text():
                    px = _pixmap_cache.get(h.coingecko_id)
                    if px:
                        cell = QWidget()
                        cell.setStyleSheet("background:transparent;")
                        hl = QHBoxLayout(cell)
                        hl.setContentsMargins(4, 2, 4, 2)
                        hl.setSpacing(6)
                        logo = QLabel()
                        logo.setPixmap(px)
                        logo.setStyleSheet("background:transparent; border:none;")
                        name_lbl = QLabel(item.text())
                        name_lbl.setStyleSheet("background:transparent; border:none; color:#c8cdd4; font-size:12px;")
                        hl.addWidget(logo)
                        hl.addWidget(name_lbl)
                        hl.addStretch()
                        self._dca_table.setCellWidget(row, 0, cell)
                        # Effacer le texte de l'item pour éviter le chevauchement
                        item.setText("")
                    break

    def _run_dca(self):
        monthly = self._dca_monthly.value()
        months  = self._dca_months.value()
        rate    = self._dca_rate.value()
        res     = simulate_dca(monthly, months, rate)

        self._dca_result.setText(
            f"Valeur finale : {res['final_value']:,.2f} €  |  "
            f"Investi : {res['total_invested']:,.2f} €  |  "
            f"Gain : {'+' if res['total_gain']>=0 else ''}{res['total_gain']:,.2f} € "
            f"({'+' if res['gain_pct']>=0 else ''}{res['gain_pct']:.1f}%)"
        )
        self._dca_result.setVisible(True)

        evol = res["evolution"]
        self._dca_upper = QLineSeries()
        self._dca_invest = QLineSeries()
        self._dca_upper.setColor(QColor("#22c55e"))
        self._dca_invest.setColor(QColor("#3b82f6"))
        for e in evol:
            self._dca_upper.append(e["month"], e["value"])
            self._dca_invest.append(e["month"], e["invested"])
        area = QAreaSeries(self._dca_upper)
        area.setColor(QColor(34, 197, 94, 30))
        area.setBorderColor(QColor("#22c55e"))
        chart = QChart()
        chart.addSeries(area)
        chart.addSeries(self._dca_invest)
        chart.setBackgroundBrush(QColor("#26292e"))
        chart.setBackgroundRoundness(0)
        chart.legend().setVisible(False)
        chart.createDefaultAxes()
        self._dca_chart.setChart(chart)
        self._dca_chart.setVisible(True)
