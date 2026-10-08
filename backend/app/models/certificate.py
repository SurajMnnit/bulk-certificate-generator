import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from app.db.base import Base
from app.models.generation_job import GUID, _now


class Certificate(Base):
    """Represents a single certificate for one recipient within a job.

    Status lifecycle:
        queued -> processing -> completed | failed
    """

    __tablename__ = "certificates"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    job_id = Column(GUID(), ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    recipient_name = Column(String, nullable=False)
    recipient_email = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    file_path = Column(String, nullable=True)      # internal storage path – never exposed in API
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now)

    # Index for fast lookup of certificates by job_id (very common query)
    __table_args__ = (Index("ix_certificates_job_id", "job_id"),)
