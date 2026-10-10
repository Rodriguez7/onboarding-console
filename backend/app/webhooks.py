"""Signed outbound webhook delivery.

Each delivery is a JSON POST with headers:

* ``X-Onboarding-Event``: the event name
* ``X-Onboarding-Delivery``: unique delivery id
* ``X-Onboarding-Signature``: ``t=<unix ts>,v1=<hex HMAC-SHA256 of "<ts>.<body>">``

Deliveries are sent synchronously and every attempt is recorded, so failures show up in the
console's error view and can be retried.
"""

import hashlib
import hmac
import json
import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import WebhookDelivery, WebhookEndpoint, utcnow

EVENTS = ("records.imported", "record.upserted", "integration.test", "workspace.live")

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify(secret: str, header: str, body: bytes, tolerance_seconds: int = 300) -> bool:
    """Reference implementation customers can copy to verify our signatures."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > tolerance_seconds:
        return False
    return hmac.compare_digest(sign(secret, ts, body), header)


def deliver(
    db: Session, endpoint: WebhookEndpoint, event: str, data: dict, attempt: int = 1
) -> WebhookDelivery:
    delivery_id = uuid.uuid4().hex
    data = json.loads(json.dumps(data, default=str))  # JSON-safe for both the body and the stored payload
    envelope = {"id": delivery_id, "event": event, "created_at": utcnow().isoformat(), "data": data}
    body = json.dumps(envelope).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "OnboardingConsole-Webhooks/1.0",
        "X-Onboarding-Event": event,
        "X-Onboarding-Delivery": delivery_id,
        "X-Onboarding-Signature": sign(endpoint.secret, int(time.time()), body),
    }
    delivery = WebhookDelivery(
        id=delivery_id,
        workspace_id=endpoint.workspace_id,
        endpoint_id=endpoint.id,
        event=event,
        payload=data,
        attempt=attempt,
        success=False,
    )
    started = time.perf_counter()
    try:
        with httpx.Client(transport=transport, timeout=settings.webhook_timeout_seconds) as client:
            resp = client.post(endpoint.url, content=body, headers=headers)
        delivery.status_code = resp.status_code
        delivery.response_excerpt = resp.text[:500]
        delivery.success = 200 <= resp.status_code < 300
        if not delivery.success:
            delivery.error = f"Endpoint responded with HTTP {resp.status_code}"
    except httpx.TimeoutException:
        delivery.error = f"Timed out after {settings.webhook_timeout_seconds:g}s"
    except httpx.HTTPError as exc:
        delivery.error = f"{type(exc).__name__}: {exc}"
    delivery.duration_ms = round((time.perf_counter() - started) * 1000, 1)
    db.add(delivery)
    db.flush()
    return delivery


def emit(db: Session, workspace_id: str, event: str, data: dict) -> list[WebhookDelivery]:
    endpoints = db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.workspace_id == workspace_id, WebhookEndpoint.active.is_(True)
        )
    ).all()
    return [deliver(db, ep, event, data) for ep in endpoints if event in ep.events]
