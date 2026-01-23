"""
Database base configuration
"""
from sqlalchemy.ext.declarative import declarative_base

# Create declarative base for SQLAlchemy models
Base = declarative_base()


# Import all models here to ensure they are registered with SQLAlchemy
# This is important for Alembic migrations to work properly
def import_models():
    """Import all models to register them with SQLAlchemy"""
    from app.models import asset  # noqa: F401
    # Import other models here as they are created
    # from app.models import user  # noqa: F401
    # from app.models import organization  # noqa: F401