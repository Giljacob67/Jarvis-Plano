import logging
from fastapi import APIRouter, Header, HTTPException

from app.config import settings
from app.schemas import TelegramUpdate, TelegramWebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/telegram", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    update: TelegramUpdate,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> TelegramWebhookResponse:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    if update.message is None:
        logger.info("Received update without message: update_id=%s", update.update_id)
        return TelegramWebhookResponse(ok=True, message="No message to process")

    msg = update.message

    if msg.voice:
        logger.info(
            "Received voice message: chat_id=%s, file_id=%s, duration=%ds — transcription not implemented yet",
            msg.chat.id,
            msg.voice.file_id,
            msg.voice.duration,
        )
        return TelegramWebhookResponse(ok=True, message="Voice received. Transcription will be implemented later.")

    if msg.text:
        logger.info("Received text message: chat_id=%s, text=%r", msg.chat.id, msg.text)
        return TelegramWebhookResponse(ok=True, message=f"Text received: {msg.text}")

    logger.info("Received message with unsupported content: chat_id=%s", msg.chat.id)
    return TelegramWebhookResponse(ok=True, message="Message received but content type not yet supported")
