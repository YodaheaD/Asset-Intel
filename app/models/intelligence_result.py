import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    String,
    Float,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base


class IntelligenceResult(Base):
    __tablename__ = "intelligence_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("intelligence_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    type = Column(
        String(100),
        nullable=False,
        index=True
    )  # e.g. image_metadata, ocr_text, tags

    data = Column(
        JSONB,
        nullable=False
    )

    confidence = Column(
        Float,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    run = relationship(
        "IntelligenceRun",
        back_populates="results"
    )
