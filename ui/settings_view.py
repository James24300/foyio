import logging
import os
"""
Vue Paramètres utilisateur — Foyio
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QFrame,
    QCheckBox, QScrollArea, QFormLayout, QFileDialog
)
from PySide6.QtCore import Qt
from services.settings_service import load_settings, save_settings
from ui.toast import Toast
logger = logging.getLogger(__name__)


def _sep():
    s = QFrame(); s.setFrameShape(QFrame.HLine)
    s.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
    return s


def _section(text):
    l = QLabel(text.upper())
    l.setStyleSheet(
        "font-size:11px; font-weight:700; color:#5a6472; "
        "letter-spacing:2px; background:transparent; border:none;"
    )
    return l


class SettingsView(QWidget):

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
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)

        settings = load_settings()

        # ── Titre ──
        title = QLabel("Paramètres")
        title.setStyleSheet("font-size:22px; font-weight:700; color:#e0e4ea;")
        layout.addWidget(title)
        layout.addWidget(_sep())

        # ── Profil ──
        layout.addWidget(_section("Profil"))
        form = QFormLayout(); form.setSpacing(12)

        self._name = QLineEdit(settings.get("user_name", ""))
        self._name.setPlaceholderText("Votre nom complet")
        self._name.setMinimumHeight(36)
        form.addRow(QLabel("Nom :"), self._name)
        layout.addLayout(form)

        layout.addWidget(_sep())

        # ── Devise ──
        layout.addWidget(_section("Devise"))
        form2 = QFormLayout(); form2.setSpacing(12)

        self._currency = QComboBox()
        self._currency.setMinimumHeight(36)
        self._currency.view().setStyleSheet(
            "background:#292d32; color:#c8cdd4; border:none; "
            "outline:none; padding:0px; margin:0px;"
        )
        self._currency.view().window().setStyleSheet(
            "background:#292d32; border:1px solid #3d4248;"
        )
        self._currency.setStyleSheet("""
            QComboBox { background:#191c20; color:#c8cdd4;
                border:1px solid #3d4248; border-radius:8px; padding:4px 8px; }
            QComboBox QAbstractItemView { background:#292d32; color:#c8cdd4;
                selection-background-color:#383d44;
                border:1px solid #3d4248;
                outline:none;
                padding:0px;
                margin:0px; }
            QComboBox QAbstractItemView::item { padding:6px 8px;
                border:none; background:#292d32; color:#c8cdd4; }
            QComboBox QAbstractItemView::item:selected { background:#383d44; }
        """)
        currencies = [
            ("EUR — Euro (€)",            "EUR", "€"),
            ("USD — Dollar US ($)",        "USD", "$"),
            ("GBP — Livre Sterling (£)",   "GBP", "£"),
            ("CHF — Franc Suisse (Fr)",    "CHF", "Fr"),
            ("CAD — Dollar Canadien (CA$)","CAD", "CA$"),
            ("MAD — Dirham Marocain (DH)", "MAD", "DH"),
            ("TND — Dinar Tunisien (DT)",  "TND", "DT"),
            ("DZD — Dinar Algérien (DA)",  "DZD", "DA"),
        ]
        cur_code = settings.get("currency", "EUR")
        for label, code, symbol in currencies:
            self._currency.addItem(label, (code, symbol))
            if code == cur_code:
                self._currency.setCurrentIndex(self._currency.count() - 1)

        form2.addRow(QLabel("Devise :"), self._currency)
        layout.addLayout(form2)

        layout.addWidget(_sep())

        # ── Notifications ──
        layout.addWidget(_section("Notifications"))
        self._notif_check = QCheckBox("Afficher les notifications au démarrage")
        self._notif_check.setChecked(settings.get("startup_notifications", True))
        layout.addWidget(self._notif_check)

        layout.addWidget(_sep())

        # ── Sauvegarde ──
        layout.addWidget(_section('Sauvegarde'))
        backup_row = QHBoxLayout()
        btn_backup = QPushButton('  Sauvegarder maintenant')
        btn_backup.setMinimumHeight(36)
        btn_backup.setStyleSheet(
            'background:#1e2124; color:#22c55e; border:1px solid #3d4248;'
            'border-radius:8px; font-size:12px; font-weight:600;'
        )
        self._backup_status = QLabel('')
        self._backup_status.setStyleSheet('font-size:11px; color:#7a8494;')

        def _do_backup():
            try:
                from services.backup_service import backup_database
                backup_database()
                from datetime import datetime
                self._backup_status.setText(
                    f'Sauvegarde effectuée le {datetime.now().strftime("%d/%m/%Y à %H:%M")}'
                )
                from ui.toast import Toast
                Toast.show(self, 'Sauvegarde effectuée', kind='success')
            except Exception as e:
                self._backup_status.setText(f'Erreur : {e}')

        btn_backup.clicked.connect(_do_backup)
        backup_row.addWidget(btn_backup)
        backup_row.addWidget(self._backup_status)
        backup_row.addStretch()
        layout.addLayout(backup_row)

        # Nettoyage DB
        btn_clean = QPushButton('  Nettoyer la base de données')
        btn_clean.setMinimumHeight(36)
        btn_clean.setStyleSheet(
            'background:#1e2124; color:#f59e0b; border:1px solid #3d4248;'
            'border-radius:8px; font-size:12px; font-weight:600;'
        )
        self._clean_status = QLabel('')
        self._clean_status.setStyleSheet('font-size:11px; color:#7a8494;')

        def _do_clean():
            try:
                from db import safe_session
                from models import Transaction, Category
                from sqlalchemy import func
                with safe_session() as session:
                    # 1. Transactions sans catégorie (orphelines)
                    orphans = session.query(Transaction)\
                        .filter(Transaction.category_id.isnot(None))\
                        .filter(~Transaction.category_id.in_(
                            session.query(Category.id)
                        )).count()
                    session.query(Transaction)\
                        .filter(Transaction.category_id.isnot(None))\
                        .filter(~Transaction.category_id.in_(
                            session.query(Category.id)
                        )).update({'category_id': None}, synchronize_session=False)
                    # 2. Doublons exacts (même date+montant+type+compte)
                    from sqlalchemy import text
                    session.execute(text("""
                        DELETE FROM transactions WHERE id NOT IN (
                            SELECT MIN(id) FROM transactions
                            GROUP BY date, amount, type, account_id, note
                        )
                    """))
                from ui.toast import Toast
                self._clean_status.setText(f'{orphans} transaction(s) corrigée(s)')
                Toast.show(self, 'Base de données nettoyée', kind='success')
            except Exception as e:
                self._clean_status.setText(f'Erreur : {e}')

        btn_clean.clicked.connect(_do_clean)
        clean_row = QHBoxLayout()
        clean_row.addWidget(btn_clean)
        clean_row.addWidget(self._clean_status)
        clean_row.addStretch()
        layout.addLayout(clean_row)
        layout.addWidget(_sep())

        # ── Sécurité ──
        layout.addWidget(_section('Sécurité'))
        sec_form = QFormLayout(); sec_form.setSpacing(12)

        self._lock_combo = QComboBox()
        self._lock_combo.setMinimumHeight(36)
        self._lock_combo.setStyleSheet("""
            QComboBox { background:#191c20; color:#c8cdd4;
                border:1px solid #3d4248; border-radius:8px; padding:4px 8px; }
            QComboBox QAbstractItemView { background:#292d32; color:#c8cdd4;
                selection-background-color:#383d44;
                border:1px solid #3d4248; outline:none; padding:0; margin:0; }
            QComboBox QAbstractItemView::item { padding:6px 8px; border:none; }
            QComboBox QAbstractItemView::item:selected { background:#383d44; }
        """)
        _lock_options = [
            ("Jamais", 0),
            ("5 minutes", 5),
            ("10 minutes", 10),
            ("15 minutes", 15),
            ("30 minutes", 30),
        ]
        _current_lock = settings.get("lock_after_minutes", 0)
        for label, val in _lock_options:
            self._lock_combo.addItem(label, val)
            if val == _current_lock:
                self._lock_combo.setCurrentIndex(self._lock_combo.count() - 1)
        sec_form.addRow(QLabel("Verrouillage automatique :"), self._lock_combo)
        layout.addLayout(sec_form)
        layout.addWidget(_sep())

        # ── Thème ──
        layout.addWidget(_section('Thème'))

        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        settings = load_settings()
        self._accent_color = settings.get('accent_color', '#22c55e')

        accent_row = QHBoxLayout()
        accent_lbl = QLabel("Couleur d'accentuation :")
        accent_lbl.setStyleSheet("font-size:12px; color:#c8cdd4;")

        self._accent_btn = QPushButton(f"  {self._accent_color}")
        self._accent_btn.setMinimumHeight(34)
        self._accent_btn.setFixedWidth(160)
        self._accent_btn.setStyleSheet(
            f"background:#1e2124; color:{self._accent_color}; "
            "border:1px solid #3d4248; border-radius:8px; "
            "font-size:12px; font-weight:600;"
        )

        def _pick_accent():
            color = QColorDialog.getColor(QColor(self._accent_color), self)
            if color.isValid():
                self._accent_color = color.name()
                self._accent_btn.setText(f"  {self._accent_color}")
                self._accent_btn.setStyleSheet(
                    f"background:#1e2124; color:{self._accent_color}; "
                    "border:1px solid #3d4248; border-radius:8px; "
                    "font-size:12px; font-weight:600;"
                )

        self._accent_btn.clicked.connect(_pick_accent)
        accent_row.addWidget(accent_lbl)
        accent_row.addWidget(self._accent_btn)
        accent_row.addStretch()
        layout.addLayout(accent_row)
        layout.addWidget(_sep())

        # ── Synchronisation ──
        layout.addWidget(_section("Synchronisation"))

        sync_info = QLabel(
            "Choisissez un dossier partagé (Dropbox, Google Drive, OneDrive, NAS…). "
            "Foyio y copie votre base lors d'un Push et la restaure lors d'un Pull."
        )
        sync_info.setWordWrap(True)
        sync_info.setStyleSheet("font-size:11px; color:#7a8494;")
        layout.addWidget(sync_info)

        sync_folder_row = QHBoxLayout()
        self._sync_folder = QLineEdit(settings.get("sync_folder", ""))
        self._sync_folder.setPlaceholderText("Aucun dossier sélectionné")
        self._sync_folder.setMinimumHeight(36)
        self._sync_folder.setReadOnly(True)
        self._sync_folder.setStyleSheet(
            "background:#191c20; color:#c8cdd4; border:1px solid #3d4248;"
            "border-radius:8px; padding:4px 10px;"
        )

        btn_browse = QPushButton("Parcourir…")
        btn_browse.setMinimumHeight(36)
        btn_browse.setFixedWidth(110)
        btn_browse.setStyleSheet(
            "background:#1e2124; color:#c8cdd4; border:1px solid #3d4248;"
            "border-radius:8px; font-size:12px;"
        )

        btn_clear_sync = QPushButton("✕")
        btn_clear_sync.setMinimumHeight(36)
        btn_clear_sync.setFixedWidth(36)
        btn_clear_sync.setToolTip("Effacer le dossier de synchronisation")
        btn_clear_sync.setStyleSheet(
            "background:#1e2124; color:#7a8494; border:1px solid #3d4248;"
            "border-radius:8px; font-size:13px;"
        )

        def _browse_sync():
            folder = QFileDialog.getExistingDirectory(
                self, "Choisir le dossier de synchronisation",
                self._sync_folder.text() or os.path.expanduser("~")
            )
            if folder:
                self._sync_folder.setText(folder)
                _refresh_sync_status()

        def _clear_sync():
            self._sync_folder.setText("")
            _refresh_sync_status()

        btn_browse.clicked.connect(_browse_sync)
        btn_clear_sync.clicked.connect(_clear_sync)
        sync_folder_row.addWidget(self._sync_folder)
        sync_folder_row.addWidget(btn_browse)
        sync_folder_row.addWidget(btn_clear_sync)
        layout.addLayout(sync_folder_row)

        self._sync_auto_check = QCheckBox("Synchroniser automatiquement au démarrage")
        self._sync_auto_check.setChecked(bool(settings.get("sync_auto", False)))
        layout.addWidget(self._sync_auto_check)

        sync_btn_row = QHBoxLayout()
        sync_btn_row.setSpacing(10)

        btn_push = QPushButton("⬆  Push (envoyer)")
        btn_push.setMinimumHeight(36)
        btn_push.setStyleSheet(
            "background:#1e2124; color:#3b82f6; border:1px solid #3a3f47;"
            "border-radius:8px; font-size:12px; font-weight:600; padding:0 14px;"
        )

        btn_pull = QPushButton("⬇  Pull (recevoir)")
        btn_pull.setMinimumHeight(36)
        btn_pull.setStyleSheet(
            "background:#1e2124; color:#22c55e; border:1px solid #3a3f47;"
            "border-radius:8px; font-size:12px; font-weight:600; padding:0 14px;"
        )

        self._sync_status = QLabel("")
        self._sync_status.setStyleSheet("font-size:11px; color:#7a8494;")

        def _save_sync_settings():
            from services.sync_service import set_sync_folder, set_auto_sync
            folder = self._sync_folder.text().strip()
            set_sync_folder(folder)
            set_auto_sync(self._sync_auto_check.isChecked())

        def _refresh_sync_status():
            folder = self._sync_folder.text().strip()
            if not folder:
                self._sync_status.setText("")
                return
            try:
                from services.sync_service import get_status
                st = get_status()
                if not st.get("configured"):
                    self._sync_status.setText("")
                    return
                lm = st["local_mtime"]
                rm = st["remote_mtime"]
                fmt = "%d/%m/%Y %H:%M"
                local_s  = lm.strftime(fmt) if lm else "—"
                remote_s = rm.strftime(fmt) if rm else "—"
                if st["up_to_date"]:
                    indicator = "✓ Synchronisé"
                elif st["ahead"]:
                    indicator = "↑ Local plus récent (Push recommandé)"
                elif st["behind"]:
                    indicator = "↓ Distant plus récent (Pull recommandé)"
                else:
                    indicator = ""
                self._sync_status.setText(
                    f"Local : {local_s}   Distant : {remote_s}   {indicator}"
                )
            except Exception as e:
                self._sync_status.setText(f"Erreur : {e}")

        def _do_push():
            _save_sync_settings()
            from services.sync_service import push
            result = push()
            if result["ok"]:
                Toast.show(self, f"Push réussi → {result['path']}", kind="success")
                _refresh_sync_status()
            else:
                Toast.show(self, f"Push échoué : {result['error']}", kind="error")

        def _do_pull():
            _save_sync_settings()
            from services.sync_service import pull, get_status
            st = get_status()
            if st.get("ahead"):
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, "Conflit de synchronisation",
                    "La base locale est plus récente que la version distante.\n"
                    "Écraser quand même avec la version distante ?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
                result = pull(force=True)
            else:
                result = pull()
            if result["ok"]:
                backup = result.get("backup")
                msg = "Pull réussi."
                if backup:
                    msg += f" Backup : {os.path.basename(backup)}"
                Toast.show(self, msg, kind="success")
                _refresh_sync_status()
            else:
                Toast.show(self, f"Pull échoué : {result['error']}", kind="error")

        btn_push.clicked.connect(_do_push)
        btn_pull.clicked.connect(_do_pull)
        sync_btn_row.addWidget(btn_push)
        sync_btn_row.addWidget(btn_pull)
        sync_btn_row.addWidget(self._sync_status, 1)
        layout.addLayout(sync_btn_row)

        _refresh_sync_status()
        layout.addWidget(_sep())

        # ── Bouton sauvegarder ──
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("  Enregistrer les paramètres")
        self._btn_save.setMinimumHeight(40)
        self._btn_save.setStyleSheet(
            "background:#22c55e; color:#ffffff; border:none; "
            "border-radius:8px; font-size:13px; font-weight:600;"
        )
        self._btn_save.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_save)
        layout.addLayout(btn_row)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _save(self):
        settings = load_settings()
        settings["user_name"]   = self._name.text().strip()
        code, symbol = self._currency.currentData()
        settings["currency"]        = code
        settings["currency_symbol"] = symbol
        settings["startup_notifications"] = self._notif_check.isChecked()
        settings["lock_after_minutes"] = self._lock_combo.currentData()
        settings["accent_color"] = self._accent_color
        settings["sync_folder"] = self._sync_folder.text().strip()
        settings["sync_auto"]   = self._sync_auto_check.isChecked()
        save_settings(settings)
        # Invalider le cache du symbole monétaire
        try:
            from utils.formatters import invalidate_currency_cache
            invalidate_currency_cache()
        except Exception:
            logger.debug("Erreur invalidation cache devise", exc_info=True)
        Toast.show(self, "Paramètres enregistrés", kind="success")
