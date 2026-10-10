"""Derive onboarding progress and go-live blockers from workspace state."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import ApiCredential, TestRun, WebhookEndpoint, Workspace
from .schemas import Step


def latest_import(ws: Workspace):
    return ws.imports[-1] if ws.imports else None


def latest_test_run(db: Session, workspace_id: str) -> TestRun | None:
    return db.scalars(
        select(TestRun).where(TestRun.workspace_id == workspace_id).order_by(TestRun.created_at.desc()).limit(1)
    ).first()


def compute_steps(db: Session, ws: Workspace) -> list[Step]:
    job = latest_import(ws)
    creds = db.scalar(
        select(func.count()).select_from(ApiCredential).where(
            ApiCredential.workspace_id == ws.id, ApiCredential.revoked_at.is_(None)
        )
    )
    hooks = db.scalar(
        select(func.count()).select_from(WebhookEndpoint).where(
            WebhookEndpoint.workspace_id == ws.id, WebhookEndpoint.active.is_(True)
        )
    )
    run = latest_test_run(db, ws.id)
    uat_done = sum(i.done for i in ws.uat_items)
    uat_total = len(ws.uat_items)

    return [
        Step(key="workspace", label="Create workspace", complete=True, detail=f"Owner: {ws.specialist_name}"),
        Step(key="import", label="Import CSV", complete=job is not None,
             detail=f"{job.filename}: {job.row_count} rows" if job else "No file uploaded"),
        Step(key="mapping", label="Map fields", complete=bool(job and job.status in ("validated", "committed")),
             detail=(f"{job.valid_count} valid / {job.invalid_count} invalid" if job and job.status != "uploaded"
                     else "Mapping not applied")),
        Step(key="integrations", label="Credentials & webhooks", complete=bool(creds and hooks),
             detail=f"{creds} active key(s), {hooks} active webhook(s)"),
        Step(key="tests", label="Validation & integration tests", complete=bool(run and run.passed),
             detail=("Last run passed" if run and run.passed else "Last run failed" if run else "Not run yet")),
        Step(key="uat", label="UAT checklist", complete=uat_total > 0 and uat_done == uat_total,
             detail=f"{uat_done}/{uat_total} items complete"),
        Step(key="live", label="Go live", complete=ws.status == "live",
             detail=f"Live since {ws.went_live_at:%Y-%m-%d}" if ws.went_live_at else "Not live"),
    ]


def go_live_blockers(db: Session, ws: Workspace) -> list[str]:
    blockers: list[str] = []
    job = latest_import(ws)
    if not job or job.status != "committed":
        blockers.append("Customer data has not been committed")
    run = latest_test_run(db, ws.id)
    if not run:
        blockers.append("Integration tests have not been run")
    elif not run.passed:
        failed = [c["name"] for c in run.checks if c["status"] == "failed"]
        blockers.append(f"Latest test run failed: {', '.join(failed)}")
    open_items = [i.title for i in ws.uat_items if not i.done]
    if open_items:
        blockers.append(f"{len(open_items)} UAT item(s) still open")
    return blockers
