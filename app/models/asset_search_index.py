import uuid
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy import String, DateTime, Text, UniqueConstraint, Index

from app.db.base import Base


class AssetSearchIndex(Base):
    __tablename__ = "asset_search_index"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Fingerprint fields
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # OCR / text search fields
    ocr_text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Postgres full-text search vector
    ocr_tsv: Mapped[object | None] = mapped_column(TSVECTOR, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("org_id", "asset_id", name="uq_asset_search_index_org_asset"),
        Index("idx_asset_search_index_ocr_tsv_gin", "ocr_tsv", postgresql_using="gin"),
    )
