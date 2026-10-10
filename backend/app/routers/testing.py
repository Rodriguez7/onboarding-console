"""Validation and integration test runs — the pre-go-live gate."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import webhooks
from ..db import get_db
from ..deps import get_workspace
from ..models import ApiCredential, TestRun, WebhookEndpoint, Workspace
from ..platform_schema import REQUIRED_FIELDS
from ..readiness import latest_import
from ..schemas import Check, TestRunOut

router = APIRouter(prefix="/workspaces/{workspace_id}/test-runs", tags=["testing"])


def _run_checks(db: Session, ws: Workspace) -> list[Check]:
    checks: list[Check] = []

    def add(key: str, name: str, status: str, detail: str) -> None:
        checks.append(Check(key=key, name=name, status=status, detail=detail))

    # Data checks
    job = latest_import(ws)
    if not job:
        add("import", "CSV import", "failed", "No customer data has been uploaded")
    else:
        add("import", "CSV import", "passed", f"{job.filename} ({job.row_count} rows)")
        mapped = set(filter(None, job.mapping.values()))
        missing = [f for f in REQUIRED_FIELDS if f not in mapped]
        if job.status == "uploaded" or missing:
            add("mapping", "Required fields mapped", "failed",
                f"Missing: {', '.join(missing)}" if missing else "Mapping has not been applied")
        else:
            add("mapping", "Required fields mapped", "passed", f"{len(mapped)} fields mapped")
        if job.status != "uploaded":
            if job.invalid_count and job.status == "committed":
                # The specialist chose to load the valid rows and skip the rest — surface, don't block.
                add("records", "Record validation", "warning",
                    f"{job.invalid_count} of {job.row_count} records were skipped at commit")
            elif job.invalid_count:
                add("records", "Record validation", "failed",
                    f"{job.invalid_count} of {job.row_count} records fail validation")
            else:
                add("records", "Record validation", "passed", f"All {job.row_count} records valid")
        if job.status == "committed":
            add("commit", "Data committed", "passed", f"{job.committed_count} records loaded")
        else:
            add("commit", "Data committed", "warning", "Validated data has not been committed yet")

    # Credential checks
    creds = db.scalars(
        select(ApiCredential).where(ApiCredential.workspace_id == ws.id, ApiCredential.revoked_at.is_(None))
    ).all()
    if not creds:
        add("credentials", "API credentials", "failed", "No active API key")
    else:
        add("credentials", "API credentials", "passed", f"{len(creds)} active key(s)")
        if any(c.environment == "production" for c in creds):
            add("production_key", "Production key issued", "passed", "Production key is active")
        else:
            add("production_key", "Production key issued", "warning", "Only sandbox keys exist")

    # Webhook connectivity: send a signed test event to every active endpoint.
    endpoints = db.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == ws.id, WebhookEndpoint.active.is_(True))
    ).all()
    if not endpoints:
        add("webhooks", "Webhook endpoints", "failed", "No active webhook endpoint")
    for ep in endpoints:
        d = webhooks.deliver(db, ep, "integration.test", {"workspace_id": ws.id, "message": "Integration test run"})
        if d.success:
            add(f"webhook:{ep.id}", f"Webhook delivery → {ep.url}", "passed",
                f"HTTP {d.status_code} in {d.duration_ms:.0f} ms")
        else:
            add(f"webhook:{ep.id}", f"Webhook delivery → {ep.url}", "failed", d.error or "Delivery failed")
    return checks


@router.post("", response_model=TestRunOut, status_code=201)
def create_test_run(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    checks = _run_checks(db, ws)
    run = TestRun(
        workspace_id=ws.id,
        passed=all(c.status != "failed" for c in checks),
        checks=[c.model_dump() for c in checks],
    )
    db.add(run)
    db.commit()
    return run


@router.get("", response_model=list[TestRunOut])
def list_test_runs(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return db.scalars(
        select(TestRun).where(TestRun.workspace_id == ws.id).order_by(TestRun.created_at.desc()).limit(20)
    ).all()
