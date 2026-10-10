import os
import tempfile

# Default to an isolated SQLite file; CI sets DATABASE_URL to a real Postgres.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import webhooks  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


class WebhookReceiver:
    """Captures outbound webhook calls; URLs containing 'fail' get HTTP 500."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if "fail" in str(request.url):
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"ok": True})


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def receiver(monkeypatch) -> WebhookReceiver:
    r = WebhookReceiver()
    monkeypatch.setattr(webhooks, "transport", httpx.MockTransport(r))
    return r


@pytest.fixture
def client(receiver) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def workspace(client) -> dict:
    resp = client.post("/workspaces", json={
        "name": "Acme Corp",
        "customer_contact_email": "ops@acme.example",
        "specialist_name": "Jordan Implementer",
        "target_go_live": "2026-12-01",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


GOOD_CSV = (
    "Customer ID,E-mail,First Name,Surname,Company Name,Tier,Monthly Revenue,Signup,Country Code\n"
    "C-001,ada@acme.example,Ada,Lovelace,Acme,Pro,1200,2024-01-15,gb\n"
    "C-002,grace@acme.example,Grace,Hopper,Acme,enterprise,\"5,000\",03/02/2023,US\n"
)

BAD_CSV = GOOD_CSV + (
    "C-003,not-an-email,Alan,Turing,Acme,platinum,-5,2024-13-01,GBR\n"
    "C-001,dup@acme.example,Dup,Licate,Acme,free,0,2024-01-01,US\n"
)


def upload(client, ws_id: str, content: str, name: str = "customers.csv") -> dict:
    resp = client.post(f"/workspaces/{ws_id}/imports", files={"file": (name, content.encode(), "text/csv")})
    assert resp.status_code == 201, resp.text
    return resp.json()
