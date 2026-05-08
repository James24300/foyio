"""
Synchronisation Foyio via dossier partagé (Dropbox / Google Drive / OneDrive / NAS).

Principe :
  - push() copie la DB locale vers {sync_folder}/foyio_sync.db
  - pull() copie {sync_folder}/foyio_sync.db vers la DB locale (backup auto avant)
  - get_status() compare les horodatages pour indiquer qui est plus récent
"""
import logging
import os
import shutil
from datetime import datetime

from config import DB_PATH, BACKUP_DIR
from services import settings_service

logger = logging.getLogger(__name__)

SYNC_FILENAME = "foyio_sync.db"
SYNC_META_KEY = "sync_folder"
SYNC_AUTO_KEY = "sync_auto"


# ── Configuration ─────────────────────────────────────────────────────────────

def get_sync_folder() -> str | None:
    """Retourne le dossier de synchronisation configuré, ou None."""
    return settings_service.get(SYNC_META_KEY) or None


def set_sync_folder(path: str):
    """Enregistre le dossier de synchronisation."""
    settings_service.set(SYNC_META_KEY, path)


def is_auto_sync() -> bool:
    return bool(settings_service.get(SYNC_AUTO_KEY))


def set_auto_sync(enabled: bool):
    settings_service.set(SYNC_AUTO_KEY, enabled)


def _remote_path(folder: str) -> str:
    return os.path.join(folder, SYNC_FILENAME)


# ── Statut ────────────────────────────────────────────────────────────────────

def get_status() -> dict:
    """
    Retourne un dictionnaire décrivant l'état de synchronisation :
      - configured   : bool
      - local_mtime  : datetime | None
      - remote_mtime : datetime | None
      - remote_exists: bool
      - up_to_date   : bool  (local >= remote)
      - ahead        : bool  (local > remote — push recommandé)
      - behind       : bool  (remote > local — pull recommandé)
    """
    folder = get_sync_folder()
    if not folder:
        return {"configured": False}

    local_mtime = None
    if os.path.exists(DB_PATH):
        local_mtime = datetime.fromtimestamp(os.path.getmtime(DB_PATH))

    remote = _remote_path(folder)
    remote_exists = os.path.exists(remote)
    remote_mtime = None
    if remote_exists:
        remote_mtime = datetime.fromtimestamp(os.path.getmtime(remote))

    ahead = behind = up_to_date = False
    if local_mtime and remote_mtime:
        delta = (local_mtime - remote_mtime).total_seconds()
        if abs(delta) < 5:
            up_to_date = True
        elif delta > 0:
            ahead = True
        else:
            behind = True
    elif local_mtime and not remote_exists:
        ahead = True
    elif remote_exists and not local_mtime:
        behind = True

    return {
        "configured":    True,
        "local_mtime":   local_mtime,
        "remote_mtime":  remote_mtime,
        "remote_exists": remote_exists,
        "up_to_date":    up_to_date,
        "ahead":         ahead,
        "behind":        behind,
    }


# ── Push ──────────────────────────────────────────────────────────────────────

def push() -> dict:
    """
    Copie la DB locale vers le dossier de synchronisation.
    Retourne {"ok": True, "path": str} ou {"ok": False, "error": str}.
    """
    folder = get_sync_folder()
    if not folder:
        return {"ok": False, "error": "Aucun dossier de synchronisation configuré."}
    if not os.path.exists(DB_PATH):
        return {"ok": False, "error": "Base de données locale introuvable."}
    if not os.path.isdir(folder):
        return {"ok": False, "error": f"Dossier introuvable : {folder}"}

    dest = _remote_path(folder)
    try:
        shutil.copy2(DB_PATH, dest)
        logger.info("Sync push → %s", dest)
        return {"ok": True, "path": dest}
    except OSError as e:
        logger.error("Sync push échoué : %s", e)
        return {"ok": False, "error": str(e)}


# ── Pull ──────────────────────────────────────────────────────────────────────

def pull(force: bool = False) -> dict:
    """
    Copie la DB distante vers la DB locale (backup automatique avant).
    Si force=False et que la locale est plus récente, retourne {"ok": False, "conflict": True}.
    Retourne {"ok": True, "backup": str} ou {"ok": False, "error": str}.
    """
    folder = get_sync_folder()
    if not folder:
        return {"ok": False, "error": "Aucun dossier de synchronisation configuré."}

    remote = _remote_path(folder)
    if not os.path.exists(remote):
        return {"ok": False, "error": "Aucun fichier de synchronisation dans le dossier distant."}

    status = get_status()
    if not force and status.get("ahead"):
        return {
            "ok": False,
            "conflict": True,
            "error": (
                "La base locale est plus récente que la version distante. "
                "Utilisez force=True pour écraser quand même."
            ),
        }

    # Backup local avant d'écraser
    backup_path = None
    if os.path.exists(DB_PATH):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"pre_sync_backup_{ts}.db")
        shutil.copy2(DB_PATH, backup_path)
        logger.info("Backup pré-pull : %s", backup_path)

    try:
        shutil.copy2(remote, DB_PATH)
        logger.info("Sync pull ← %s", remote)
        return {"ok": True, "backup": backup_path}
    except OSError as e:
        logger.error("Sync pull échoué : %s", e)
        return {"ok": False, "error": str(e)}
