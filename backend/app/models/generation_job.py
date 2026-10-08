import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, CHAR
from app.db.base import Base


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID when available, otherwise stores as
    a 32-char hex string for SQLite (used in tests).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID())
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return "%.32x" % uuid.UUID(str(value)).int
        return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GenerationJob(Base):
    """Represents a bulk certificate generation job.

    Status lifecycle:
        queued -> processing -> completed | partially_failed | failed
    """

    __tablename__ = "generation_jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    event_name = Column(String, nullable=False)
    completion_date = Column(String, nullable=False)  # stored as ISO date string
    status = Column(String, nullable=False, default="queued")
    total_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now)

    # Index for listing/filtering jobs by status (useful for admin dashboards)
    __table_args__ = (Index("ix_generation_jobs_status", "status"),)
