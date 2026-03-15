import json
import logging
from datetime import datetime, timezone, time, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.action_log import ActionLog
from app.models.suggestion_log import SuggestionLog
from app.models.memory_item import MemoryItem
from app.services.memory_service import get_memories_by_context

logger = logging.getLogger(__name__)


def _log_action(db: Session, event_type: str, status: str, details: dict) -> None:
    entry = ActionLog(
        event_type=event_type,
        status=status,
        details_json=json.dumps(details, ensure_ascii=False),
    )
    db.add(entry)
    db.commit()


def _now_in_tz() -> datetime:
    import zoneinfo
    tz = zoneinfo.ZoneInfo(settings.default_timezone)
    return datetime.now(tz)


def is_quiet_time(db: Session, user_id: str) -> bool:
    if not settings.quiet_hours_enabled:
        return False

    user_pref = db.query(MemoryItem).filter(
        MemoryItem.user_id == user_id,
        MemoryItem.category == "preference",
        MemoryItem.content == "quiet_hours_disabled",
        MemoryItem.is_active == True,
    ).first()
    if user_pref:
        return False

    now = _now_in_tz()
    current_time = now.time()
    start = time.fromisoformat(settings.quiet_hours_start)
    end = time.fromisoformat(settings.quiet_hours_end)

    if start > end:
        return current_time >= start or current_time < end
    return start <= current_time < end


def is_on_cooldown(db: Session, user_id: str, subject: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.proactive_min_interval_minutes)
    recent = db.query(ActionLog).filter(
        ActionLog.event_type == "proactive_message_sent",
        ActionLog.created_at >= cutoff,
    ).all()
    for entry in recent:
        if entry.details_json:
            try:
                details = json.loads(entry.details_json)
                if details.get("user_id") == user_id and details.get("subject") == subject:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def set_quiet_hours_preference(db: Session, user_id: str, enabled: bool) -> None:
    existing = db.query(MemoryItem).filter(
        MemoryItem.user_id == user_id,
        MemoryItem.category == "preference",
        MemoryItem.content == "quiet_hours_disabled",
    ).first()
    if enabled:
        if existing:
            existing.is_active = False
            db.commit()
    else:
        if existing:
            existing.is_active = True
            db.commit()
        else:
            item = MemoryItem(
                user_id=user_id,
                category="preference",
                content="quiet_hours_disabled",
                source="command",
            )
            db.add(item)
            db.commit()


def get_quiet_hours_preference(db: Session, user_id: str) -> bool:
    disabled = db.query(MemoryItem).filter(
        MemoryItem.user_id == user_id,
        MemoryItem.category == "preference",
        MemoryItem.content == "quiet_hours_disabled",
        MemoryItem.is_active == True,
    ).first()
    return disabled is None


def create_suggestion(
    db: Session,
    user_id: str,
    suggestion_type: str,
    title: str,
    body: str,
    source: str = "system",
) -> SuggestionLog:
    suggestion = SuggestionLog(
        user_id=user_id,
        suggestion_type=suggestion_type,
        title=title,
        body=body,
        source=source,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    _log_action(db, "suggestion_created", "success", {
        "suggestion_id": suggestion.id,
        "user_id": user_id,
        "suggestion_type": suggestion_type,
        "title": title,
    })
    return suggestion


async def send_proactive_message(
    db: Session,
    user_id: str,
    message: str,
    subject: str = "general",
) -> bool:
    if is_quiet_time(db, user_id):
        logger.info("Skipping proactive message for user=%s: quiet hours", user_id)
        return False

    if is_on_cooldown(db, user_id, subject):
        logger.info("Skipping proactive message for user=%s: cooldown for subject=%s", user_id, subject)
        return False

    from app.services import telegram_service
    chat_id = int(settings.telegram_allowed_user_id) if settings.telegram_allowed_user_id else None
    if not chat_id:
        logger.warning("No telegram_allowed_user_id configured, cannot send proactive message")
        return False

    try:
        await telegram_service.send_message(chat_id, message)
        _log_action(db, "proactive_message_sent", "success", {
            "user_id": user_id,
            "subject": subject,
            "length": len(message),
        })
        return True
    except Exception:
        logger.exception("Failed to send proactive message to user=%s", user_id)
        return False


async def generate_morning_briefing(db: Session, user_id: str) -> str:
    from app.services import google_oauth_service
    from app.services import google_calendar as google_calendar_service
    from app.services import google_tasks as google_tasks_service
    from app.services import google_gmail_service
    from app.services.approval_service import list_pending_approvals

    lines = ["☀️ *Bom dia! Aqui está seu briefing matinal:*\n"]

    status = google_oauth_service.get_status(db, user_id)
    connected = status.get("connected", False)

    events = []
    if connected:
        try:
            events = await google_calendar_service.list_today_events(db, user_id, settings.default_timezone)
        except Exception:
            logger.exception("Briefing: failed to get events")

    if events:
        lines.append("📆 *Agenda de hoje:*")
        conflict_times = []
        for ev in events:
            start = ev.get("start", "")
            end = ev.get("end", "")
            loc = f" — {ev.get('location')}" if ev.get("location") else ""
            lines.append(f"  • {start[:16] if len(start) > 16 else start} – {end[:16] if len(end) > 16 else end}: {ev.get('title', '?')}{loc}")
            conflict_times.append((start, end))

        for i in range(len(conflict_times)):
            for j in range(i + 1, len(conflict_times)):
                if conflict_times[i][1] > conflict_times[j][0] and conflict_times[i][0] < conflict_times[j][1]:
                    lines.append(f"  ⚠️ Possível conflito entre '{events[i].get('title')}' e '{events[j].get('title')}'")
        lines.append("")
    else:
        lines.append("📆 Sem eventos na agenda hoje.\n")

    tasks = []
    if connected:
        try:
            tasks = await google_tasks_service.list_tasks(db, user_id, limit=10)
        except Exception:
            logger.exception("Briefing: failed to get tasks")

    if tasks:
        lines.append("✅ *Tarefas prioritárias:*")
        for t in tasks[:5]:
            due_str = f" (vence: {t['due'][:10]})" if t.get("due") else ""
            lines.append(f"  • {t['title']}{due_str}")
        lines.append("")
    else:
        lines.append("✅ Nenhuma tarefa pendente.\n")

    emails = []
    if connected and status.get("gmail_enabled"):
        try:
            emails = await google_gmail_service.get_priority_emails(db, user_id, max_results=5)
        except Exception:
            logger.exception("Briefing: failed to get emails")

    if emails:
        lines.append("📧 *E-mails importantes:*")
        for m in emails[:3]:
            sender = m.get("from", "?")
            if "<" in sender:
                sender = sender.split("<")[0].strip().strip('"')
            lines.append(f"  • {m.get('subject', '(sem assunto)')} (de {sender})")
        lines.append("")

    approvals = list_pending_approvals(db, user_id)
    if approvals:
        lines.append(f"⏳ *{len(approvals)} aprovação(ões) pendente(s)*")
        for a in approvals[:3]:
            lines.append(f"  • #{a.id}: {a.title}")
        lines.append("")

    memories = get_memories_by_context(db, user_id, ["project", "decision", "followup"], limit=5)
    if memories:
        lines.append("🧠 *Contexto relevante:*")
        for m in memories[:3]:
            lines.append(f"  • [{m.category}] {m.content[:100]}")
        lines.append("")

    if tasks:
        lines.append(f"🎯 *Sugestão de foco:* {tasks[0]['title']}")
    else:
        lines.append("🎯 *Sugestão:* Ótimo dia para organizar pendências!")

    return "\n".join(lines)


async def generate_evening_review(db: Session, user_id: str) -> str:
    from app.services import google_oauth_service
    from app.services import google_tasks as google_tasks_service
    from app.services import google_calendar as google_calendar_service
    from app.services.approval_service import list_pending_approvals

    lines = ["🌙 *Fechamento do dia:*\n"]

    status = google_oauth_service.get_status(db, user_id)
    connected = status.get("connected", False)

    today_events = []
    if connected:
        try:
            today_events = await google_calendar_service.list_today_events(db, user_id, settings.default_timezone)
        except Exception:
            logger.exception("Review: failed to get events")

    if today_events:
        lines.append(f"📆 *{len(today_events)} evento(s) no dia*")
        lines.append("")

    tasks = []
    if connected:
        try:
            tasks = await google_tasks_service.list_tasks(db, user_id, limit=20)
        except Exception:
            logger.exception("Review: failed to get tasks")

    pending = [t for t in tasks if t.get("status") != "completed"]
    if pending:
        lines.append(f"📋 *{len(pending)} tarefa(s) ainda pendente(s):*")
        for t in pending[:5]:
            lines.append(f"  • {t['title']}")
        lines.append("")
    else:
        lines.append("✅ Todas as tarefas foram concluídas!\n")

    approvals = list_pending_approvals(db, user_id)
    if approvals:
        lines.append(f"⏳ *{len(approvals)} aprovação(ões) aguardando sua decisão*\n")

    followup_memories = get_memories_by_context(db, user_id, ["followup"], limit=5)
    if followup_memories:
        lines.append("📌 *Follow-ups pendentes:*")
        for m in followup_memories[:3]:
            lines.append(f"  • {m.content[:100]}")
        lines.append("")

    tomorrow_events = []
    if connected:
        try:
            from app.utils.date_utils import week_bounds
            tomorrow_events = await google_calendar_service.list_upcoming_events(
                db, user_id, days=2, limit=5, tz=settings.default_timezone
            )
        except Exception:
            logger.exception("Review: failed to get tomorrow events")

    if tomorrow_events:
        lines.append("📅 *Proposta para amanhã:*")
        for ev in tomorrow_events[:3]:
            lines.append(f"  • {ev.get('start', '')[:16]}: {ev.get('title', '?')}")
        lines.append("")

    lines.append("💤 Bom descanso!")
    return "\n".join(lines)


async def check_upcoming_events(db: Session, user_id: str) -> list[dict]:
    from app.services import google_oauth_service
    from app.services import google_calendar as google_calendar_service

    status = google_oauth_service.get_status(db, user_id)
    if not status.get("connected"):
        return []

    try:
        events = await google_calendar_service.list_today_events(db, user_id, settings.default_timezone)
        now = _now_in_tz()
        upcoming = []
        for ev in events:
            start_str = ev.get("start", "")
            try:
                if "T" in start_str:
                    from dateutil.parser import parse as dt_parse
                    start_dt = dt_parse(start_str)
                    if start_dt.tzinfo is None:
                        import zoneinfo
                        start_dt = start_dt.replace(tzinfo=zoneinfo.ZoneInfo(settings.default_timezone))
                    diff_minutes = (start_dt - now).total_seconds() / 60
                    if 0 < diff_minutes <= 15:
                        upcoming.append(ev)
            except Exception:
                continue
        return upcoming
    except Exception:
        logger.exception("check_upcoming_events failed")
        return []


async def check_due_tasks(db: Session, user_id: str) -> list[dict]:
    from app.services import google_oauth_service
    from app.services import google_tasks as google_tasks_service
    from datetime import date

    status = google_oauth_service.get_status(db, user_id)
    if not status.get("connected"):
        return []

    try:
        tasks = await google_tasks_service.list_tasks(db, user_id, limit=20)
        today = date.today().isoformat()
        due_today = []
        for t in tasks:
            due = t.get("due", "")
            if due and due[:10] <= today and t.get("status") != "completed":
                due_today.append(t)
        return due_today
    except Exception:
        logger.exception("check_due_tasks failed")
        return []


async def check_followups(db: Session, user_id: str) -> list[MemoryItem]:
    return get_memories_by_context(db, user_id, ["followup"], limit=10)


async def check_pending_drafts(db: Session, user_id: str) -> list[dict]:
    from app.services import google_oauth_service
    from app.services import google_gmail_service

    status = google_oauth_service.get_status(db, user_id)
    if not status.get("connected") or not status.get("gmail_enabled"):
        return []

    try:
        result = await google_gmail_service.list_drafts(db, user_id, max_results=5)
        return result.get("drafts", [])
    except Exception:
        logger.exception("check_pending_drafts failed")
        return []


async def get_proactive_suggestions(db: Session, user_id: str) -> dict:
    upcoming = await check_upcoming_events(db, user_id)
    due_tasks = await check_due_tasks(db, user_id)
    followups = await check_followups(db, user_id)
    drafts = await check_pending_drafts(db, user_id)

    suggestions = []
    for ev in upcoming:
        suggestions.append(f"⏰ Evento em breve: {ev.get('title', '?')}")
    for t in due_tasks:
        suggestions.append(f"📋 Tarefa vencendo: {t['title']}")
    for m in followups[:3]:
        suggestions.append(f"📌 Follow-up: {m.content[:80]}")
    for d in drafts[:2]:
        suggestions.append(f"📝 Rascunho não enviado: {d.get('subject', '?')}")

    return {
        "upcoming_events": len(upcoming),
        "due_tasks": len(due_tasks),
        "followups": len(followups),
        "pending_drafts": len(drafts),
        "suggestions": suggestions,
    }
