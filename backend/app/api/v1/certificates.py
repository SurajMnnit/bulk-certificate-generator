import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.download_service import (
    get_certificate,
    verify_certificate_downloadable,
    get_secure_download_response,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/{certificate_id}/download",
    summary="Download a generated certificate",
    description=(
        "Returns the PDF file for a completed certificate. "
        "Returns 404 if the certificate or file does not exist, "
        "and 409 if generation has not completed yet. "
        "For cloud storage, this may issue a secure redirect."
    ),
    responses={
        200: {"content": {"application/pdf": {}}},
        307: {"description": "Temporary redirect to secure cloud URL"},
        404: {"description": "Certificate or file not found"},
        409: {"description": "Certificate not ready for download"},
    },
)
def download_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    cert = get_certificate(db, str(certificate_id))
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    try:
        verify_certificate_downloadable(cert)
    except FileNotFoundError as exc:
        logger.warning("Certificate file missing: cert_id=%s path=%s", certificate_id, cert.file_path)
        raise HTTPException(status_code=404, detail="Certificate file not found on storage") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return get_secure_download_response(cert)
