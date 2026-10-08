from sqlalchemy.orm import Session
from app.models.generation_job import GenerationJob, _now
from app.models.certificate import Certificate
from app.schemas.job import JobCreate
from app.schemas.certificate import CertificateResponse
import uuid
from typing import Optional


def create_job(db: Session, job_data: JobCreate) -> GenerationJob:
    """Create a GenerationJob and all Certificate records in a single commit.

    The returned job is in 'queued' status.  Background processing starts
    after this function returns.
    """
    job = GenerationJob(
        id=uuid.uuid4(),
        event_name=job_data.event_name,
        completion_date=str(job_data.completion_date),
        total_count=len(job_data.recipients),
        status="queued",
        success_count=0,
        failure_count=0,
    )
    db.add(job)
    db.flush()  # get job.id without committing yet

    certificates = [
        Certificate(
            id=uuid.uuid4(),
            job_id=job.id,
            recipient_name=recipient.name,
            recipient_email=recipient.email,
            status="queued",
        )
        for recipient in job_data.recipients
    ]
    db.add_all(certificates)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Optional[GenerationJob]:
    return db.query(GenerationJob).filter(GenerationJob.id == job_id).first()


def get_job_certificates(
    db: Session,
    job_id: str,
    skip: int = 0,
    limit: int = 100,
) -> list[Certificate]:
    return (
        db.query(Certificate)
        .filter(Certificate.job_id == job_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def build_certificate_response(cert: Certificate, request_base_url: str) -> CertificateResponse:
    """Convert a Certificate ORM model to a CertificateResponse schema.

    Populates download_url when the certificate is completed so clients
    never need to handle raw file paths.
    """
    download_url: Optional[str] = None
    if cert.status == "completed" and cert.file_path:
        download_url = f"{request_base_url}api/v1/certificates/{cert.id}/download"

    return CertificateResponse(
        id=cert.id,
        job_id=cert.job_id,
        recipient_name=cert.recipient_name,
        recipient_email=cert.recipient_email,
        status=cert.status,
        download_url=download_url,
        error_message=cert.error_message,
        created_at=cert.created_at,
        updated_at=cert.updated_at,
    )
