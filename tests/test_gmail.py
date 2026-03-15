import base64
import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.models.google_credential import GoogleCredential
from app.utils.gmail_utils import (
    extract_header,
    extract_message_fields,
    extract_plain_body,
    strip_quoted_text,
    build_mime_message,
    build_mime_reply,
    format_message_for_telegram,
    format_messages_list_telegram,
    date_to_gmail_after_query,
)


GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/tasks "
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.compose"
)

NO_GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/tasks"
)


def _make_cred(db, user_id="12345", scope=GMAIL_SCOPES):
    cred = GoogleCredential(
        user_id=user_id,
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
        scope=scope,
        token_type="Bearer",
    )
    db.add(cred)
    db.commit()
    return cred


def _make_telegram_body(text, update_id=1001):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": "12345", "is_bot": False, "first_name": "Test"},
            "chat": {"id": 12345, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


FAKE_MSG_PAYLOAD = {
    "id": "msg123",
    "threadId": "thread456",
    "snippet": "Olá, tudo bem?",
    "labelIds": ["INBOX", "UNREAD"],
    "payload": {
        "headers": [
            {"name": "Subject", "value": "Reunião amanhã"},
            {"name": "From", "value": "João Silva <joao@example.com>"},
            {"name": "To", "value": "eu@example.com"},
            {"name": "Date", "value": "Mon, 15 Mar 2026 10:00:00 -0300"},
            {"name": "Message-ID", "value": "<abc123@mail.gmail.com>"},
            {"name": "References", "value": "<ref1@mail.gmail.com>"},
        ],
        "mimeType": "text/plain",
        "body": {
            "data": base64.urlsafe_b64encode(b"Oi, vamos reunir amanha?").decode(),
        },
    },
}


class TestGmailUtils:
    def test_extract_header(self):
        headers = [{"name": "Subject", "value": "Test"}, {"name": "From", "value": "a@b.com"}]
        assert extract_header(headers, "Subject") == "Test"
        assert extract_header(headers, "from") == "a@b.com"
        assert extract_header(headers, "Missing") == ""

    def test_extract_message_fields(self):
        fields = extract_message_fields(FAKE_MSG_PAYLOAD)
        assert fields["id"] == "msg123"
        assert fields["threadId"] == "thread456"
        assert fields["subject"] == "Reunião amanhã"
        assert "joao@example.com" in fields["from"]
        assert fields["message_id"] == "<abc123@mail.gmail.com>"
        assert fields["references"] == "<ref1@mail.gmail.com>"

    def test_extract_plain_body(self):
        body = extract_plain_body(FAKE_MSG_PAYLOAD["payload"])
        assert "reunir" in body.lower()

    def test_extract_plain_body_multipart(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(b"Plain text body").decode()},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<p>HTML body</p>").decode()},
                },
            ],
        }
        body = extract_plain_body(payload)
        assert body == "Plain text body"

    def test_strip_quoted_text(self):
        text = "Obrigado!\n\nOn Mon, 15 Mar 2026, someone wrote:\n> old text"
        stripped = strip_quoted_text(text)
        assert "Obrigado" in stripped
        assert "old text" not in stripped

    def test_strip_quoted_text_pt(self):
        text = "OK, combinado.\n\nEm seg, 15 mar 2026, alguém escreveu:\n> texto antigo"
        stripped = strip_quoted_text(text)
        assert "combinado" in stripped
        assert "texto antigo" not in stripped

    def test_build_mime_message(self):
        raw = build_mime_message("to@test.com", "Test Subject", "Hello body")
        decoded = base64.urlsafe_b64decode(raw).decode()
        assert "To: to@test.com" in decoded
        assert "Subject: Test Subject" in decoded
        assert "SGVsbG8gYm9keQ==" in decoded or "Hello body" in decoded

    def test_build_mime_reply_headers(self):
        raw = build_mime_reply(
            to="sender@test.com",
            body="My reply",
            original_message_id="<orig@mail.gmail.com>",
            original_references="<ref1@mail.gmail.com>",
            original_subject="Original Subject",
        )
        decoded = base64.urlsafe_b64decode(raw).decode()
        assert "In-Reply-To: <orig@mail.gmail.com>" in decoded
        assert "<ref1@mail.gmail.com> <orig@mail.gmail.com>" in decoded
        assert "Subject: Re: Original Subject" in decoded

    def test_build_mime_reply_already_re(self):
        raw = build_mime_reply(
            to="sender@test.com",
            body="Reply",
            original_message_id="<orig@mail.gmail.com>",
            original_references="",
            original_subject="Re: Already replied",
        )
        decoded = base64.urlsafe_b64decode(raw).decode()
        assert "Subject: Re: Already replied" in decoded
        assert "Subject: Re: Re:" not in decoded

    def test_format_message_for_telegram(self):
        fields = {"from": "João <joao@test.com>", "subject": "Test", "snippet": "Hello", "id": "msg1", "threadId": "t1"}
        formatted = format_message_for_telegram(fields, index=1)
        assert "João" in formatted
        assert "Test" in formatted
        assert "msg1" in formatted
        assert "t1" in formatted

    def test_format_messages_list_telegram_empty(self):
        result = format_messages_list_telegram([])
        assert "Nenhum" in result

    def test_date_to_gmail_after_query(self):
        result = date_to_gmail_after_query(2026, 3, 15)
        assert result.startswith("after:")
        assert int(result.split(":")[1]) > 0


class TestGmailCommands:
    def test_inbox_not_connected(self, client, db_session):
        body = _make_telegram_body("/inbox", update_id=2001)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_inbox_no_gmail_scopes(self, client, db_session):
        _make_cred(db_session, scope=NO_GMAIL_SCOPES)
        body = _make_telegram_body("/inbox", update_id=2002)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_inbox_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().messages().list().execute.return_value = {
            "messages": [{"id": "m1"}]
        }
        mock_gmail.users().messages().get().execute.return_value = FAKE_MSG_PAYLOAD
        body = _make_telegram_body("/inbox", update_id=2003)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_emailsearch_no_query(self, client, db_session):
        body = _make_telegram_body("/emailsearch", update_id=2004)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_emailsearch_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().messages().list().execute.return_value = {"messages": []}
        body = _make_telegram_body("/emailsearch from:test@test.com", update_id=2005)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_thread_no_id(self, client, db_session):
        body = _make_telegram_body("/thread", update_id=2006)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_thread_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().threads().get().execute.return_value = {
            "messages": [FAKE_MSG_PAYLOAD]
        }
        body = _make_telegram_body("/thread thread456", update_id=2007)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_draftemail_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().drafts().create().execute.return_value = {"id": "draft1"}
        body = _make_telegram_body("/draftemail joao@test.com | Teste | Corpo do email", update_id=2008)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_draftemail_missing_parts(self, client, db_session):
        body = _make_telegram_body("/draftemail joao@test.com", update_id=2009)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_replydraft_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().messages().get().execute.return_value = FAKE_MSG_PAYLOAD
        mock_gmail.users().drafts().create().execute.return_value = {"id": "draft_reply1"}
        body = _make_telegram_body("/replydraft msg123 | Obrigado, confirmo!", update_id=2010)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_replydraft_missing_parts(self, client, db_session):
        body = _make_telegram_body("/replydraft", update_id=2011)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_senddraft_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().drafts().send().execute.return_value = {"id": "sent1"}
        body = _make_telegram_body("/senddraft draft1", update_id=2012)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_senddraft_no_id(self, client, db_session):
        body = _make_telegram_body("/senddraft", update_id=2013)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_inboxsummary_success(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().messages().list().execute.return_value = {
            "messages": [{"id": "m1"}]
        }
        mock_gmail.users().messages().get().execute.return_value = FAKE_MSG_PAYLOAD
        body = _make_telegram_body("/inboxsummary", update_id=2014)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    @patch("app.services.google_gmail_service._get_gmail_service")
    def test_drafts_list(self, mock_svc, client, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().drafts().list().execute.return_value = {"drafts": []}
        body = _make_telegram_body("/drafts", update_id=2015)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200


class TestConnectGoogleReconsent:
    def test_connectgoogle_shows_reconsent_message_when_no_gmail_scopes(self, client, db_session, monkeypatch):
        monkeypatch.setattr("app.config.settings.app_base_url", "https://test.replit.app")
        monkeypatch.setattr("app.config.settings.google_client_id", "test-id")
        _make_cred(db_session, scope=NO_GMAIL_SCOPES)
        body = _make_telegram_body("/connectgoogle", update_id=3001)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200

    def test_connectgoogle_normal_when_fully_connected(self, client, db_session, monkeypatch):
        monkeypatch.setattr("app.config.settings.app_base_url", "https://test.replit.app")
        monkeypatch.setattr("app.config.settings.google_client_id", "test-id")
        _make_cred(db_session, scope=GMAIL_SCOPES)
        body = _make_telegram_body("/connectgoogle", update_id=3002)
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
        assert resp.status_code == 200


class TestGmailOAuthStatus:
    def test_status_not_connected(self, client, db_session):
        resp = client.get("/auth/google/status")
        data = resp.json()
        assert data["connected"] is False
        assert data["gmail_enabled"] is False

    def test_status_with_gmail_scopes(self, client, db_session):
        _make_cred(db_session, scope=GMAIL_SCOPES)
        resp = client.get("/auth/google/status")
        data = resp.json()
        assert data["connected"] is True
        assert data["gmail_enabled"] is True
        assert data["calendar_enabled"] is True
        assert data["tasks_enabled"] is True

    def test_status_without_gmail_scopes(self, client, db_session):
        _make_cred(db_session, scope=NO_GMAIL_SCOPES)
        resp = client.get("/auth/google/status")
        data = resp.json()
        assert data["connected"] is True
        assert data["gmail_enabled"] is False
        assert data["calendar_enabled"] is True
        assert data["tasks_enabled"] is True


class TestGmailToolExecutor:
    @pytest.mark.asyncio
    async def test_send_email_draft_with_draft_id_returns_instruction(self, db_session):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("send_email_draft", {"draft_id": "d123"}, db_session, "12345")
        assert result["status"] == "draft_only"
        assert "/senddraft" in result["message"]

    @patch("app.services.google_gmail_service._get_gmail_service")
    @pytest.mark.asyncio
    async def test_send_email_draft_with_composition_creates_draft(self, mock_svc, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail
        mock_gmail.users().drafts().create().execute.return_value = {"id": "auto_draft_1"}

        from app.services.assistant_service import tool_executor
        result = await tool_executor(
            "send_email_draft",
            {"to": "test@test.com", "subject": "Hello", "body": "Hi there"},
            db_session, "12345"
        )
        assert result["status"] == "draft_created"
        assert result["draft_id"] == "auto_draft_1"
        assert "/senddraft" in result["message"]

    @pytest.mark.asyncio
    async def test_get_inbox_summary_no_db(self):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("get_inbox_summary", {}, None, "12345")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_gmail_connection_status_no_db(self):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("get_gmail_connection_status", {}, None, "12345")
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_search_emails_not_connected(self, db_session):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("search_emails", {"query": "test"}, db_session, "12345")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_email_draft_not_connected(self, db_session):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("create_email_draft", {"to": "a@b.com", "subject": "t", "body": "b"}, db_session, "12345")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_reply_draft_not_connected(self, db_session):
        from app.services.assistant_service import tool_executor
        result = await tool_executor("create_reply_draft", {"message_id": "m1", "body": "r"}, db_session, "12345")
        assert "error" in result


class TestReplyDraftHeaders:
    @patch("app.services.google_gmail_service._get_gmail_service")
    @pytest.mark.asyncio
    async def test_reply_draft_includes_in_reply_to_and_references(self, mock_svc, db_session):
        _make_cred(db_session)
        mock_gmail = MagicMock()
        mock_svc.return_value = mock_gmail

        mock_gmail.users().messages().get().execute.return_value = FAKE_MSG_PAYLOAD
        mock_gmail.users().drafts().create().execute.return_value = {"id": "reply_draft_1"}

        from app.services.google_gmail_service import create_reply_draft
        result = await create_reply_draft(db_session, "12345", message_id="msg123", body="Obrigado!")

        assert "error" not in result
        assert result["draft_id"] == "reply_draft_1"
        assert result["thread_id"] == "thread456"

        create_call = mock_gmail.users().drafts().create
        call_kwargs = create_call.call_args
        draft_body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][0] if call_kwargs[0] else {}
        if not draft_body and hasattr(create_call, 'call_args_list'):
            for c in create_call.call_args_list:
                if c.kwargs.get("body"):
                    draft_body = c.kwargs["body"]
                    break

        msg_data = draft_body.get("message", {})
        raw = msg_data.get("raw", "")
        if raw:
            decoded = base64.urlsafe_b64decode(raw).decode()
            assert "In-Reply-To: <abc123@mail.gmail.com>" in decoded
            assert "<ref1@mail.gmail.com>" in decoded

        assert msg_data.get("threadId") == "thread456"


class TestMeDayWithGmail:
    @patch("app.services.google_gmail_service._get_gmail_service")
    @patch("app.services.google_calendar.list_today_events", new_callable=AsyncMock)
    @patch("app.services.google_tasks.list_tasks", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_myday_includes_emails_when_gmail_connected(
        self, mock_tasks, mock_cal, mock_gmail_svc, db_session
    ):
        _make_cred(db_session)
        mock_cal.return_value = []
        mock_tasks.return_value = []

        mock_gmail = MagicMock()
        mock_gmail_svc.return_value = mock_gmail
        mock_gmail.users().messages().list().execute.return_value = {
            "messages": [{"id": "m1"}]
        }
        mock_gmail.users().messages().get().execute.return_value = FAKE_MSG_PAYLOAD

        from app.services.assistant_service import get_real_or_mock_day_overview
        overview = await get_real_or_mock_day_overview(db_session, "12345")
        assert len(overview.emails) >= 1
        assert overview.emails[0].subject == "Reunião amanhã"

    @pytest.mark.asyncio
    async def test_myday_no_emails_when_not_connected(self, db_session):
        from app.services.assistant_service import get_real_or_mock_day_overview
        overview = await get_real_or_mock_day_overview(db_session, "12345")
        assert len(overview.emails) == 0
