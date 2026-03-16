import json
import logging
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import settings
from app.models.action_log import ActionLog
from app.models.browser_artifact import BrowserArtifact

logger = logging.getLogger(__name__)

_SENSITIVE_BUTTON_PATTERNS = re.compile(
    r"\b(enviar|submit|confirmar|confirm|pagar|pay|excluir|deletar|delete|remove|remover"
    r"|finalizar|concluir|contratar|hire|checkout|comprar|buy|purchase|assinar|subscribe"
    r"|transferir|transfer|cancelar conta|delete account)\b",
    re.IGNORECASE,
)

_SENSITIVE_URL_PATTERNS = re.compile(
    r"(checkout|payment|pagamento|pagar|compra|order|confirm|delete|remove|cancel)",
    re.IGNORECASE,
)

_LOGIN_URL_PATTERNS = re.compile(
    r"(login|signin|sign-in|sign_in|auth|password|2fa|mfa|verify|otp|oauth|sso)",
    re.IGNORECASE,
)

_LOGIN_TITLE_PATTERNS = re.compile(
    r"(login|entrar|sign\s*in|autenticar|autenticação|senha|password|verificação|verify)",
    re.IGNORECASE,
)


def sanitize_url_for_logs(url: str) -> str:
    try:
        parsed = urlparse(url)
        safe = parsed._replace(query="", fragment="")
        return safe.geturl()
    except Exception:
        return "[url-parse-error]"


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def is_domain_allowed(url: str) -> bool:
    raw = settings.browser_allowed_domains.strip()
    if not raw:
        return False
    allowed = {d.strip().lower().lstrip("www.") for d in raw.split(",") if d.strip()}
    if not allowed:
        return False
    domain = extract_domain(url)
    if not domain:
        return False
    for allowed_domain in allowed:
        if domain == allowed_domain or domain.endswith("." + allowed_domain):
            return True
    return False


def is_sensitive_action(
    action_type: str,
    selector: str | None = None,
    value: str | None = None,
    current_url: str | None = None,
) -> bool:
    if action_type in ("browser_submit_form",):
        return True
    text_to_check = " ".join(filter(None, [selector, value]))
    if _SENSITIVE_BUTTON_PATTERNS.search(text_to_check):
        return True
    if current_url and _SENSITIVE_URL_PATTERNS.search(current_url):
        return True
    return False


def is_login_page(url: str, title: str, has_password_input: bool = False) -> bool:
    if _LOGIN_URL_PATTERNS.search(url):
        return True
    if _LOGIN_TITLE_PATTERNS.search(title):
        return True
    if has_password_input:
        return True
    return False


def summarize_page_text(text: str, max_chars: int = 2000) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    joined = "\n".join(lines)
    if len(joined) <= max_chars:
        return joined
    return joined[:max_chars] + "…"


def clean_old_browser_artifacts(db: Session, older_than_days: int = 7) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    rows = (
        db.query(BrowserArtifact)
        .filter(BrowserArtifact.created_at < cutoff)
        .all()
    )
    deleted = 0
    for row in rows:
        if row.file_path and os.path.exists(row.file_path):
            try:
                os.remove(row.file_path)
            except OSError:
                logger.warning("Could not delete artifact file: %s", row.file_path)
        db.delete(row)
        deleted += 1
    db.commit()
    return deleted


def _log_action(db: Session, event_type: str, status: str, **details: object) -> None:
    try:
        entry = ActionLog(
            event_type=event_type,
            status=status,
            details_json=json.dumps(details, default=str) if details else None,
        )
        db.add(entry)
        db.commit()
    except Exception:
        logger.exception("Failed to write ActionLog for %s", event_type)


def log_session_started(db: Session, session_id: str, user_id: str, url: str) -> None:
    _log_action(db, "browser_session_started", "ok",
                session_id=session_id, user_id=user_id, url=sanitize_url_for_logs(url))


def log_navigation(db: Session, session_id: str, url: str, status: str = "ok",
                   error: str | None = None) -> None:
    _log_action(db, "browser_navigation", status,
                session_id=session_id, url=sanitize_url_for_logs(url), error=error)


def log_click(db: Session, session_id: str, selector: str, status: str = "ok") -> None:
    _log_action(db, "browser_click", status, session_id=session_id, selector=selector)


def log_fill(db: Session, session_id: str, selector: str, status: str = "ok") -> None:
    _log_action(db, "browser_fill", status, session_id=session_id, selector=selector)


def log_sensitive_action_blocked(db: Session, session_id: str, action_type: str,
                                  selector: str | None, url: str | None) -> None:
    _log_action(db, "browser_sensitive_action_blocked", "blocked",
                session_id=session_id, action_type=action_type,
                selector=selector, url=sanitize_url_for_logs(url or ""))


def log_approval_created(db: Session, session_id: str, approval_id: int,
                          action_type: str) -> None:
    _log_action(db, "browser_approval_created", "pending",
                session_id=session_id, approval_id=approval_id, action_type=action_type)


def log_download_completed(db: Session, session_id: str, file_path: str,
                            url: str | None) -> None:
    _log_action(db, "browser_download_completed", "ok",
                session_id=session_id, file_path=file_path,
                url=sanitize_url_for_logs(url or ""))


def log_session_closed(db: Session, session_id: str, reason: str = "user") -> None:
    _log_action(db, "browser_session_closed", "ok",
                session_id=session_id, reason=reason)


def log_session_failed(db: Session, session_id: str, error: str) -> None:
    _log_action(db, "browser_session_failed", "error",
                session_id=session_id, error=error)


def ensure_dirs() -> None:
    os.makedirs(settings.browser_screenshot_dir, exist_ok=True)
    os.makedirs(settings.browser_download_dir, exist_ok=True)
