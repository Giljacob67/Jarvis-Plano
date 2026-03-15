import os
import pytest
from unittest.mock import AsyncMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-secret"
os.environ["TELEGRAM_ALLOWED_USER_ID"] = "12345"
os.environ["JARVIS_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = ""

from app.db import Base, get_db
import app.models  # noqa: F401
from app.main import app
from app.services import telegram_service

_test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

Base.metadata.create_all(bind=_test_engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture(autouse=True)
def _patch_telegram_send(monkeypatch):
    mock_send = AsyncMock(return_value={"ok": True, "result": {"message_id": 999}})
    monkeypatch.setattr(telegram_service, "send_message", mock_send)
    monkeypatch.setattr(telegram_service, "_client", True)
    yield mock_send


@pytest.fixture
def db_session():
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
