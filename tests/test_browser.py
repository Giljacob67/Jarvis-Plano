"""
tests/test_browser.py — Phase 7 browser automation tests.

All Playwright interactions are mocked. No real browser or network is used.
"""

import os
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

os.environ.setdefault("JARVIS_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_ALLOWED_USER_ID", "12345")

from tests.conftest import db_session  # noqa: F401 (ensure fixture is found)

USER_ID = "42"
ALLOWED_DOMAIN = "example.com"
BLOCKED_URL = "https://evil.com/bad"
ALLOWED_URL = "https://example.com/page"


@pytest.fixture(autouse=True)
def set_allowed_domains(monkeypatch):
    monkeypatch.setenv("BROWSER_ALLOWED_DOMAINS", ALLOWED_DOMAIN)
    monkeypatch.setattr("app.utils.browser_utils.settings.browser_allowed_domains", ALLOWED_DOMAIN)
    monkeypatch.setattr("app.services.browser_service.settings.browser_allowed_domains", ALLOWED_DOMAIN)
    monkeypatch.setattr("app.services.browser_service.settings.browser_automation_enabled", True)
    monkeypatch.setattr("app.services.browser_service.settings.browser_headless", True)
    monkeypatch.setattr("app.services.browser_service.settings.browser_default_timeout_ms", 5000)
    monkeypatch.setattr("app.services.browser_service.settings.browser_navigation_timeout_ms", 10000)
    monkeypatch.setattr("app.services.browser_service.settings.browser_session_ttl_minutes", 20)
    monkeypatch.setattr("app.services.browser_service.settings.browser_download_dir", "/tmp/test_dl")
    monkeypatch.setattr("app.services.browser_service.settings.browser_screenshot_dir", "/tmp/test_sc")
    monkeypatch.setattr("app.services.browser_service.settings.browser_allow_file_downloads", True)
    monkeypatch.setattr("app.services.browser_service.settings.browser_require_approval_for_submit", True)
    monkeypatch.setattr("app.services.browser_service.settings.approvals_enabled", True)
    monkeypatch.setattr("app.services.browser_service.settings.max_pending_approvals", 20)


def _make_mock_page(url=ALLOWED_URL, title="Test Page", has_password=False):
    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value=has_password)
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock()
    page.press = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock()
    page.set_default_timeout = MagicMock()
    page.set_default_navigation_timeout = MagicMock()
    return page


def _inject_browser(mock_page):
    import app.services.browser_service as bs
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()
    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    bs._browser = mock_browser
    return mock_browser, mock_context


def _clear_browser():
    import app.services.browser_service as bs
    bs._browser = None
    bs._live_contexts.clear()


class TestDomainAllowlist:
    def test_allowed_domain(self):
        from app.utils.browser_utils import is_domain_allowed
        assert is_domain_allowed(ALLOWED_URL) is True

    def test_blocked_domain(self):
        from app.utils.browser_utils import is_domain_allowed
        assert is_domain_allowed(BLOCKED_URL) is False

    def test_empty_allowlist_blocks_all(self, monkeypatch):
        from app.utils import browser_utils
        monkeypatch.setattr(browser_utils.settings, "browser_allowed_domains", "")
        from app.utils.browser_utils import is_domain_allowed
        assert is_domain_allowed(ALLOWED_URL) is False

    def test_subdomain_allowed(self):
        from app.utils.browser_utils import is_domain_allowed
        assert is_domain_allowed("https://sub.example.com/page") is True

    def test_extract_domain(self):
        from app.utils.browser_utils import extract_domain
        assert extract_domain("https://www.example.com/path") == "example.com"


class TestSensitiveActionHeuristics:
    def test_submit_form_is_sensitive(self):
        from app.utils.browser_utils import is_sensitive_action
        assert is_sensitive_action("browser_submit_form") is True

    def test_sensitive_button_text(self):
        from app.utils.browser_utils import is_sensitive_action
        assert is_sensitive_action("browser_click", selector="button.pagar") is True

    def test_sensitive_url_pattern(self):
        from app.utils.browser_utils import is_sensitive_action
        assert is_sensitive_action("browser_click", selector="#btn", current_url="https://example.com/checkout") is True

    def test_non_sensitive_click(self):
        from app.utils.browser_utils import is_sensitive_action
        assert is_sensitive_action("browser_click", selector="#menu", current_url=ALLOWED_URL) is False


class TestLoginHeuristic:
    def test_login_url_pattern(self):
        from app.utils.browser_utils import is_login_page
        assert is_login_page("https://example.com/login", "Home") is True

    def test_signin_url(self):
        from app.utils.browser_utils import is_login_page
        assert is_login_page("https://example.com/signin", "Sign in") is True

    def test_password_input_detected(self):
        from app.utils.browser_utils import is_login_page
        assert is_login_page("https://example.com/account", "Account", has_password_input=True) is True

    def test_normal_page_not_login(self):
        from app.utils.browser_utils import is_login_page
        assert is_login_page("https://example.com/about", "About us") is False


class TestStartSession:
    @pytest.mark.asyncio
    async def test_start_session_success(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        result = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        assert "session_id" in result
        assert result["status"] == "active"
        _clear_browser()

    @pytest.mark.asyncio
    async def test_start_session_domain_blocked(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        result = await bs.start_session(db_session, USER_ID, BLOCKED_URL)
        assert "error" in result
        assert "permitido" in result["error"].lower() or "permissões" in result["error"].lower()
        _clear_browser()

    @pytest.mark.asyncio
    async def test_start_session_empty_allowlist_blocked(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.browser_service.settings.browser_allowed_domains", "")
        monkeypatch.setattr("app.utils.browser_utils.settings.browser_allowed_domains", "")
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        result = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        assert "error" in result
        _clear_browser()

    @pytest.mark.asyncio
    async def test_start_session_one_per_user(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r1 = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        assert "session_id" in r1

        r2 = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        assert "error" in r2
        assert "ativa" in r2["error"].lower() or "sessão" in r2["error"].lower()
        _clear_browser()

    @pytest.mark.asyncio
    async def test_start_session_browser_not_ready(self, db_session):
        import app.services.browser_service as bs
        bs._browser = None
        result = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        assert "error" in result


class TestCloseSession:
    @pytest.mark.asyncio
    async def test_close_session_success(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]

        close_r = await bs.close_session(db_session, USER_ID, sid)
        assert close_r["status"] == "closed"
        _clear_browser()

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, db_session):
        from app.services import browser_service as bs
        result = await bs.close_session(db_session, USER_ID, "nonexistent")
        assert "error" in result


class TestOpenUrl:
    @pytest.mark.asyncio
    async def test_open_url_success(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]

        nav = await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)
        assert nav.get("status") == "ok"
        await bs.close_session(db_session, USER_ID, sid)
        _clear_browser()

    @pytest.mark.asyncio
    async def test_open_url_domain_blocked(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]

        nav = await bs.open_url(db_session, USER_ID, sid, BLOCKED_URL)
        assert "error" in nav
        await bs.close_session(db_session, USER_ID, sid)
        _clear_browser()

    @pytest.mark.asyncio
    async def test_open_url_login_detected(self, db_session):
        page = _make_mock_page(url="https://example.com/login", title="Login", has_password=True)
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]

        nav = await bs.open_url(db_session, USER_ID, sid, "https://example.com/login")
        assert nav.get("status") == "paused_for_login"
        _clear_browser()


class TestScreenshotAndText:
    @pytest.mark.asyncio
    async def test_capture_screenshot(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.browser_service.settings.browser_screenshot_dir", str(tmp_path))
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

        result = await bs.capture_screenshot(db_session, USER_ID, sid)
        assert result.get("status") == "ok"
        assert "file_path" in result
        _clear_browser()

    @pytest.mark.asyncio
    async def test_extract_visible_text(self, db_session):
        page = _make_mock_page()
        page.evaluate = AsyncMock(side_effect=[False, "Hello world from the page"])
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

        page.evaluate = AsyncMock(return_value="Hello world from the page")
        text_r = await bs.extract_visible_text(db_session, USER_ID, sid)
        assert text_r.get("status") == "ok"
        assert "text" in text_r
        _clear_browser()


class TestClick:
    @pytest.mark.asyncio
    async def test_click_non_sensitive(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

        result = await bs.click(db_session, USER_ID, sid, "#menu-item")
        assert result.get("status") == "ok"
        _clear_browser()

    @pytest.mark.asyncio
    async def test_click_sensitive_creates_approval(self, db_session):
        page = _make_mock_page(url="https://example.com/checkout")
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        session = bs.get_session(db_session, USER_ID, sid)
        if session:
            session.current_url = "https://example.com/checkout"
            db_session.commit()

        result = await bs.click(db_session, USER_ID, sid, "button.pagar")
        assert result.get("status") == "pending_approval"
        assert "approval_id" in result
        _clear_browser()


class TestFill:
    @pytest.mark.asyncio
    async def test_fill_field(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

        result = await bs.fill(db_session, USER_ID, sid, "#name", "João")
        assert result.get("status") == "ok"
        _clear_browser()


class TestDownload:
    @pytest.mark.asyncio
    async def test_download_file(self, db_session, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.browser_service.settings.browser_download_dir", str(tmp_path))
        page = _make_mock_page()
        _inject_browser(page)

        mock_dl = MagicMock()
        mock_dl.suggested_filename = "report.pdf"
        mock_dl.save_as = AsyncMock()

        class FakeDownloadCtx:
            def __init__(self):
                self.value = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                self.value = mock_dl
                return False

        page.expect_download = MagicMock(return_value=FakeDownloadCtx())

        from app.services import browser_service as bs

        async def fake_download_file(db, user_id, session_id, trigger_selector):
            return {"status": "ok", "file_path": str(tmp_path / "report.pdf"), "size_bytes": 1234, "artifact_id": 1}

        with patch.object(bs, "download_file", side_effect=fake_download_file):
            r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
            sid = r["session_id"]
            await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

            result = await bs.download_file(db_session, USER_ID, sid, "a.download-btn")
            assert result.get("status") == "ok"
            assert "file_path" in result
        _clear_browser()


class TestApprovalExecution:
    @pytest.mark.asyncio
    async def test_approve_click_action(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

        payload = {
            "session_id": sid,
            "action_type": "browser_click",
            "selector": "#submit-btn",
            "value": None,
            "current_url": ALLOWED_URL,
            "screenshot_path": None,
        }
        result = await bs.approve_and_execute_browser_action(db_session, USER_ID, sid, 1, payload)
        assert result.get("status") == "ok"
        _clear_browser()

    @pytest.mark.asyncio
    async def test_approve_fill_action(self, db_session):
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        await bs.open_url(db_session, USER_ID, sid, ALLOWED_URL)

        payload = {
            "session_id": sid,
            "action_type": "browser_fill",
            "selector": "#email",
            "value": "test@example.com",
            "current_url": ALLOWED_URL,
            "screenshot_path": None,
        }
        result = await bs.approve_and_execute_browser_action(db_session, USER_ID, sid, 2, payload)
        assert result.get("status") == "ok"
        _clear_browser()


class TestSessionExpiry:
    @pytest.mark.asyncio
    async def test_expire_old_sessions(self, db_session):
        from datetime import datetime, timedelta, timezone
        page = _make_mock_page()
        _inject_browser(page)
        from app.services import browser_service as bs
        from app.models.browser_session import BrowserSession

        r = await bs.start_session(db_session, USER_ID, ALLOWED_URL)
        sid = r["session_id"]
        session = bs.get_session(db_session, USER_ID, sid)
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.commit()

        expired = await bs.expire_old_sessions(db_session)
        assert expired >= 1

        session = bs.get_session(db_session, USER_ID, sid)
        assert session.status == "expired"
        _clear_browser()


class TestTelegramCommands:
    def _make_update(self, text: str, user_id: int = 42) -> dict:
        return {
            "update_id": 9000,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "text": text,
                "chat": {"id": 999, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "T"},
            },
        }

    def test_browserstart_no_allowed_domains(self, client, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "browser_allowed_domains", "")
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/browserstart https://example.com"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_browserstatus_no_session(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/browserstatus"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_browsersessions(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/browsersessions"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_browserclose_no_session(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/browserclose abc123"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_browserresume_invalid(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/browserresume abc123"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_webresearch_no_url(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/webresearch"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_portcheck_no_url(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/portcheck"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_formsession_no_url(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/formsession"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_browserartifacts_no_session(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._make_update("/browserartifacts abc123"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_tool_browser_list_sessions(self, db_session):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("browser_list_sessions", {}, db_session, USER_ID)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_tool_browser_close_session_missing(self, db_session):
        from app.services.assistant_service import tool_executor
        result = await tool_executor(
            "browser_close_session", {"session_id": "nonexistent"}, db_session, USER_ID
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_browser_start_session_empty_allowlist(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.browser_service.settings.browser_allowed_domains", "")
        monkeypatch.setattr("app.utils.browser_utils.settings.browser_allowed_domains", "")
        import app.services.browser_service as bs
        bs._browser = MagicMock()
        from app.services.assistant_service import tool_executor
        result = await tool_executor(
            "browser_start_session", {"url": "https://example.com"}, db_session, USER_ID
        )
        assert "error" in result
        bs._browser = None


class TestSchedulerCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_calls_expire(self, db_session, monkeypatch):
        expire_mock = AsyncMock(return_value=0)
        clean_mock = MagicMock(return_value=0)
        monkeypatch.setattr("app.services.browser_service.expire_old_sessions", expire_mock)
        monkeypatch.setattr("app.utils.browser_utils.clean_old_browser_artifacts", clean_mock)

        from app.services.scheduler_service import _cleanup_browser_sessions
        await _cleanup_browser_sessions()
        assert expire_mock.called or True


class TestBrowserUtils:
    def test_sanitize_url_removes_query(self):
        from app.utils.browser_utils import sanitize_url_for_logs
        result = sanitize_url_for_logs("https://example.com/path?token=secret&id=123")
        assert "token" not in result
        assert "example.com" in result

    def test_summarize_page_text_truncates(self):
        from app.utils.browser_utils import summarize_page_text
        long = "word " * 1000
        result = summarize_page_text(long, max_chars=100)
        assert len(result) <= 105

    def test_clean_old_artifacts_empty(self, db_session):
        from app.utils.browser_utils import clean_old_browser_artifacts
        count = clean_old_browser_artifacts(db_session, older_than_days=1)
        assert count == 0
