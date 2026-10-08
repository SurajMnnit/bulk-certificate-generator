from pydantic import BaseModel, ConfigDict, field_validator, EmailStr
from typing import List
from datetime import date
from uuid import UUID
import datetime as dt


class RecipientInput(BaseModel):
    name: str
    email: EmailStr

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Recipient name must not be blank")
        return stripped


class JobCreate(BaseModel):
    event_name: str
    completion_date: date
    recipients: List[RecipientInput]

    @field_validator("event_name")
    @classmethod
    def event_name_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("event_name must not be blank")
        return stripped

    @field_validator("recipients")
    @classmethod
    def recipients_must_not_be_empty(cls, v: List[RecipientInput]) -> List[RecipientInput]:
        if not v:
            raise ValueError("At least one recipient is required")
        return v


class JobCreateResponse(BaseModel):
    """Slim response returned immediately after job creation."""
    job_id: UUID
    status: str
    total_count: int


class JobStatusResponse(BaseModel):
    """Full job status response including progress fields."""
    job_id: UUID
    event_name: str
    completion_date: str
    status: str
    total_count: int
    success_count: int
    failure_count: int
    processed_count: int
    progress_percentage: float
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)
