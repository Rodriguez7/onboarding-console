from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import Workspace


def get_workspace(workspace_id: str, db: Session = Depends(get_db)) -> Workspace:
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws


def get_owned(db: Session, model, obj_id: str, workspace_id: str, label: str):
    """Fetch a child object, 404ing if it belongs to a different workspace."""
    obj = db.get(model, obj_id)
    if not obj or obj.workspace_id != workspace_id:
        raise HTTPException(404, f"{label} not found")
    return obj
