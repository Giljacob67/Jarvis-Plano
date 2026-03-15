import logging
from typing import Any

logger = logging.getLogger(__name__)


class GmailService:
    # TODO: Implement real Gmail integration
    # - OAuth2 token management
    # - List priority/unread emails
    # - Read email content
    # - Send replies
    # - Label management

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    async def list_priority_emails(self, access_token: str, max_results: int = 5) -> list[dict[str, Any]]:
        logger.info("STUB: list_priority_emails(max_results=%d)", max_results)
        return []

    async def get_email(self, access_token: str, message_id: str) -> dict[str, Any]:
        logger.info("STUB: get_email(message_id=%s)", message_id)
        return {}
