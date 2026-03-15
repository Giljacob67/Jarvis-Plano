from app.config import settings
from app.services.telegram import TelegramService
from app.services.openai_service import OpenAIService
from app.services.google_calendar import GoogleCalendarService
from app.services.gmail import GmailService
from app.services.google_tasks import GoogleTasksService

telegram_service = TelegramService(bot_token=settings.telegram_bot_token)

__all__ = [
    "telegram_service",
    "TelegramService",
    "OpenAIService",
    "GoogleCalendarService",
    "GmailService",
    "GoogleTasksService",
]
