import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.action_log import ActionLog
from app.services import google_oauth_service
from app.utils.gmail_utils import (
    build_mime_message,
    build_mime_reply,
    extract_message_fields,
    extract_plain_body,
    format_messages_list_telegram,
    strip_quoted_text,
)

logger = logging.getLogger(__name__)

GMAIL_NOT_CONNECTED = "Gmail não conectado. Use /connectgoogle para conectar sua conta Google com permissões de Gmail."
GMAIL_SCOPES_MISSING = (
    "Sua conta Google está conectada, mas sem permissões de Gmail. "
    "Use /connectgoogle para reconectar com os escopos de Gmail."
)


def _check_gmail(db: Session, user_id: str) -> str | None:
    status = google_oauth_service.get_status(db, user_id)
    if not status.get("connected"):
        return GMAIL_NOT_CONNECTED
    if not status.get("gmail_enabled"):
        return GMAIL_SCOPES_MISSING
    return None


def _get_gmail_service(db: Session, user_id: str):
    from googleapiclient.discovery import build

    creds = google_oauth_service.get_credentials(db, user_id)
    if creds is None:
        return None
    return build("gmail", "v1", credentials=creds)


def _log_action(db: Session, event_type: str, status: str, details: dict) -> None:
    entry = ActionLog(
        event_type=event_type,
        status=status,
        details_json=json.dumps(details, ensure_ascii=False),
    )
    db.add(entry)
    db.commit()


async def list_messages(
    db: Session,
    user_id: str,
    query: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    q = query or settings.gmail_inbox_query_default
    limit = max_results or settings.gmail_max_list_results

    try:
        result = service.users().messages().list(
            userId="me", q=q, maxResults=limit
        ).execute()
    except Exception as e:
        logger.exception("Gmail list_messages error for user=%s", user_id)
        return {"error": f"Erro ao listar e-mails: {e}"}

    message_ids = result.get("messages", [])
    messages = []
    for msg_stub in message_ids:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_stub["id"], format="metadata",
                metadataHeaders=["Subject", "From", "To", "Date", "Message-ID", "References"],
            ).execute()
            messages.append(extract_message_fields(msg))
        except Exception:
            logger.warning("Failed to get message %s", msg_stub.get("id"))

    _log_action(db, "gmail_list", "success", {"user_id": user_id, "query": q, "count": len(messages)})
    return {"messages": messages, "count": len(messages)}


async def search_emails(
    db: Session,
    user_id: str,
    query: str,
    max_results: int = 10,
) -> dict[str, Any]:
    return await list_messages(db, user_id, query=query, max_results=max_results)


async def get_message(db: Session, user_id: str, message_id: str) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    except Exception as e:
        logger.exception("Gmail get_message error for user=%s msg=%s", user_id, message_id)
        return {"error": f"Erro ao buscar e-mail: {e}"}

    fields = extract_message_fields(msg)
    body = extract_plain_body(msg.get("payload", {}))
    fields["body"] = strip_quoted_text(body) if body else ""

    _log_action(db, "gmail_get_message", "success", {"user_id": user_id, "message_id": message_id})
    return fields


async def get_thread(db: Session, user_id: str, thread_id: str) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    try:
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()
    except Exception as e:
        logger.exception("Gmail get_thread error for user=%s thread=%s", user_id, thread_id)
        return {"error": f"Erro ao buscar thread: {e}"}

    messages_in_thread = []
    for msg in thread.get("messages", []):
        fields = extract_message_fields(msg)
        body = extract_plain_body(msg.get("payload", {}))
        fields["body"] = strip_quoted_text(body) if body else ""
        messages_in_thread.append(fields)

    _log_action(db, "gmail_get_thread", "success", {"user_id": user_id, "thread_id": thread_id, "count": len(messages_in_thread)})
    return {"threadId": thread_id, "messages": messages_in_thread, "count": len(messages_in_thread)}


async def summarize_inbox(db: Session, user_id: str, max_results: int = 5) -> dict[str, Any]:
    result = await list_messages(
        db, user_id,
        query="is:unread in:inbox -category:promotions",
        max_results=max_results,
    )
    if "error" in result:
        return result

    messages = result.get("messages", [])
    if not messages:
        return {"summary": "📭 Inbox vazia — nenhum e-mail não lido importante.", "count": 0}

    lines = []
    for i, m in enumerate(messages, 1):
        sender = m.get("from", "desconhecido")
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')
        subject = m.get("subject", "(sem assunto)")
        lines.append(f"{i}. {subject} — de {sender}")

    summary = f"📬 Você tem {len(messages)} e-mail(s) não lido(s):\n" + "\n".join(lines)
    return {"summary": summary, "count": len(messages), "messages": messages}


async def create_draft(
    db: Session,
    user_id: str,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    raw = build_mime_message(to, subject, body)
    try:
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw}},
        ).execute()
    except Exception as e:
        logger.exception("Gmail create_draft error for user=%s", user_id)
        return {"error": f"Erro ao criar rascunho: {e}"}

    draft_id = draft.get("id", "")
    _log_action(db, "gmail_create_draft", "success", {"user_id": user_id, "draft_id": draft_id, "to": to, "subject": subject})
    return {"draft_id": draft_id, "message": f"✅ Rascunho criado (ID: {draft_id}). Use /senddraft {draft_id} para enviar."}


async def create_reply_draft(
    db: Session,
    user_id: str,
    message_id: str,
    body: str,
) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    original = await get_message(db, user_id, message_id)
    if "error" in original:
        return original

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    original_message_id_header = original.get("message_id", "")
    original_references = original.get("references", "")
    original_subject = original.get("subject", "")
    reply_to = original.get("from", "")
    thread_id = original.get("threadId", "")

    if not original_message_id_header:
        return {"error": "Não foi possível encontrar o Message-ID da mensagem original."}

    raw = build_mime_reply(
        to=reply_to,
        body=body,
        original_message_id=original_message_id_header,
        original_references=original_references,
        original_subject=original_subject,
    )

    try:
        draft = service.users().drafts().create(
            userId="me",
            body={
                "message": {
                    "raw": raw,
                    "threadId": thread_id,
                },
            },
        ).execute()
    except Exception as e:
        logger.exception("Gmail create_reply_draft error for user=%s", user_id)
        return {"error": f"Erro ao criar rascunho de resposta: {e}"}

    draft_id = draft.get("id", "")
    _log_action(db, "gmail_create_draft", "success", {
        "user_id": user_id,
        "draft_id": draft_id,
        "reply_to_message": message_id,
        "thread_id": thread_id,
        "in_reply_to": original_message_id_header,
    })
    return {
        "draft_id": draft_id,
        "thread_id": thread_id,
        "message": f"✅ Rascunho de resposta criado (ID: {draft_id}). Use /senddraft {draft_id} para enviar.",
    }


async def list_drafts(db: Session, user_id: str, max_results: int = 10) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    try:
        result = service.users().drafts().list(
            userId="me", maxResults=max_results
        ).execute()
    except Exception as e:
        logger.exception("Gmail list_drafts error for user=%s", user_id)
        return {"error": f"Erro ao listar rascunhos: {e}"}

    drafts_raw = result.get("drafts", [])
    drafts = []
    for d in drafts_raw:
        draft_id = d.get("id", "")
        msg = d.get("message", {})
        msg_id = msg.get("id", "")
        try:
            full_draft = service.users().drafts().get(
                userId="me", id=draft_id, format="metadata",
            ).execute()
            msg_data = full_draft.get("message", {})
            headers = msg_data.get("payload", {}).get("headers", [])
            from app.utils.gmail_utils import extract_header
            drafts.append({
                "draft_id": draft_id,
                "message_id": msg_data.get("id", msg_id),
                "subject": extract_header(headers, "Subject"),
                "to": extract_header(headers, "To"),
                "snippet": msg_data.get("snippet", ""),
            })
        except Exception:
            drafts.append({"draft_id": draft_id, "message_id": msg_id, "subject": "", "to": "", "snippet": ""})

    return {"drafts": drafts, "count": len(drafts)}


async def get_draft(db: Session, user_id: str, draft_id: str) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    try:
        draft = service.users().drafts().get(
            userId="me", id=draft_id, format="full"
        ).execute()
    except Exception as e:
        logger.exception("Gmail get_draft error for user=%s draft=%s", user_id, draft_id)
        return {"error": f"Erro ao buscar rascunho: {e}"}

    msg = draft.get("message", {})
    fields = extract_message_fields(msg)
    body = extract_plain_body(msg.get("payload", {}))
    fields["body"] = body
    fields["draft_id"] = draft_id
    return fields


async def send_draft(db: Session, user_id: str, draft_id: str) -> dict[str, Any]:
    error = _check_gmail(db, user_id)
    if error:
        return {"error": error}

    service = _get_gmail_service(db, user_id)
    if service is None:
        return {"error": GMAIL_NOT_CONNECTED}

    try:
        result = service.users().drafts().send(
            userId="me",
            body={"id": draft_id},
        ).execute()
    except Exception as e:
        logger.exception("Gmail send_draft error for user=%s draft=%s", user_id, draft_id)
        return {"error": f"Erro ao enviar rascunho: {e}"}

    sent_id = result.get("id", "")
    _log_action(db, "gmail_send_draft", "success", {"user_id": user_id, "draft_id": draft_id, "sent_message_id": sent_id})
    return {"sent": True, "message_id": sent_id, "message": "✅ E-mail enviado com sucesso!"}


async def get_priority_emails(db: Session, user_id: str, max_results: int = 5) -> list[dict[str, str]]:
    if not google_oauth_service.has_gmail_scopes(db, user_id):
        return []

    result = await list_messages(
        db, user_id,
        query="is:unread in:inbox -category:promotions",
        max_results=max_results,
    )
    if "error" in result:
        return []

    return result.get("messages", [])
