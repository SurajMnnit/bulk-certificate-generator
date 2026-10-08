import os
import logging
from abc import ABC, abstractmethod
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService(ABC):
    """Abstract base class for all storage backends.

    The rest of the application depends only on this interface.
    Provider-specific logic is fully contained within each subclass.
    """

    @abstractmethod
    def save(self, content: bytes, job_id: str, certificate_id: str) -> str:
        """Persist PDF bytes and return a storage key/path for the database."""

    @abstractmethod
    def exists(self, file_path: str) -> bool:
        """Return True if the stored file identified by file_path/key exists."""

    @abstractmethod
    def get(self, file_path: str) -> bytes:
        """Retrieve raw bytes of the stored file."""

    @abstractmethod
    def delete(self, file_path: str) -> bool:
        """Delete the stored file. Returns True on success."""

    @abstractmethod
    def get_download_response(self, file_path: str, filename: str) -> Response:
        """Return a FastAPI Response for securely downloading the file.

        For local storage this streams the file.
        For cloud storage this issues a secure temporary redirect.
        """


# ---------------------------------------------------------------------------
# Local Storage
# ---------------------------------------------------------------------------

class LocalStorageService(StorageService):
    """Stores PDFs on the local filesystem under STORAGE_PATH/{job_id}/{cert_id}.pdf.

    Suitable for development and environments with persistent disk storage.
    Not suitable for ephemeral container deployments – use CloudinaryStorageService
    in production.
    """

    def save(self, content: bytes, job_id: str, certificate_id: str) -> str:
        dir_path = os.path.join(settings.STORAGE_PATH, job_id)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, f"{certificate_id}.pdf")
        with open(file_path, "wb") as f:
            f.write(content)
        # Forward slashes for cross-platform consistency in DB records
        return file_path.replace("\\", "/")

    def exists(self, file_path: str) -> bool:
        return os.path.isfile(file_path)

    def get(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    def delete(self, file_path: str) -> bool:
        try:
            os.remove(file_path)
            return True
        except FileNotFoundError:
            return False

    def get_download_response(self, file_path: str, filename: str) -> Response:
        abs_path = os.path.abspath(file_path)
        return FileResponse(
            path=abs_path,
            filename=filename,
            media_type="application/pdf",
        )


# ---------------------------------------------------------------------------
# Cloudinary Storage
# ---------------------------------------------------------------------------

class CloudinaryStorageService(StorageService):
    """Stores PDF certificates in Cloudinary using resource_type='raw'.

    Activated by setting STORAGE_PROVIDER=cloudinary in the environment.
    Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and
    CLOUDINARY_API_SECRET to be set.

    Downloads issue a secure, signed temporary redirect (not a permanent
    public URL) so the Cloudinary bucket does not need to be publicly
    accessible.
    """

    # Signed URL expiry in seconds (5 minutes)
    _SIGNED_URL_TTL = 300

    def __init__(self) -> None:
        try:
            import cloudinary
            import cloudinary.uploader
            import cloudinary.api
            import cloudinary.utils
        except ImportError:
            raise RuntimeError(
                "The 'cloudinary' package is required when STORAGE_PROVIDER=cloudinary. "
                "Run: pip install cloudinary"
            )

        missing = [
            name
            for name, val in {
                "CLOUDINARY_CLOUD_NAME": settings.CLOUDINARY_CLOUD_NAME,
                "CLOUDINARY_API_KEY": settings.CLOUDINARY_API_KEY,
                "CLOUDINARY_API_SECRET": settings.CLOUDINARY_API_SECRET,
            }.items()
            if not val
        ]
        if missing:
            raise ValueError(
                f"Missing required Cloudinary environment variables: {', '.join(missing)}"
            )

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )

    def _public_id(self, job_id: str, certificate_id: str) -> str:
        """Build a stable, namespaced Cloudinary public_id."""
        return f"certificates/{job_id}/{certificate_id}"

    def save(self, content: bytes, job_id: str, certificate_id: str) -> str:
        import cloudinary.uploader

        public_id = self._public_id(job_id, certificate_id)
        result = cloudinary.uploader.upload(
            content,
            public_id=public_id,
            resource_type="raw",  # 'raw' preserves the PDF as-is without re-encoding
            overwrite=True,
        )
        # Store only the public_id in the database – never an expiring URL
        stored_key: str = result["public_id"]
        return stored_key

    def exists(self, file_path: str) -> bool:
        import cloudinary.api
        from cloudinary.exceptions import NotFound

        try:
            cloudinary.api.resource(file_path, resource_type="raw")
            return True
        except NotFound:
            return False
        except Exception as exc:
            logger.warning("Cloudinary exists() check failed for %s: %s", file_path, exc)
            return False

    def get(self, file_path: str) -> bytes:
        """Download raw bytes from Cloudinary (used internally)."""
        import cloudinary.utils
        import urllib.request

        url, _ = cloudinary.utils.cloudinary_url(
            file_path,
            resource_type="raw",
            secure=True,
        )
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            return resp.read()

    def delete(self, file_path: str) -> bool:
        import cloudinary.uploader

        result = cloudinary.uploader.destroy(file_path, resource_type="raw")
        return result.get("result") == "ok"

    def get_download_response(self, file_path: str, filename: str) -> Response:
        """Issue a signed, temporary Cloudinary URL and redirect the client.

        The URL expires after _SIGNED_URL_TTL seconds so the bucket can
        remain private.  The fl_attachment flag forces a browser download
        with the correct filename rather than an inline preview.
        """
        import cloudinary.utils
        import time

        expires_at = int(time.time()) + self._SIGNED_URL_TTL
        safe_filename = filename.replace('"', "")  # Guard against header injection

        url, _ = cloudinary.utils.cloudinary_url(
            file_path,
            resource_type="raw",
            secure=True,
            sign_url=True,
            expires_at=expires_at,
            attachment=safe_filename,
        )
        return RedirectResponse(url=url, status_code=307)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage_service() -> StorageService:
    """Instantiate the correct StorageService based on STORAGE_PROVIDER env var.

    Supported values:
        local        – LocalStorageService
        cloudinary   – CloudinaryStorageService

    Any other value raises a ValueError at startup so that a production
    misconfiguration is caught immediately rather than silently falling back
    to local storage (which would cause certificates to be stored on an
    ephemeral container filesystem instead of Cloudinary).
    """
    provider = settings.STORAGE_PROVIDER.strip().lower()
    if provider == "local":
        return LocalStorageService()
    if provider == "cloudinary":
        return CloudinaryStorageService()
    raise ValueError(
        f"Unknown STORAGE_PROVIDER={settings.STORAGE_PROVIDER!r}. "
        "Supported values are: 'local', 'cloudinary'."
    )


# Module-level singleton – imported across the application
storage_service: StorageService = get_storage_service()
