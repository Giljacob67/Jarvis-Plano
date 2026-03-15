import logging

from sqlalchemy.orm import Session

from app.models.memory_item import MemoryItem

logger = logging.getLogger(__name__)


def save_memory(
    db: Session,
    user_id: str,
    content: str,
    category: str = "general",
    source: str = "user",
) -> MemoryItem:
    item = MemoryItem(
        user_id=user_id,
        content=content,
        category=category,
        source=source,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    logger.info("Saved memory id=%s for user=%s category=%s", item.id, user_id, category)
    return item


def list_memories(
    db: Session,
    user_id: str,
    limit: int = 10,
) -> list[MemoryItem]:
    return (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id, MemoryItem.is_active == True)
        .order_by(MemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )


def search_memories(
    db: Session,
    user_id: str,
    query: str,
    limit: int = 10,
) -> list[MemoryItem]:
    return (
        db.query(MemoryItem)
        .filter(
            MemoryItem.user_id == user_id,
            MemoryItem.is_active == True,
            MemoryItem.content.ilike(f"%{query}%"),
        )
        .order_by(MemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )
