import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import webhooks
from ..db import get_db
from ..deps import get_owned, get_workspace
from ..models import UATItem, Workspace, utcnow
from ..readiness import compute_steps, go_live_blockers
from ..schemas import UATItemCreate, UATItemOut, UATItemUpdate, WorkspaceCreate, WorkspaceDetail, WorkspaceOut

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

DEFAULT_UAT = (
    ("Data", "Customer has reviewed a sample of imported records and confirmed accuracy"),
    ("Data", "Record counts match the customer's source system"),
    ("Integration", "Customer's system authenticates against the API with a production key"),
    ("Integration", "Customer has received and verified the signature of a live webhook"),
    ("Integration", "Error handling agreed: retry policy and alerting contact confirmed"),
    ("Security", "API keys stored in the customer's secret manager, not in code"),
    ("Training", "Customer admins trained on the console and support process"),
    ("Sign-off", "Customer stakeholder has signed off on go-live"),
)


def _slugify(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    slug, n = base, 2
    while db.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def _detail(db: Session, ws: Workspace) -> WorkspaceDetail:
    return WorkspaceDetail(
        **WorkspaceOut.model_validate(ws).model_dump(),
        steps=compute_steps(db, ws),
        blockers=go_live_blockers(db, ws) if ws.status != "live" else [],
    )


@router.post("", response_model=WorkspaceDetail, status_code=201)
def create_workspace(body: WorkspaceCreate, db: Session = Depends(get_db)):
    ws = Workspace(**body.model_dump(), slug=_slugify(db, body.name))
    ws.uat_items = [UATItem(position=i, category=c, title=t) for i, (c, t) in enumerate(DEFAULT_UAT)]
    db.add(ws)
    db.commit()
    return _detail(db, ws)


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db)):
    return db.scalars(select(Workspace).order_by(Workspace.created_at.desc())).all()


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace_detail(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    return _detail(db, ws)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    db.delete(ws)
    db.commit()


@router.post("/{workspace_id}/go-live", response_model=WorkspaceDetail)
def go_live(ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    if ws.status == "live":
        raise HTTPException(409, "Workspace is already live")
    blockers = go_live_blockers(db, ws)
    if blockers:
        raise HTTPException(409, {"message": "Workspace is not ready for go-live", "blockers": blockers})
    ws.status = "live"
    ws.went_live_at = utcnow()
    webhooks.emit(db, ws.id, "workspace.live", {"workspace_id": ws.id, "went_live_at": ws.went_live_at})
    db.commit()
    return _detail(db, ws)


# --- UAT checklist ---------------------------------------------------------------------------

@router.get("/{workspace_id}/uat", response_model=list[UATItemOut])
def list_uat(ws: Workspace = Depends(get_workspace)):
    return ws.uat_items


@router.post("/{workspace_id}/uat", response_model=UATItemOut, status_code=201)
def add_uat_item(body: UATItemCreate, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)):
    item = UATItem(position=len(ws.uat_items), **body.model_dump())
    ws.uat_items.append(item)
    db.commit()
    return item


@router.patch("/{workspace_id}/uat/{item_id}", response_model=UATItemOut)
def update_uat_item(
    item_id: str, body: UATItemUpdate, ws: Workspace = Depends(get_workspace), db: Session = Depends(get_db)
):
    item = get_owned(db, UATItem, item_id, ws.id, "UAT item")
    if body.notes is not None:
        item.notes = body.notes
    if body.done is not None and body.done != item.done:
        if body.done and not (body.completed_by or "").strip():
            raise HTTPException(422, "completed_by is required when marking an item done")
        item.done = body.done
        item.completed_by = body.completed_by.strip() if body.done else None
        item.completed_at = utcnow() if body.done else None
    db.commit()
    return item
