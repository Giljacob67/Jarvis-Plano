import json
import logging

from fastapi import APIRouter, Header, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.telegram import TelegramUpdate, TelegramWebhookResponse
from app.models.processed_update import ProcessedTelegramUpdate
from app.models.conversation import Conversation
from app.models.message import Message
from app.services import telegram_service
from app.services.assistant_service import (
    handle_free_text,
    get_real_or_mock_day_overview,
    format_day_overview_text,
    _get_or_create_conversation,
)
from app.services.memory_service import save_memory, list_memories
from app.services import google_oauth_service
from app.services import google_calendar as google_calendar_service
from app.services import google_tasks as google_tasks_service
from app.utils.date_utils import parse_datetime_local

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/telegram", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default="", alias="X-Telegram-Bot-Api-Secret-Token"),
    db: Session = Depends(get_db),
):
    if not settings.telegram_webhook_secret or x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        return JSONResponse(
            status_code=403,
            content=TelegramWebhookResponse(ok=False, message="Forbidden").model_dump(),
        )

    body = await request.json()
    try:
        update = TelegramUpdate(**body)
    except Exception as e:
        logger.error("Failed to parse Telegram update: %s", e)
        return TelegramWebhookResponse(ok=True, message="ignored")

    if update.message and update.message.from_user:
        sender_id = update.message.from_user.id
        if settings.telegram_allowed_user_id and sender_id != settings.telegram_allowed_user_id:
            logger.info("Ignoring message from unauthorized user_id=%s", sender_id)
            return TelegramWebhookResponse(ok=True, message="ignored")
    else:
        return TelegramWebhookResponse(ok=True, message="ignored")

    existing = db.query(ProcessedTelegramUpdate).filter(
        ProcessedTelegramUpdate.update_id == update.update_id
    ).first()
    if existing:
        logger.info("Duplicate update_id=%s, ignoring", update.update_id)
        return TelegramWebhookResponse(ok=True, message="duplicate")

    processed = ProcessedTelegramUpdate(update_id=update.update_id, user_id=sender_id)
    db.add(processed)
    db.commit()

    chat_id = update.message.chat.id
    user_id = str(sender_id)
    msg = update.message

    if msg.voice:
        conv = _get_or_create_conversation(db, user_id)
        voice_meta = {
            "type": "voice",
            "file_id": msg.voice.file_id,
            "duration": msg.voice.duration,
            "mime_type": msg.voice.mime_type,
            "file_size": msg.voice.file_size,
        }
        voice_msg = Message(
            conversation_id=conv.id,
            role="user",
            channel="telegram",
            text="[voice message]",
            raw_json=json.dumps({"voice": voice_meta, "update_id": update.update_id}, ensure_ascii=False),
        )
        db.add(voice_msg)
        db.commit()

        reply_text = (
            "🎤 Recebi seu áudio! A transcrição de voz será implementada em breve. "
            "Por enquanto, envie sua mensagem como texto."
        )
        await telegram_service.send_message(chat_id, reply_text)
        return TelegramWebhookResponse(ok=True, message="voice_noted")

    text = (msg.text or "").strip()
    if not text:
        return TelegramWebhookResponse(ok=True, message="ignored")

    reply_text = ""

    if text.startswith("/start"):
        reply_text = (
            "Olá! 👋 Sou o Jarvis, seu assistente pessoal de produtividade.\n\n"
            "Comandos disponíveis:\n"
            "/myday — resumo do dia (agenda, tarefas)\n"
            "/remember <texto> — salvar uma anotação\n"
            "/memories — listar anotações recentes\n"
            "/connectgoogle — conectar conta Google\n"
            "/google — status da conexão Google\n"
            "/tasks — listar tarefas do Google Tasks\n"
            "/newtask <titulo> — criar tarefa\n"
            "/newevent <titulo> | <inicio> | <fim> — criar evento\n"
            "/help — ver esta mensagem novamente\n\n"
            "Ou simplesmente me envie uma mensagem e eu respondo com a ajuda da IA! 🤖"
        )
    elif text.startswith("/help"):
        reply_text = (
            "Comandos disponíveis:\n"
            "/myday — resumo do dia\n"
            "/remember <texto> — salvar uma anotação\n"
            "/memories — listar anotações recentes\n"
            "/connectgoogle — conectar conta Google\n"
            "/google — status da conexão Google\n"
            "/tasks — listar tarefas\n"
            "/newtask <titulo> — criar tarefa\n"
            "/newevent <titulo> | <inicio> | <fim> — criar evento\n"
            "/help — ver esta mensagem\n\n"
            "Ou envie texto livre para conversar comigo!"
        )
    elif text.startswith("/myday"):
        overview = await get_real_or_mock_day_overview(db, user_id)
        reply_text = format_day_overview_text(overview)
    elif text.startswith("/remember"):
        note = text[len("/remember"):].strip()
        if not note:
            reply_text = "Use: /remember <sua anotação aqui>"
        else:
            save_memory(db, user_id, note, category="general", source="command")
            reply_text = f"✅ Anotação salva: \"{note}\""
    elif text.startswith("/memories"):
        items = list_memories(db, user_id, limit=10)
        if not items:
            reply_text = "Você ainda não tem anotações salvas. Use /remember para salvar uma."
        else:
            lines = ["📝 Suas anotações recentes:"]
            for i, m in enumerate(items, 1):
                lines.append(f"{i}. [{m.category}] {m.content}")
            reply_text = "\n".join(lines)
    elif text.startswith("/connectgoogle"):
        if not settings.app_base_url:
            reply_text = "⚠️ APP_BASE_URL não está configurado. Peça ao administrador para definir."
        elif not settings.google_client_id:
            reply_text = "⚠️ Credenciais Google OAuth não configuradas. Peça ao administrador."
        else:
            auth_link = f"{settings.app_base_url.rstrip('/')}/auth/google/start"
            reply_text = f"🔗 [Clique aqui para conectar sua conta Google]({auth_link})"
    elif text.startswith("/google"):
        status = google_oauth_service.get_status(db, user_id)
        if status.get("connected"):
            reply_text = (
                "✅ Conta Google conectada!\n"
                f"Escopos: {status.get('scope', '')}\n"
                f"Validade do token: {status.get('token_expiry', 'N/A')}"
            )
        else:
            reply_text = "❌ Conta Google não conectada. Use /connectgoogle para conectar."
    elif text.startswith("/tasks"):
        status = google_oauth_service.get_status(db, user_id)
        if not status.get("connected"):
            reply_text = "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
        else:
            tasks = await google_tasks_service.list_tasks(db, user_id, limit=15)
            if not tasks:
                reply_text = "✅ Nenhuma tarefa pendente!"
            else:
                lines = ["📋 Suas tarefas pendentes:"]
                for i, t in enumerate(tasks, 1):
                    due_str = f" (vence: {t['due'][:10]})" if t.get("due") else ""
                    lines.append(f"{i}. {t['title']}{due_str}")
                reply_text = "\n".join(lines)
    elif text.startswith("/newtask"):
        title = text[len("/newtask"):].strip()
        if not title:
            reply_text = "Use: /newtask <título da tarefa>"
        else:
            status = google_oauth_service.get_status(db, user_id)
            if not status.get("connected"):
                reply_text = "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
            else:
                result = await google_tasks_service.create_task(db, user_id, title)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    reply_text = f"✅ Tarefa criada: \"{result.get('title', title)}\""
    elif text.startswith("/newevent"):
        parts_raw = text[len("/newevent"):].strip()
        parts = [p.strip() for p in parts_raw.split("|")]
        if len(parts) < 3:
            reply_text = (
                "Use: /newevent título | início | fim\n"
                "Formato de data: YYYY-MM-DD HH:MM\n"
                "Exemplo: /newevent Reunião | 2026-03-16 09:00 | 2026-03-16 10:00"
            )
        else:
            ev_title = parts[0]
            status = google_oauth_service.get_status(db, user_id)
            if not status.get("connected"):
                reply_text = "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
            else:
                try:
                    start_dt = parse_datetime_local(parts[1], settings.timezone)
                    end_dt = parse_datetime_local(parts[2], settings.timezone)
                except ValueError as e:
                    reply_text = f"❌ {e}"
                else:
                    result = await google_calendar_service.create_event(
                        db, user_id, ev_title, start_dt, end_dt, tz=settings.timezone
                    )
                    if "error" in result:
                        reply_text = f"❌ {result['error']}"
                    else:
                        reply_text = f"✅ Evento criado: \"{result.get('title', ev_title)}\""
                        if result.get("link"):
                            reply_text += f"\n🔗 {result['link']}"
    else:
        reply_text = await handle_free_text(db, user_id, text, raw_update=body)

    if reply_text:
        await telegram_service.send_message(chat_id, reply_text)

    return TelegramWebhookResponse(ok=True, message="processed")
