from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VoiceMessageLog(Base):
    __tablename__ = "voice_message_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_update_id: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_file_id: Mapped[str] = mapped_column(String, nullable=False)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_temp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    transcription_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcription_model: Mapped[str | None] = mapped_column(String, nullable=True)
    transcription_raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_status: Mapped[str] = mapped_column(String, nullable=False, default="received")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
