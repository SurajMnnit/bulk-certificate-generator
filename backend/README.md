# Bulk Certificate Generator — Backend

A production-ready **FastAPI** backend that accepts bulk certificate generation requests, creates personalized PDF certificates asynchronously, and stores them using a pluggable storage abstraction (local filesystem or Cloudinary).

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  API Routes  │────▶│   Services   │────▶│   Database     │
│  (thin)      │     │              │     │  (PostgreSQL)  │
└─────────────┘     │  job_service  │     └────────────────┘
                    │  cert_service │────▶┌────────────────┐
                    │  pdf_service  │     │  Storage       │
                    │  download_svc │     │  (Local/Cloud) │
                    └──────────────┘     └────────────────┘
```

**Separation of concerns:**

- **API layer** (`app/api/`) — Thin route handlers. Validation, HTTP status codes, and response formatting only. No business logic.
- **Service layer** (`app/services/`) — All business logic. Job creation, background certificate processing, PDF generation, download resolution.
- **Data layer** (`app/models/`, `app/schemas/`) — SQLAlchemy 2.0 ORM models and Pydantic v2 schemas.
- **Storage layer** (`app/services/storage_service.py`) — Abstract `StorageService` with `LocalStorageService` and `CloudinaryStorageService` implementations.

---

## Technology Stack

| Component | Technology |
|---|---|
| Framework | FastAPI (Python 3.12+) |
| Database | PostgreSQL via SQLAlchemy 2.0 (Production: Neon PostgreSQL) |
| Migrations | Alembic |
| PDF Generation | ReportLab |
| Background Processing | FastAPI `BackgroundTasks` |
| Cloud Storage | Cloudinary |
| Validation | Pydantic v2 |
| Testing | Pytest + HTTPX |

---

## Setup

### 1. Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 3. Database Migrations

```bash
alembic upgrade head
```

### 4. Start the Server

```bash
uvicorn app.main:app --reload
```

Access Swagger docs at: `http://127.0.0.1:8000/docs`

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | `sqlite:///./test.db` | PostgreSQL connection string (use Neon in production) |
| `APP_ENV` | No | `development` | Application environment |
| `STORAGE_PROVIDER` | No | `local` | `local` or `cloudinary` — any other value is a startup error |
| `STORAGE_PATH` | No | `storage` | Local filesystem directory (only for `local` provider) |
| `CLOUDINARY_CLOUD_NAME` | When cloudinary | — | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | When cloudinary | — | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | When cloudinary | — | Cloudinary API secret |
| `CORS_ALLOWED_ORIGINS` | No | `*` | Comma-separated allowed origins |

> **Security:** Never commit `.env` or real credentials. Only `.env.example` with placeholders is tracked.

---

## Neon PostgreSQL

This project uses [Neon](https://neon.tech) serverless PostgreSQL in production.

Set your connection string in `.env`:

```
DATABASE_URL=postgresql://user:password@your-host.neon.tech/neondb?sslmode=require
```

Then run `alembic upgrade head` to create the schema.

---

## Database Tables

### `generation_jobs`

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `event_name` | String | Name of the event |
| `completion_date` | String | ISO date |
| `status` | String | `queued` → `processing` → `completed` / `partially_failed` / `failed` |
| `total_count` | Integer | Total recipients |
| `success_count` | Integer | Certificates generated |
| `failure_count` | Integer | Certificates failed |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC |

### `certificates`

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `job_id` | UUID (FK) | References `generation_jobs.id` with cascade delete |
| `recipient_name` | String | Recipient's full name |
| `recipient_email` | String | Recipient's email |
| `status` | String | `queued` → `processing` → `completed` / `failed` |
| `file_path` | String (nullable) | Storage key/path — never exposed in API |
| `error_message` | String (nullable) | Error details on failure |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC |

---

## Certificate Generation

Uses **ReportLab** to produce professional landscape PDF certificates containing:

- "CERTIFICATE OF COMPLETION" title
- Recipient name
- Event name
- Completion date
- Issue date (auto-generated)
- Certificate ID

No external fonts or network dependencies are required during generation.

---

## Background Processing

When `POST /api/v1/jobs` is called:

1. The API creates the job and certificate records in one transaction.
2. Returns `201 Created` immediately — the client does not wait.
3. A background task processes each certificate independently.
4. Each certificate has its own `try/except` — **a failure on one recipient never stops processing of others**.
5. Counters (`success_count`, `failure_count`) are updated atomically.
6. Final job status is determined:
   - All succeed → `completed`
   - Some fail → `partially_failed`
   - All fail → `failed`

The background task opens its own database session, independent of the request session.

---

## Storage

### Why Two Providers?

- **Local** (`STORAGE_PROVIDER=local`): Perfect for development. Saves PDFs to disk under `STORAGE_PATH`. Downloads are streamed via `FileResponse`.
- **Cloudinary** (`STORAGE_PROVIDER=cloudinary`): Required for production. Container filesystems are ephemeral. Cloudinary stores PDFs durably. Downloads use signed, time-limited redirects (HTTP 307) — the backend never streams cloud files through itself.

### Switching Providers

Change one environment variable:

```bash
STORAGE_PROVIDER=cloudinary
```

The rest of the application (services, routes, tests) does not change. Only `StorageService` is aware of the provider.

### Invalid Provider Protection

Setting `STORAGE_PROVIDER` to an unsupported value (e.g., `s3`, a typo) raises a `ValueError` at application startup. This prevents production misconfigurations from silently storing certificates on ephemeral local storage.

---

## API Endpoints

### `POST /api/v1/jobs`

Create a bulk certificate generation job.

**Request:**
```json
{
  "event_name": "Python Workshop 2026",
  "completion_date": "2026-10-07",
  "recipients": [
    {"name": "Rahul Kumar", "email": "rahul@example.com"},
    {"name": "Priya Sharma", "email": "priya@example.com"}
  ]
}
```

**Response (201):**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "total_count": 2
}
```

### `GET /api/v1/jobs/{job_id}`

Get job status and progress.

**Response (200):**
```json
{
  "job_id": "uuid",
  "event_name": "Python Workshop 2026",
  "completion_date": "2026-10-07",
  "status": "completed",
  "total_count": 2,
  "success_count": 2,
  "failure_count": 0,
  "processed_count": 2,
  "progress_percentage": 100.0,
  "created_at": "...",
  "updated_at": "..."
}
```

### `GET /api/v1/jobs/{job_id}/certificates`

List certificates for a job (with `skip`/`limit` pagination).

### `GET /api/v1/certificates/{certificate_id}/download`

Download a completed certificate PDF.

- **Local:** streams the file (200)
- **Cloudinary:** redirects to a signed URL (307)
- **Not ready:** returns 409
- **Not found:** returns 404

### `GET /health`

Health check endpoint.

---

## Testing

Tests use an isolated **SQLite in-memory database** and mock storage — no Neon database or Cloudinary account is required.

```bash
pytest -v
```

### Coverage

| Area | Tests |
|---|---|
| Job creation & validation | 7 |
| Job status & progress | 4 |
| Certificate listing | 1 |
| PDF generation & content | 2 |
| Failure isolation | 2 |
| Download (success, fail, missing) | 3 |
| Local storage (CRUD + download) | 5 |
| Cloudinary storage (mocked) | 5 |
| Provider selection & validation | 2 |
| Missing credentials | 1 |
| **Total** | **34** |

---

## Deployment

### Production Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Checklist

- [x] All config via environment variables
- [x] No hardcoded credentials or localhost URLs
- [x] No Windows-specific paths
- [x] CORS configurable via `CORS_ALLOWED_ORIGINS`
- [x] Catch-all exception handler prevents stack trace leaks
- [x] `.env` excluded from version control
- [x] Storage provider validated at startup

### Container Note

Use `STORAGE_PROVIDER=cloudinary` in production. Local filesystem storage will be lost on container restart.

---

## Known Limitations

1. **Background task durability:** Uses FastAPI's in-process `BackgroundTasks`. If the server crashes mid-job, pending certificates are not automatically resumed. For high-scale production, migrate to Celery or a task queue.
2. **Pagination:** Uses basic `skip`/`limit`. Cursor-based pagination would be more robust for very large result sets.
3. **Email delivery:** Recipient emails are stored but no notification emails are sent. Integrate SendGrid/SES to close this loop.

---

## Future Improvements

- Celery/Redis for durable background processing
- Email notification on certificate completion
- Certificate template customization
- Bulk download (ZIP) endpoint
- Admin dashboard endpoints
- Rate limiting
