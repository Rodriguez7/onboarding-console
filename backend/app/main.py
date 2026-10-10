from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import models  # noqa: F401 — register tables
from .config import settings
from .db import Base, SessionLocal, engine
from .routers import handover, imports, ingest, integrations, monitoring, testing, workspaces


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Onboarding & Integration Console API",
    version="1.0.0",
    description="Take a SaaS customer from workspace creation to a monitored, live integration.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for r in (workspaces, imports, integrations, testing, handover, monitoring, ingest):
    app.include_router(r.router)


@app.get("/health", tags=["ops"])
def health():
    with SessionLocal() as db:
        db.execute(text("select 1"))
    return {"status": "ok"}


@app.post("/sink/{outcome}", tags=["ops"], include_in_schema=False)
async def webhook_sink(outcome: str, request: Request):
    """Demo receiver so webhooks can be exercised without an external service.

    ``/sink/ok`` accepts deliveries, ``/sink/fail`` answers 500.
    """
    await request.body()
    if outcome == "fail":
        return JSONResponse({"error": "simulated receiver failure"}, status_code=500)
    return {"received": True, "event": request.headers.get("x-onboarding-event")}
