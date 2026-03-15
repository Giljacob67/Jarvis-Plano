import logging
from typing import Any

logger = logging.getLogger(__name__)


class TelegramService:
    # TODO: Implement real Telegram Bot API integration
    # - Send messages via Bot API
    # - Set webhook via setWebhook endpoint
    # - Handle inline keyboards and callbacks
    # - Download voice/audio files for transcription

    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        logger.info("STUB: send_message(chat_id=%s, text=%r)", chat_id, text[:50])
        return {"ok": True, "stub": True}

    async def set_webhook(self, url: str, secret_token: str = "") -> dict[str, Any]:
        logger.info("STUB: set_webhook(url=%s)", url)
        return {"ok": True, "stub": True}

    async def download_file(self, file_id: str) -> bytes:
        logger.info("STUB: download_file(file_id=%s)", file_id)
        return b""
