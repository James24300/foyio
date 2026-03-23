"""
Service de gestion des pièces jointes (reçus, factures).
"""
import os
import shutil
import logging
from datetime import datetime

from config import ATTACHMENTS_DIR
from db import safe_session, Session
from models import Attachment

logger = logging.getLogger(__name__)

# Créer le dossier de stockage s'il n'existe pas
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)


def save_attachment(transaction_id: int, source_path: str) -> Attachment:
    """Copie le fichier dans ATTACHMENTS_DIR et crée l'enregistrement."""
    filename = os.path.basename(source_path)
    dest_name = f"{transaction_id}_{filename}"
    dest_path = os.path.join(ATTACHMENTS_DIR, dest_name)

    # Éviter les collisions de noms
    counter = 1
    while os.path.exists(dest_path):
        name, ext = os.path.splitext(filename)
        dest_name = f"{transaction_id}_{name}_{counter}{ext}"
        dest_path = os.path.join(ATTACHMENTS_DIR, dest_name)
        counter += 1

    shutil.copy2(source_path, dest_path)

    with safe_session() as session:
        att = Attachment(
            transaction_id=transaction_id,
            filename=filename,
            filepath=dest_path,
            added_at=datetime.now(),
        )
        session.add(att)
        session.flush()
        att_id = att.id
        session.expunge(att)

    logger.info("Pièce jointe ajoutée : %s (transaction %d)", filename, transaction_id)
    return att


def get_attachments(transaction_id: int) -> list:
    """Retourne la liste des pièces jointes d'une transaction."""
    with Session() as session:
        atts = (
            session.query(Attachment)
            .filter_by(transaction_id=transaction_id)
            .order_by(Attachment.added_at.desc())
            .all()
        )
        session.expunge_all()
        return atts


def delete_attachment(attachment_id: int):
    """Supprime l'enregistrement et le fichier associé."""
    with safe_session() as session:
        att = session.query(Attachment).filter_by(id=attachment_id).first()
        if not att:
            return
        filepath = att.filepath
        session.delete(att)

    # Supprimer le fichier du disque
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info("Fichier supprimé : %s", filepath)
        except OSError as e:
            logger.warning("Impossible de supprimer %s : %s", filepath, e)


def open_attachment(attachment: Attachment):
    """Ouvre le fichier avec l'application par défaut du système."""
    if not os.path.exists(attachment.filepath):
        logger.warning("Fichier introuvable : %s", attachment.filepath)
        return
    os.startfile(attachment.filepath)


def get_transaction_ids_with_attachments(transaction_ids: list) -> set:
    """Retourne l'ensemble des IDs de transactions qui ont des pièces jointes."""
    if not transaction_ids:
        return set()
    with Session() as session:
        rows = (
            session.query(Attachment.transaction_id)
            .filter(Attachment.transaction_id.in_(transaction_ids))
            .distinct()
            .all()
        )
        return {r[0] for r in rows}
