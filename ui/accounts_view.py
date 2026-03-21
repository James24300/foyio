"""
Vue de gestion des comptes bancaires.
Permet d'ajouter, renommer, supprimer des comptes et voir leur solde global.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QScrollArea, QMessageBox,
    QDialog, QFormLayout, QDialogButtonBox, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon
import os

from utils.icons import get_icon
from ui.spellcheck_lineedit import SpellCheckLineEdit
from utils.formatters import format_money
import account_state

from services.account_service import (
    get_accounts, add_account, rename_account, delete_account,
    get_account_balance, get_account_tx_count, update_account_url
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACCOUNT_TYPES = [
    ("checking", "Compte courant"),
    ("joint",    "Compte joint"),
    ("savings",  "Livret / Épargne"),
    ("other",    "Autre"),
]

ACCOUNT_COLORS = [
    ("#7a8494", "Bleu"),
    ("#22c55e", "Vert"),
    ("#8b5cf6", "Violet"),
    ("#f59e0b", "Orange"),
    ("#ef4444", "Rouge"),
    ("#06b6d4", "Cyan"),
    ("#ec4899", "Rose"),
    ("#64748b", "Gris"),
]


class AccountsView(QWidget):

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Titre ──
        title = QLabel("Gestion des comptes")
        title.setStyleSheet("font-size:15px; font-weight:600; color:#c8cdd4;")
        layout.addWidget(title)

        info = QLabel("Gérez vos comptes bancaires. Chaque compte a ses propres transactions, budgets et récurrentes.")
        info.setStyleSheet("font-size:12px; color:#6b7280;")
        info.setWordWrap(True)
        layout.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none; margin:4px 0;")
        layout.addWidget(sep)

        # ── Formulaire ajout ──
        form_title = QLabel("Nouveau compte")
        form_title.setStyleSheet("font-size:13px; font-weight:600; color:#7a8494;")
        layout.addWidget(form_title)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._name_input = SpellCheckLineEdit()
        self._name_input.setPlaceholderText("Nom du compte (ex: Compte courant, Livret A...)")
        self._name_input.setMinimumHeight(36)
        row1.addWidget(self._name_input, 2)

        self._type_combo = QComboBox()
        self._type_combo.setMinimumHeight(36)
        self._type_combo.setMinimumWidth(160)
        for code, label in ACCOUNT_TYPES:
            self._type_combo.addItem(label, code)
        row1.addWidget(self._type_combo)

        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        # Sélecteur couleur
        color_label = QLabel("Couleur :")
        color_label.setStyleSheet("color:#7a8494; font-size:12px;")
        row2.addWidget(color_label)

        self._color_combo = QComboBox()
        self._color_combo.setMinimumHeight(36)
        self._color_combo.setMinimumWidth(120)
        for hex_color, name in ACCOUNT_COLORS:
            self._color_combo.addItem(name, hex_color)
        row2.addWidget(self._color_combo)

        row2.addStretch()

        btn_add = QPushButton("  Ajouter le compte")
        btn_add.setIcon(get_icon("add.png"))
        btn_add.setMinimumHeight(36)
        btn_add.clicked.connect(self._add)
        row2.addWidget(btn_add)

        btn_pwd = QPushButton("Mot de passe")
        btn_pwd.setMinimumHeight(36)
        btn_pwd.setStyleSheet(
            "background:#2e3238; color:#848c94; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; padding:0 10px;"
        )
        btn_pwd.clicked.connect(self._change_password)
        row2.addWidget(btn_pwd)

        layout.addLayout(row2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background:#2e3238; max-height:1px; border:none; margin:4px 0;")
        layout.addWidget(sep2)

        # ── Liste des comptes ──
        list_title = QLabel("Comptes existants")
        list_title.setStyleSheet("font-size:13px; font-weight:600; color:#7a8494;")
        layout.addWidget(list_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")

        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background:transparent;")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setSpacing(10)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_widget)
        layout.addWidget(scroll, 1)


        self.load()

    # ------------------------------------------------------------------
    def load(self):
        """Reconstruit la liste des cartes de comptes."""
        # Vider
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accounts = get_accounts()
        active_id = account_state.get_id()

        for acc in accounts:
            income, expense, balance = get_account_balance(acc.id)
            tx_count = get_account_tx_count(acc.id)
            is_active = (acc.id == active_id)
            card = self._make_card(acc, balance, tx_count, is_active)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        if not accounts:
            empty = QLabel("Aucun compte. Ajoutez-en un ci-dessus.")
            empty.setStyleSheet("color:#4b5563; font-size:13px; padding:20px;")
            empty.setAlignment(Qt.AlignCenter)
            self._cards_layout.insertWidget(0, empty)

    def _make_card(self, acc, balance, tx_count, is_active):
        """Crée une carte pour un compte."""
        card = QWidget()
        border_color = acc.color if is_active else "#3a3f47"
        card.setStyleSheet(f"""
            QWidget {{
                background:#26292e;
                border-radius:10px;
                border:2px solid {border_color};
            }}
        """)

        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        # Pastille couleur
        dot = QLabel()
        dot.setFixedSize(14, 14)
        dot.setStyleSheet(f"background:{acc.color}; border-radius:7px; border:none;")
        row.addWidget(dot)

        # Infos
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name_row = QHBoxLayout()
        name_lbl = QLabel(acc.name)
        name_lbl.setStyleSheet("font-size:14px; font-weight:600; color:#c8cdd4; border:none;")
        name_row.addWidget(name_lbl)

        if is_active:
            badge = QLabel("  actif  ")
            badge.setStyleSheet(
                "background:#3e4550; color:#b8c0c8; font-size:10px; "
                "border-radius:4px; padding:1px 6px; border:1px solid #6a7484;"
            )
            name_row.addWidget(badge)
        name_row.addStretch()
        info_col.addLayout(name_row)

        type_label = dict(ACCOUNT_TYPES).get(acc.type, acc.type)
        sub_lbl = QLabel(f"{type_label}  •  {tx_count} transaction(s)")
        sub_lbl.setStyleSheet("font-size:11px; color:#6b7280; border:none;")
        info_col.addWidget(sub_lbl)

        row.addLayout(info_col)
        row.addStretch()

        # Solde
        sign = "+" if balance >= 0 else ""
        color = "#22c55e" if balance >= 0 else "#ef4444"
        bal_lbl = QLabel(f"{sign}{format_money(balance)}")
        bal_lbl.setStyleSheet(
            f"font-size:15px; font-weight:700; color:{color}; border:none;"
        )
        bal_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(bal_lbl)

        # Boutons
        btn_select = QPushButton("Sélectionner")
        btn_select.setMinimumHeight(34)
        btn_select.setFixedWidth(110)
        btn_select.setStyleSheet(
            "background:#3e4550; color:#b8c0c8; border-radius:6px; "
            "font-size:12px; font-weight:600; border:none; padding:0 12px;"
        )
        btn_select.setEnabled(not is_active)
        btn_select.clicked.connect(lambda _, a=acc: self._select(a))

        btn_rename = QPushButton("Renommer")
        btn_rename.setMinimumHeight(34)
        btn_rename.setFixedWidth(110)
        btn_rename.setToolTip("Renommer")
        btn_rename.setStyleSheet(
            "background:#3a3f47; color:#a0a8b0; border-radius:6px; "
            "font-size:12px; font-weight:600; border:none; padding:0 12px;"
        )
        btn_rename.clicked.connect(lambda _, a=acc: self._rename(a))

        btn_delete = QPushButton("Supprimer")
        btn_delete.setMinimumHeight(34)
        btn_delete.setFixedWidth(110)
        btn_delete.setToolTip("Supprimer ce compte")
        btn_delete.setStyleSheet(
            "background:#2e1f1f; color:#f4a0a0; border-radius:6px; "
            "font-size:12px; font-weight:600; border:none; padding:0 12px;"
        )
        btn_delete.setEnabled(not is_active)
        if is_active:
            btn_delete.setToolTip("Selectionnez un autre compte avant de supprimer celui-ci")
        else:
            btn_delete.setToolTip("Supprimer ce compte")
        btn_delete.clicked.connect(lambda _, aid=acc.id, aname=acc.name, n=tx_count: self._delete_by_id(aid, aname, n))

        # Bouton URL banque
        has_url = bool(getattr(acc, 'url', None))
        acc_url = getattr(acc, 'url', None) or ''
        btn_url = QPushButton("Site banque")
        btn_url.setMinimumHeight(32)
        btn_url.setToolTip(acc_url if has_url else "Définir l'URL de l'espace client")
        btn_url.setStyleSheet(
            f"background:#{'2e3238' if has_url else '1e2226'}; "
            f"color:#{'a0a8b0' if has_url else '505870'}; "
            "border-radius:6px; font-size:11px; border:none; padding:0 8px;"
        )
        btn_url.clicked.connect(lambda _, a=acc: self._edit_url(a))

        btn_chart = QPushButton("Graphique")
        btn_chart.setMinimumHeight(34)
        btn_chart.setFixedWidth(110)
        btn_chart.setStyleSheet(
            "background:#1a2030; color:#7aaee8; border-radius:6px; "
            "font-size:12px; font-weight:600; border:none; padding:0 12px;"
        )
        btn_chart.clicked.connect(lambda _, aid=acc.id, aname=acc.name: self._show_account_chart_by_id(aid, aname))

        row.addWidget(btn_url)
        row.addWidget(btn_select)
        row.addWidget(btn_rename)
        row.addWidget(btn_chart)
        row.addWidget(btn_delete)

        return card

    # ------------------------------------------------------------------
    def _add(self):
        name = self._name_input.text().strip()
        if not name:
            from ui.toast import Toast
            Toast.show(self, "✕  Saisissez un nom de compte", kind="error")
            self._name_input.setFocus()
            return

        # Vérifier doublon
        existing = [a.name.lower() for a in get_accounts()]
        if name.lower() in existing:
            from ui.toast import Toast
            Toast.show(self, "✕  Un compte avec ce nom existe déjà", kind="error")
            return

        atype = self._type_combo.currentData()
        color = self._color_combo.currentData()

        # Icône selon le type
        icon = {"checking": "bank.png", "joint": "bank.png",
                "savings": "money.png", "other": "wallet.png"}.get(atype, "bank.png")

        add_account(name, atype, color, icon)

        self._name_input.clear()
        self._type_combo.setCurrentIndex(0)
        self.load()
        self._reload_selector()

        from ui.toast import Toast
        Toast.show(self, f"✓  Compte '{name}' créé", kind="success")

    def _show_account_chart_by_id(self, acc_id: int, acc_name: str):
        """Wrapper qui recharge l'objet account depuis la DB."""
        from services.account_service import get_accounts
        accs = [a for a in get_accounts() if a.id == acc_id]
        if accs:
            self._show_account_chart(accs[0])

    def _delete_by_id(self, acc_id: int, acc_name: str, tx_count: int):
        """Wrapper delete avec id."""
        from services.account_service import get_accounts
        accs = [a for a in get_accounts() if a.id == acc_id]
        if accs:
            self._delete(accs[0], tx_count)

    def _show_account_chart(self, acc):
        """Affiche le graphique d'évolution du solde pour un compte."""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton)
        from PySide6.QtCharts import (QChart, QChartView, QLineSeries,
            QAreaSeries, QValueAxis, QBarCategoryAxis)
        from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
        from PySide6.QtCore import QDateTime, QDate, QTime, Qt, QMargins
        from db import Session
        from models import Transaction
        from sqlalchemy import func

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Évolution du solde — {acc.name}")
        dlg.setMinimumSize(700, 420)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(16, 16, 16, 16)

        # Récupérer toutes les transactions du compte triées par date
        with Session() as session:
            txns = session.query(Transaction)                .filter(Transaction.account_id == acc.id)                .order_by(Transaction.date.asc()).all()
            session.expunge_all()

        if not txns:
            from PySide6.QtWidgets import QLabel
            lbl = QLabel("Aucune transaction pour ce compte.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#7a8494; font-size:13px;")
            vl.addWidget(lbl)
        else:
            # Construire points (label, balance)
            balance = 0.0
            points = []
            for t in txns:
                balance += t.amount if t.type == 'income' else -t.amount
                lbl = f"{t.date.day:02d}/{t.date.month:02d}"
                points.append((lbl, round(balance, 2)))

            series = QLineSeries()
            series.setColor(QColor("#22c55e"))
            pen = QPen(QColor("#22c55e")); pen.setWidth(2)
            series.setPen(pen)
            for i, (_, bal) in enumerate(points):
                series.append(i, bal)

            lower = QLineSeries()
            base = min(0, min(p[1] for p in points))
            for i in range(len(points)):
                lower.append(i, base)
            area = QAreaSeries(series, lower)
            area.setColor(QColor("#22c55e33"))
            area.setBorderColor(QColor("#22c55e"))

            chart = QChart()
            chart.addSeries(area)
            chart.setBackgroundBrush(QColor("#1e2124"))
            chart.setTitle(f"Solde - {acc.name}")
            chart.setTitleFont(QFont("", 12, QFont.Bold))
            chart.setTitleBrush(QColor("#c8cdd4"))
            chart.legend().setVisible(False)
            chart.setMargins(QMargins(8, 4, 8, 4))
            chart.setAnimationOptions(QChart.SeriesAnimations)

            n = len(points)
            step = max(1, n // 6)
            cats = [points[i][0] if i % step == 0 else '' for i in range(n)]
            axis_x = QBarCategoryAxis()
            axis_x.append(cats)
            axis_x.setLabelsColor(QColor("#848c94"))
            axis_x.setLabelsFont(QFont("", 8))
            axis_x.setGridLineColor(QColor("#2e3238"))
            chart.addAxis(axis_x, Qt.AlignBottom)
            area.attachAxis(axis_x)

            vals = [p[1] for p in points]
            min_v = min(vals); max_v = max(vals)
            margin = max(abs(max_v - min_v) * 0.1, 100)
            axis_y = QValueAxis()
            axis_y.setRange(min_v - margin, max_v + margin)
            axis_y.setLabelsColor(QColor("#848c94"))
            axis_y.setLabelsFont(QFont("", 8))
            axis_y.setGridLineColor(QColor("#2e3238"))
            axis_y.setLabelFormat("%d")
            axis_y.setTickCount(5)
            chart.addAxis(axis_y, Qt.AlignLeft)
            area.attachAxis(axis_y)

            view = QChartView(chart)
            view.setRenderHint(QPainter.Antialiasing)
            vl.addWidget(view, 1)

        btn = QPushButton("Fermer")
        btn.setMinimumHeight(34)
        btn.clicked.connect(dlg.accept)
        vl.addWidget(btn)
        dlg.exec()

    def _select(self, acc):
        account_state.set_account(acc.id, acc.name)
        self.load()
        self._reload_selector()
        if hasattr(self.main_window, "refresh_all"):
            self.main_window.refresh_all()
        from ui.toast import Toast
        Toast.show(self, f"✓  Compte '{acc.name}' sélectionné", kind="info")

    def _rename(self, acc):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Renommer « {acc.name} »")
        dlg.setMinimumWidth(340)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(12)

        inp = QLineEdit(acc.name)
        inp.setMinimumHeight(34)
        inp.selectAll()
        form.addRow("Nouveau nom :", inp)

        btns = QDialogButtonBox()
        btns.addButton("OK",      QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler", QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        new_name = inp.text().strip()
        if not new_name or new_name == acc.name:
            return

        rename_account(acc.id, new_name)

        # Mettre à jour account_state si c'est le compte actif
        if acc.id == account_state.get_id():
            account_state.set_account(acc.id, new_name)

        self.load()
        self._reload_selector()
        from ui.toast import Toast
        Toast.show(self, f"✓  Renommé en '{new_name}'", kind="success")

    def _delete(self, acc, tx_count):
        msg = QMessageBox(self)
        msg.setWindowTitle("Supprimer le compte")
        msg.setText(f"Supprimer le compte « {acc.name} » ?")
        if tx_count > 0:
            msg.setInformativeText(
                f"Ce compte contient {tx_count} transaction(s).\n"
                "Elles ne seront pas supprimées mais deviendront orphelines."
            )
        btn_yes = msg.addButton("Supprimer", QMessageBox.DestructiveRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()

        if msg.clickedButton() != btn_yes:
            return

        delete_account(acc.id)

        # Si c'était le compte actif, basculer sur le premier disponible
        if acc.id == account_state.get_id():
            remaining = get_accounts()
            if remaining:
                account_state.set_account(remaining[0].id, remaining[0].name)

        self.load()
        self._reload_selector()
        if hasattr(self.main_window, "refresh_all"):
            self.main_window.refresh_all()
        from ui.toast import Toast
        Toast.show(self, f"Compte '{acc.name}' supprimé", kind="warning")

    def _edit_url(self, acc):
        """Dialogue pour saisir/modifier l'URL de l'espace client bancaire."""
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QPushButton
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Espace client — {acc.name}")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(12)

        from ui.spellcheck_lineedit import SpellCheckLineEdit
        url_input = SpellCheckLineEdit()
        url_input.set_spell_enabled(False)  # pas de correction sur une URL
        url_input.setPlaceholderText("https://particuliers.sg.fr")
        url_input.setMinimumHeight(34)
        if getattr(acc, 'url', None):
            url_input.setText(acc.url)
        form.addRow("URL :", url_input)

        # Bouton tester l'URL
        btn_test = QPushButton("Ouvrir dans le navigateur →")
        btn_test.setStyleSheet("background:transparent; color:#848c94; border:none; font-size:12px; text-align:left;")
        btn_test.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url_input.text())) if url_input.text() else None)
        form.addRow("", btn_test)

        btns = QDialogButtonBox()
        btns.addButton("Enregistrer", QDialogButtonBox.AcceptRole)
        btns.addButton("Annuler",      QDialogButtonBox.RejectRole)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        new_url = url_input.text().strip()
        # Ajouter https:// si absent
        if new_url and not new_url.startswith("http"):
            new_url = "https://" + new_url

        update_account_url(acc.id, new_url)
        self.load()

        from ui.toast import Toast
        if new_url:
            Toast.show(self, f"✓  URL enregistrée pour {acc.name}", kind="success")
        else:
            Toast.show(self, f"URL supprimée", kind="info")

    def _change_password(self):
        from ui.password_dialog import ChangePasswordDialog
        from ui.toast import Toast
        dlg = ChangePasswordDialog(self)
        if dlg.exec() == ChangePasswordDialog.Accepted:
            Toast.show(self, "Mot de passe modifie", kind="success")

    def _reload_selector(self):
        """Met à jour le combo de sélection de compte dans la barre de titre."""
        if hasattr(self.main_window, "_reload_accounts"):
            self.main_window._reload_accounts()
