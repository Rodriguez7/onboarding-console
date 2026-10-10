"""Customer-facing REST API, authenticated with workspace API keys.

Every request is logged to ``api_request_logs`` so the console can monitor the integration.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import webhooks
from ..db import get_db
from ..models import ApiCredential, ApiRequestLog, CustomerRecord, utcnow
from ..platform_schema import validate_record
from ..schemas import IngestIn, IngestOut, IngestRejected
from .integrations import hash_key

router = APIRouter(prefix="/api/v1", tags=["customer api"])


def _log(db: Session, cred: ApiCredential, request: Request, started: float, status: int, error: str | None = None):
    db.add(ApiRequestLog(
        workspace_id=cred.workspace_id,
        method=request.method,
        path=request.url.path,
        status_code=status,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        error=error,
    ))


def authenticate(request: Request, db: Session = Depends(get_db)) -> ApiCredential:
    auth = request.headers.get("authorization", "")
    scheme, _, key = auth.partition(" ")
    if scheme.lower() != "bearer" or not key:
        raise HTTPException(401, "Missing bearer API key", headers={"WWW-Authenticate": "Bearer"})
    cred = db.scalar(select(ApiCredential).where(ApiCredential.key_hash == hash_key(key.strip())))
    if not cred:
        raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "Bearer"})
    if cred.revoked_at:
        # Known workspace, so record it: revoked keys still in use are an integration problem worth seeing.
        _log(db, cred, request, time.perf_counter(), 401, "Revoked API key used")
        db.commit()
        raise HTTPException(401, "API key has been revoked", headers={"WWW-Authenticate": "Bearer"})
    cred.last_used_at = utcnow()
    return cred


@router.post("/records", response_model=IngestOut)
def upsert_records(body: IngestIn, request: Request, cred: ApiCredential = Depends(authenticate),
                   db: Session = Depends(get_db)):
    started = time.perf_counter()
    rejected: list[IngestRejected] = []
    accepted: list[dict] = []
    for i, rec in enumerate(body.records):
        normalized, errors = validate_record(rec)
        if errors:
            rejected.append(IngestRejected(index=i, errors=errors))
        else:
            accepted.append(normalized)

    for data in accepted:
        ext = str(data["external_id"])
        existing = db.scalar(select(CustomerRecord).where(
            CustomerRecord.workspace_id == cred.workspace_id, CustomerRecord.external_id == ext))
        if existing:
            existing.data, existing.source = data, "api"
        else:
            db.add(CustomerRecord(workspace_id=cred.workspace_id, external_id=ext, data=data, source="api"))
        webhooks.emit(db, cred.workspace_id, "record.upserted", data)

    status = 200 if accepted or not rejected else 422
    _log(db, cred, request, started, status,
         f"{len(rejected)} of {len(body.records)} records rejected" if rejected else None)
    db.commit()
    payload = IngestOut(accepted=len(accepted), rejected=rejected)
    return JSONResponse(payload.model_dump(), status_code=status)


@router.get("/records")
def list_records(request: Request, limit: int = 50, cred: ApiCredential = Depends(authenticate),
                 db: Session = Depends(get_db)):
    started = time.perf_counter()
    rows = db.scalars(
        select(CustomerRecord).where(CustomerRecord.workspace_id == cred.workspace_id)
        .order_by(CustomerRecord.external_id).limit(min(limit, 500))
    ).all()
    _log(db, cred, request, started, 200)
    db.commit()
    return {"records": [{"external_id": r.external_id, "source": r.source, **r.data} for r in rows]}
