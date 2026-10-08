
import logging
from sqlalchemy.orm import Session
from fastapi.responses import Response

from app.models.certificate import Certificate
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


def get_certificate(db: Session, certificate_id: str) -> Certificate | None:
    return db.query(Certificate).filter(Certificate.id == certificate_id).first()


def verify_certificate_downloadable(cert: Certificate) -> None:
    """Raise a descriptive ValueError if the certificate cannot be downloaded.

    Callers (route handlers) convert this to the appropriate HTTP error.
    """
    if cert.status != "completed":
        raise ValueError(f"Certificate is not ready for download (status={cert.status})")
    if not cert.file_path:
        raise ValueError("Certificate file path is not recorded")
    if not storage_service.exists(cert.file_path):
        raise FileNotFoundError(f"Certificate file not found on storage")


def get_secure_download_response(cert: Certificate) -> Response:
    """Generate a secure response (file stream or redirect) based on the storage provider."""
    if not cert.file_path:
        raise ValueError("No file_path recorded for certificate")
    
    # Sanitize filename: keep only safe characters for Content-Disposition
    import re
    sanitized = re.sub(r"[^\w\s-]", "", cert.recipient_name).strip().replace(" ", "_")
    safe_name = f"certificate_{sanitized or 'download'}.pdf"
    
    return storage_service.get_download_response(cert.file_path, safe_name)
