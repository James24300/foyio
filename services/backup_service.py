import logging
import os
import shutil
from datetime import datetime

from config import DB_PATH, BACKUP_DIR

logger = logging.getLogger(__name__)

MAX_BACKUPS = 10


def backup_database():
    """Crée une sauvegarde horodatée de la base de données."""
    if not os.path.exists(DB_PATH):
        logger.warning("Aucune base de données à sauvegarder.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"finance_backup_{timestamp}.db")

    shutil.copy2(DB_PATH, backup_file)
    logger.info("Backup créé : %s", backup_file)

    _cleanup_backups()


def _cleanup_backups():
    """Supprime les backups les plus anciens au-delà de MAX_BACKUPS."""
    files = sorted(
        f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")
    )

    if len(files) <= MAX_BACKUPS:
        return

    for filename in files[:-MAX_BACKUPS]:
        path = os.path.join(BACKUP_DIR, filename)
        os.remove(path)
        logger.info("Ancien backup supprimé : %s", filename)
