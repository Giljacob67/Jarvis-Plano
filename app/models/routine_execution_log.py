from datetime import datetime, timezone

from sqlalchemy import Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RoutineExecutionLog(Base):
    __tablename__ = "routine_execution_logs"
    __table_args__ = (
        UniqueConstraint("routine_type", "run_key", name="uq_routine_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    routine_type: Mapped[str] = mapped_column(String, nullable=False)
    run_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
