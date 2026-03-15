import json
import logging
import os
import uuid

from fastapi import APIRouter, Header, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.telegram import TelegramUpdate, TelegramWebhookResponse
from app.models.processed_update import ProcessedTelegramUpdate
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.action_log import ActionLog
from app.models.voice_message_log import VoiceMessageLog
from app.services import telegram_service
from app.services.assistant_service import (
    handle_free_text,
    get_real_or_mock_day_overview,
    format_day_overview_text,
    _get_or_create_conversation,
)
from app.services.memory_service import save_memory, list_memories
from app.services import google_oauth_service
from app.services import google_calendar as google_calendar_service
from app.services import google_tasks as google_tasks_service
from app.services import google_gmail_service
from app.services import audio_service
from app.utils.date_utils import parse_datetime_local
from app.utils.gmail_utils import format_messages_list_telegram

logger = logging.getLogger(__name__)

router = APIRouter()

HELP_TEXT = (
    "Comandos disponíveis:\n"
    "/myday — resumo do dia\n"
    "/remember <texto> — salvar uma anotação\n"
    "/memories — listar anotações recentes\n"
    "/connectgoogle — conectar conta Google\n"
    "/google — status da conexão Google\n"
    "/tasks — listar tarefas\n"
    "/newtask <titulo> — criar tarefa\n"
    "/newevent <titulo> | <inicio> | <fim> — criar evento\n"
    "/inbox — e-mails recentes da inbox\n"
    "/emailsearch <consulta> — buscar e-mails\n"
    "/thread <thread_id> — ver thread de e-mail\n"
    "/drafts — listar rascunhos\n"
    "/draftemail <para> | <assunto> | <corpo> — criar rascunho\n"
    "/replydraft <message_id> | <corpo> — responder e-mail (rascunho)\n"
    "/senddraft <draft_id> — enviar rascunho\n"
    "/inboxsummary — resumo da inbox\n"
    "/voiceon — ativar respostas por áudio\n"
    "/voiceoff — desativar respostas por áudio\n"
    "/voicestatus — status das respostas por áudio\n"
    "/help — ver esta mensagem\n\n"
    "Ou envie texto livre ou nota de voz para conversar comigo!"
)

START_TEXT = (
    "Olá! 👋 Sou o Jarvis, seu assistente pessoal de produtividade.\n\n"
    f"{HELP_TEXT}"
)


def _gmail_not_ready_msg(db: Session, user_id: str) -> str | None:
    status = google_oauth_service.get_status(db, user_id)
    if not status.get("connected"):
        return "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
    if not status.get("gmail_enabled"):
        return (
            "⚠️ Sua conta Google está conectada, mas sem permissões de Gmail. "
            "Use /connectgoogle para reconectar com os escopos de Gmail."
        )
    return None


def _log_action(db: Session, event_type: str, status: str, details: dict) -> None:
    entry = ActionLog(
        event_type=event_type,
        status=status,
        details_json=json.dumps(details, ensure_ascii=False),
    )
    db.add(entry)
    db.commit()


async def _handle_voice_message(
    db: Session,
    user_id: str,
    chat_id: int,
    update_id: int,
    file_id: str,
    file_unique_id: str,
    mime_type: str | None,
    duration: int | None,
    file_size: int | None,
    source_type: str,
) -> str:
    conv = _get_or_create_conversation(db, user_id)

    voice_log = VoiceMessageLog(
        user_id=user_id,
        conversation_id=conv.id,
        telegram_update_id=update_id,
        telegram_file_id=file_id,
        telegram_file_unique_id=file_unique_id,
        mime_type=mime_type,
        duration_seconds=duration,
        original_file_size=file_size,
        processing_status="received",
    )
    db.add(voice_log)
    db.commit()
    db.refresh(voice_log)

    _log_action(db, "telegram_voice_received", "success", {
        "user_id": user_id,
        "file_id": file_id,
        "source_type": source_type,
        "duration": duration,
        "file_size": file_size,
    })

    max_mb = settings.effective_max_audio_mb
    if file_size and file_size > max_mb * 1024 * 1024:
        voice_log.processing_status = "error"
        voice_log.error_message = f"Arquivo muito grande: {file_size / (1024*1024):.1f} MB"
        db.commit()
        return f"⚠️ O arquivo de áudio é muito grande ({file_size / (1024*1024):.1f} MB). O limite é {max_mb} MB."

    temp_path = None
    try:
        temp_dir = audio_service.ensure_temp_dir()
        ext = ".ogg" if source_type == "voice" else (".mp3" if not mime_type else _ext_from_mime(mime_type))
        temp_path = str(temp_dir / f"{uuid.uuid4().hex}{ext}")
        voice_log.local_temp_path = temp_path

        audio_bytes = await telegram_service.download_file(file_id)
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        voice_log.processing_status = "transcribing"
        db.commit()

        result = await audio_service.transcribe_file(temp_path)

        if result.get("error"):
            voice_log.processing_status = "transcription_failed"
            voice_log.error_message = result["error"]
            db.commit()
            _log_action(db, "audio_transcription_failed", "error", {
                "user_id": user_id,
                "error": result["error"],
            })
            return f"❌ Não consegui transcrever o áudio: {result['error']}"

        transcription = result.get("text", "")
        voice_log.transcription_text = transcription
        voice_log.transcription_model = settings.openai_transcribe_model
        voice_log.transcription_raw_json = result.get("raw_json")
        voice_log.processing_status = "transcribed"
        db.commit()

        _log_action(db, "audio_transcribed", "success", {
            "user_id": user_id,
            "text_length": len(transcription),
            "model": settings.openai_transcribe_model,
        })

        if not transcription.strip():
            return "🎤 Recebi seu áudio, mas a transcrição ficou vazia. Pode tentar novamente ou enviar em texto?"

        reply_text = await handle_free_text(
            db, user_id, transcription,
            raw_update={"voice_log_id": voice_log.id, "source_type": source_type, "file_id": file_id, "duration": duration},
            channel="telegram_voice",
        )

        voice_log.processing_status = "completed"
        db.commit()

        transcription_note = f"🎤 _{transcription}_\n\n" if len(transcription) < 500 else "🎤 _[áudio transcrito]_\n\n"
        full_reply = f"{transcription_note}{reply_text}"

        await telegram_service.send_message(chat_id, full_reply)

        if audio_service.should_reply_with_voice(db, user_id):
            tts_ok = await _send_voice_reply(db, chat_id, reply_text, user_id)
            if tts_ok:
                voice_log.tts_generated = True
                db.commit()

        return ""

    except Exception as e:
        logger.exception("Voice processing failed for user=%s", user_id)
        voice_log.processing_status = "error"
        voice_log.error_message = str(e)
        db.commit()
        return f"❌ Erro ao processar áudio: {e}"
    finally:
        audio_service.cleanup_temp_file(temp_path)


async def _send_voice_reply(db: Session, chat_id: int, text: str, user_id: str) -> bool:
    tts_result = await audio_service.synthesize_speech(text)
    if tts_result.get("error") or not tts_result.get("audio_bytes"):
        logger.warning("TTS failed, skipping voice reply: %s", tts_result.get("error"))
        return False

    audio_bytes = tts_result["audio_bytes"]
    tts_format = tts_result.get("format", "opus")

    try:
        await telegram_service.send_voice(chat_id, audio_bytes)
        _log_action(db, "audio_reply_generated", "success", {
            "user_id": user_id,
            "method": "send_voice",
            "size": len(audio_bytes),
        })
        return True
    except Exception:
        logger.info("send_voice failed, falling back to send_audio")
        ext = tts_format if tts_format != "opus" else "ogg"
        fallback_filename = f"jarvis_response.{ext}"
        try:
            await telegram_service.send_audio(chat_id, audio_bytes, filename=fallback_filename)
            _log_action(db, "audio_reply_generated", "success", {
                "user_id": user_id,
                "method": "send_audio_fallback",
                "size": len(audio_bytes),
            })
            return True
        except Exception:
            logger.exception("send_audio fallback also failed")
            return False


def _ext_from_mime(mime_type: str) -> str:
    mime_map = {
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/flac": ".flac",
    }
    return mime_map.get(mime_type, ".ogg")


@router.post("/telegram", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default="", alias="X-Telegram-Bot-Api-Secret-Token"),
    db: Session = Depends(get_db),
):
    if not settings.telegram_webhook_secret or x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        return JSONResponse(
            status_code=403,
            content=TelegramWebhookResponse(ok=False, message="Forbidden").model_dump(),
        )

    body = await request.json()
    try:
        update = TelegramUpdate(**body)
    except Exception as e:
        logger.error("Failed to parse Telegram update: %s", e)
        return TelegramWebhookResponse(ok=True, message="ignored")

    if update.message and update.message.from_user:
        sender_id = update.message.from_user.id
        if settings.telegram_allowed_user_id and sender_id != settings.telegram_allowed_user_id:
            logger.info("Ignoring message from unauthorized user_id=%s", sender_id)
            return TelegramWebhookResponse(ok=True, message="ignored")
    else:
        return TelegramWebhookResponse(ok=True, message="ignored")

    existing = db.query(ProcessedTelegramUpdate).filter(
        ProcessedTelegramUpdate.update_id == update.update_id
    ).first()
    if existing:
        logger.info("Duplicate update_id=%s, ignoring", update.update_id)
        return TelegramWebhookResponse(ok=True, message="duplicate")

    processed = ProcessedTelegramUpdate(update_id=update.update_id, user_id=sender_id)
    db.add(processed)
    db.commit()

    chat_id = update.message.chat.id
    user_id = str(sender_id)
    msg = update.message

    if msg.voice:
        reply = await _handle_voice_message(
            db=db,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            file_id=msg.voice.file_id,
            file_unique_id=msg.voice.file_unique_id,
            mime_type=msg.voice.mime_type,
            duration=msg.voice.duration,
            file_size=msg.voice.file_size,
            source_type="voice",
        )
        if reply:
            await telegram_service.send_message(chat_id, reply)
        return TelegramWebhookResponse(ok=True, message="voice_processed")

    if msg.audio:
        reply = await _handle_voice_message(
            db=db,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            file_id=msg.audio.file_id,
            file_unique_id=msg.audio.file_unique_id,
            mime_type=msg.audio.mime_type,
            duration=msg.audio.duration,
            file_size=msg.audio.file_size,
            source_type="audio",
        )
        if reply:
            await telegram_service.send_message(chat_id, reply)
        return TelegramWebhookResponse(ok=True, message="audio_processed")

    text = (msg.text or "").strip()
    if not text:
        return TelegramWebhookResponse(ok=True, message="ignored")

    reply_text = ""

    if text.startswith("/start"):
        reply_text = START_TEXT
    elif text.startswith("/help"):
        reply_text = HELP_TEXT
    elif text.startswith("/myday"):
        overview = await get_real_or_mock_day_overview(db, user_id)
        reply_text = format_day_overview_text(overview)
    elif text.startswith("/remember"):
        note = text[len("/remember"):].strip()
        if not note:
            reply_text = "Use: /remember <sua anotação aqui>"
        else:
            save_memory(db, user_id, note, category="general", source="command")
            reply_text = f"✅ Anotação salva: \"{note}\""
    elif text.startswith("/memories"):
        items = list_memories(db, user_id, limit=10)
        if not items:
            reply_text = "Você ainda não tem anotações salvas. Use /remember para salvar uma."
        else:
            lines = ["📝 Suas anotações recentes:"]
            for i, m in enumerate(items, 1):
                lines.append(f"{i}. [{m.category}] {m.content}")
            reply_text = "\n".join(lines)
    elif text.startswith("/voiceon"):
        audio_service.set_voice_preference(db, user_id, True)
        if settings.voice_responses_enabled:
            reply_text = "🔊 Respostas por áudio ativadas! Agora vou responder também com áudio quando você enviar mensagens."
        else:
            reply_text = (
                "🔊 Preferência de áudio ativada para sua conta.\n"
                "⚠️ Porém, as respostas por áudio estão desativadas globalmente (VOICE_RESPONSES_ENABLED=false). "
                "Peça ao administrador para ativar."
            )
    elif text.startswith("/voiceoff"):
        audio_service.set_voice_preference(db, user_id, False)
        reply_text = "🔇 Respostas por áudio desativadas. Vou responder apenas em texto."
    elif text.startswith("/voicestatus"):
        global_enabled = settings.voice_responses_enabled
        user_enabled = audio_service.get_voice_preference(db, user_id)
        active = global_enabled and user_enabled
        lines = [
            "🎙️ Status de respostas por áudio:",
            f"  Global: {'✅ ativado' if global_enabled else '❌ desativado'}",
            f"  Sua preferência: {'✅ ativado' if user_enabled else '❌ desativado'}",
            f"  Resultado: {'🔊 áudio ativo' if active else '🔇 apenas texto'}",
        ]
        reply_text = "\n".join(lines)
    elif text.startswith("/transcribe"):
        reply_text = (
            "🎤 Para transcrever áudio, basta enviar uma nota de voz ou arquivo de áudio diretamente neste chat. "
            "O Jarvis transcreverá automaticamente e responderá."
        )
    elif text.startswith("/connectgoogle"):
        if not settings.app_base_url:
            reply_text = "⚠️ APP_BASE_URL não está configurado. Peça ao administrador para definir."
        elif not settings.google_client_id:
            reply_text = "⚠️ Credenciais Google OAuth não configuradas. Peça ao administrador."
        else:
            auth_link = f"{settings.app_base_url.rstrip('/')}/auth/google/start"
            status = google_oauth_service.get_status(db, user_id)
            if status.get("connected") and not status.get("gmail_enabled"):
                reply_text = (
                    "⚠️ Sua conta Google está conectada, mas sem permissões de Gmail.\n"
                    "Ao clicar no link abaixo, você será redirecionado para autorizar os escopos adicionais de Gmail.\n"
                    "Seus acessos anteriores (Calendar, Tasks) serão mantidos.\n\n"
                    f"🔗 [Reconectar com Gmail]({auth_link})"
                )
            else:
                reply_text = f"🔗 [Clique aqui para conectar sua conta Google]({auth_link})"
    elif text.startswith("/google"):
        status = google_oauth_service.get_status(db, user_id)
        if status.get("connected"):
            gmail_str = "✅" if status.get("gmail_enabled") else "❌"
            cal_str = "✅" if status.get("calendar_enabled") else "❌"
            tasks_str = "✅" if status.get("tasks_enabled") else "❌"
            reply_text = (
                "✅ Conta Google conectada!\n"
                f"Calendar: {cal_str} | Tasks: {tasks_str} | Gmail: {gmail_str}\n"
                f"Validade do token: {status.get('token_expiry', 'N/A')}"
            )
            if not status.get("gmail_enabled"):
                reply_text += "\n\n⚠️ Gmail não autorizado. Use /connectgoogle para reconectar com escopos de Gmail."
        else:
            reply_text = "❌ Conta Google não conectada. Use /connectgoogle para conectar."
    elif text.startswith("/tasks"):
        status = google_oauth_service.get_status(db, user_id)
        if not status.get("connected"):
            reply_text = "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
        else:
            tasks = await google_tasks_service.list_tasks(db, user_id, limit=15)
            if not tasks:
                reply_text = "✅ Nenhuma tarefa pendente!"
            else:
                lines = ["📋 Suas tarefas pendentes:"]
                for i, t in enumerate(tasks, 1):
                    due_str = f" (vence: {t['due'][:10]})" if t.get("due") else ""
                    lines.append(f"{i}. {t['title']}{due_str}")
                reply_text = "\n".join(lines)
    elif text.startswith("/newtask"):
        title = text[len("/newtask"):].strip()
        if not title:
            reply_text = "Use: /newtask <título da tarefa>"
        else:
            status = google_oauth_service.get_status(db, user_id)
            if not status.get("connected"):
                reply_text = "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
            else:
                result = await google_tasks_service.create_task(db, user_id, title)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    reply_text = f"✅ Tarefa criada: \"{result.get('title', title)}\""
    elif text.startswith("/newevent"):
        parts_raw = text[len("/newevent"):].strip()
        parts = [p.strip() for p in parts_raw.split("|")]
        if len(parts) < 3:
            reply_text = (
                "Use: /newevent título | início | fim\n"
                "Formato de data: YYYY-MM-DD HH:MM\n"
                "Exemplo: /newevent Reunião | 2026-03-16 09:00 | 2026-03-16 10:00"
            )
        else:
            ev_title = parts[0]
            status = google_oauth_service.get_status(db, user_id)
            if not status.get("connected"):
                reply_text = "❌ Google não conectado. Use /connectgoogle para conectar sua conta primeiro."
            else:
                try:
                    start_dt = parse_datetime_local(parts[1], settings.timezone)
                    end_dt = parse_datetime_local(parts[2], settings.timezone)
                except ValueError as e:
                    reply_text = f"❌ {e}"
                else:
                    result = await google_calendar_service.create_event(
                        db, user_id, ev_title, start_dt, end_dt, tz=settings.timezone
                    )
                    if "error" in result:
                        reply_text = f"❌ {result['error']}"
                    else:
                        reply_text = f"✅ Evento criado: \"{result.get('title', ev_title)}\""
                        if result.get("link"):
                            reply_text += f"\n🔗 {result['link']}"
    elif text.startswith("/inboxsummary"):
        gmail_err = _gmail_not_ready_msg(db, user_id)
        if gmail_err:
            reply_text = gmail_err
        else:
            result = await google_gmail_service.summarize_inbox(db, user_id)
            if "error" in result:
                reply_text = f"❌ {result['error']}"
            else:
                reply_text = result.get("summary", "Não foi possível gerar o resumo.")
    elif text.startswith("/inbox"):
        gmail_err = _gmail_not_ready_msg(db, user_id)
        if gmail_err:
            reply_text = gmail_err
        else:
            result = await google_gmail_service.list_messages(db, user_id)
            if "error" in result:
                reply_text = f"❌ {result['error']}"
            else:
                reply_text = format_messages_list_telegram(result.get("messages", []))
    elif text.startswith("/emailsearch"):
        query = text[len("/emailsearch"):].strip()
        if not query:
            reply_text = (
                "Use: /emailsearch <consulta>\n"
                "Exemplos:\n"
                "  /emailsearch from:joao@email.com\n"
                "  /emailsearch is:unread subject:relatório\n"
                "  /emailsearch newer_than:3d"
            )
        else:
            gmail_err = _gmail_not_ready_msg(db, user_id)
            if gmail_err:
                reply_text = gmail_err
            else:
                result = await google_gmail_service.search_emails(db, user_id, query=query)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    reply_text = format_messages_list_telegram(result.get("messages", []))
    elif text.startswith("/thread"):
        thread_id = text[len("/thread"):].strip()
        if not thread_id:
            reply_text = "Use: /thread <thread_id>"
        else:
            gmail_err = _gmail_not_ready_msg(db, user_id)
            if gmail_err:
                reply_text = gmail_err
            else:
                result = await google_gmail_service.get_thread(db, user_id, thread_id=thread_id)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    msgs = result.get("messages", [])
                    if not msgs:
                        reply_text = "Nenhuma mensagem nesta thread."
                    else:
                        lines = [f"📧 Thread ({len(msgs)} mensagens):"]
                        for i, m in enumerate(msgs, 1):
                            sender = m.get("from", "?")
                            if "<" in sender:
                                sender = sender.split("<")[0].strip().strip('"')
                            subject = m.get("subject", "(sem assunto)")
                            body_preview = m.get("body", "")[:200]
                            lines.append(f"\n--- Mensagem {i} ---")
                            lines.append(f"De: {sender}")
                            lines.append(f"Assunto: {subject}")
                            if body_preview:
                                lines.append(f"{body_preview}")
                        reply_text = "\n".join(lines)
    elif text.startswith("/draftemail"):
        parts_raw = text[len("/draftemail"):].strip()
        parts = [p.strip() for p in parts_raw.split("|")]
        if len(parts) < 3:
            reply_text = (
                "Use: /draftemail destinatário | assunto | corpo\n"
                "Exemplo: /draftemail joao@email.com | Reunião amanhã | Olá João, podemos..."
            )
        else:
            gmail_err = _gmail_not_ready_msg(db, user_id)
            if gmail_err:
                reply_text = gmail_err
            else:
                to_addr = parts[0]
                subject = parts[1]
                body = parts[2]
                result = await google_gmail_service.create_draft(db, user_id, to=to_addr, subject=subject, body=body)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    reply_text = result.get("message", "Rascunho criado.")
    elif text.startswith("/replydraft"):
        parts_raw = text[len("/replydraft"):].strip()
        parts = [p.strip() for p in parts_raw.split("|", 1)]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            reply_text = (
                "Use: /replydraft <message_id> | <corpo da resposta>\n"
                "Exemplo: /replydraft 18abc123def | Obrigado, confirmo presença!"
            )
        else:
            gmail_err = _gmail_not_ready_msg(db, user_id)
            if gmail_err:
                reply_text = gmail_err
            else:
                msg_id = parts[0]
                body = parts[1]
                result = await google_gmail_service.create_reply_draft(db, user_id, message_id=msg_id, body=body)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    reply_text = result.get("message", "Rascunho de resposta criado.")
    elif text.startswith("/senddraft"):
        draft_id = text[len("/senddraft"):].strip()
        if not draft_id:
            reply_text = "Use: /senddraft <draft_id>"
        else:
            gmail_err = _gmail_not_ready_msg(db, user_id)
            if gmail_err:
                reply_text = gmail_err
            else:
                result = await google_gmail_service.send_draft(db, user_id, draft_id=draft_id)
                if "error" in result:
                    reply_text = f"❌ {result['error']}"
                else:
                    reply_text = result.get("message", "E-mail enviado!")
    elif text.startswith("/drafts"):
        gmail_err = _gmail_not_ready_msg(db, user_id)
        if gmail_err:
            reply_text = gmail_err
        else:
            result = await google_gmail_service.list_drafts(db, user_id)
            if "error" in result:
                reply_text = f"❌ {result['error']}"
            else:
                drafts = result.get("drafts", [])
                if not drafts:
                    reply_text = "📝 Nenhum rascunho encontrado."
                else:
                    lines = ["📝 Seus rascunhos:"]
                    for i, d in enumerate(drafts, 1):
                        to_str = d.get("to", "?")
                        subj = d.get("subject", "(sem assunto)")
                        did = d.get("draft_id", "")
                        lines.append(f"{i}. Para: {to_str} — {subj}\n   ID: {did}")
                    reply_text = "\n".join(lines)
    else:
        reply_text = await handle_free_text(db, user_id, text, raw_update=body)

    if reply_text:
        await telegram_service.send_message(chat_id, reply_text)

    return TelegramWebhookResponse(ok=True, message="processed")
