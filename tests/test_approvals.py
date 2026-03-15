import json
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone, timedelta

from app.models.pending_approval import PendingApproval
from app.services import approval_service


class TestCreateApproval:
    def test_create_basic_approval(self, db_session):
        result = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_email_draft",
            title="Enviar e-mail para João",
            summary="Follow-up da proposta comercial",
            payload={"draft_id": "abc123"},
        )
        assert result is not None
        assert result.status == "pending"
        assert result.action_type == "send_email_draft"
        assert result.title == "Enviar e-mail para João"
        assert result.expires_at is not None

    def test_create_with_idempotency_key(self, db_session):
        a1 = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_email_draft",
            title="Test",
            summary="Test summary",
            idempotency_key="unique_key_1",
        )
        a2 = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_email_draft",
            title="Test duplicate",
            summary="Test summary 2",
            idempotency_key="unique_key_1",
        )
        assert a1.id == a2.id

    def test_max_pending_limit(self, db_session, monkeypatch):
        monkeypatch.setattr("app.services.approval_service.settings.max_pending_approvals", 2)
        approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="A1", summary="S1",
        )
        approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="A2", summary="S2",
        )
        result = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="A3", summary="S3",
        )
        assert result is None

    def test_action_log_created(self, db_session):
        from app.models.action_log import ActionLog
        approval_service.create_pending_approval(
            db_session, "12345",
            action_type="create_followup_task",
            title="Test", summary="S",
        )
        log = db_session.query(ActionLog).filter(
            ActionLog.event_type == "approval_created"
        ).first()
        assert log is not None


class TestListApprovals:
    def test_list_pending(self, db_session):
        approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="A1", summary="S1",
        )
        approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="A2", summary="S2",
        )
        result = approval_service.list_pending_approvals(db_session, "12345")
        assert len(result) == 2

    def test_expired_auto_cleanup(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Old", summary="S", expires_in_hours=0,
        )
        a.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        result = approval_service.list_pending_approvals(db_session, "12345")
        assert len(result) == 0
        db_session.refresh(a)
        assert a.status == "expired"

    def test_different_users(self, db_session):
        approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="User1", summary="S",
        )
        approval_service.create_pending_approval(
            db_session, "67890", action_type="send_email_draft",
            title="User2", summary="S",
        )
        assert len(approval_service.list_pending_approvals(db_session, "12345")) == 1
        assert len(approval_service.list_pending_approvals(db_session, "67890")) == 1


class TestApproveReject:
    def test_approve(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        result = approval_service.approve_pending_approval(db_session, "12345", a.id)
        assert result["status"] == "approved"

    def test_approve_already_approved(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        approval_service.approve_pending_approval(db_session, "12345", a.id)
        result = approval_service.approve_pending_approval(db_session, "12345", a.id)
        assert result["status"] == "already_approved"

    def test_approve_expired(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        a.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()
        result = approval_service.approve_pending_approval(db_session, "12345", a.id)
        assert "error" in result
        assert "expirou" in result["error"]

    def test_reject(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        result = approval_service.reject_pending_approval(db_session, "12345", a.id)
        assert result["status"] == "rejected"

    def test_reject_already_rejected(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        approval_service.reject_pending_approval(db_session, "12345", a.id)
        result = approval_service.reject_pending_approval(db_session, "12345", a.id)
        assert result["status"] == "already_rejected"

    def test_approve_nonexistent(self, db_session):
        result = approval_service.approve_pending_approval(db_session, "12345", 9999)
        assert "error" in result

    def test_action_log_on_approve(self, db_session):
        from app.models.action_log import ActionLog
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        approval_service.approve_pending_approval(db_session, "12345", a.id)
        log = db_session.query(ActionLog).filter(
            ActionLog.event_type == "approval_approved"
        ).first()
        assert log is not None

    def test_action_log_on_reject(self, db_session):
        from app.models.action_log import ActionLog
        a = approval_service.create_pending_approval(
            db_session, "12345", action_type="send_email_draft",
            title="Test", summary="S",
        )
        approval_service.reject_pending_approval(db_session, "12345", a.id)
        log = db_session.query(ActionLog).filter(
            ActionLog.event_type == "approval_rejected"
        ).first()
        assert log is not None


class TestExecuteApproval:
    @pytest.mark.asyncio
    async def test_execute_idempotent(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_proactive_followup_message",
            title="Test", summary="S",
            payload={"message": "Hello"},
        )
        approval_service.approve_pending_approval(db_session, "12345", a.id)
        r1 = await approval_service.execute_approved_action(db_session, "12345", a.id)
        assert r1["status"] == "executed"
        r2 = await approval_service.execute_approved_action(db_session, "12345", a.id)
        assert r2["status"] == "already_executed"

    @pytest.mark.asyncio
    async def test_execute_unapproved(self, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_proactive_followup_message",
            title="Test", summary="S",
        )
        result = await approval_service.execute_approved_action(db_session, "12345", a.id)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_action_log_on_execute(self, db_session):
        from app.models.action_log import ActionLog
        a = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_proactive_followup_message",
            title="Test", summary="S",
            payload={"message": "Hello"},
        )
        approval_service.approve_pending_approval(db_session, "12345", a.id)
        await approval_service.execute_approved_action(db_session, "12345", a.id)
        log = db_session.query(ActionLog).filter(
            ActionLog.event_type == "approval_executed"
        ).first()
        assert log is not None


class TestTelegramApprovalCommands:
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

    def test_approvals_empty(self, client, db_session):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/approvals", 100),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_approvals_with_pending(self, client, db_session):
        approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_email_draft",
            title="Enviar e-mail",
            summary="Test",
        )
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/approvals", 101),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_approve_command(self, client, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_proactive_followup_message",
            title="Test", summary="S",
            payload={"message": "Hello"},
        )
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update(f"/approve {a.id}", 102),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_reject_command(self, client, db_session):
        a = approval_service.create_pending_approval(
            db_session, "12345",
            action_type="send_email_draft",
            title="Test", summary="S",
        )
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update(f"/reject {a.id}", 103),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_approve_invalid_id(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/approve abc", 104),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200
