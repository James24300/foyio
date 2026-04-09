"""Service Boîte à idées — Foyio"""
from datetime import datetime
from db import Session, safe_session
from models import Idea
import account_state


def submit_idea(author: str, content: str) -> "Idea":
    acc_id = account_state.get_id()
    with safe_session() as session:
        idea = Idea(
            author=author.strip(),
            content=content.strip(),
            submitted_at=datetime.now(),
            read=False,
            account_id=acc_id,
        )
        session.add(idea)
    return idea


def get_ideas() -> list:
    with Session() as session:
        ideas = session.query(Idea).order_by(Idea.submitted_at.desc()).all()
        session.expunge_all()
        return ideas


def mark_read(idea_id: int):
    with safe_session() as session:
        idea = session.query(Idea).filter_by(id=idea_id).first()
        if idea:
            idea.read = True


def delete_idea(idea_id: int):
    with safe_session() as session:
        idea = session.query(Idea).filter_by(id=idea_id).first()
        if idea:
            session.delete(idea)


def get_unread_count() -> int:
    with Session() as session:
        return session.query(Idea).filter_by(read=False).count()


def set_status(idea_id: int, status: str, response: str = None):
    """Met à jour le statut (et optionnellement la réponse) d'une idée."""
    with safe_session() as session:
        idea = session.query(Idea).filter_by(id=idea_id).first()
        if idea:
            idea.status = status
            if response is not None:
                idea.response = response.strip() or None
            idea.read = True
