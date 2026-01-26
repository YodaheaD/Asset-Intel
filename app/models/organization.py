from sqlalchemy import Column, String, DateTime, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import validates
import uuid
import re
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def slugify(value: str) -> str:
    """
    Convert a string to a URL-safe slug.
    Example: "Yoda's Labs Inc" -> "yodas-labs-inc"
    """
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    name = Column(String(255), nullable=False, unique=True)

    slug = Column(String(100), nullable=False, unique=True)
    # e.g. "acme", "yodas-labs"

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    ## Phase 5 Addition
    stripe_customer_id: Mapped[str | None] = mapped_column(
    String(255),
    nullable=True,
    index=True,
    )

    plan: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="free",
    )

    # -----------------------------
    # Auto-slug generation
    # -----------------------------
    @validates("name")
    def _set_slug_from_name(self, key, value: str) -> str:
        if not self.slug:
            self.slug = slugify(value)
        return value

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name} slug={self.slug}>"
