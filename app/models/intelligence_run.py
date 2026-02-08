from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class IntelligenceRun(Base):
    __tablename__ = "intelligence_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    processor_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    processor_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    input_fingerprint_signature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    estimated_cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ✅ Now SQLAlchemy can infer join via FK on IntelligenceResult.run_id
    results = relationship(
        "IntelligenceResult",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
