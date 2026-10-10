"""Post-launch integration health."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_workspace
from ..models import ApiRequestLog, CustomerRecord, WebhookDelivery, Workspace, utcnow

router = APIRouter(prefix="/workspaces/{workspace_id}/monitoring", tags=["monitoring"])

DEGRADED_ERROR_RATE = 0.05
DOWN_ERROR_RATE = 0.5


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))], 1)


def _aware(dt):
    # SQLite drops tzinfo; Postgres keeps it. Compare everything as naive UTC.
    return dt.replace(tzinfo=None)


@router.get("")
def get_monitoring(
    hours: int = Query(24, ge=1, le=168), ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)
):
    now = utcnow()
    since = now - timedelta(hours=hours)
    logs = db.scalars(
        select(ApiRequestLog).where(ApiRequestLog.workspace_id == ws.id, ApiRequestLog.created_at >= since)
    ).all()
    deliveries = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.workspace_id == ws.id, WebhookDelivery.created_at >= since)
    ).all()
    records = db.scalar(select(func.count()).select_from(CustomerRecord).where(CustomerRecord.workspace_id == ws.id))

    # Auth/rate-limit/server failures are integration errors; other 4xx are rejected payloads.
    api_errors = [l for l in logs if l.status_code >= 500 or l.status_code in (401, 403, 429)]
    rejected = [l for l in logs if 400 <= l.status_code < 500 and l.status_code not in (401, 403, 429)]
    failed_deliveries = [d for d in deliveries if not d.success]
    api_error_rate = len(api_errors) / len(logs) if logs else 0.0
    webhook_failure_rate = len(failed_deliveries) / len(deliveries) if deliveries else 0.0
    worst = max(api_error_rate, webhook_failure_rate)
    health = "no_traffic" if not logs and not deliveries else (
        "down" if worst >= DOWN_ERROR_RATE else "degraded" if worst >= DEGRADED_ERROR_RATE else "healthy"
    )

    start = _aware(now).replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)
    buckets = {start + timedelta(hours=i): {"requests": 0, "errors": 0, "deliveries": 0, "failed_deliveries": 0}
               for i in range(hours)}

    def bucket(dt):
        return buckets.get(_aware(dt).replace(minute=0, second=0, microsecond=0))

    for l in logs:
        if b := bucket(l.created_at):
            b["requests"] += 1
            b["errors"] += l.status_code >= 400
    for d in deliveries:
        if b := bucket(d.created_at):
            b["deliveries"] += 1
            b["failed_deliveries"] += not d.success

    timestamps = [l.created_at for l in logs] + [d.created_at for d in deliveries]
    recent_errors = sorted(
        [{"kind": "api", "at": l.created_at, "status_code": l.status_code, "message": l.error or f"{l.method} {l.path}"}
         for l in api_errors + rejected]
        + [{"kind": "webhook", "at": d.created_at, "status_code": d.status_code, "message": d.error or d.event}
           for d in failed_deliveries],
        key=lambda e: _aware(e["at"]),
        reverse=True,
    )[:20]

    return {
        "window_hours": hours,
        "health": health,
        "workspace_status": ws.status,
        "went_live_at": ws.went_live_at,
        "records_total": records,
        "api": {
            "requests": len(logs),
            "errors": len(api_errors),
            "rejected": len(rejected),
            "error_rate": round(api_error_rate, 4),
            "p95_latency_ms": _p95([l.latency_ms for l in logs]),
        },
        "webhooks": {
            "deliveries": len(deliveries),
            "failed": len(failed_deliveries),
            "failure_rate": round(webhook_failure_rate, 4),
            "p95_latency_ms": _p95([d.duration_ms for d in deliveries]),
        },
        "last_activity_at": max(timestamps, key=_aware) if timestamps else None,
        "series": [{"hour": h.isoformat() + "Z", **v} for h, v in buckets.items()],
        "recent_errors": recent_errors,
    }
