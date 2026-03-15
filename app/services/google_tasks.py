import logging
from typing import Any

logger = logging.getLogger(__name__)


class GoogleTasksService:
    # TODO: Implement real Google Tasks integration
    # - OAuth2 token management
    # - List task lists
    # - List tasks from default list
    # - Create/update/complete tasks
    # - Sync with local database

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    async def list_tasks(self, access_token: str, task_list_id: str = "@default") -> list[dict[str, Any]]:
        logger.info("STUB: list_tasks(task_list_id=%s)", task_list_id)
        return []

    async def create_task(self, access_token: str, title: str, due: str = "") -> dict[str, Any]:
        logger.info("STUB: create_task(title=%r)", title)
        return {"id": "stub", "title": title, "status": "needsAction"}
