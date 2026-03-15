import logging

from fastapi import APIRouter, Header, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.telegram import TelegramUpdate, TelegramWebhookResponse
from app.models.processed_update import ProcessedTelegramUpdate
from app.services import telegram_service
from app.services.assistant_service import (
    handle_free_text,
    get_mock_day_overview,
    format_day_overview_text,
)
from app.services.memory_service import save_memory, list_memories

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
        sender_id = str(update.message.from_user.id)
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
    user_id = sender_id
    msg = update.message

    if msg.voice:
        reply_text = (
            "🎤 Recebi seu áudio! A transcrição de voz será implementada na Fase 3. "
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
            "/myday — resumo do dia (agenda, tarefas, e-mails)\n"
            "/remember <texto> — salvar uma anotação\n"
            "/memories — listar anotações recentes\n"
            "/help — ver esta mensagem novamente\n\n"
            "Ou simplesmente me envie uma mensagem e eu respondo com a ajuda da IA! 🤖"
        )
    elif text.startswith("/help"):
        reply_text = (
            "Comandos disponíveis:\n"
            "/myday — resumo do dia\n"
            "/remember <texto> — salvar uma anotação\n"
            "/memories — listar anotações recentes\n"
            "/help — ver esta mensagem\n\n"
            "Ou envie texto livre para conversar comigo!"
        )
    elif text.startswith("/myday"):
        overview = get_mock_day_overview()
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
    else:
        reply_text = await handle_free_text(db, user_id, text, raw_update=body)

    if reply_text:
        await telegram_service.send_message(chat_id, reply_text)

    return TelegramWebhookResponse(ok=True, message="processed")
