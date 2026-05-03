"""
Page À propos de Foyio.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QProgressDialog, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _DownloadThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def run(self):
        from services.update_service import download_and_install_update
        success, message = download_and_install_update(self.progress.emit)
        self.finished.emit(success, message)


class AboutView(QWidget):

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent; border:none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        # ── Logo + Nom ──
        logo_row = QHBoxLayout()
        logo_row.setAlignment(Qt.AlignCenter)
        logo_row.setSpacing(16)

        from utils.icons import get_icon
        logo_icon = QLabel()
        logo_icon.setPixmap(get_icon("wallet.png", 56).pixmap(56, 56))
        logo_icon.setStyleSheet("background:transparent; border:none;")

        name_col = QVBoxLayout()
        name_col.setSpacing(2)

        app_name = QLabel("Foyio")
        app_name.setStyleSheet(
            "font-size:42px; font-weight:800; color:#e0e4ea; "
            "background:transparent; border:none; letter-spacing:2px;"
        )
        tagline = QLabel("Gestion financière personnelle")
        tagline.setStyleSheet(
            "font-size:14px; color:#5a6472; background:transparent; border:none;"
        )
        name_col.addWidget(app_name)
        name_col.addWidget(tagline)

        logo_row.addWidget(logo_icon)
        logo_row.addLayout(name_col)
        layout.addLayout(logo_row)
        layout.addSpacing(8)

        # Version + bouton mise à jour
        from services.update_service import get_current_version, is_update_available, get_latest_version
        cur_v = get_current_version()
        self._version_lbl = QLabel(f"Version {cur_v}")
        self._version_lbl.setAlignment(Qt.AlignCenter)
        self._version_lbl.setStyleSheet(
            "font-size:12px; color:#848c94; background:#292d32; "
            "border-radius:20px; padding:4px 16px; border:none;"
        )
        version_lbl = self._version_lbl

        self._update_btn = QPushButton("  Vérifier les mises à jour")
        self._update_btn.setMinimumHeight(34)
        self._update_btn.setStyleSheet(
            "background:#1e2124; color:#7aaee8; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px; padding:0 14px;"
        )
        self._update_btn.clicked.connect(self._check_update)

        if is_update_available():
            self._update_btn.setText(f"  Mettre à jour vers v{get_latest_version()}")
            self._update_btn.setStyleSheet(
                "background:#1a2a1a; color:#22c55e; border:1px solid #2a5a2a;"
                "border-radius:8px; font-size:12px; font-weight:600; padding:0 14px;"
            )

        vrow = QHBoxLayout()
        vrow.setAlignment(Qt.AlignCenter)
        vrow.setSpacing(12)
        vrow.addWidget(version_lbl)
        vrow.addWidget(self._update_btn)
        layout.addLayout(vrow)
        layout.addSpacing(32)

        # ── Séparateur ──
        layout.addWidget(self._sep())
        layout.addSpacing(24)

        # ── Description ──
        desc = QLabel(
            "Foyio est une application de gestion financière personnelle "
            "conçue pour vous aider à suivre vos revenus, dépenses, budgets "
            "et objectifs d'épargne. Simple, rapide et sécurisée, elle fonctionne "
            "entièrement en local — vos données restent sur votre ordinateur."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            "font-size:13px; color:#848c94; background:transparent; "
            "border:none; line-height:1.6;"
        )
        layout.addWidget(desc)
        layout.addSpacing(32)

        # ── Fonctionnalités ──
        layout.addWidget(self._section_title("Fonctionnalités"))
        layout.addSpacing(12)

        features = [
            ("transactions.png", "Transactions",       "Suivi complet de vos revenus et dépenses"),
            ("budget.png",       "Budgets",            "Plafonds mensuels par catégorie avec alertes"),
            ("epargne.png",      "Épargne",            "Objectifs, versements et simulateur"),
            ("stats.png",        "Statistiques",       "Graphiques et analyses sur 12 mois"),
            ("stats.png",        "Outils",             "Calculatrice, convertisseur, simulateur de prêt"),
            ("bank.png",         "Multi-comptes",      "Gérez plusieurs comptes bancaires"),
            ("money.png",        "Import / Export",    "CSV, PDF et partage par email ou WhatsApp"),
        ]

        feat_grid = QHBoxLayout()
        feat_grid.setSpacing(12)
        left_col  = QVBoxLayout(); left_col.setSpacing(8)
        right_col = QVBoxLayout(); right_col.setSpacing(8)

        for i, (icon, title, desc_f) in enumerate(features):
            card = self._feature_card(icon, title, desc_f)
            if i % 2 == 0:
                left_col.addWidget(card)
            else:
                right_col.addWidget(card)

        feat_grid.addLayout(left_col, 1)
        feat_grid.addLayout(right_col, 1)
        layout.addLayout(feat_grid)
        layout.addSpacing(32)

        # ── Séparateur ──
        layout.addWidget(self._sep())
        layout.addSpacing(24)

        # ── Développé avec ──
        layout.addWidget(self._section_title("Développé avec"))
        layout.addSpacing(12)

        tech_row = QHBoxLayout()
        tech_row.setAlignment(Qt.AlignCenter)
        tech_row.setSpacing(12)

        techs = [
            ("Python 3",      "#3b82f6", "https://www.python.org"),
            ("PySide6 / Qt",  "#22c55e", "https://www.qt.io"),
            ("SQLAlchemy",    "#f59e0b", "https://www.sqlalchemy.org"),
            ("ReportLab",     "#8b5cf6", "https://www.reportlab.com"),
            ("Claude.ai",     "#c8cdd4", "https://claude.ai"),
        ]

        for name, color, url in techs:
            btn = QPushButton(name)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                "background:#292d32; color:#c8cdd4; "
                "border:none; border-radius:16px; "
                "font-size:12px; font-weight:600; padding:0 14px;"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            tech_row.addWidget(btn)

        layout.addLayout(tech_row)
        layout.addSpacing(32)

        # ── Séparateur ──
        layout.addWidget(self._sep())
        layout.addSpacing(24)

        # ── Informations légales ──
        layout.addWidget(self._section_title("Informations"))
        layout.addSpacing(12)

        infos = [
            ("🔒  Confidentialité",
             "Toutes vos données sont stockées localement sur votre ordinateur. "
             "Aucune donnée n'est envoyée vers des serveurs externes."),
            ("💾  Sauvegarde",
             "Une sauvegarde automatique est créée à chaque démarrage "
             "dans le dossier le dossier de sauvegarde Foyio."),
            ("📄  Licence",
             "Foyio est un logiciel personnel. Tous droits réservés."),
        ]

        for title_i, text_i in infos:
            info_w = QWidget()
            info_w.setStyleSheet(
                "background:#292d32; border-radius:10px; border:1px solid #3d4248;"
            )
            ilay = QVBoxLayout(info_w)
            ilay.setContentsMargins(16, 12, 16, 12)
            ilay.setSpacing(4)
            t = QLabel(title_i)
            t.setStyleSheet(
                "font-size:13px; font-weight:700; color:#c8cdd4; "
                "background:transparent; border:none;"
            )
            d = QLabel(text_i)
            d.setWordWrap(True)
            d.setStyleSheet(
                "font-size:12px; color:#7a8494; background:transparent; border:none;"
            )
            ilay.addWidget(t)
            ilay.addWidget(d)
            layout.addWidget(info_w)
            layout.addSpacing(8)

        layout.addSpacing(24)
        layout.addWidget(self._sep())
        layout.addSpacing(20)

        # ── Mise à jour ──
        layout.addWidget(self._sep())
        layout.addSpacing(20)
        layout.addWidget(self._section_title("Version & Mise à jour"))
        layout.addSpacing(12)

        from services.update_service import (
            get_current_version, is_update_available,
            get_latest_version, get_release_notes, VERSION_URL
        )

        update_w = QWidget()
        update_w.setStyleSheet(
            "background:#292d32; border-radius:10px; border:1px solid #3d4248;"
        )
        ul = QHBoxLayout(update_w)
        ul.setContentsMargins(16, 14, 16, 14)
        ul.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(4)
        v_lbl = QLabel(f"Version actuelle : {get_current_version()}")
        v_lbl.setStyleSheet(
            "font-size:13px; font-weight:600; color:#c8cdd4; "
            "background:transparent; border:none;"
        )
        if VERSION_URL:
            if is_update_available():
                status = QLabel(f"Nouvelle version disponible : v{get_latest_version()} — {get_release_notes()}")
                status.setStyleSheet("font-size:12px; color:#22c55e; background:transparent; border:none;")
            else:
                status = QLabel("Foyio est à jour.")
                status.setStyleSheet("font-size:12px; color:#7a8494; background:transparent; border:none;")
        else:
            status = QLabel("Vérification automatique non configurée — GitHub requis.")
            status.setStyleSheet("font-size:12px; color:#5a6472; background:transparent; border:none;")
        col.addWidget(v_lbl)
        col.addWidget(status)
        ul.addLayout(col, 1)
        layout.addWidget(update_w)
        layout.addSpacing(24)

        # ── Pied de page ──
        from services.settings_service import get as _get
        _name = _get('user_name') or 'James-William PULSFORD'
        author = QLabel(f'Développé par  {_name}')
        author.setAlignment(Qt.AlignCenter)
        author.setStyleSheet(
            "font-size:13px; font-weight:600; color:#848c94; "
            "background:transparent; border:none;"
        )
        layout.addWidget(author)
        layout.addSpacing(6)

        footer = QLabel("Foyio — Conçu avec ❤ et Claude.ai")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(
            "font-size:12px; color:#3e4550; background:transparent; border:none;"
        )
        layout.addWidget(footer)
        layout.addSpacing(20)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def showEvent(self, event):
        """Rafraîchit la version et l'état du bouton à chaque affichage."""
        super().showEvent(event)
        from services.update_service import get_current_version, is_update_available, get_latest_version
        self._version_lbl.setText(f"Version {get_current_version()}")
        if is_update_available():
            self._update_btn.setText(f"  Mettre à jour vers v{get_latest_version()}")
            self._update_btn.setStyleSheet(
                "background:#1a2a1a; color:#22c55e; border:1px solid #2a5a2a;"
                "border-radius:8px; font-size:12px; font-weight:600; padding:0 14px;"
            )
        else:
            self._update_btn.setText("  Vérifier les mises à jour")
            self._update_btn.setStyleSheet(
                "background:#1e2124; color:#7aaee8; border:1px solid #3d4248;"
                "border-radius:8px; font-size:12px; padding:0 14px;"
            )

    def _check_update(self):
        """Vérifie et installe la mise à jour."""
        from services.update_service import (
            check_for_update, is_update_available,
            get_latest_version, get_release_notes,
        )

        self._update_btn.setText("  Vérification...")
        self._update_btn.setEnabled(False)
        QApplication.processEvents()

        check_for_update()

        if not is_update_available():
            self._update_btn.setEnabled(True)
            self._update_btn.setText("  Foyio est à jour ✓")
            return

        latest = get_latest_version()
        notes  = get_release_notes()
        msg = QMessageBox(self)
        msg.setWindowTitle("Mise à jour disponible")
        msg.setText(f"Version {latest} disponible.")
        if notes:
            msg.setInformativeText(notes)
        btn_dl = msg.addButton("Télécharger et installer", QMessageBox.AcceptRole)
        msg.addButton("Plus tard", QMessageBox.RejectRole)
        msg.exec()

        if msg.clickedButton() != btn_dl:
            self._update_btn.setEnabled(True)
            self._update_btn.setText(f"  Mettre à jour vers v{latest}")
            return

        # ── Téléchargement en arrière-plan ──
        progress = QProgressDialog("Téléchargement en cours...", None, 0, 100, self)
        progress.setWindowTitle("Mise à jour Foyio")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        self._dl_thread = _DownloadThread()
        self._dl_thread.progress.connect(progress.setValue)

        def on_done(success, message):
            progress.close()
            self._update_btn.setEnabled(True)
            self._update_btn.setText("  Vérifier les mises à jour")
            if success:
                QMessageBox.information(self, "Mise à jour", message)
            else:
                QMessageBox.warning(self, "Erreur", message)

        self._dl_thread.finished.connect(on_done)
        self._dl_thread.start()

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.HLine)
        s.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
        return s

    def _section_title(self, text: str) -> QLabel:
        l = QLabel(text.upper())
        l.setStyleSheet(
            "font-size:11px; font-weight:700; color:#5a6472; "
            "letter-spacing:2px; background:transparent; border:none;"
        )
        return l

    def _feature_card(self, icon: str, title: str, desc: str) -> QWidget:
        from utils.icons import get_icon
        w = QWidget()
        w.setStyleSheet(
            "background:#292d32; border-radius:10px; border:1px solid #3d4248;"
        )
        row = QHBoxLayout(w)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon, 24).pixmap(24, 24))
        icon_lbl.setStyleSheet("background:transparent; border:none;")
        icon_lbl.setFixedSize(28, 28)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            "font-size:13px; font-weight:600; color:#c8cdd4; "
            "background:transparent; border:none;"
        )
        d = QLabel(desc)
        d.setStyleSheet(
            "font-size:11px; color:#7a8494; background:transparent; border:none;"
        )
        col.addWidget(t)
        col.addWidget(d)

        row.addWidget(icon_lbl)
        row.addLayout(col, 1)
        return w
