import csv
import io
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import webhooks
from ..config import settings
from ..db import get_db
from ..deps import get_owned, get_workspace
from ..mapping import mapping_problems, suggest_mapping
from ..models import CustomerRecord, ImportJob, ImportRow, Workspace
from ..platform_schema import schema_as_dicts, validate_record
from ..schemas import ImportJobCreated, ImportJobOut, ImportRowOut, MappingIn, RowFix

router = APIRouter(tags=["imports"])


@router.get("/schema")
def platform_schema():
    """The platform fields incoming data is mapped onto."""
    return schema_as_dicts()


def _parse_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "File must be UTF-8 encoded CSV")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise HTTPException(422, "CSV is empty")
    headers = [h.strip() for h in rows[0]]
    if any(not h for h in headers):
        raise HTTPException(422, "Every column needs a header")
    dupes = [h for h, n in Counter(headers).items() if n > 1]
    if dupes:
        raise HTTPException(422, f"Duplicate column headers: {', '.join(dupes)}")
    body = rows[1:]
    if not body:
        raise HTTPException(422, "CSV has a header row but no data")
    if len(body) > settings.max_import_rows:
        raise HTTPException(413, f"CSV exceeds {settings.max_import_rows} rows")
    records = [{h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(headers)} for r in body]
    return headers, records


@router.post("/workspaces/{workspace_id}/imports", response_model=ImportJobCreated, status_code=201)
async def upload_csv(file: UploadFile, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB")
    headers, records = _parse_csv(data)
    suggested = suggest_mapping(headers)
    job = ImportJob(
        workspace_id=ws.id,
        filename=file.filename or "upload.csv",
        headers=headers,
        mapping={h: s["field"] for h, s in suggested.items()},
        row_count=len(records),
    )
    job.rows = [ImportRow(row_number=i + 1, raw=r) for i, r in enumerate(records)]
    db.add(job)
    db.commit()
    return ImportJobCreated(
        **ImportJobOut.model_validate(job).model_dump(), suggested_mapping=suggested, preview=records[:5]
    )


@router.get("/workspaces/{workspace_id}/imports", response_model=list[ImportJobOut])
def list_imports(ws: Workspace = Depends(get_workspace)):
    return list(reversed(ws.imports))


@router.get("/workspaces/{workspace_id}/imports/{job_id}", response_model=ImportJobOut)
def get_import(job_id: str, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return get_owned(db, ImportJob, job_id, ws.id, "Import")


def _validate_row(row: ImportRow, mapping: dict[str, str | None], seen_ids: Counter) -> None:
    values: dict[str, object] = {target: row.raw.get(src, "") for src, target in mapping.items() if target}
    values.update(row.overrides)
    normalized, errors = validate_record(values)
    ext = normalized.get("external_id")
    if ext and seen_ids[ext] > 1:
        errors.append({"field": "external_id", "message": f"External ID '{ext}' appears {seen_ids[ext]} times"})
    row.normalized, row.errors, row.is_valid = normalized, errors, not errors


def _revalidate(job: ImportJob) -> None:
    def ext_id(row: ImportRow) -> str:
        src = next((s for s, t in job.mapping.items() if t == "external_id"), None)
        return str(row.overrides.get("external_id") or (row.raw.get(src, "") if src else "")).strip()

    seen = Counter(i for i in map(ext_id, job.rows) if i)
    for row in job.rows:
        _validate_row(row, job.mapping, seen)
    job.valid_count = sum(r.is_valid for r in job.rows)
    job.invalid_count = job.row_count - job.valid_count
    job.status = "validated"


@router.put("/workspaces/{workspace_id}/imports/{job_id}/mapping", response_model=ImportJobOut)
def apply_mapping(job_id: str, body: MappingIn, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    job = get_owned(db, ImportJob, job_id, ws.id, "Import")
    if job.status == "committed":
        raise HTTPException(409, "Import already committed")
    problems = mapping_problems(body.mapping, job.headers)
    if problems:
        raise HTTPException(422, {"message": "Mapping is incomplete", "problems": problems})
    job.mapping = {h: body.mapping.get(h) for h in job.headers}
    _revalidate(job)
    db.commit()
    return job


@router.get("/workspaces/{workspace_id}/imports/{job_id}/rows", response_model=list[ImportRowOut])
def list_rows(
    job_id: str,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
    ws: Workspace = Depends(get_workspace),
    db: Session = Depends(get_db),
):
    get_owned(db, ImportJob, job_id, ws.id, "Import")
    q = select(ImportRow).where(ImportRow.job_id == job_id)
    if status == "invalid":
        q = q.where(ImportRow.is_valid.is_(False))
    elif status == "valid":
        q = q.where(ImportRow.is_valid.is_(True))
    return db.scalars(q.order_by(ImportRow.row_number).offset(offset).limit(min(limit, 1000))).all()


@router.patch("/workspaces/{workspace_id}/imports/{job_id}/rows/{row_id}", response_model=ImportRowOut)
def fix_row(
    job_id: str, row_id: str, body: RowFix, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)
):
    """Correct individual field values on a failed record, then re-validate the import."""
    job = get_owned(db, ImportJob, job_id, ws.id, "Import")
    if job.status == "uploaded":
        raise HTTPException(409, "Apply a field mapping before fixing records")
    if job.status == "committed":
        raise HTTPException(409, "Import already committed")
    row = db.get(ImportRow, row_id)
    if not row or row.job_id != job.id:
        raise HTTPException(404, "Row not found")
    row.overrides = {**row.overrides, **body.values}
    _revalidate(job)
    db.commit()
    return row


@router.post("/workspaces/{workspace_id}/imports/{job_id}/commit", response_model=ImportJobOut)
def commit_import(job_id: str, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    """Upsert every valid row into the workspace's customer records. Invalid rows are skipped."""
    job = get_owned(db, ImportJob, job_id, ws.id, "Import")
    if job.status != "validated":
        raise HTTPException(409, f"Import must be validated before commit (status: {job.status})")
    valid = [r for r in job.rows if r.is_valid]
    existing = {
        rec.external_id: rec
        for rec in db.scalars(select(CustomerRecord).where(CustomerRecord.workspace_id == ws.id))
    }
    for row in valid:
        ext = str(row.normalized["external_id"])
        if ext in existing:
            existing[ext].data, existing[ext].source = row.normalized, "csv"
        else:
            db.add(CustomerRecord(workspace_id=ws.id, external_id=ext, data=row.normalized, source="csv"))
    job.committed_count = len(valid)
    job.status = "committed"
    webhooks.emit(db, ws.id, "records.imported", {
        "import_id": job.id, "filename": job.filename, "committed": len(valid), "skipped": job.invalid_count,
    })
    db.commit()
    return job
