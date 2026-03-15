import json
import pytest
from unittest.mock import patch, AsyncMock

from app.models.workflow_run import WorkflowRun
from app.models.pending_approval import PendingApproval
from app.models.suggestion_log import SuggestionLog
from app.models.memory_item import MemoryItem
from app.services import workflow_service


class TestLeadFollowup:
    @pytest.mark.asyncio
    @patch("app.services.google_gmail_service.create_draft", new_callable=AsyncMock)
    @patch("app.services.google_tasks.create_task", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_full_lead_followup(self, mock_status, mock_task, mock_draft, db_session):
        mock_status.return_value = {"connected": True, "gmail_enabled": True}
        mock_task.return_value = {"title": "Follow-up: Empresa X"}
        mock_draft.return_value = {"draft_id": "draft123", "message": "Rascunho criado"}

        result = await workflow_service.run_workflow(
            db_session, "12345", "lead_followup",
            ["Empresa X", "contato@x.com", "follow-up da proposta"],
        )
        assert "Empresa X" in result
        assert "contato@x.com" in result

        run = db_session.query(WorkflowRun).filter(
            WorkflowRun.workflow_name == "lead_followup"
        ).first()
        assert run is not None
        assert run.status == "completed"

        approval = db_session.query(PendingApproval).filter(
            PendingApproval.action_type == "send_email_draft"
        ).first()
        assert approval is not None

        memory = db_session.query(MemoryItem).filter(
            MemoryItem.category == "followup"
        ).first()
        assert memory is not None

    @pytest.mark.asyncio
    async def test_lead_followup_missing_params(self, db_session):
        result = await workflow_service.run_workflow(
            db_session, "12345", "lead_followup", ["only_company"],
        )
        assert "Parâmetros insuficientes" in result

    @pytest.mark.asyncio
    @patch("app.services.google_oauth_service.get_status")
    async def test_lead_followup_no_google(self, mock_status, db_session):
        mock_status.return_value = {"connected": False}
        result = await workflow_service.run_workflow(
            db_session, "12345", "lead_followup",
            ["Empresa", "email@test.com", "contexto"],
        )
        assert "Google não conectado" in result


class TestMeetingPrep:
    @pytest.mark.asyncio
    @patch("app.services.google_calendar.list_upcoming_events", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_meeting_prep_with_event(self, mock_status, mock_events, db_session):
        mock_status.return_value = {"connected": True, "gmail_enabled": False}
        mock_events.return_value = [
            {"title": "Sprint Review", "start": "2026-03-16 14:00", "end": "2026-03-16 15:00", "location": "Zoom", "description": "Review sprint 42"},
        ]
        result = await workflow_service.run_workflow(db_session, "12345", "meeting_prep", [])
        assert "Sprint Review" in result
        assert "Pauta sugerida" in result

        run = db_session.query(WorkflowRun).filter(
            WorkflowRun.workflow_name == "meeting_prep"
        ).first()
        assert run is not None
        assert run.status == "completed"

    @pytest.mark.asyncio
    @patch("app.services.google_calendar.list_upcoming_events", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_meeting_prep_no_events(self, mock_status, mock_events, db_session):
        mock_status.return_value = {"connected": True}
        mock_events.return_value = []
        result = await workflow_service.run_workflow(db_session, "12345", "meeting_prep", [])
        assert "Nenhum evento" in result

    @pytest.mark.asyncio
    @patch("app.services.google_oauth_service.get_status")
    async def test_meeting_prep_no_google(self, mock_status, db_session):
        mock_status.return_value = {"connected": False}
        result = await workflow_service.run_workflow(db_session, "12345", "meeting_prep", [])
        assert "não conectado" in result


class TestInboxTriage:
    @pytest.mark.asyncio
    @patch("app.services.google_gmail_service.get_priority_emails", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_inbox_triage_with_emails(self, mock_status, mock_emails, db_session):
        mock_status.return_value = {"connected": True, "gmail_enabled": True}
        mock_emails.return_value = [
            {"subject": "Proposta comercial", "from": "joao@test.com", "snippet": "Olá, segue proposta"},
            {"subject": "Reunião amanhã", "from": "Maria <maria@test.com>", "snippet": "Confirma?"},
        ]
        result = await workflow_service.run_workflow(db_session, "12345", "inbox_triage", [])
        assert "Proposta comercial" in result
        assert "2 e-mail(s)" in result

        suggestions = db_session.query(SuggestionLog).all()
        assert len(suggestions) == 2

        run = db_session.query(WorkflowRun).filter(
            WorkflowRun.workflow_name == "inbox_triage"
        ).first()
        assert run is not None
        assert run.status == "completed"

    @pytest.mark.asyncio
    @patch("app.services.google_gmail_service.get_priority_emails", new_callable=AsyncMock)
    @patch("app.services.google_oauth_service.get_status")
    async def test_inbox_triage_empty(self, mock_status, mock_emails, db_session):
        mock_status.return_value = {"connected": True, "gmail_enabled": True}
        mock_emails.return_value = []
        result = await workflow_service.run_workflow(db_session, "12345", "inbox_triage", [])
        assert "Inbox limpa" in result

    @pytest.mark.asyncio
    @patch("app.services.google_oauth_service.get_status")
    async def test_inbox_triage_no_gmail(self, mock_status, db_session):
        mock_status.return_value = {"connected": True, "gmail_enabled": False}
        result = await workflow_service.run_workflow(db_session, "12345", "inbox_triage", [])
        assert "não conectado" in result or "não autorizado" in result


class TestInvalidWorkflow:
    @pytest.mark.asyncio
    async def test_unknown_workflow(self, db_session):
        result = await workflow_service.run_workflow(db_session, "12345", "nonexistent", [])
        assert "não encontrado" in result


class TestListPlaybooks:
    def test_lists_all(self):
        result = workflow_service.list_playbooks()
        assert "lead_followup" in result
        assert "meeting_prep" in result
        assert "inbox_triage" in result


class TestTelegramWorkflowCommands:
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

    def test_playbooks_command(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/playbooks", 300),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_runworkflow_empty(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/runworkflow", 301),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    @patch("app.services.google_oauth_service.get_status")
    def test_runworkflow_meeting_prep(self, mock_status, client):
        mock_status.return_value = {"connected": False}
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/runworkflow meeting_prep", 302),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_runworkflow_invalid(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/runworkflow nonexistent", 303),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_runworkflow_lead_with_params(self, client):
        resp = client.post(
            "/webhooks/telegram",
            json=self._build_update("/runworkflow lead_followup | only_company", 304),
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200
