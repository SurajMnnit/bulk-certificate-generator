"""
Test suite for the Bulk Certificate Generator backend.

Uses an in-memory SQLite database so no production (Neon) database is
touched.  All tests are synchronous and use FastAPI's TestClient.
"""

import os
import shutil
import time
import uuid
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.database import get_db
from app.core.config import settings
from app.models.generation_job import GenerationJob, _now
from app.models.certificate import Certificate


# ---------------------------------------------------------------------------
# Test database & storage setup
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///./test_suite.db"
TEST_STORAGE = "test_storage_suite"

_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session", autouse=True)
def _setup_test_env():
    """Create schema and temp storage once per test session, clean up after."""
    Base.metadata.create_all(bind=_engine)
    os.makedirs(TEST_STORAGE, exist_ok=True)
    settings.STORAGE_PATH = TEST_STORAGE
    
    # Force API tests to use local storage regardless of .env configuration
    from app.services.storage_service import LocalStorageService
    import app.services.storage_service as storage_module
    import app.services.certificate_service as cert_svc
    import app.services.download_service as dl_svc
    local_storage = LocalStorageService()
    storage_module.storage_service = local_storage
    cert_svc.storage_service = local_storage
    dl_svc.storage_service = local_storage

    yield
    Base.metadata.drop_all(bind=_engine)
    shutil.rmtree(TEST_STORAGE, ignore_errors=True)
    if os.path.exists("./test_suite.db"):
        try:
            os.remove("./test_suite.db")
        except PermissionError:
            pass  # Windows may keep the file locked briefly


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    session = _TestingSession()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "event_name": "Python Workshop 2026",
    "completion_date": "2026-10-07",
    "recipients": [
        {"name": "Rahul Kumar", "email": "rahul@example.com"},
        {"name": "Priya Sharma", "email": "priya@example.com"},
    ],
}


def _create_job(client, payload=None):
    payload = payload or _VALID_PAYLOAD
    return client.post("/api/v1/jobs", json=payload)


def _wait_for_job(client, job_id: str, timeout: int = 10) -> dict:
    """Poll until job leaves 'processing'/'queued' state or timeout."""
    for _ in range(timeout * 2):
        r = client.get(f"/api/v1/jobs/{job_id}")
        data = r.json()
        if data["status"] not in ("queued", "processing"):
            return data
        time.sleep(0.5)
    return client.get(f"/api/v1/jobs/{job_id}").json()


# ===========================================================================
# 1. Successful job creation
# ===========================================================================

def test_create_job_success(client):
    resp = _create_job(client)
    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["total_count"] == 2


# ===========================================================================
# 2. Invalid event name (blank)
# ===========================================================================

def test_create_job_blank_event_name(client):
    payload = {**_VALID_PAYLOAD, "event_name": "   "}
    resp = _create_job(client, payload)
    assert resp.status_code == 422


# ===========================================================================
# 3. Invalid / missing completion_date
# ===========================================================================

def test_create_job_invalid_date(client):
    payload = {**_VALID_PAYLOAD, "completion_date": "not-a-date"}
    resp = _create_job(client, payload)
    assert resp.status_code == 422


def test_create_job_missing_date(client):
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "completion_date"}
    resp = _create_job(client, payload)
    assert resp.status_code == 422


# ===========================================================================
# 4. Empty recipients list
# ===========================================================================

def test_create_job_empty_recipients(client):
    payload = {**_VALID_PAYLOAD, "recipients": []}
    resp = _create_job(client, payload)
    assert resp.status_code == 422


# ===========================================================================
# 5. Invalid email in recipient
# ===========================================================================

def test_create_job_invalid_email(client):
    payload = {
        **_VALID_PAYLOAD,
        "recipients": [{"name": "Alice", "email": "not-an-email"}],
    }
    resp = _create_job(client, payload)
    assert resp.status_code == 422


def test_create_job_blank_recipient_name(client):
    payload = {
        **_VALID_PAYLOAD,
        "recipients": [{"name": "  ", "email": "alice@example.com"}],
    }
    resp = _create_job(client, payload)
    assert resp.status_code == 422


# ===========================================================================
# 6. Job status retrieval
# ===========================================================================

def test_get_job_status(client):
    resp = _create_job(client)
    job_id = resp.json()["job_id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["job_id"] == job_id
    assert data["event_name"] == _VALID_PAYLOAD["event_name"]
    assert "progress_percentage" in data
    assert "processed_count" in data


# ===========================================================================
# 7. Certificate listing for a job
# ===========================================================================

def test_list_certificates(client):
    resp = _create_job(client)
    job_id = resp.json()["job_id"]

    certs_resp = client.get(f"/api/v1/jobs/{job_id}/certificates")
    assert certs_resp.status_code == 200
    certs = certs_resp.json()
    assert isinstance(certs, list)
    assert len(certs) == 2
    for cert in certs:
        assert "id" in cert
        assert "recipient_name" in cert
        assert "status" in cert
        assert "file_path" not in cert  # must never be exposed


# ===========================================================================
# 8. Successful PDF generation (end-to-end)
# ===========================================================================

def test_pdf_generation_end_to_end(client):
    from app.services.pdf_service import PDFService

    pdf_bytes = PDFService.generate_certificate(
        recipient_name="Test User",
        event_name="Test Event",
        completion_date="2026-10-07",
        certificate_id=str(uuid.uuid4()),
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 100
    assert pdf_bytes[:4] == b"%PDF"


# ===========================================================================
# 9. Certificate marked as failed on generation error
# ===========================================================================

def test_certificate_fails_gracefully(client, db):
    from app.services.certificate_service import _process_single_certificate
    from app.services.storage_service import storage_service
    from unittest.mock import patch

    # Create a job and certificate directly in DB
    job = GenerationJob(
        id=uuid.uuid4(),
        event_name="Error Event",
        completion_date="2026-10-07",
        total_count=1,
        status="processing",
    )
    db.add(job)
    db.flush()

    cert = Certificate(
        id=uuid.uuid4(),
        job_id=job.id,
        recipient_name="Fail User",
        recipient_email="fail@example.com",
        status="queued",
    )
    db.add(cert)
    db.commit()

    with patch(
        "app.services.certificate_service.storage_service.save",
        side_effect=RuntimeError("disk full"),
    ):
        _process_single_certificate(db, cert, job)

    db.refresh(cert)
    assert cert.status == "failed"
    assert "disk full" in (cert.error_message or "")


# ===========================================================================
# 10. Failure isolation – one failure must not stop other recipients
# ===========================================================================

def test_failure_does_not_stop_other_recipients(client, db):
    from app.services.certificate_service import process_job_certificates_background
    from app.services.storage_service import LocalStorageService
    from unittest.mock import patch

    job = GenerationJob(
        id=uuid.uuid4(),
        event_name="Isolation Test",
        completion_date="2026-10-07",
        total_count=3,
        status="processing",
    )
    db.add(job)
    db.flush()

    certs = [
        Certificate(id=uuid.uuid4(), job_id=job.id, recipient_name=f"User {i}",
                    recipient_email=f"user{i}@example.com", status="queued")
        for i in range(3)
    ]
    db.add_all(certs)
    db.commit()

    local_storage = LocalStorageService()
    call_count = [0]
    original_save = local_storage.save

    def _flaky_save(content, job_id, certificate_id):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("simulated failure on cert 2")
        return original_save(content=content, job_id=job_id, certificate_id=certificate_id)

    with patch("app.services.certificate_service.storage_service.save", side_effect=_flaky_save), \
         patch("app.services.certificate_service.SessionLocal", return_value=db):
        job_id = job.id
        process_job_certificates_background(str(job_id))

    # Re-fetch via a new DB session or test client since 'db' was closed
    db_new = _TestingSession()
    try:
        refreshed_job = db_new.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        refreshed_certs = db_new.query(Certificate).filter(Certificate.job_id == job_id).all()
        
        statuses = [c.status for c in refreshed_certs]

        # 2 succeeded, 1 failed
        assert statuses.count("completed") == 2
        assert statuses.count("failed") == 1

        assert refreshed_job.status == "partially_failed"
        assert refreshed_job.success_count == 2
        assert refreshed_job.failure_count == 1
    finally:
        db_new.close()


# ===========================================================================
# 11. Download a completed certificate
# ===========================================================================

def test_download_completed_certificate(client, db):
    import os

    job = GenerationJob(
        id=uuid.uuid4(),
        event_name="Download Event",
        completion_date="2026-10-07",
        total_count=1,
        status="completed",
    )
    db.add(job)
    db.flush()

    cert_id = uuid.uuid4()
    # Write a real (tiny) PDF file
    pdf_dir = os.path.join(TEST_STORAGE, str(job.id))
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"{cert_id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4 fake pdf content")

    cert = Certificate(
        id=cert_id,
        job_id=job.id,
        recipient_name="Download User",
        recipient_email="dl@example.com",
        status="completed",
        file_path=pdf_path,
    )
    db.add(cert)
    db.commit()

    resp = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]


# ===========================================================================
# 12. Download a failed/not-ready certificate returns 409
# ===========================================================================

def test_download_failed_certificate_returns_409(client, db):
    job = GenerationJob(
        id=uuid.uuid4(),
        event_name="Fail Download",
        completion_date="2026-10-07",
        total_count=1,
        status="partially_failed",
    )
    db.add(job)
    db.flush()

    cert = Certificate(
        id=uuid.uuid4(),
        job_id=job.id,
        recipient_name="Failed User",
        recipient_email="fail@example.com",
        status="failed",
        error_message="PDF generation failed",
    )
    db.add(cert)
    db.commit()

    resp = client.get(f"/api/v1/certificates/{cert.id}/download")
    assert resp.status_code == 409


# ===========================================================================
# 13. Unknown job returns 404
# ===========================================================================

def test_unknown_job_returns_404(client):
    fake_id = uuid.uuid4()
    resp = client.get(f"/api/v1/jobs/{fake_id}")
    assert resp.status_code == 404


def test_unknown_job_certificates_returns_404(client):
    fake_id = uuid.uuid4()
    resp = client.get(f"/api/v1/jobs/{fake_id}/certificates")
    assert resp.status_code == 404


# ===========================================================================
# 14. Unknown certificate returns 404
# ===========================================================================

def test_unknown_certificate_download_returns_404(client):
    fake_id = uuid.uuid4()
    resp = client.get(f"/api/v1/certificates/{fake_id}/download")
    assert resp.status_code == 404


# ===========================================================================
# 15. Progress calculation
# ===========================================================================

def test_progress_calculation(client, db):
    job = GenerationJob(
        id=uuid.uuid4(),
        event_name="Progress Event",
        completion_date="2026-10-07",
        total_count=10,
        status="processing",
        success_count=7,
        failure_count=1,
    )
    db.add(job)
    db.commit()

    resp = client.get(f"/api/v1/jobs/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed_count"] == 8
    assert data["progress_percentage"] == 80.0


def test_progress_zero_division_safe(client, db):
    """A job with total_count=0 must not cause a division-by-zero error."""
    job = GenerationJob(
        id=uuid.uuid4(),
        event_name="Empty Event",
        completion_date="2026-10-07",
        total_count=0,
        status="queued",
    )
    db.add(job)
    db.commit()

    resp = client.get(f"/api/v1/jobs/{job.id}")
    assert resp.status_code == 200
    assert resp.json()["progress_percentage"] == 0.0
