import base64
import re
import time
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any
from zoneinfo import ZoneInfo


def extract_header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def extract_message_fields(msg: dict[str, Any]) -> dict[str, str]:
    headers = msg.get("payload", {}).get("headers", [])
    return {
        "id": msg.get("id", ""),
        "threadId": msg.get("threadId", ""),
        "subject": extract_header(headers, "Subject"),
        "from": extract_header(headers, "From"),
        "to": extract_header(headers, "To"),
        "date": extract_header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
        "message_id": extract_header(headers, "Message-ID"),
        "references": extract_header(headers, "References"),
        "labelIds": msg.get("labelIds", []),
    }


def extract_plain_body(payload: dict[str, Any]) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain" and "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = extract_plain_body(part)
        if result:
            return result
    return ""


def strip_quoted_text(body: str) -> str:
    lines = body.split("\n")
    result = []
    for line in lines:
        if re.match(r"^>", line):
            continue
        if re.match(r"^On .+ wrote:$", line.strip()):
            break
        if re.match(r"^Em .+ escreveu:$", line.strip()):
            break
        if line.strip().startswith("---------- Forwarded message"):
            break
        result.append(line)
    return "\n".join(result).strip()


def format_message_for_telegram(msg_fields: dict[str, str], index: int = 0) -> str:
    sender = msg_fields.get("from", "desconhecido")
    if "<" in sender:
        sender = sender.split("<")[0].strip().strip('"')
    subject = msg_fields.get("subject", "(sem assunto)")
    snippet = msg_fields.get("snippet", "")
    if len(snippet) > 100:
        snippet = snippet[:97] + "..."
    prefix = f"{index}. " if index > 0 else ""
    msg_id = msg_fields.get("id", "")
    thread_id = msg_fields.get("threadId", "")
    id_line = ""
    if msg_id or thread_id:
        id_line = f"\n   ID: {msg_id} | Thread: {thread_id}"
    return f"{prefix}📧 *{subject}*\n   De: {sender}\n   {snippet}{id_line}"


def format_messages_list_telegram(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "📭 Nenhum e-mail encontrado."
    lines = ["📬 E-mails recentes:"]
    for i, m in enumerate(messages, 1):
        lines.append(format_message_for_telegram(m, index=i))
    return "\n\n".join(lines)


def build_mime_message(to: str, subject: str, body: str, from_addr: str = "") -> str:
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    if from_addr:
        msg["From"] = from_addr
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def build_mime_reply(
    to: str,
    body: str,
    original_message_id: str,
    original_references: str,
    original_subject: str,
    from_addr: str = "",
) -> str:
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to

    subject = original_subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    msg["Subject"] = subject

    if original_message_id:
        msg["In-Reply-To"] = original_message_id

    refs = original_references.strip()
    if original_message_id:
        if refs:
            refs = f"{refs} {original_message_id}"
        else:
            refs = original_message_id
    if refs:
        msg["References"] = refs

    if from_addr:
        msg["From"] = from_addr

    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def datetime_to_gmail_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())


def date_to_gmail_after_query(year: int, month: int, day: int, tz_name: str = "America/Sao_Paulo") -> str:
    tz = ZoneInfo(tz_name)
    dt = datetime(year, month, day, tzinfo=tz)
    ts = int(dt.timestamp())
    return f"after:{ts}"
