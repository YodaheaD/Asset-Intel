from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Integer, Text, DateTime

from app.db.base import Base


class DeadletterEvent(Base):
    __tablename__ = "deadletter_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    processor_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    processor_version: Mapped[str] = mapped_column(String(50), nullable=False)

    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_try: Mapped[int] = mapped_column(Integer, nullable=False)

    # Keep API “safe”: we will only expose error_summary; error_raw remains internal.
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    requeued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
