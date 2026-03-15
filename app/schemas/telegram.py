from pydantic import BaseModel
from typing import Optional


class TelegramChat(BaseModel):
    id: int
    type: str = "private"
    first_name: Optional[str] = None


class TelegramVoice(BaseModel):
    file_id: str
    duration: int


class TelegramMessage(BaseModel):
    message_id: int
    chat: TelegramChat
    text: Optional[str] = None
    voice: Optional[TelegramVoice] = None


class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[TelegramMessage] = None


class TelegramWebhookResponse(BaseModel):
    ok: bool
    message: str
