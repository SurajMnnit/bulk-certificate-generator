import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.job import JobCreate, JobCreateResponse, JobStatusResponse
from app.schemas.certificate import CertificateResponse
from app.services import job_service, certificate_service
from app.services.certificate_service import process_job_certificates_background

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=201,
    summary="Create bulk certificate generation job",
    description=(
        "Accepts an event name, completion date, and a list of recipients. "
        "Creates a job and all certificate records, then immediately returns. "
        "PDF generation happens asynchronously in the background."
    ),
)
def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    job = job_service.create_job(db, payload)
    background_tasks.add_task(process_job_certificates_background, str(job.id))
    logger.info("Job %s created with %d recipients", job.id, job.total_count)
    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Returns current job status, counters, and progress percentage.",
    responses={404: {"description": "Job not found"}},
)
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = job_service.get_job(db, str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    processed_count = job.success_count + job.failure_count
    progress_percentage = (
        round((processed_count / job.total_count) * 100, 2)
        if job.total_count > 0
        else 0.0
    )

    return JobStatusResponse(
        job_id=job.id,
        event_name=job.event_name,
        completion_date=job.completion_date,
        status=job.status,
        total_count=job.total_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        processed_count=processed_count,
        progress_percentage=progress_percentage,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/{job_id}/certificates",
    response_model=list[CertificateResponse],
    summary="List certificates for a job",
    description="Returns all certificates for the given job with pagination support.",
    responses={404: {"description": "Job not found"}},
)
def list_certificates(
    job_id: UUID,
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[CertificateResponse]:
    job = job_service.get_job(db, str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    certs = job_service.get_job_certificates(db, str(job_id), skip=skip, limit=limit)
    base_url = str(request.base_url)
    return [job_service.build_certificate_response(cert, base_url) for cert in certs]
