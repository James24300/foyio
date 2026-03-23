"""
Dialogue de mot de passe Foyio.
- Premier lancement : création du mot de passe
- Lancements suivants : vérification

Le mot de passe est stocké sous forme de hash SHA-256 dans le dossier
de configuration de l'application (APP_DIR).
"""
import hashlib
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

from config import APP_DIR

PASSWORD_FILE = os.path.join(APP_DIR, "auth.key")


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _load_hash() -> str | None:
    if not os.path.exists(PASSWORD_FILE):
        return None
    with open(PASSWORD_FILE, "r") as f:
        return f.read().strip()


def _save_hash(password: str):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(PASSWORD_FILE, "w") as f:
        f.write(_hash(password))


def is_password_set() -> bool:
    return _load_hash() is not None


def check_password(password: str) -> bool:
    stored = _load_hash()
    if stored is None:
        return False
    return _hash(password) == stored


class PasswordDialog(QDialog):
    """
    Dialogue affiché au démarrage.
    Mode création si aucun mot de passe n'existe, mode vérification sinon.
    """

    def __init__(self):
        super().__init__()
        self._mode = "create" if not is_password_set() else "verify"
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Foyio")
        self.setFixedSize(360, 380)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 32, 32, 32)

        # Logo image
        import os as _os
        _logo_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "icons", "foyio_logo.png"
        )
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo.setPixmap(QIcon(_logo_path).pixmap(80, 80))
        logo.setStyleSheet("background:transparent;")
        layout.addWidget(logo)

        subtitle = QLabel(
            "Créez votre mot de passe" if self._mode == "create"
            else "Entrez votre mot de passe"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:13px; color:#848c94; background:transparent;")
        layout.addWidget(subtitle)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#3d4248; background:#3d4248; max-height:1px;")
        layout.addWidget(sep)

        # Champ mot de passe
        self._pwd_input = QLineEdit()
        self._pwd_input.setEchoMode(QLineEdit.Password)
        self._pwd_input.setPlaceholderText("Mot de passe")
        self._pwd_input.setMinimumHeight(40)
        self._pwd_input.returnPressed.connect(self._submit)
        layout.addWidget(self._pwd_input)

        # Champ confirmation (mode création uniquement)
        self._confirm_input = QLineEdit()
        self._confirm_input.setEchoMode(QLineEdit.Password)
        self._confirm_input.setPlaceholderText("Confirmer le mot de passe")
        self._confirm_input.setMinimumHeight(40)
        self._confirm_input.returnPressed.connect(self._submit)
        self._confirm_input.setVisible(self._mode == "create")
        layout.addWidget(self._confirm_input)

        # Checkbox afficher le mot de passe
        layout.addSpacing(10)
        from PySide6.QtWidgets import QCheckBox
        self._show_pwd = QCheckBox("Afficher le mot de passe")
        self._show_pwd.setStyleSheet("""
            QCheckBox { font-size:11px; color:#7a8494; background:transparent; spacing:6px; }
            QCheckBox::indicator { width:16px; height:16px; border:2px solid #7a8494; border-radius:3px; background:#1e2330; }
            QCheckBox::indicator:checked { background:#3b82f6; border-color:#3b82f6; }
        """)
        self._show_pwd.toggled.connect(self._toggle_visibility)
        layout.addWidget(self._show_pwd)

        # Message d'erreur
        self._error_lbl = QLabel("")
        self._error_lbl.setAlignment(Qt.AlignCenter)
        self._error_lbl.setStyleSheet(
            "font-size:12px; color:#ef4444; background:transparent;"
        )
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        # Bouton
        self._btn = QPushButton(
            "Créer le mot de passe" if self._mode == "create" else "Déverrouiller"
        )
        self._btn.setMinimumHeight(40)
        self._btn.clicked.connect(self._submit)
        layout.addWidget(self._btn)

        # Bouton Quitter
        btn_quit = QPushButton("Quitter")
        btn_quit.setMinimumHeight(36)
        btn_quit.setStyleSheet(
            "background:transparent; color:#848c94; border:1px solid #3d4248; font-size:12px;"
        )
        btn_quit.clicked.connect(self.reject)
        layout.addWidget(btn_quit)

        layout.addStretch()
        self._pwd_input.setFocus()

    def _toggle_visibility(self, checked):
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self._pwd_input.setEchoMode(mode)
        self._confirm_input.setEchoMode(mode)

    def _submit(self):
        pwd = self._pwd_input.text()

        if not pwd:
            self._show_error("Saisissez un mot de passe.")
            return

        if self._mode == "create":
            confirm = self._confirm_input.text()
            if len(pwd) < 4:
                self._show_error("Minimum 4 caractères.")
                return
            if pwd != confirm:
                self._show_error("Les mots de passe ne correspondent pas.")
                self._confirm_input.clear()
                self._confirm_input.setFocus()
                return
            _save_hash(pwd)
            self.accept()

        else:  # verify
            if check_password(pwd):
                self.accept()
            else:
                self._show_error("Mot de passe incorrect.")
                self._pwd_input.clear()
                self._pwd_input.setFocus()

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)


class ChangePasswordDialog(QDialog):
    """Dialogue pour changer le mot de passe existant."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Changer le mot de passe")
        self.setFixedSize(360, 320)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(32, 28, 32, 28)

        title = QLabel("Changer le mot de passe")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:15px; font-weight:600; color:#c8cdd4; background:transparent;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#3d4248; background:#3d4248; max-height:1px;")
        layout.addWidget(sep)

        self._current = QLineEdit()
        self._current.setEchoMode(QLineEdit.Password)
        self._current.setPlaceholderText("Mot de passe actuel")
        self._current.setMinimumHeight(38)
        layout.addWidget(self._current)

        self._new = QLineEdit()
        self._new.setEchoMode(QLineEdit.Password)
        self._new.setPlaceholderText("Nouveau mot de passe (min. 4 caractères)")
        self._new.setMinimumHeight(38)
        layout.addWidget(self._new)

        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.Password)
        self._confirm.setPlaceholderText("Confirmer le nouveau mot de passe")
        self._confirm.setMinimumHeight(38)
        self._confirm.returnPressed.connect(self._submit)
        layout.addWidget(self._confirm)

        # Checkbox afficher les mots de passe
        from PySide6.QtWidgets import QCheckBox
        self._show_pwd = QCheckBox("Afficher les mots de passe")
        self._show_pwd.setStyleSheet("""
            QCheckBox { font-size:11px; color:#7a8494; background:transparent; spacing:6px; }
            QCheckBox::indicator { width:16px; height:16px; border:2px solid #7a8494; border-radius:3px; background:#1e2330; }
            QCheckBox::indicator:checked { background:#3b82f6; border-color:#3b82f6; }
        """)
        self._show_pwd.toggled.connect(self._toggle_visibility)
        layout.addWidget(self._show_pwd)

        self._error = QLabel("")
        self._error.setAlignment(Qt.AlignCenter)
        self._error.setStyleSheet("font-size:12px; color:#ef4444; background:transparent;")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(38)
        btn_cancel.setStyleSheet("background:#2e3238; color:#848c94; border:1px solid #3d4248;")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Enregistrer")
        btn_save.setMinimumHeight(38)
        btn_save.clicked.connect(self._submit)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        layout.addStretch()
        self._current.setFocus()

    def _toggle_visibility(self, checked):
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self._current.setEchoMode(mode)
        self._new.setEchoMode(mode)
        self._confirm.setEchoMode(mode)

    def _submit(self):
        current = self._current.text()
        new_pwd = self._new.text()
        confirm = self._confirm.text()

        if not current:
            self._show_error("Saisissez votre mot de passe actuel.")
            return
        if not check_password(current):
            self._show_error("Mot de passe actuel incorrect.")
            self._current.clear()
            self._current.setFocus()
            return
        if len(new_pwd) < 4:
            self._show_error("Minimum 4 caractères.")
            return
        if new_pwd != confirm:
            self._show_error("Les mots de passe ne correspondent pas.")
            self._confirm.clear()
            self._confirm.setFocus()
            return

        _save_hash(new_pwd)
        self.accept()

    def _show_error(self, msg: str):
        self._error.setText(msg)
        self._error.setVisible(True)
