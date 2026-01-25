import uuid
from datetime import datetime

from app.models.intelligence_run import IntelligenceRun
from sqlalchemy import DateTime, String, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IntelligenceResult(Base):
    __tablename__ = "intelligence_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intelligence_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # ✅ THIS is what you're missing (or it's not being registered)
    run: Mapped["IntelligenceRun"] = relationship(
        "IntelligenceRun",
        back_populates="results",
    )
