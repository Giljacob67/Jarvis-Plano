from fastapi.testclient import TestClient


def test_google_start_returns_501(client: TestClient) -> None:
    response = client.get("/auth/google/start")
    assert response.status_code == 501
    data = response.json()
    assert data["status"] == "not_implemented"
    assert "not implemented" in data["message"].lower()


def test_google_callback_returns_501(client: TestClient) -> None:
    response = client.get("/auth/google/callback")
    assert response.status_code == 501
    data = response.json()
    assert data["status"] == "not_implemented"
    assert "not implemented" in data["message"].lower()
