import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.certificate import Certificate
from app.models.generation_job import GenerationJob, _now
from app.services.pdf_service import PDFService
from app.services.storage_service import storage_service
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


def _determine_job_final_status(success: int, failure: int, total: int) -> str:
    """Compute the correct terminal job status."""
    if success == total:
        return "completed"
    if failure == total:
        return "failed"
    return "partially_failed"


def _process_single_certificate(db: Session, cert: Certificate, job: GenerationJob) -> None:
    """Generate and persist a single certificate.

    This function has its own try/except boundary so that a failure here
    cannot abort the processing of subsequent certificates.
    """
    cert.status = "processing"
    cert.updated_at = _now()
    db.commit()

    try:
        pdf_bytes = PDFService.generate_certificate(
            recipient_name=cert.recipient_name,
            event_name=job.event_name,
            completion_date=job.completion_date,
            certificate_id=str(cert.id),
        )

        file_path = storage_service.save(
            content=pdf_bytes,
            job_id=str(job.id),
            certificate_id=str(cert.id),
        )

        cert.file_path = file_path
        cert.status = "completed"
        cert.updated_at = _now()
        db.commit()

        # Atomically increment success_count
        db.query(GenerationJob).filter(GenerationJob.id == job.id).update(
            {
                GenerationJob.success_count: GenerationJob.success_count + 1,
                GenerationJob.updated_at: _now(),
            }
        )
        db.commit()

    except Exception as exc:
        logger.exception("Certificate generation failed for cert_id=%s: %s", cert.id, exc)
        db.rollback()

        # Refresh objects after rollback so we can still update them
        db.refresh(cert)
        cert.status = "failed"
        cert.error_message = str(exc)
        cert.updated_at = _now()
        db.commit()

        # Atomically increment failure_count
        db.query(GenerationJob).filter(GenerationJob.id == job.id).update(
            {
                GenerationJob.failure_count: GenerationJob.failure_count + 1,
                GenerationJob.updated_at: _now(),
            }
        )
        db.commit()


def process_job_certificates_background(job_id: str) -> None:
    """Entry point for FastAPI BackgroundTasks.

    Opens its own DB session (independent of the request session) and
    processes every queued certificate for the given job.  A failure on
    any individual certificate is caught and logged; remaining
    certificates continue processing.
    """
    db: Session = SessionLocal()
    try:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            logger.error("Background task started for unknown job_id=%s", job_id)
            return

        # Mark job as processing
        job.status = "processing"
        job.updated_at = _now()
        db.commit()

        certificates = (
            db.query(Certificate)
            .filter(Certificate.job_id == job_id, Certificate.status == "queued")
            .all()
        )

        for cert in certificates:
            _process_single_certificate(db, cert, job)

        # Determine final job status
        db.refresh(job)
        final_status = _determine_job_final_status(
            success=job.success_count,
            failure=job.failure_count,
            total=job.total_count,
        )
        job.status = final_status
        job.updated_at = _now()
        db.commit()

    except Exception as exc:
        logger.exception("Unexpected error in background processing for job_id=%s: %s", job_id, exc)
        db.rollback()
        # Attempt to mark job as failed so status is not stuck at 'processing'
        try:
            db.query(GenerationJob).filter(GenerationJob.id == job_id).update(
                {GenerationJob.status: "failed", GenerationJob.updated_at: _now()}
            )
            db.commit()
        except Exception:
            logger.exception("Could not mark job %s as failed after crash", job_id)
    finally:
        db.close()
