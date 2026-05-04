# -*- coding: utf-8 -*-

"""
Dialogue de mot de passe Foyio.
- Premier lancement : création du mot de passe
- Lancements suivants : vérification

Le mot de passe est stocké sous forme de hash bcrypt sécurisé dans le dossier
de configuration de l'application (APP_DIR).
"""
import bcrypt
import hashlib
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFrame, QToolButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QAction

from config import APP_DIR

PASSWORD_FILE = os.path.join(APP_DIR, "auth.key")

def _hash(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

def _load_hash() -> bytes | None:
    if not os.path.exists(PASSWORD_FILE):
        return None
    with open(PASSWORD_FILE, "rb") as f:
        return f.read().strip()

def _save_hash(password: str):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(PASSWORD_FILE, "wb") as f:
        f.write(_hash(password))

def is_password_set() -> bool:
    return _load_hash() is not None

def check_password(password: str) -> bool:
    stored_hash = _load_hash()
    if stored_hash is None:
        return False
    try:
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
            return True
    except ValueError:
        pass
    old_hash = hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")
    if old_hash == stored_hash:
        _save_hash(password)
        return True
    return False

def _toggle_password_visibility(line_edit: QLineEdit, button: QToolButton, checked: bool):
    if checked:
        line_edit.setEchoMode(QLineEdit.Normal)
        button.setText("Cacher")
    else:
        line_edit.setEchoMode(QLineEdit.Password)
        button.setText("Voir")

class PasswordDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Foyio - Mot de passe")
        self.setFixedSize(380, 180)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.mode = "create" if not is_password_set() else "verify"

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        password_layout = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Entrez votre mot de passe")
        self.password_input.setMinimumHeight(35)
        self.password_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #3a3f47;
                border-radius: 8px;
                padding: 5px 10px;
                background-color: #23272b;
                color: #c8cdd4;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #6c757d;
            }
        """)
        self.password_input.returnPressed.connect(self.accept)
        password_layout.addWidget(self.password_input)

        self.show_password_button = QToolButton()
        self.show_password_button.setText("Voir")
        self.show_password_button.setCheckable(True)
        self.show_password_button.setMinimumHeight(35)
        self.show_password_button.setMinimumWidth(60)
        self.show_password_button.clicked.connect(lambda checked: _toggle_password_visibility(self.password_input, self.show_password_button, checked))
        self.show_password_button.setStyleSheet("""
            QToolButton {
                border: 1px solid #3a3f47;
                border-radius: 8px;
                background-color: #3a3f47;
                color: #c8cdd4;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #4a4f57;
            }
            QToolButton:checked {
                background-color: #007bff;
                color: white;
            }
        """)
        password_layout.addWidget(self.show_password_button)
        layout.addLayout(password_layout)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        layout.addWidget(self.error_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.setFixedSize(100, 35)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.setFixedSize(100, 35)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.ok_button.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        if self.mode == "create":
            self.setWindowTitle("Foyio - Créer un mot de passe")
            self.password_input.setPlaceholderText("Créez votre mot de passe")
        else:
            self.setWindowTitle("Foyio - Entrez votre mot de passe")

    def accept(self):
        password = self.password_input.text()
        if self.mode == "create":
            if len(password) < 8:
                self.error_label.setText("Le mot de passe doit contenir au moins 8 caractères.")
                return
            _save_hash(password)
            super().accept()
        else:
            if check_password(password):
                super().accept()
            else:
                self.error_label.setText("Mot de passe incorrect.")

class ChangePasswordDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Foyio - Changer le mot de passe")
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        def create_password_field(placeholder: str) -> tuple[QHBoxLayout, QLineEdit]:
            field_layout = QHBoxLayout()
            line_edit = QLineEdit()
            line_edit.setEchoMode(QLineEdit.Password)
            line_edit.setPlaceholderText(placeholder)
            line_edit.setMinimumHeight(35)
            line_edit.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #3a3f47;
                    border-radius: 8px;
                    padding: 5px 10px;
                    background-color: #23272b;
                    color: #c8cdd4;
                    font-size: 14px;
                }
                QLineEdit:focus {
                    border: 1px solid #6c757d;
                }
            """)
            field_layout.addWidget(line_edit)

            show_button = QToolButton()
            show_button.setText("Voir")
            show_button.setCheckable(True)
            show_button.setMinimumHeight(35)
            show_button.setMinimumWidth(60)
            show_button.clicked.connect(lambda checked: _toggle_password_visibility(line_edit, show_button, checked))
            show_button.setStyleSheet("""
                QToolButton {
                    border: 1px solid #3a3f47;
                    border-radius: 8px;
                    background-color: #3a3f47;
                    color: #c8cdd4;
                    font-size: 12px;
                }
                QToolButton:hover {
                    background-color: #4a4f57;
                }
                QToolButton:checked {
                    background-color: #007bff;
                    color: white;
                }
            """)
            field_layout.addWidget(show_button)
            return field_layout, line_edit

        old_layout, self.old_password_input = create_password_field("Ancien mot de passe")
        layout.addLayout(old_layout)

        new_layout, self.new_password_input = create_password_field("Nouveau mot de passe")
        layout.addLayout(new_layout)

        confirm_layout, self.confirm_password_input = create_password_field("Confirmer le nouveau mot de passe")
        layout.addLayout(confirm_layout)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        layout.addWidget(self.error_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.setFixedSize(100, 35)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.setFixedSize(100, 35)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.ok_button.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def accept(self):
        old_password = self.old_password_input.text()
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()

        if not check_password(old_password):
            self.error_label.setText("Ancien mot de passe incorrect.")
            return

        if len(new_password) < 8:
            self.error_label.setText("Le nouveau mot de passe doit contenir au moins 8 caractères.")
            return

        if new_password != confirm_password:
            self.error_label.setText("Les nouveaux mots de passe ne correspondent pas.")
            return

        _save_hash(new_password)
        super().accept()
