"""
Storage service tests.

Cloud tests mock Cloudinary entirely so no real account or network
connection is required to run the suite.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.responses import FileResponse, RedirectResponse

from app.core.config import settings
from app.services.storage_service import LocalStorageService, CloudinaryStorageService


# ---------------------------------------------------------------------------
# Local Storage
# ---------------------------------------------------------------------------

def test_local_save_creates_file(tmp_path):
    settings.STORAGE_PATH = str(tmp_path)
    service = LocalStorageService()

    path = service.save(b"fake-pdf", "job-1", "cert-1")

    assert path.endswith("cert-1.pdf")
    assert "job-1" in path
    assert os.path.isfile(path)


def test_local_exists(tmp_path):
    settings.STORAGE_PATH = str(tmp_path)
    service = LocalStorageService()

    path = service.save(b"data", "job-2", "cert-2")
    assert service.exists(path) is True
    assert service.exists("nonexistent/path.pdf") is False


def test_local_get_returns_content(tmp_path):
    settings.STORAGE_PATH = str(tmp_path)
    service = LocalStorageService()

    content = b"hello pdf"
    path = service.save(content, "job-3", "cert-3")
    assert service.get(path) == content


def test_local_delete(tmp_path):
    settings.STORAGE_PATH = str(tmp_path)
    service = LocalStorageService()

    path = service.save(b"bye", "job-4", "cert-4")
    assert service.delete(path) is True
    assert service.exists(path) is False
    assert service.delete(path) is False  # idempotent


def test_local_download_response(tmp_path):
    settings.STORAGE_PATH = str(tmp_path)
    service = LocalStorageService()

    path = service.save(b"%PDF", "job-5", "cert-5")
    response = service.get_download_response(path, "test.pdf")
    assert isinstance(response, FileResponse)


# ---------------------------------------------------------------------------
# Cloudinary Storage (fully mocked – no real credentials needed)
# ---------------------------------------------------------------------------

@pytest.fixture()
def cloudinary_settings(monkeypatch):
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    monkeypatch.setattr(settings, "CLOUDINARY_API_KEY", "test-key")
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", "test-secret")


@patch("cloudinary.config")
@patch("cloudinary.uploader.upload")
def test_cloudinary_save(mock_upload, mock_config, cloudinary_settings):
    mock_upload.return_value = {"public_id": "certificates/job-a/cert-a"}

    service = CloudinaryStorageService()
    key = service.save(b"%PDF-data", "job-a", "cert-a")

    assert key == "certificates/job-a/cert-a"
    mock_upload.assert_called_once()
    call_kwargs = mock_upload.call_args.kwargs
    assert call_kwargs["public_id"] == "certificates/job-a/cert-a"
    assert call_kwargs["resource_type"] == "raw"


@patch("cloudinary.config")
@patch("cloudinary.api.resource")
def test_cloudinary_exists_true(mock_resource, mock_config, cloudinary_settings):
    mock_resource.return_value = {"public_id": "certificates/job-b/cert-b"}

    service = CloudinaryStorageService()
    assert service.exists("certificates/job-b/cert-b") is True
    mock_resource.assert_called_once_with("certificates/job-b/cert-b", resource_type="raw")


@patch("cloudinary.config")
@patch("cloudinary.api.resource")
def test_cloudinary_exists_false_on_not_found(mock_resource, mock_config, cloudinary_settings):
    from cloudinary.exceptions import NotFound
    mock_resource.side_effect = NotFound()

    service = CloudinaryStorageService()
    assert service.exists("nonexistent") is False


@patch("cloudinary.config")
@patch("cloudinary.uploader.destroy")
def test_cloudinary_delete(mock_destroy, mock_config, cloudinary_settings):
    mock_destroy.return_value = {"result": "ok"}

    service = CloudinaryStorageService()
    assert service.delete("certificates/job-c/cert-c") is True
    mock_destroy.assert_called_once_with("certificates/job-c/cert-c", resource_type="raw")


@patch("cloudinary.config")
@patch("cloudinary.utils.cloudinary_url")
def test_cloudinary_download_response_is_redirect(mock_url, mock_config, cloudinary_settings):
    mock_url.return_value = ("https://res.cloudinary.com/signed-url", {})

    service = CloudinaryStorageService()
    response = service.get_download_response("certificates/job-d/cert-d", "cert.pdf")

    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "https://res.cloudinary.com/signed-url"
    assert response.status_code == 307


def test_cloudinary_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", None)
    monkeypatch.setattr(settings, "CLOUDINARY_API_KEY", None)
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", None)

    with pytest.raises(ValueError, match="Missing required Cloudinary"):
        CloudinaryStorageService()


# ---------------------------------------------------------------------------
# Factory / provider selection
# ---------------------------------------------------------------------------

def test_unknown_provider_raises_at_startup(monkeypatch):
    """An unrecognised STORAGE_PROVIDER must raise ValueError immediately.

    This prevents a production typo from silently storing certificates on
    an ephemeral container filesystem instead of the intended cloud backend.
    """
    from app.services.storage_service import get_storage_service

    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3")
    with pytest.raises(ValueError, match="Unknown STORAGE_PROVIDER"):
        get_storage_service()


def test_local_provider_does_not_require_cloudinary_credentials(monkeypatch):
    """Local development must work without any Cloudinary credentials."""
    from app.services.storage_service import get_storage_service

    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local")
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", None)
    monkeypatch.setattr(settings, "CLOUDINARY_API_KEY", None)
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", None)

    service = get_storage_service()
    assert isinstance(service, LocalStorageService)
