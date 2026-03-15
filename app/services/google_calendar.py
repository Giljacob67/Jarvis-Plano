import logging
from typing import Any

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    # TODO: Implement real Google Calendar integration
    # - OAuth2 token management (access + refresh tokens)
    # - List today's events from primary calendar
    # - Create/update/delete events
    # - Handle recurring events

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    async def list_today_events(self, access_token: str) -> list[dict[str, Any]]:
        logger.info("STUB: list_today_events()")
        return []

    async def create_event(self, access_token: str, event: dict[str, Any]) -> dict[str, Any]:
        logger.info("STUB: create_event()")
        return {"id": "stub", "status": "confirmed"}
