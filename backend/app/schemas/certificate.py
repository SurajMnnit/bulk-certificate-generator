from pydantic import BaseModel, ConfigDict
from typing import Optional
import datetime as dt
from uuid import UUID


class CertificateResponse(BaseModel):
    """Certificate record returned in list responses.

    Note: file_path is intentionally excluded – clients use the
    /download endpoint and should never see raw filesystem paths.
    """

    id: UUID
    job_id: UUID
    recipient_name: str
    recipient_email: str
    status: str
    download_url: Optional[str] = None   # populated by the service layer
    error_message: Optional[str] = None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=False)
