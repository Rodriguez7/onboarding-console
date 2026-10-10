import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import webhooks
from ..db import get_db
from ..deps import get_owned, get_workspace
from ..models import ApiCredential, WebhookDelivery, WebhookEndpoint, Workspace, utcnow
from ..schemas import CredentialCreate, CredentialCreated, CredentialOut, DeliveryOut, WebhookCreate, WebhookOut, WebhookUpdate

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["integrations"])


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# --- API credentials ------------------------------------------------------------------------

@router.post("/credentials", response_model=CredentialCreated, status_code=201)
def create_credential(body: CredentialCreate, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    env = "live" if body.environment == "production" else "test"
    key = f"oc_{env}_{secrets.token_urlsafe(32)}"
    cred = ApiCredential(
        workspace_id=ws.id, name=body.name, environment=body.environment, key_prefix=key[:12], key_hash=hash_key(key)
    )
    db.add(cred)
    db.commit()
    return CredentialCreated(**CredentialOut.model_validate(cred).model_dump(), api_key=key)


@router.get("/credentials", response_model=list[CredentialOut])
def list_credentials(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return db.scalars(
        select(ApiCredential).where(ApiCredential.workspace_id == ws.id).order_by(ApiCredential.created_at)
    ).all()


@router.delete("/credentials/{credential_id}", response_model=CredentialOut)
def revoke_credential(credential_id: str, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    cred = get_owned(db, ApiCredential, credential_id, ws.id, "Credential")
    if cred.revoked_at is None:
        cred.revoked_at = utcnow()
        db.commit()
    return cred


# --- Webhook endpoints ----------------------------------------------------------------------

@router.post("/webhooks", response_model=WebhookOut, status_code=201)
def create_webhook(body: WebhookCreate, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    ep = WebhookEndpoint(
        workspace_id=ws.id, url=str(body.url), description=body.description, events=body.events,
        secret=f"whsec_{secrets.token_hex(24)}",
    )
    db.add(ep)
    db.commit()
    return ep


@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return db.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == ws.id).order_by(WebhookEndpoint.created_at)
    ).all()


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
def update_webhook(
    webhook_id: str, body: WebhookUpdate, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)
):
    ep = get_owned(db, WebhookEndpoint, webhook_id, ws.id, "Webhook")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ep, k, v)
    db.commit()
    return ep


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: str, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    db.delete(get_owned(db, WebhookEndpoint, webhook_id, ws.id, "Webhook"))
    db.commit()


@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryOut)
def send_test_event(webhook_id: str, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    ep = get_owned(db, WebhookEndpoint, webhook_id, ws.id, "Webhook")
    delivery = webhooks.deliver(db, ep, "integration.test", {"workspace_id": ws.id, "message": "Test event"})
    db.commit()
    return delivery


@router.get("/webhook-deliveries", response_model=list[DeliveryOut])
def list_deliveries(
    failed: bool = False, limit: int = 100, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)
):
    q = select(WebhookDelivery).where(WebhookDelivery.workspace_id == ws.id)
    if failed:
        q = q.where(WebhookDelivery.success.is_(False))
    return db.scalars(q.order_by(WebhookDelivery.created_at.desc()).limit(min(limit, 500))).all()


@router.post("/webhook-deliveries/{delivery_id}/retry", response_model=DeliveryOut)
def retry_delivery(delivery_id: str, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    original = get_owned(db, WebhookDelivery, delivery_id, ws.id, "Delivery")
    ep = db.get(WebhookEndpoint, original.endpoint_id)
    if not ep:
        raise HTTPException(404, "Webhook endpoint no longer exists")
    delivery = webhooks.deliver(db, ep, original.event, original.payload, attempt=original.attempt + 1)
    db.commit()
    return delivery
