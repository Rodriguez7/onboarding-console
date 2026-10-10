"""Generate the customer handover document as Markdown."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_workspace
from ..models import ApiCredential, CustomerRecord, WebhookDelivery, WebhookEndpoint, Workspace, utcnow
from ..platform_schema import FIELDS_BY_NAME
from ..readiness import go_live_blockers, latest_import, latest_test_run

router = APIRouter(prefix="/workspaces/{workspace_id}/handover", tags=["handover"])

_ICON = {"passed": "✅", "warning": "⚠️", "failed": "❌"}


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_handover(db: Session, ws: Workspace) -> str:
    now = utcnow()
    job = latest_import(ws)
    run = latest_test_run(db, ws.id)
    creds = db.scalars(select(ApiCredential).where(ApiCredential.workspace_id == ws.id)).all()
    hooks = db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == ws.id)).all()
    records = db.scalar(select(func.count()).select_from(CustomerRecord).where(CustomerRecord.workspace_id == ws.id))
    failed_deliveries = db.scalar(
        select(func.count()).select_from(WebhookDelivery).where(
            WebhookDelivery.workspace_id == ws.id, WebhookDelivery.success.is_(False)
        )
    )
    blockers = go_live_blockers(db, ws) if ws.status != "live" else []

    out: list[str] = [
        f"# Customer Handover — {ws.name}",
        "",
        f"_Generated {now:%Y-%m-%d %H:%M} UTC_",
        "",
        "## 1. Summary",
        "",
        "| | |",
        "|---|---|",
        f"| Workspace | `{ws.slug}` |",
        f"| Status | **{ws.status.upper()}** |",
        f"| Implementation specialist | {_cell(ws.specialist_name)} |",
        f"| Customer contact | {ws.customer_contact_email} |",
        f"| Target go-live | {ws.target_go_live or '—'} |",
        f"| Went live | {f'{ws.went_live_at:%Y-%m-%d %H:%M} UTC' if ws.went_live_at else '—'} |",
        f"| Customer records loaded | {records} |",
        "",
    ]
    if blockers:
        out += ["> **Not yet ready for go-live:**", *[f"> - {b}" for b in blockers], ""]

    out += ["## 2. Data migration", ""]
    if job:
        out += [
            f"Source file **{_cell(job.filename)}** — {job.row_count} rows, {job.valid_count} valid, "
            f"{job.invalid_count} rejected, {job.committed_count} committed (status: {job.status}).",
            "",
            "### Field mapping",
            "",
            "| Source column | Platform field | Required |",
            "|---|---|---|",
        ]
        for src, target in job.mapping.items():
            f = FIELDS_BY_NAME.get(target) if target else None
            out.append(f"| {_cell(src)} | {f'`{target}`' if f else '_not imported_'} | {'yes' if f and f.required else ''} |")
        out.append("")
    else:
        out += ["No data import has been performed.", ""]

    out += ["## 3. API access", "", "Base URL: `/api/v1` — authenticate with `Authorization: Bearer <api key>`.", ""]
    if creds:
        out += ["| Name | Environment | Key prefix | Status |", "|---|---|---|---|"]
        for c in creds:
            status = f"revoked {c.revoked_at:%Y-%m-%d}" if c.revoked_at else "active"
            out.append(f"| {_cell(c.name)} | {c.environment} | `{c.key_prefix}…` | {status} |")
        out += ["", "Full keys were shown once at creation and are not recoverable — rotate if lost.", ""]
    else:
        out += ["No API credentials issued.", ""]

    out += ["## 4. Webhooks", ""]
    if hooks:
        out += ["| URL | Events | Active |", "|---|---|---|"]
        for h in hooks:
            out.append(f"| {_cell(h.url)} | {', '.join(h.events)} | {'yes' if h.active else 'no'} |")
        out += [
            "",
            "Each request carries `X-Onboarding-Signature: t=<ts>,v1=<hmac>` where the HMAC is SHA-256 over "
            "`\"<ts>.\" + raw body` using the endpoint secret. Reject signatures older than 5 minutes.",
            f"Failed deliveries to date: **{failed_deliveries}**.",
            "",
        ]
    else:
        out += ["No webhook endpoints configured.", ""]

    out += ["## 5. Test results", ""]
    if run:
        out += [
            f"Latest run {run.created_at:%Y-%m-%d %H:%M} UTC — **{'PASSED' if run.passed else 'FAILED'}**",
            "",
            "| Check | Result | Detail |",
            "|---|---|---|",
            *[f"| {_cell(c['name'])} | {_ICON[c['status']]} {c['status']} | {_cell(c['detail'])} |" for c in run.checks],
            "",
        ]
    else:
        out += ["Integration tests have not been run.", ""]

    done = sum(i.done for i in ws.uat_items)
    out += [f"## 6. UAT sign-off ({done}/{len(ws.uat_items)})", "", "| | Category | Item | Signed off by | Notes |",
            "|---|---|---|---|---|"]
    for i in ws.uat_items:
        who = f"{_cell(i.completed_by)} ({i.completed_at:%Y-%m-%d})" if i.done and i.completed_at else ""
        out.append(f"| {'☑' if i.done else '☐'} | {_cell(i.category)} | {_cell(i.title)} | {who} | {_cell(i.notes)} |")

    out += [
        "",
        "## 7. Support runbook",
        "",
        "- **Monitoring:** the console's Monitor tab shows API volume, error rate, p95 latency and webhook "
        "success for the last 24 hours. Investigate when status is _degraded_ (error rate ≥ 5%).",
        "- **Failed webhooks:** open Issues → Webhook errors, fix the receiving endpoint, then retry the delivery.",
        "- **Rejected records:** the ingest API returns per-record validation errors; the same rules apply as "
        "for CSV import.",
        "- **Key rotation:** issue a new key, deploy it on the customer side, then revoke the old key.",
        f"- **Escalation:** {_cell(ws.specialist_name)} (implementation) → customer contact {ws.customer_contact_email}.",
        "",
    ]
    return "\n".join(out)


@router.get("")
def get_handover(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return {"filename": f"{ws.slug}-handover.md", "markdown": build_handover(db, ws)}


@router.get(".md", response_class=PlainTextResponse)
def download_handover(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return PlainTextResponse(
        build_handover(db, ws),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ws.slug}-handover.md"'},
    )
