import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.config import settings
from app.models.google_credential import GoogleCredential

logger = logging.getLogger(__name__)

# TODO: When GOOGLE_ENCRYPTION_KEY is set, encrypt access_token and refresh_token
# before persisting and decrypt on read. For now tokens are stored in plain text.
# In production, consider using a secrets manager or envelope encryption.

_pending_states: dict[str, str] = {}


def _get_scopes() -> list[str]:
    return settings.google_oauth_scopes.split()


def _make_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=_get_scopes(),
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


def get_auth_url(user_id: str) -> str:
    flow = _make_flow()
    state = secrets.token_urlsafe(32)
    _pending_states[state] = user_id

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return auth_url


def exchange_code(db: Session, code: str, state: str) -> GoogleCredential:
    user_id = _pending_states.pop(state, None)
    if user_id is None:
        raise ValueError("State inválido ou expirado. Tente conectar novamente via /connectgoogle.")

    flow = _make_flow()
    flow.fetch_token(code=code)

    creds = flow.credentials
    if not creds.refresh_token:
        # NOTE: Google only returns refresh_token on first consent.
        # If re-authorizing, the user may need to revoke app access in
        # https://myaccount.google.com/permissions and re-consent.
        # The flow uses prompt=consent to maximize chances of getting it.
        raise ValueError(
            "O Google não retornou um refresh_token. "
            "Isso pode acontecer ao reconectar. "
            "Remova o acesso do app em https://myaccount.google.com/permissions "
            "e tente novamente via /connectgoogle."
        )

    token_expiry = None
    if creds.expiry:
        token_expiry = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry.tzinfo is None else creds.expiry

    existing = db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()
    if existing:
        existing.access_token = creds.token
        existing.refresh_token = creds.refresh_token
        existing.token_expiry = token_expiry
        existing.scope = " ".join(creds.scopes or _get_scopes())
        existing.token_type = "Bearer"
        existing.raw_json = creds.to_json()
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    credential = GoogleCredential(
        user_id=user_id,
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        token_expiry=token_expiry,
        scope=" ".join(creds.scopes or _get_scopes()),
        token_type="Bearer",
        raw_json=creds.to_json(),
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential


def refresh_credentials(db: Session, user_id: str) -> Credentials | None:
    cred = db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()
    if cred is None or not cred.access_token:
        return None

    expiry = cred.token_expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    credentials = Credentials(
        token=cred.access_token,
        refresh_token=cred.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=cred.scope.split() if cred.scope else _get_scopes(),
        expiry=expiry,
    )

    if credentials.expired and credentials.refresh_token:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        try:
            credentials.refresh(GoogleAuthRequest())
            new_expiry = credentials.expiry
            if new_expiry and new_expiry.tzinfo is None:
                new_expiry = new_expiry.replace(tzinfo=timezone.utc)
            cred.access_token = credentials.token
            cred.token_expiry = new_expiry
            cred.updated_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("Refreshed Google token for user=%s", user_id)
        except Exception:
            logger.exception("Failed to refresh Google token for user=%s", user_id)
            return None

    return credentials


def get_credentials(db: Session, user_id: str) -> Credentials | None:
    return refresh_credentials(db, user_id)


def get_status(db: Session, user_id: str) -> dict[str, Any]:
    cred = db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()
    if cred is None or not cred.access_token:
        return {"connected": False, "scope": "", "token_expiry": None}

    return {
        "connected": True,
        "scope": cred.scope,
        "token_expiry": cred.token_expiry.isoformat() if cred.token_expiry else None,
        "has_refresh_token": cred.refresh_token is not None,
    }


async def revoke_and_disconnect(db: Session, user_id: str) -> dict[str, Any]:
    cred = db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()
    if cred is None:
        return {"disconnected": False, "message": "Nenhuma conta Google conectada."}

    revoked = False
    token_to_revoke = cred.refresh_token or cred.access_token
    if token_to_revoke:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token_to_revoke},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                revoked = resp.status_code == 200
                if not revoked:
                    logger.warning("Google token revocation returned %s for user=%s", resp.status_code, user_id)
        except Exception:
            logger.exception("Failed to revoke Google token for user=%s (best-effort)", user_id)

    db.delete(cred)
    db.commit()
    logger.info("Disconnected Google for user=%s (revoked=%s)", user_id, revoked)

    return {"disconnected": True, "revoked": revoked}
