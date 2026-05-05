"""
Service de notifications OS natives — Foyio
- Windows  : QSystemTrayIcon.showMessage() (natif via Qt/Action Center)
- Linux    : notify-send  (libnotify, sans dépendance Python supplémentaire)
- macOS    : osascript    (sans dépendance Python supplémentaire)
Fallback Qt tray si la méthode native est indisponible.
"""
import logging
import sys

logger = logging.getLogger(__name__)

_icon_path: str = ""


def set_icon(path: str):
    """Enregistre le chemin de l'icône utilisée dans les notifications."""
    global _icon_path
    _icon_path = path


def send(title: str, body: str):
    """Envoie une notification OS native. Non-bloquant."""
    if sys.platform == "darwin":
        _send_macos(title, body)
    elif sys.platform.startswith("linux"):
        _send_linux(title, body)
    else:
        _send_qt(title, body)


# ── Backends ────────────────────────────────────────────────────────────────

def _send_macos(title: str, body: str):
    import subprocess
    # Échapper les guillemets pour éviter l'injection de commande AppleScript
    t = title.replace('"', '\\"')
    b = body.replace('"', '\\"')
    try:
        subprocess.Popen(
            ["osascript", "-e", f'display notification "{b}" with title "{t}"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.debug("osascript indisponible, fallback Qt", exc_info=True)
        _send_qt(title, body)


def _send_linux(title: str, body: str):
    import subprocess
    try:
        cmd = ["notify-send", "--app-name=Foyio", title, body]
        if _icon_path:
            cmd += ["--icon", _icon_path]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        logger.debug("notify-send indisponible, fallback Qt", exc_info=True)
        _send_qt(title, body)


def _send_qt(title: str, body: str):
    try:
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
        from PySide6.QtGui import QIcon
        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            tray = getattr(widget, "_tray", None)
            if isinstance(tray, QSystemTrayIcon):
                icon = QIcon(_icon_path) if _icon_path else QSystemTrayIcon.Information
                tray.showMessage(title, body, QIcon(_icon_path) if _icon_path else QIcon(), 5000)
                return
    except Exception:
        logger.debug("Notification Qt indisponible", exc_info=True)
