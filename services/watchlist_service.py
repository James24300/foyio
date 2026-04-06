"""Service Watchlist crypto — Foyio"""
from datetime import datetime
from db import Session, safe_session
from models import WatchlistItem


def get_watchlist() -> list:
    with Session() as session:
        items = session.query(WatchlistItem).order_by(WatchlistItem.added_at.desc()).all()
        session.expunge_all()
        return items


def add_to_watchlist(coingecko_id: str, symbol: str, name: str, note: str = "") -> bool:
    """Retourne False si déjà présent."""
    with Session() as session:
        if session.query(WatchlistItem).filter_by(coingecko_id=coingecko_id).first():
            return False
    with safe_session() as session:
        session.add(WatchlistItem(
            coingecko_id=coingecko_id,
            symbol=symbol,
            name=name,
            added_at=datetime.now(),
            note=note or None,
        ))
    return True


def remove_from_watchlist(item_id: int):
    with safe_session() as session:
        item = session.query(WatchlistItem).filter_by(id=item_id).first()
        if item:
            session.delete(item)


def is_in_watchlist(coingecko_id: str) -> bool:
    with Session() as session:
        return session.query(WatchlistItem).filter_by(coingecko_id=coingecko_id).first() is not None


def get_watchlist_ids() -> list[str]:
    with Session() as session:
        return [w.coingecko_id for w in session.query(WatchlistItem).all()]
