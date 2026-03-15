import json
import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.models.voice_message_log import VoiceMessageLog
from app.models.memory_item import MemoryItem


HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


def _make_voice_body(update_id=5001, user_id=12345, file_id="voice_file_1", duration=5, file_size=8000, mime_type="audio/ogg"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 100,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "voice": {
                "file_id": file_id,
                "file_unique_id": f"unique_{file_id}",
                "duration": duration,
                "mime_type": mime_type,
                "file_size": file_size,
            },
        },
    }


def _make_audio_body(update_id=5002, user_id=12345, file_id="audio_file_1", duration=10, file_size=12000, mime_type="audio/mpeg"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 101,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "audio": {
                "file_id": file_id,
                "file_unique_id": f"unique_{file_id}",
                "duration": duration,
                "mime_type": mime_type,
                "file_size": file_size,
                "title": "Test Audio",
                "file_name": "test.mp3",
            },
        },
    }


def _make_text_body(text, update_id=5099, user_id=12345):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 200,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": text,
        },
    }


class TestVoiceReceived:
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_voice_with_valid_secret(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        mock_transcribe.return_value = {"text": "olá mundo", "raw_json": None, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(), headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "voice_processed"

        mock_download.assert_called_once()
        mock_transcribe.assert_called_once()

    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_audio_with_valid_secret(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        mock_transcribe.return_value = {"text": "teste áudio", "raw_json": None, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_audio_body(), headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "audio_processed"

    def test_voice_unauthorized_user(self, client, db_session, _patch_telegram_send):
        body = _make_voice_body(user_id=99999)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["message"] == "ignored"

    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_voice_duplicate_update(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        mock_transcribe.return_value = {"text": "olá", "raw_json": None, "error": None}

        body = _make_voice_body(update_id=5010)
        client.post("/webhooks/telegram", json=body, headers=HEADERS)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["message"] == "duplicate"

    def test_voice_invalid_secret(self, client, db_session):
        body = _make_voice_body()
        resp = client.post("/webhooks/telegram", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        assert resp.status_code == 403


class TestTranscription:
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_transcription_success(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        mock_transcribe.return_value = {"text": "criar uma tarefa para amanhã", "raw_json": None, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5020), headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args_list[0][0][1]
        assert "criar uma tarefa para amanhã" in sent_text

        voice_log = db_session.query(VoiceMessageLog).first()
        assert voice_log is not None
        assert voice_log.transcription_text == "criar uma tarefa para amanhã"
        assert voice_log.processing_status == "completed"

    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_transcription_failure(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        mock_transcribe.return_value = {"text": None, "raw_json": None, "error": "Modelo não disponível"}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5021), headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "transcrever" in sent_text.lower() or "Modelo não disponível" in sent_text

        voice_log = db_session.query(VoiceMessageLog).first()
        assert voice_log is not None
        assert voice_log.processing_status == "transcription_failed"

    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_transcription_empty(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        mock_transcribe.return_value = {"text": "   ", "raw_json": None, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5022), headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "vazia" in sent_text.lower() or "vazio" in sent_text.lower()

    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_transcription_raw_json_stored(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio_data"
        raw = '{"logprobs": [0.95, 0.88]}'
        mock_transcribe.return_value = {"text": "teste", "raw_json": raw, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5023), headers=HEADERS)
        assert resp.status_code == 200

        voice_log = db_session.query(VoiceMessageLog).first()
        assert voice_log.transcription_raw_json == raw


class TestAssistantIntegration:
    @patch("app.routes.telegram.handle_free_text", new_callable=AsyncMock)
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_assistant_called_with_transcription(self, mock_download, mock_transcribe, mock_handle, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "qual é minha agenda de hoje?", "raw_json": None, "error": None}
        mock_handle.return_value = "Você tem 2 reuniões hoje."

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5030), headers=HEADERS)
        assert resp.status_code == 200

        mock_handle.assert_called_once()
        call_args = mock_handle.call_args
        assert call_args[0][2] == "qual é minha agenda de hoje?"

    @patch("app.routes.telegram.handle_free_text", new_callable=AsyncMock)
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_text_response_sent(self, mock_download, mock_transcribe, mock_handle, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "bom dia", "raw_json": None, "error": None}
        mock_handle.return_value = "Bom dia! Como posso ajudar?"

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5031), headers=HEADERS)
        assert resp.status_code == 200

        assert _patch_telegram_send.call_count >= 1
        first_call_text = _patch_telegram_send.call_args_list[0][0][1]
        assert "bom dia" in first_call_text.lower()


class TestVoiceResponse:
    @patch("app.services.audio_service.synthesize_speech", new_callable=AsyncMock)
    @patch("app.services.audio_service.maybe_should_reply_with_voice")
    @patch("app.routes.telegram.handle_free_text", new_callable=AsyncMock)
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_voice_response_when_enabled(self, mock_download, mock_transcribe, mock_handle, mock_should, mock_synth, client, db_session, _patch_telegram_send, monkeypatch):
        mock_send_voice = AsyncMock(return_value={"ok": True})
        monkeypatch.setattr("app.services.telegram_service.send_voice", mock_send_voice)

        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "olá", "raw_json": None, "error": None}
        mock_handle.return_value = "Olá! Tudo bem?"
        mock_should.return_value = True
        mock_synth.return_value = {"audio_bytes": b"tts_audio_data", "format": "opus", "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5040), headers=HEADERS)
        assert resp.status_code == 200

        mock_synth.assert_called_once()
        mock_send_voice.assert_called_once()

        voice_log = db_session.query(VoiceMessageLog).first()
        assert voice_log is not None
        assert voice_log.tts_generated is True

    @patch("app.services.audio_service.maybe_should_reply_with_voice")
    @patch("app.routes.telegram.handle_free_text", new_callable=AsyncMock)
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_no_voice_response_when_disabled(self, mock_download, mock_transcribe, mock_handle, mock_should, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "olá", "raw_json": None, "error": None}
        mock_handle.return_value = "Olá!"
        mock_should.return_value = False

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5041), headers=HEADERS)
        assert resp.status_code == 200

    @patch("app.services.audio_service.synthesize_speech", new_callable=AsyncMock)
    @patch("app.services.audio_service.maybe_should_reply_with_voice")
    @patch("app.routes.telegram.handle_free_text", new_callable=AsyncMock)
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_fallback_to_send_audio(self, mock_download, mock_transcribe, mock_handle, mock_should, mock_synth, client, db_session, _patch_telegram_send, monkeypatch):
        mock_send_voice = AsyncMock(side_effect=Exception("sendVoice failed"))
        mock_send_audio = AsyncMock(return_value={"ok": True})
        monkeypatch.setattr("app.services.telegram_service.send_voice", mock_send_voice)
        monkeypatch.setattr("app.services.telegram_service.send_audio", mock_send_audio)

        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "olá", "raw_json": None, "error": None}
        mock_handle.return_value = "Resposta"
        mock_should.return_value = True
        mock_synth.return_value = {"audio_bytes": b"tts_data", "format": "mp3", "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5042), headers=HEADERS)
        assert resp.status_code == 200

        mock_send_voice.assert_called_once()
        mock_send_audio.assert_called_once()


class TestTempFileCleanup:
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_temp_file_cleaned_on_success(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send, tmp_path, monkeypatch):
        monkeypatch.setattr("app.config.settings.temp_audio_dir", str(tmp_path))
        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "olá", "raw_json": None, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5050), headers=HEADERS)
        assert resp.status_code == 200

        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0

    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_temp_file_cleaned_on_error(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send, tmp_path, monkeypatch):
        monkeypatch.setattr("app.config.settings.temp_audio_dir", str(tmp_path))
        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": None, "error": "fail", "raw_json": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5051), headers=HEADERS)
        assert resp.status_code == 200

        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0


class TestFileSizeLimit:
    def test_oversized_audio_rejected(self, client, db_session, _patch_telegram_send):
        body = _make_voice_body(update_id=5060, file_size=20 * 1024 * 1024 + 1)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "grande" in sent_text.lower() or "limite" in sent_text.lower()


class TestVoiceCommands:
    def test_voiceon(self, client, db_session, _patch_telegram_send):
        body = _make_text_body("/voiceon", update_id=5070)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "áudio" in sent_text.lower() or "ativad" in sent_text.lower()

        pref = db_session.query(MemoryItem).filter(
            MemoryItem.user_id == "12345",
            MemoryItem.category == "voice_preference",
        ).first()
        assert pref is not None

    def test_voiceoff(self, client, db_session, _patch_telegram_send):
        body_on = _make_text_body("/voiceon", update_id=5071)
        client.post("/webhooks/telegram", json=body_on, headers=HEADERS)

        body_off = _make_text_body("/voiceoff", update_id=5072)
        resp = client.post("/webhooks/telegram", json=body_off, headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "desativad" in sent_text.lower() or "texto" in sent_text.lower()

        pref = db_session.query(MemoryItem).filter(
            MemoryItem.user_id == "12345",
            MemoryItem.category == "voice_preference",
            MemoryItem.is_active == True,
        ).first()
        assert pref is None

    def test_voicestatus(self, client, db_session, _patch_telegram_send):
        body = _make_text_body("/voicestatus", update_id=5073)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "Status" in sent_text or "status" in sent_text
        assert "Global" in sent_text
        assert "preferência" in sent_text.lower() or "Sua" in sent_text

    def test_voicestatus_shows_active_when_both_enabled(self, client, db_session, _patch_telegram_send, monkeypatch):
        monkeypatch.setattr("app.config.settings.voice_responses_enabled", True)

        body_on = _make_text_body("/voiceon", update_id=5074)
        client.post("/webhooks/telegram", json=body_on, headers=HEADERS)

        body_status = _make_text_body("/voicestatus", update_id=5075)
        resp = client.post("/webhooks/telegram", json=body_status, headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "ativo" in sent_text.lower()

    def test_transcribe_command(self, client, db_session, _patch_telegram_send):
        body = _make_text_body("/transcribe", update_id=5076)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200

        sent_text = _patch_telegram_send.call_args[0][1]
        assert "nota de voz" in sent_text.lower() or "áudio" in sent_text.lower()


class TestVoiceMessageLog:
    @patch("app.services.audio_service.transcribe_file", new_callable=AsyncMock)
    @patch("app.services.telegram_service.download_file", new_callable=AsyncMock)
    def test_voice_log_created(self, mock_download, mock_transcribe, client, db_session, _patch_telegram_send):
        mock_download.return_value = b"fake_audio"
        mock_transcribe.return_value = {"text": "teste log", "raw_json": None, "error": None}

        resp = client.post("/webhooks/telegram", json=_make_voice_body(update_id=5080), headers=HEADERS)
        assert resp.status_code == 200

        log = db_session.query(VoiceMessageLog).first()
        assert log is not None
        assert log.user_id == "12345"
        assert log.telegram_file_id == "voice_file_1"
        assert log.transcription_text == "teste log"
        assert log.processing_status == "completed"
        assert log.mime_type == "audio/ogg"
        assert log.duration_seconds == 5


class TestExistingCommandsNotBroken:
    def test_text_commands_still_work(self, client, db_session, _patch_telegram_send):
        body = _make_text_body("/help", update_id=5090)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200
        sent_text = _patch_telegram_send.call_args[0][1]
        assert "Comandos disponíveis" in sent_text
        assert "/voiceon" in sent_text

    def test_start_command_still_works(self, client, db_session, _patch_telegram_send):
        body = _make_text_body("/start", update_id=5091)
        resp = client.post("/webhooks/telegram", json=body, headers=HEADERS)
        assert resp.status_code == 200
        sent_text = _patch_telegram_send.call_args[0][1]
        assert "Jarvis" in sent_text
