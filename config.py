import os
import sys

APP_NAME = "Foyio"

# Répertoire de données compatible Windows / macOS / Linux
if sys.platform == "win32":
    APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), APP_NAME)
elif sys.platform == "darwin":
    APP_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
else:
    APP_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", APP_NAME)

os.makedirs(APP_DIR, exist_ok=True)

DB_PATH = os.path.join(APP_DIR, "finance.db")
BACKUP_DIR = os.path.join(APP_DIR, "backups")

# ── Migration ancien répertoire "FinanceFoyer" → "Foyio" ──
# Si l'ancien dossier existe et le nouveau est vide, on migre
_OLD_NAME = "FinanceFoyer"
if sys.platform == "win32":
    _OLD_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), _OLD_NAME)
elif sys.platform == "darwin":
    _OLD_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", _OLD_NAME)
else:
    _OLD_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", _OLD_NAME)

if os.path.isdir(_OLD_DIR) and not os.path.exists(DB_PATH):
    import shutil
    try:
        for item in os.listdir(_OLD_DIR):
            src = os.path.join(_OLD_DIR, item)
            dst = os.path.join(APP_DIR, item)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
            elif os.path.isdir(src) and not os.path.exists(dst):
                shutil.copytree(src, dst)
        import logging as _log
        _log.getLogger(__name__).info("Migration : données déplacées de %s → %s", _OLD_NAME, APP_NAME)
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("Migration warning : %s", e)
