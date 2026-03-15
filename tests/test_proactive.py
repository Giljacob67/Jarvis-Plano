import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta, time

from app.models.action_log import ActionLog
from app.models.memory_item import MemoryItem
from app.models.suggestion_log import SuggestionLog
from app.services import proactive_service


class TestQuietHours:
    def test_quiet_time_enabled_during_hours(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_enabled", True)
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_start", "22:00")
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_end", "07:00")
        mock_now = MagicMock()
        mock_now.time.return_value = time(23, 30)
        monkeypatch.setattr("app.services.proactive_service._now_in_tz", lambda: mock_now)
        assert proactive_service.is_quiet_time(db_session, "12345") is True

    def test_quiet_time_not_during_hours(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_enabled", True)
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_start", "22:00")
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_end", "07:00")
        mock_now = MagicMock()
        mock_now.time.return_value = time(10, 0)
        monkeypatch.setattr("app.services.proactive_service._now_in_tz", lambda: mock_now)
        assert proactive_service.is_quiet_time(db_session, "12345") is False

    def test_quiet_time_disabled_globally(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_enabled", False)
        assert proactive_service.is_quiet_time(db_session, "12345") is False

    def test_quiet_time_disabled_by_user(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_enabled", True)
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_start", "22:00")
        monkeypatch.setattr("app.services.proactive_service.settings.quiet_hours_end", "07:00")
        mock_now = MagicMock()
        mock_now.time.return_value = time(23, 30)
        monkeypatch.setattr("app.services.proactive_service._now_in_tz", lambda: mock_now)
        proactive_service.set_quiet_hours_preference(db_session, "12345", False)
        assert proactive_service.is_quiet_time(db_session, "12345") is False

    def test_set_quiet_hours_on_off(self, db_session):
        proactive_service.set_quiet_hours_preference(db_session, "12345", False)
        assert proactive_service.get_quiet_hours_preference(db_session, "12345") is False
        proactive_service.set_quiet_hours_preference(db_session, "12345", True)
        assert proactive_service.get_quiet_hours_preference(db_session, "12345") is True


class TestCooldown:
    def test_on_cooldown(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.proactive_min_interval_minutes", 30)
        entry = ActionLog(
            event_type="proactive_message_sent",
            status="success",
            details_json=json.dumps({"user_id": "12345", "subject": "test_subject"}),
        )
        db_session.add(entry)
        db_session.commit()
        assert proactive_service.is_on_cooldown(db_session, "12345", "test_subject") is True

    def test_not_on_cooldown_different_subject(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.proactive_min_interval_minutes", 30)
        entry = ActionLog(
            event_type="proactive_message_sent",
            status="success",
            details_json=json.dumps({"user_id": "12345", "subject": "other_subject"}),
        )
        db_session.add(entry)
        db_session.commit()
        assert proactive_service.is_on_cooldown(db_session, "12345", "test_subject") is False

    def test_not_on_cooldown_after_interval(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.settings.proactive_min_interval_minutes", 30)
        entry = ActionLog(
            event_type="proactive_message_sent",
            status="success",
            details_json=json.dumps({"user_id": "12345", "subject": "test_subject"}),
        )
        entry.created_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        db_session.add(entry)
        db_session.commit()
        assert proactive_service.is_on_cooldown(db_session, "12345", "test_subject") is False


class TestCreateSuggestion:
    def test_creates_suggestion_and_log(self, db_session):
        result = proactive_service.create_suggestion(
            db_session, "12345",
            suggestion_type="email_response",
            title="Responder e-mail",
            body="E-mail de João sobre proposta",
        )
        assert result.id is not None
        assert result.suggestion_type == "email_response"
        log = db_session.query(ActionLog).filter(
            ActionLog.event_type == "suggestion_created"
        ).first()
        assert log is not None


class TestSendProactiveMessage:
    @pytest.mark.asyncio
    async def test_skips_during_quiet_hours(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.is_quiet_time", lambda db, uid: True)
        result = await proactive_service.send_proactive_message(db_session, "12345", "Test", "test")
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_on_cooldown(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.proactive_service.is_quiet_time", lambda db, uid: False)
        monkeypatch.setattr("app.services.proactive_service.is_on_cooldown", lambda db, uid, subj: True)
        result = await proactive_service.send_proactive_message(db_session, "12345", "Test", "test")
        assert result is False

    @pytest.mark.asyncio
    async def test_sends_message(self, db_session, monkeypatch, _patch_telegram_send):
        monkeypatch.setattr("app.services.proactive_service.is_quiet_time", lambda db, uid: False)
        monkeypatch.setattr("app.services.proactive_service.is_on_cooldown", lambda db, uid, subj: False)
        monkeypatch.setattr("app.services.proactive_service.settings.telegram_allowed_user_id", "12345")
        result = await proactive_service.send_proactive_message(db_session, "12345", "Test msg", "test")
        assert result is True
        log = db_session.query(ActionLog).filter(
            ActionLog.event_type == "proactive_message_sent"
        ).first()
        assert log is not None


class TestMorningBriefing:
    @pytest.mark.asyncio
    @patch("app.services.google_gmail_service.get_priority_emails", new_callable=AsyncMock)
    @patch("app.services.google_tasks.list_tasks", new_callable=AsyncMock)
    @patch("app.services.google_calendar.list_today_events", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_generates_briefing(self, mock_status, mock_events, mock_tasks, mock_emails, db_session):
        mock_status.return_value = {"connected": True, "gmail_enabled": True}
        mock_events.return_value = [
            {"title": "Daily standup", "start": "09:00", "end": "09:30", "location": "Meet"},
        ]
        mock_tasks.return_value = [
            {"title": "Review PR", "due": "2026-03-15", "status": "needsAction"},
        ]
        mock_emails.return_value = [
            {"subject": "Proposta", "from": "joao@test.com", "snippet": "Olá"},
        ]
        result = await proactive_service.generate_morning_briefing(db_session, "12345")
        assert "Bom dia" in result
        assert "Daily standup" in result
        assert "Review PR" in result
        assert "Proposta" in result

    @pytest.mark.asyncio
    @patch("app.services.google_oauth_service.get_status")
    async def test_briefing_without_google(self, mock_status, db_session):
        mock_status.return_value = {"connected": False}
        result = await proactive_service.generate_morning_briefing(db_session, "12345")
        assert "Bom dia" in result
        assert "Sem eventos" in result


class TestEveningReview:
    @pytest.mark.asyncio
    @patch("app.services.google_calendar.list_upcoming_events", new_callable=AsyncMock)
    @patch("app.services.google_tasks.list_tasks", new_callable=AsyncMock)
    @patch("app.services.google_calendar.list_today_events", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_generates_review(self, mock_status, mock_today, mock_tasks, mock_tomorrow, db_session):
        mock_status.return_value = {"connected": True}
        mock_today.return_value = [{"title": "Meeting", "start": "14:00", "end": "15:00"}]
        mock_tasks.return_value = [
            {"title": "Pending task", "status": "needsAction"},
        ]
        mock_tomorrow.return_value = [
            {"title": "Tomorrow meeting", "start": "2026-03-16T09:00"},
        ]
        result = await proactive_service.generate_evening_review(db_session, "12345")
        assert "Fechamento" in result
        assert "Pending task" in result


class TestCheckUpcomingEvents:
    @pytest.mark.asyncio
    @patch("app.services.google_calendar.list_today_events", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_returns_empty_when_not_connected(self, mock_status, mock_events, db_session):
        mock_status.return_value = {"connected": False}
        result = await proactive_service.check_upcoming_events(db_session, "12345")
        assert result == []


class TestCheckDueTasks:
    @pytest.mark.asyncio
    @patch("app.services.google_tasks.list_tasks", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_returns_due_tasks(self, mock_status, mock_tasks, db_session):
        mock_status.return_value = {"connected": True}
        from datetime import date
        today = date.today().isoformat()
        mock_tasks.return_value = [
            {"title": "Due today", "due": today, "status": "needsAction"},
            {"title": "Not due", "due": "2099-12-31", "status": "needsAction"},
        ]
        result = await proactive_service.check_due_tasks(db_session, "12345")
        assert len(result) == 1
        assert result[0]["title"] == "Due today"


class TestTelegramRoutineCommands:
    def _build_update(self, text, update_id=1):
        return {
            "update_id": update_id,
            "message": {
                "message_id": 1,
                "date": 1234567890,
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 12345, "is_bot": False, "first_name": "Test"},
                "text": text,
            },
        }

    def test_routineon(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/routineon morning", 200),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_routineoff(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/routineoff evening", 201),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_routinestatus(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/routinestatus", 202),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_routineon_invalid(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/routineon invalid", 203),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_quieton(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/quieton", 204),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_quietoff(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/quietoff", 205),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_quietstatus(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/quietstatus", 206),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200


class TestTelegramBriefingReview:
    def _build_update(self, text, update_id=1):
        return {
            "update_id": update_id,
            "message": {
                "message_id": 1,
                "date": 1234567890,
                "chat": {"id": 12345, "type": "private"},
                "from": {"id": 12345, "is_bot": False, "first_name": "Test"},
                "text": text,
            },
        }

    @patch("app.services.google_oauth_service.get_status")
    def test_briefing_command(self, mock_status, client):
        mock_status.return_value = {"connected": False}
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/briefing", 210),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    @patch("app.services.google_oauth_service.get_status")
    def test_review_command(self, mock_status, client):
        mock_status.return_value = {"connected": False}
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/review", 211),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200
