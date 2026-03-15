from fastapi.testclient import TestClient


def test_telegram_text_message(client: TestClient) -> None:
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "chat": {"id": 123, "type": "private"},
            "text": "Hello Jarvis",
        },
    }
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "Hello Jarvis" in data["message"]


def test_telegram_voice_message(client: TestClient) -> None:
    payload = {
        "update_id": 2,
        "message": {
            "message_id": 101,
            "chat": {"id": 123, "type": "private"},
            "voice": {"file_id": "abc123", "duration": 5},
        },
    }
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "Transcription" in data["message"] or "Voice" in data["message"]


def test_telegram_no_message(client: TestClient) -> None:
    payload = {"update_id": 3}
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_telegram_invalid_secret(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.routes.telegram.settings.telegram_webhook_secret", "correct-secret")
    payload = {
        "update_id": 4,
        "message": {
            "message_id": 102,
            "chat": {"id": 123, "type": "private"},
            "text": "Test",
        },
    }
    response = client.post(
        "/webhooks/telegram",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert response.status_code == 403


def test_telegram_valid_secret(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.routes.telegram.settings.telegram_webhook_secret", "correct-secret")
    payload = {
        "update_id": 5,
        "message": {
            "message_id": 103,
            "chat": {"id": 123, "type": "private"},
            "text": "Authenticated",
        },
    }
    response = client.post(
        "/webhooks/telegram",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
