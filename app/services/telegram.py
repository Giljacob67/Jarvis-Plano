import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}"


class TelegramService:
    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._base = _BASE_URL.format(token=bot_token)
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("TelegramService not started. Call start() first.")
        return self._client

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        url = f"{self._base}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        logger.info("Sending message to chat_id=%s (len=%d)", chat_id, len(text))
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def set_webhook(self, url: str, secret_token: str = "") -> dict[str, Any]:
        api_url = f"{self._base}/setWebhook"
        payload: dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        logger.info("Setting webhook to url=%s", url)
        resp = await self.client.post(api_url, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_webhook_info(self) -> dict[str, Any]:
        url = f"{self._base}/getWebhookInfo"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def download_file(self, file_id: str) -> bytes:
        # TODO (Fase 3): Implement real file download for voice transcription
        # 1. Call getFile to get file_path
        # 2. Download from https://api.telegram.org/file/bot{token}/{file_path}
        # 3. Return raw bytes for OpenAI Whisper
        logger.info("download_file stub called for file_id=%s — will be implemented in Fase 3", file_id)
        return b""
