from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


def test_google_start_no_credentials(client: TestClient) -> None:
    with patch("app.routes.auth.settings") as mock_settings:
        mock_settings.google_client_id = ""
        mock_settings.google_client_secret = ""
        mock_settings.telegram_allowed_user_id = "12345"
        response = client.get("/auth/google/start")
        assert response.status_code == 501
        data = response.json()
        assert data["status"] == "not_implemented"
        assert "não configurado" in data["message"].lower() or "not_implemented" in data["status"]


def test_google_start_redirects(client: TestClient) -> None:
    with patch("app.routes.auth.google_oauth_service") as mock_oauth:
        mock_oauth.get_auth_url.return_value = "https://accounts.google.com/o/oauth2/auth?test=1"
        with patch("app.routes.auth.settings") as mock_settings:
            mock_settings.google_client_id = "test-client-id"
            mock_settings.google_client_secret = "test-secret"
            mock_settings.telegram_allowed_user_id = "12345"
            response = client.get("/auth/google/start", follow_redirects=False)
            assert response.status_code == 307
            assert "accounts.google.com" in response.headers["location"]


def test_google_callback_missing_state(client: TestClient) -> None:
    response = client.get("/auth/google/callback?code=testcode")
    assert response.status_code == 403
    data = response.json()
    assert "state" in data["message"].lower()


def test_google_callback_missing_code(client: TestClient) -> None:
    response = client.get("/auth/google/callback?state=teststate")
    assert response.status_code == 400


def test_google_callback_invalid_state(client: TestClient) -> None:
    with patch("app.routes.auth.google_oauth_service") as mock_oauth:
        mock_oauth.exchange_code.side_effect = ValueError("State inválido ou expirado.")
        response = client.get("/auth/google/callback?code=testcode&state=invalid")
        assert response.status_code == 403


def test_google_callback_no_refresh_token(client: TestClient) -> None:
    with patch("app.routes.auth.google_oauth_service") as mock_oauth:
        mock_oauth.exchange_code.side_effect = ValueError("O Google não retornou um refresh_token.")
        response = client.get("/auth/google/callback?code=testcode&state=teststate")
        assert response.status_code == 400


def test_google_callback_success(client: TestClient) -> None:
    mock_cred = MagicMock()
    mock_cred.user_id = "12345"
    mock_cred.scope = "calendar.events tasks"
    with patch("app.routes.auth.google_oauth_service") as mock_oauth:
        mock_oauth.exchange_code.return_value = mock_cred
        response = client.get("/auth/google/callback?code=testcode&state=valid")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


def test_google_callback_error_param(client: TestClient) -> None:
    response = client.get("/auth/google/callback?error=access_denied")
    assert response.status_code == 400
    assert "access_denied" in response.json()["message"]


def test_google_status_disconnected(client: TestClient) -> None:
    response = client.get("/auth/google/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False


def test_google_disconnect(client: TestClient) -> None:
    with patch("app.routes.auth.google_oauth_service") as mock_oauth:
        mock_oauth.revoke_and_disconnect = AsyncMock(return_value={"disconnected": True, "revoked": False})
        response = client.post("/auth/google/disconnect")
        assert response.status_code == 200
        data = response.json()
        assert data["disconnected"] is True
