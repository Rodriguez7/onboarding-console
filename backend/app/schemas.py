from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from .webhooks import EVENTS


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Workspaces -----------------------------------------------------------------------------

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    customer_contact_email: EmailStr
    specialist_name: str = Field(min_length=2, max_length=200)
    target_go_live: date | None = None


class WorkspaceOut(ORM):
    id: str
    name: str
    slug: str
    customer_contact_email: str
    specialist_name: str
    target_go_live: date | None
    status: str
    went_live_at: datetime | None
    created_at: datetime


class Step(BaseModel):
    key: str
    label: str
    complete: bool
    detail: str


class WorkspaceDetail(WorkspaceOut):
    steps: list[Step]
    blockers: list[str]


# --- Imports --------------------------------------------------------------------------------

class MappingSuggestion(BaseModel):
    field: str | None
    confidence: float


class ImportJobOut(ORM):
    id: str
    workspace_id: str
    filename: str
    headers: list[str]
    mapping: dict[str, str | None]
    status: str
    row_count: int
    valid_count: int
    invalid_count: int
    committed_count: int
    created_at: datetime


class ImportJobCreated(ImportJobOut):
    suggested_mapping: dict[str, MappingSuggestion]
    preview: list[dict[str, str]]


class MappingIn(BaseModel):
    mapping: dict[str, str | None]


class ImportRowOut(ORM):
    id: str
    row_number: int
    raw: dict[str, str]
    overrides: dict[str, str]
    normalized: dict
    errors: list[dict[str, str]]
    is_valid: bool


class RowFix(BaseModel):
    values: dict[str, str]


# --- Credentials & webhooks -----------------------------------------------------------------

class CredentialCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    environment: Literal["sandbox", "production"] = "sandbox"


class CredentialOut(ORM):
    id: str
    name: str
    environment: str
    key_prefix: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CredentialCreated(CredentialOut):
    api_key: str = Field(description="Shown once; only a hash is stored.")


class WebhookCreate(BaseModel):
    url: HttpUrl
    description: str = Field(default="", max_length=500)
    events: list[str] = Field(default_factory=lambda: list(EVENTS), min_length=1)

    @field_validator("events")
    @classmethod
    def known_events(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(EVENTS))
        if unknown:
            raise ValueError(f"unknown events: {', '.join(unknown)}")
        return sorted(set(v), key=EVENTS.index)


class WebhookUpdate(BaseModel):
    active: bool | None = None
    description: str | None = Field(default=None, max_length=500)


class WebhookOut(ORM):
    id: str
    url: str
    description: str
    events: list[str]
    secret: str
    active: bool
    created_at: datetime


class DeliveryOut(ORM):
    id: str
    endpoint_id: str
    event: str
    payload: dict
    attempt: int
    success: bool
    status_code: int | None
    error: str | None
    response_excerpt: str | None
    duration_ms: float
    created_at: datetime


# --- Tests, UAT -----------------------------------------------------------------------------

class Check(BaseModel):
    key: str
    name: str
    status: Literal["passed", "warning", "failed"]
    detail: str


class TestRunOut(ORM):
    id: str
    passed: bool
    checks: list[Check]
    created_at: datetime


class UATItemOut(ORM):
    id: str
    position: int
    category: str
    title: str
    done: bool
    notes: str
    completed_by: str | None
    completed_at: datetime | None


class UATItemCreate(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=3, max_length=300)


class UATItemUpdate(BaseModel):
    done: bool | None = None
    notes: str | None = None
    completed_by: str | None = Field(default=None, max_length=200)


# --- Ingest API -----------------------------------------------------------------------------

class IngestIn(BaseModel):
    records: list[dict[str, object]] = Field(min_length=1, max_length=1000)


class IngestRejected(BaseModel):
    index: int
    errors: list[dict[str, str]]


class IngestOut(BaseModel):
    accepted: int
    rejected: list[IngestRejected]
