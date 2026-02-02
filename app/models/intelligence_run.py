import uuid
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import (
    Column,
    DateTime,
    String,
    ForeignKey,
    Text,
    Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class IntelligenceRun(Base):
    __tablename__ = "intelligence_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    org_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    processor_name = Column(String(100), nullable=False)
    processor_version = Column(String(50), nullable=False)

    status = Column(
        String(20),
        nullable=False,
        index=True
    )  # pending | running | completed | failed

    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # Cost attribution per run
    estimated_cost_cents: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    default=0,
    )

    # Phase 6.2
    input_fingerprint_signature: Mapped[str | None] = mapped_column(
    String(128),
    nullable=True,
    index=True,
    )
    #Phase 6.11 Addition
    retry_count: Mapped[int] = mapped_column(
    Integer,
    default=0,
    nullable=False,
    )

    last_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


    # Relationships
    results = relationship(
        "IntelligenceResult",
        back_populates="run",
        cascade="all, delete-orphan"
    )
