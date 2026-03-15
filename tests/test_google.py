from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

VALID_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}
ALLOWED_USER_ID = 12345


def _make_payload(update_id, text=None, user_id=ALLOWED_USER_ID):
    msg = {
        "message_id": 200 + update_id,
        "chat": {"id": user_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
    }
    if text is not None:
        msg["text"] = text
    return {"update_id": update_id, "message": msg}


def test_me_day_disconnected_uses_mock(client: TestClient) -> None:
    response = client.get("/me/day")
    assert response.status_code == 200
    data = response.json()
    assert data["date"]
    assert len(data["calendar"]) == 3
    assert len(data["tasks"]) == 3


def test_me_day_connected_uses_real(client: TestClient) -> None:
    with patch("app.services.assistant_service.google_oauth_service") as mock_oauth, \
         patch("app.services.assistant_service.google_calendar_service") as mock_cal, \
         patch("app.services.assistant_service.google_tasks_service") as mock_tasks:
        mock_oauth.get_status.return_value = {"connected": True, "scope": "calendar tasks"}
        mock_cal.list_today_events = AsyncMock(return_value=[
            {"title": "Real Meeting", "start": "10:00", "end": "11:00", "location": "Office", "description": ""},
        ])
        mock_tasks.list_tasks = AsyncMock(return_value=[
            {"title": "Real Task", "due": "2026-03-15", "status": "needsAction"},
        ])
        response = client.get("/me/day")
        assert response.status_code == 200
        data = response.json()
        assert len(data["calendar"]) == 1
        assert data["calendar"][0]["title"] == "Real Meeting"
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["title"] == "Real Task"


def test_telegram_connectgoogle(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.settings") as mock_settings:
        mock_settings.telegram_webhook_secret = "test-secret"
        mock_settings.telegram_allowed_user_id = "12345"
        mock_settings.app_base_url = "https://example.com"
        mock_settings.google_client_id = "test-id"
        payload = _make_payload(100, text="/connectgoogle")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "https://example.com/auth/google/start" in call_text


def test_telegram_connectgoogle_no_base_url(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.settings") as mock_settings:
        mock_settings.telegram_webhook_secret = "test-secret"
        mock_settings.telegram_allowed_user_id = "12345"
        mock_settings.app_base_url = ""
        payload = _make_payload(101, text="/connectgoogle")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "APP_BASE_URL" in call_text


def test_telegram_google_status_disconnected(client: TestClient, _patch_telegram_send) -> None:
    payload = _make_payload(102, text="/google")
    response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200
    call_text = _patch_telegram_send.call_args[0][1]
    assert "não conectada" in call_text.lower() or "connectgoogle" in call_text.lower()


def test_telegram_google_status_connected(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.google_oauth_service") as mock_oauth:
        mock_oauth.get_status.return_value = {
            "connected": True,
            "scope": "calendar.events tasks",
            "token_expiry": "2026-03-15T12:00:00",
        }
        payload = _make_payload(103, text="/google")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "conectada" in call_text.lower()


def test_telegram_tasks_disconnected(client: TestClient, _patch_telegram_send) -> None:
    payload = _make_payload(104, text="/tasks")
    response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200
    call_text = _patch_telegram_send.call_args[0][1]
    assert "connectgoogle" in call_text.lower()


def test_telegram_tasks_connected(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.google_oauth_service") as mock_oauth, \
         patch("app.routes.telegram.google_tasks_service") as mock_tasks:
        mock_oauth.get_status.return_value = {"connected": True}
        mock_tasks.list_tasks = AsyncMock(return_value=[
            {"title": "Buy milk", "due": "2026-03-16", "status": "needsAction"},
            {"title": "Write tests", "due": "", "status": "needsAction"},
        ])
        payload = _make_payload(105, text="/tasks")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "Buy milk" in call_text
        assert "Write tests" in call_text


def test_telegram_tasks_empty(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.google_oauth_service") as mock_oauth, \
         patch("app.routes.telegram.google_tasks_service") as mock_tasks:
        mock_oauth.get_status.return_value = {"connected": True}
        mock_tasks.list_tasks = AsyncMock(return_value=[])
        payload = _make_payload(106, text="/tasks")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "nenhuma" in call_text.lower() or "pendente" in call_text.lower()


def test_telegram_newtask_no_title(client: TestClient, _patch_telegram_send) -> None:
    payload = _make_payload(107, text="/newtask")
    response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200
    call_text = _patch_telegram_send.call_args[0][1]
    assert "use" in call_text.lower() or "título" in call_text.lower()


def test_telegram_newtask_disconnected(client: TestClient, _patch_telegram_send) -> None:
    payload = _make_payload(108, text="/newtask Buy coffee")
    response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200
    call_text = _patch_telegram_send.call_args[0][1]
    assert "connectgoogle" in call_text.lower()


def test_telegram_newtask_success(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.google_oauth_service") as mock_oauth, \
         patch("app.routes.telegram.google_tasks_service") as mock_tasks:
        mock_oauth.get_status.return_value = {"connected": True}
        mock_tasks.create_task = AsyncMock(return_value={"id": "t1", "title": "Buy coffee", "status": "needsAction"})
        payload = _make_payload(109, text="/newtask Buy coffee")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "Buy coffee" in call_text


def test_telegram_newevent_bad_format(client: TestClient, _patch_telegram_send) -> None:
    payload = _make_payload(110, text="/newevent Meeting only no pipes")
    response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200
    call_text = _patch_telegram_send.call_args[0][1]
    assert "YYYY-MM-DD" in call_text or "formato" in call_text.lower() or "título" in call_text.lower()


def test_telegram_newevent_bad_date(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.google_oauth_service") as mock_oauth:
        mock_oauth.get_status.return_value = {"connected": True}
        payload = _make_payload(111, text="/newevent Meeting | bad-date | bad-end")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "formato" in call_text.lower() or "YYYY-MM-DD" in call_text


def test_telegram_newevent_disconnected(client: TestClient, _patch_telegram_send) -> None:
    payload = _make_payload(112, text="/newevent Meeting | 2026-03-16 09:00 | 2026-03-16 10:00")
    response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200
    call_text = _patch_telegram_send.call_args[0][1]
    assert "connectgoogle" in call_text.lower()


def test_telegram_newevent_success(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.google_oauth_service") as mock_oauth, \
         patch("app.routes.telegram.google_calendar_service") as mock_cal:
        mock_oauth.get_status.return_value = {"connected": True}
        mock_cal.create_event = AsyncMock(return_value={
            "id": "ev1", "title": "Meeting", "start": "2026-03-16T09:00:00",
            "end": "2026-03-16T10:00:00", "link": "https://calendar.google.com/event?id=ev1",
        })
        payload = _make_payload(113, text="/newevent Meeting | 2026-03-16 09:00 | 2026-03-16 10:00")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "Meeting" in call_text
        assert "calendar.google.com" in call_text


def test_telegram_myday_connected(client: TestClient, _patch_telegram_send) -> None:
    with patch("app.routes.telegram.get_real_or_mock_day_overview", new_callable=AsyncMock) as mock_overview:
        from app.schemas.day import DayOverview, CalendarEvent, Task
        mock_overview.return_value = DayOverview(
            date="2026-03-15",
            calendar=[CalendarEvent(title="Stand-up", start="09:00", end="09:15", location="Zoom")],
            tasks=[Task(title="Deploy", due="2026-03-15", status="pending")],
            emails=[],
        )
        payload = _make_payload(114, text="/myday")
        response = client.post("/webhooks/telegram", json=payload, headers=VALID_HEADERS)
        assert response.status_code == 200
        call_text = _patch_telegram_send.call_args[0][1]
        assert "Stand-up" in call_text
        assert "Deploy" in call_text
