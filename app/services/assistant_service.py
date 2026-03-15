import json
import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.conversation import Conversation
from app.models.message import Message
from app.prompts import format_history_context
from app.services.memory_service import save_memory, list_memories
from app.services.openai_service import OpenAIService
from app.schemas.day import DayOverview, CalendarEvent, Task, Email

logger = logging.getLogger(__name__)

_openai_service = OpenAIService()


def get_mock_day_overview() -> DayOverview:
    today = date.today().isoformat()
    return DayOverview(
        date=today,
        calendar=[
            CalendarEvent(title="Daily standup", start="09:00", end="09:30", location="Google Meet"),
            CalendarEvent(title="Sprint review", start="14:00", end="15:00", location="Zoom"),
            CalendarEvent(title="Lunch with client", start="12:00", end="13:00", location="Restaurante Central"),
        ],
        tasks=[
            Task(title="Review PR #42", due=today, status="pending"),
            Task(title="Write API docs", due=today, status="in_progress"),
            Task(title="Deploy staging", due=today, status="done"),
        ],
        emails=[
            Email(subject="Quarterly report ready", sender="cfo@company.com", snippet="The Q1 report is attached...", priority="high"),
            Email(subject="Team offsite planning", sender="hr@company.com", snippet="Please vote on the dates...", priority="normal"),
            Email(subject="Invoice #1234", sender="billing@vendor.com", snippet="Your invoice is due on...", priority="low"),
        ],
    )


async def tool_executor(tool_name: str, tool_args: dict[str, Any], db: Session | None, user_id: str) -> Any:
    if tool_name == "get_my_day":
        overview = get_mock_day_overview()
        return overview.model_dump()

    if tool_name == "save_memory":
        note = tool_args.get("note", "")
        category = tool_args.get("category", "general")
        if db and note:
            item = save_memory(db, user_id, note, category, source="assistant")
            return {"saved": True, "id": item.id, "content": note}
        return {"saved": False, "error": "Nenhuma nota fornecida"}

    if tool_name == "list_memories":
        limit = tool_args.get("limit", 5)
        if db:
            items = list_memories(db, user_id, limit=limit)
            return [{"content": m.content, "category": m.category} for m in items]
        return []

    return {"error": f"Tool '{tool_name}' não reconhecida"}


def _get_or_create_conversation(db: Session, user_id: str) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .first()
    )
    if conv is None:
        conv = Conversation(user_id=user_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def _get_recent_messages(db: Session, conversation_id: int, limit: int) -> list[Message]:
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(msgs))


def _save_message(db: Session, conversation_id: int, role: str, text: str, channel: str = "telegram", raw_json: str | None = None) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        channel=channel,
        text=text,
        raw_json=raw_json,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


async def handle_free_text(db: Session, user_id: str, text: str, raw_update: dict | None = None) -> str:
    conv = _get_or_create_conversation(db, user_id)

    _save_message(
        db, conv.id, role="user", text=text,
        raw_json=json.dumps(raw_update, ensure_ascii=False) if raw_update else None,
    )

    recent = _get_recent_messages(db, conv.id, settings.context_max_messages)
    history = format_history_context(recent[:-1])

    memories = list_memories(db, user_id, limit=settings.context_max_memories)

    reply = await _openai_service.generate_reply(
        user_id=user_id,
        user_text=text,
        recent_messages=history,
        memories=memories,
        tool_executor=tool_executor,
        db=db,
    )

    _save_message(db, conv.id, role="assistant", text=reply)

    return reply


def format_day_overview_text(overview: DayOverview) -> str:
    lines = [f"📅 Resumo do dia ({overview.date}):", ""]
    lines.append("📆 Agenda:")
    for ev in overview.calendar:
        loc = f" — {ev.location}" if ev.location else ""
        lines.append(f"  • {ev.start}–{ev.end}: {ev.title}{loc}")
    lines.append("")
    lines.append("✅ Tarefas:")
    for t in overview.tasks:
        status_icon = {"done": "✓", "in_progress": "⏳", "pending": "○"}.get(t.status, "○")
        lines.append(f"  {status_icon} {t.title}")
    lines.append("")
    lines.append("📧 E-mails prioritários:")
    for e in overview.emails:
        prio = {"high": "🔴", "normal": "🟡", "low": "⚪"}.get(e.priority, "⚪")
        lines.append(f"  {prio} {e.subject} (de {e.sender})")
    return "\n".join(lines)
