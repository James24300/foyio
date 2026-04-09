"""
Vue Boîte à idées — Foyio
Permet aux utilisateurs de soumettre des suggestions, et aux admins de les consulter.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QLineEdit as QLE, QFrame, QScrollArea,
    QDialog, QComboBox, QSizePolicy, QDialogButtonBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from services.ideas_service import submit_idea, get_ideas, mark_read, delete_idea, get_unread_count, set_status
from services.settings_service import get as get_setting
from ui.toast import Toast


_STYLE_BTN_PRIMARY = """
    QPushButton {
        background: #3b82f6;
        color: #ffffff;
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton:hover  { background: #2563eb; }
    QPushButton:pressed { background: #1d4ed8; }
    QPushButton:disabled { background: #2e3a4a; color: #5a6472; }
"""

_STYLE_BTN_SECONDARY = """
    QPushButton {
        background: #292d32;
        color: #c8cdd4;
        border: 1px solid #3d4248;
        border-radius: 8px;
        padding: 8px 18px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton:hover  { background: #2e3238; color: #e0e4ea; }
    QPushButton:pressed { background: #26292e; }
"""

_STYLE_BTN_DANGER = """
    QPushButton {
        background: #3b1f1f;
        color: #fca5a5;
        border: 1px solid #7f1d1d;
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover  { background: #7f1d1d; color: #fecaca; }
    QPushButton:pressed { background: #991b1b; }
"""

_STYLE_BTN_SUCCESS = """
    QPushButton {
        background: #14532d;
        color: #86efac;
        border: 1px solid #166534;
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover  { background: #166534; color: #bbf7d0; }
    QPushButton:pressed { background: #15803d; }
"""

# ── Statuts disponibles ──────────────────────────────────────────────────────
_STATUTS = [
    ("en_attente",  "En attente",  "#6b7280", "#374151"),
    ("en_cours",    "En cours",    "#3b82f6", "#1e3a5f"),
    ("acceptee",    "Acceptée",    "#22c55e", "#14532d"),
    ("planifiee",   "Planifiée",   "#a855f7", "#3b1f5f"),
    ("refusee",     "Refusée",     "#ef4444", "#7f1d1d"),
]
_STATUT_LABEL  = {k: lbl  for k, lbl, _fg, _bg in _STATUTS}
_STATUT_FG     = {k: fg   for k, _lbl, fg, _bg in _STATUTS}
_STATUT_BG     = {k: bg   for k, _lbl, _fg, bg in _STATUTS}

_STYLE_INPUT = """
    QLineEdit, QTextEdit {
        background: #191c20;
        color: #c8cdd4;
        border: 1px solid #3d4248;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
        selection-background-color: #3b82f6;
    }
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid #3b82f6;
    }
"""

_STYLE_TABLE = """
    QTableWidget {
        background: #191c20;
        color: #c8cdd4;
        border: 1px solid #3d4248;
        border-radius: 8px;
        gridline-color: #2e3238;
        font-size: 12px;
    }
    QTableWidget::item {
        padding: 6px 8px;
        border: none;
    }
    QTableWidget::item:selected {
        background: #2d3748;
        color: #e0e4ea;
    }
    QHeaderView::section {
        background: #26292e;
        color: #7a8494;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 8px;
        border: none;
        border-bottom: 1px solid #3d4248;
    }
    QScrollBar:vertical {
        background: #1e2023;
        width: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #3d4248;
        border-radius: 4px;
        min-height: 24px;
    }
    QScrollBar::handle:vertical:hover { background: #5a6472; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _sep():
    s = QFrame()
    s.setFrameShape(QFrame.HLine)
    s.setStyleSheet("background: #2e3238; max-height: 1px; border: none;")
    return s


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "font-size: 11px; font-weight: 700; color: #5a6472; "
        "letter-spacing: 2px; background: transparent; border: none;"
    )
    return lbl


class IdeasView(QWidget):

    def __init__(self):
        super().__init__()
        self._admin_unlocked = False
        self._admin_panel = None   # built lazily

        # ── Outer scroll area ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(40, 32, 40, 32)
        self._layout.setSpacing(24)
        self._layout.setAlignment(Qt.AlignTop)

        # ── Title ──
        title = QLabel("💡 Boîte à idées")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e0e4ea;")
        self._layout.addWidget(title)

        subtitle = QLabel(
            "Partagez vos idées, suggestions ou retours pour améliorer Foyio."
        )
        subtitle.setStyleSheet("font-size: 13px; color: #7a8494;")
        subtitle.setWordWrap(True)
        self._layout.addWidget(subtitle)

        self._layout.addWidget(_sep())

        # ── Submit section ──
        self._build_submit_section()

        self._layout.addWidget(_sep())

        # ── Admin toggle button ──
        admin_row = QHBoxLayout()
        admin_row.setAlignment(Qt.AlignLeft)
        self._btn_admin_toggle = QPushButton("Vue Admin")
        self._btn_admin_toggle.setStyleSheet(_STYLE_BTN_SECONDARY)
        self._btn_admin_toggle.setFixedHeight(36)
        self._btn_admin_toggle.setMinimumWidth(140)
        self._btn_admin_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_admin_toggle.clicked.connect(self._on_admin_toggle)
        admin_row.addWidget(self._btn_admin_toggle)
        admin_row.addStretch()
        self._layout.addLayout(admin_row)

        # Placeholder for admin panel (hidden by default)
        self._admin_placeholder = QWidget()
        self._admin_placeholder.setVisible(False)
        self._layout.addWidget(self._admin_placeholder)

        self._layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ──────────────────────────────────────────────────────────────
    # Submit section
    # ──────────────────────────────────────────────────────────────

    def _build_submit_section(self):
        card = QWidget()
        card.setStyleSheet("""
            QWidget#submitCard {
                background: #26292e;
                border-radius: 12px;
                border: 1px solid #3a3f47;
            }
        """)
        card.setObjectName("submitCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(14)

        card_layout.addWidget(_section_label("Soumettre une idée"))

        # Author field
        self._inp_author = QLineEdit()
        self._inp_author.setPlaceholderText("Votre prénom")
        self._inp_author.setMinimumHeight(36)
        self._inp_author.setStyleSheet(_STYLE_INPUT)
        card_layout.addWidget(self._inp_author)

        # Content field
        self._inp_content = QTextEdit()
        self._inp_content.setPlaceholderText("Décrivez votre idée ou suggestion...")
        self._inp_content.setMinimumHeight(120)
        self._inp_content.setStyleSheet(_STYLE_INPUT)
        card_layout.addWidget(self._inp_content)

        # Submit button row
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignRight)
        self._btn_submit = QPushButton("  Envoyer l'idée")
        self._btn_submit.setStyleSheet(_STYLE_BTN_PRIMARY)
        self._btn_submit.setFixedHeight(38)
        self._btn_submit.setCursor(Qt.PointingHandCursor)
        self._btn_submit.clicked.connect(self._on_submit)
        btn_row.addWidget(self._btn_submit)
        card_layout.addLayout(btn_row)

        self._layout.addWidget(card)

    # ──────────────────────────────────────────────────────────────
    # Admin panel
    # ──────────────────────────────────────────────────────────────

    def _build_admin_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("adminPanel")
        panel.setStyleSheet("""
            QWidget#adminPanel {
                background: #26292e;
                border-radius: 12px;
                border: 1px solid #3a3f47;
            }
        """)

        vlayout = QVBoxLayout(panel)
        vlayout.setContentsMargins(24, 20, 24, 20)
        vlayout.setSpacing(14)

        vlayout.addWidget(_section_label("Administration — Idées reçues"))

        # Top bar: unread badge + mark-all button
        top_bar = QHBoxLayout()
        self._lbl_unread = QLabel("0 idée(s) non lue(s)")
        self._lbl_unread.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #f59e0b; "
            "background: transparent; border: none;"
        )
        top_bar.addWidget(self._lbl_unread)
        top_bar.addStretch()

        btn_mark_all = QPushButton("Tout marquer comme lu")
        btn_mark_all.setStyleSheet(_STYLE_BTN_SECONDARY)
        btn_mark_all.setFixedHeight(32)
        btn_mark_all.setMinimumWidth(200)
        btn_mark_all.setCursor(Qt.PointingHandCursor)
        btn_mark_all.clicked.connect(self._on_mark_all_read)
        top_bar.addWidget(btn_mark_all)

        vlayout.addLayout(top_bar)

        # Table  cols: Date | Auteur | Idée | Statut | Répondre | Réponse | Supprimer
        self._table = QTableWidget()
        self._table.setStyleSheet(_STYLE_TABLE)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Date", "Auteur", "Idée", "Statut", "Répondre", "Réponse", "Supprimer"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.Fixed)
        self._table.setColumnWidth(3, 110)   # Statut
        self._table.setColumnWidth(4, 110)   # Répondre
        self._table.setColumnWidth(6, 110)   # Supprimer
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setAlternatingRowColors(False)
        self._table.setMinimumHeight(300)
        vlayout.addWidget(self._table)

        return panel

    def _populate_table(self):
        if self._table is None:
            return

        ideas = get_ideas()
        unread = sum(1 for i in ideas if not i.read)
        self._lbl_unread.setText(
            f"{unread} idée(s) non lue(s)" if unread else "Toutes les idées ont été lues ✓"
        )
        self._lbl_unread.setStyleSheet(
            "font-size: 13px; font-weight: 700; "
            + ("color: #f59e0b;" if unread else "color: #22c55e;")
            + " background: transparent; border: none;"
        )

        self._table.setRowCount(0)
        for idea in ideas:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Background for unread rows
            unread_bg = QColor("#1e2a3a")
            read_bg   = QColor("#1e2023")
            row_bg    = unread_bg if not idea.read else read_bg

            # Date
            date_str = idea.submitted_at.strftime("%d/%m/%Y %H:%M") if idea.submitted_at else "—"
            date_item = QTableWidgetItem(date_str)
            date_item.setBackground(row_bg)
            date_item.setForeground(QColor("#7a8494"))
            self._table.setItem(row, 0, date_item)

            # Author
            author_item = QTableWidgetItem(idea.author or "—")
            author_item.setBackground(row_bg)
            author_item.setForeground(QColor("#c8cdd4"))
            self._table.setItem(row, 1, author_item)

            # Content
            content_item = QTableWidgetItem(idea.content or "")
            content_item.setBackground(row_bg)
            content_item.setForeground(QColor("#c8cdd4"))
            content_item.setToolTip(idea.content or "")
            self._table.setItem(row, 2, content_item)

            idea_id = idea.id
            status  = getattr(idea, "status", None) or "en_attente"

            # Statut badge (col 3)
            statut_lbl = QLabel(_STATUT_LABEL.get(status, status))
            statut_lbl.setAlignment(Qt.AlignCenter)
            statut_lbl.setStyleSheet(
                f"color: {_STATUT_FG.get(status, '#c8cdd4')};"
                f"background: {_STATUT_BG.get(status, '#374151')};"
                "border-radius: 6px; padding: 3px 8px;"
                "font-size: 11px; font-weight: 700;"
            )
            cell_w = QWidget()
            cell_l = QHBoxLayout(cell_w)
            cell_l.setContentsMargins(4, 2, 4, 2)
            cell_l.addWidget(statut_lbl)
            self._table.setCellWidget(row, 3, cell_w)

            # "Répondre" button (col 4)
            btn_reply = QPushButton("Répondre")
            btn_reply.setStyleSheet(_STYLE_BTN_SECONDARY)
            btn_reply.setFixedHeight(28)
            btn_reply.setMinimumWidth(90)
            btn_reply.setCursor(Qt.PointingHandCursor)
            btn_reply.clicked.connect(
                lambda checked=False, iid=idea_id, st=status: self._on_reply(iid, st)
            )
            self._table.setCellWidget(row, 4, btn_reply)

            # Réponse texte (col 5)
            resp_text = getattr(idea, "response", None) or ""
            resp_item = QTableWidgetItem(resp_text)
            resp_item.setBackground(row_bg)
            resp_item.setForeground(QColor("#7a8494"))
            resp_item.setToolTip(resp_text)
            self._table.setItem(row, 5, resp_item)

            # "Delete" button (col 6)
            btn_del = QPushButton("Supprimer")
            btn_del.setStyleSheet(_STYLE_BTN_DANGER)
            btn_del.setFixedHeight(28)
            btn_del.setMinimumWidth(90)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.clicked.connect(lambda checked=False, iid=idea_id: self._on_delete(iid))
            self._table.setCellWidget(row, 6, btn_del)

        self._table.resizeRowsToContents()

    # ──────────────────────────────────────────────────────────────
    # Slots
    # ──────────────────────────────────────────────────────────────

    def _on_submit(self):
        author  = self._inp_author.text().strip()
        content = self._inp_content.toPlainText().strip()

        if not author:
            Toast.show(self, "Veuillez renseigner votre prénom.", kind="error")
            return
        if not content:
            Toast.show(self, "Veuillez décrire votre idée.", kind="error")
            return
        if len(content) < 10:
            Toast.show(self, "L'idée doit comporter au moins 10 caractères.", kind="error")
            return

        try:
            submit_idea(author, content)
        except Exception as exc:
            Toast.show(self, f"Erreur : {exc}", kind="error")
            return

        self._inp_author.clear()
        self._inp_content.clear()
        Toast.show(self, "Idée envoyée ! Merci 😊", kind="success")

        # Refresh admin panel if visible
        if self._admin_unlocked and self._admin_panel and self._admin_panel.isVisible():
            self._populate_table()

    def _on_admin_toggle(self):
        if self._admin_unlocked:
            # Already authenticated — just toggle visibility
            visible = self._admin_panel.isVisible()
            self._admin_panel.setVisible(not visible)
            self._btn_admin_toggle.setText(
                "Masquer Admin" if not visible else "Vue Admin"
            )
            return

        # Ask for password
        admin_pw = get_setting("admin_password") or "admin1234"

        password, ok = QInputDialog.getText(
            self,
            "Accès administrateur",
            "Mot de passe admin :",
            QLE.Password,
        )

        if not ok:
            return

        if password != admin_pw:
            Toast.show(self, "Mot de passe incorrect", kind="error")
            return

        # Unlock admin
        self._admin_unlocked = True
        self._btn_admin_toggle.setText("Masquer Admin")

        # Build admin panel once and replace placeholder
        if self._admin_panel is None:
            self._admin_panel = self._build_admin_panel()
            # Replace the placeholder widget in the layout
            idx = self._layout.indexOf(self._admin_placeholder)
            self._layout.removeWidget(self._admin_placeholder)
            self._admin_placeholder.deleteLater()
            self._layout.insertWidget(idx, self._admin_panel)

        self._admin_panel.setVisible(True)
        self._populate_table()

    def _on_reply(self, idea_id: int, current_status: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("Répondre à l'idée")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet("""
            QDialog { background: #1e2023; color: #c8cdd4; }
            QLabel  { color: #c8cdd4; background: transparent; }
        """)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        lay.addWidget(QLabel("Statut :"))
        combo = QComboBox()
        combo.setStyleSheet("""
            QComboBox {
                background: #26292e; color: #c8cdd4;
                border: 1px solid #3d4248; border-radius: 6px;
                padding: 6px 10px; font-size: 13px;
            }
            QComboBox QAbstractItemView {
                background: #26292e; color: #c8cdd4;
                selection-background-color: #3b82f6;
            }
        """)
        for key, label, _fg, _bg in _STATUTS:
            combo.addItem(label, key)
        # Pre-select current status
        idx = next((i for i, (k, *_) in enumerate(_STATUTS) if k == current_status), 0)
        combo.setCurrentIndex(idx)
        lay.addWidget(combo)

        lay.addWidget(QLabel("Réponse (optionnelle) :"))
        inp_resp = QTextEdit()
        inp_resp.setStyleSheet(_STYLE_INPUT)
        inp_resp.setMinimumHeight(90)
        lay.addWidget(inp_resp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Enregistrer")
        btns.button(QDialogButtonBox.Cancel).setText("Annuler")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        chosen_status = combo.currentData()
        response_text = inp_resp.toPlainText().strip()
        try:
            set_status(idea_id, chosen_status, response_text or None)
        except Exception as exc:
            Toast.show(self, f"Erreur : {exc}", kind="error")
            return
        self._populate_table()
        Toast.show(self, "Statut mis à jour.", kind="success")

    def _on_mark_read(self, idea_id: int):
        try:
            mark_read(idea_id)
        except Exception as exc:
            Toast.show(self, f"Erreur : {exc}", kind="error")
            return
        self._populate_table()

    def _on_mark_all_read(self):
        ideas = get_ideas()
        unread_ids = [i.id for i in ideas if not i.read]
        if not unread_ids:
            Toast.show(self, "Aucune idée non lue.", kind="info")
            return
        for iid in unread_ids:
            mark_read(iid)
        self._populate_table()
        Toast.show(self, f"{len(unread_ids)} idée(s) marquée(s) comme lue(s).", kind="success")

    def _on_delete(self, idea_id: int):
        try:
            delete_idea(idea_id)
        except Exception as exc:
            Toast.show(self, f"Erreur : {exc}", kind="error")
            return
        self._populate_table()
        Toast.show(self, "Idée supprimée.", kind="info")

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def refresh(self):
        """Reloads the admin table if the admin panel is currently visible."""
        if self._admin_panel and self._admin_panel.isVisible():
            self._populate_table()
