import uuid
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, DateTime, Integer, Text, Boolean

from app.db.base import Base


class IntelligenceRun(Base):
    __tablename__ = "intelligence_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    processor_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    processor_version: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cost controls
    estimated_cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Phase 6.2 — signature-aware reprocessing
    input_fingerprint_signature: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Phase 6.11 — retry safety
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 6.14 — progress tracking
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 6.15 — cancel workflow
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
