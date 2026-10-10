"""End-to-end API tests covering the full onboarding workflow."""

import json

from app.webhooks import verify

from .conftest import BAD_CSV, GOOD_CSV, upload


def _apply_suggested(client, ws_id, job):
    mapping = {h: s["field"] for h, s in job["suggested_mapping"].items()}
    return client.put(f"/workspaces/{ws_id}/imports/{job['id']}/mapping", json={"mapping": mapping})


def test_create_workspace_seeds_uat_and_steps(client, workspace):
    assert workspace["slug"] == "acme-corp"
    assert workspace["status"] == "onboarding"
    assert [s["key"] for s in workspace["steps"]] == [
        "workspace", "import", "mapping", "integrations", "tests", "uat", "live"]
    assert workspace["blockers"]
    uat = client.get(f"/workspaces/{workspace['id']}/uat").json()
    assert len(uat) == 8 and not any(i["done"] for i in uat)

    again = client.post("/workspaces", json={
        "name": "Acme Corp", "customer_contact_email": "x@acme.example", "specialist_name": "Sam"}).json()
    assert again["slug"] == "acme-corp-2"


def test_csv_upload_suggests_mapping_and_previews(client, workspace):
    job = upload(client, workspace["id"], GOOD_CSV)
    assert job["row_count"] == 2
    assert job["status"] == "uploaded"
    assert job["suggested_mapping"]["Tier"]["field"] == "plan"
    assert job["preview"][0]["Customer ID"] == "C-001"


def test_csv_upload_rejects_bad_files(client, workspace):
    ws = workspace["id"]
    for content, msg in [("", "empty"), ("a,b\n", "no data"), ("a,a\n1,2\n", "Duplicate"), (",b\n1,2\n", "header")]:
        r = client.post(f"/workspaces/{ws}/imports", files={"file": ("x.csv", content.encode(), "text/csv")})
        assert r.status_code == 422 and msg in r.json()["detail"], (content, r.text)
    r = client.post(f"/workspaces/{ws}/imports", files={"file": ("x.csv", b"\xff\xfe\x00", "text/csv")})
    assert r.status_code == 422


def test_semicolon_csv_is_sniffed(client, workspace):
    job = upload(client, workspace["id"], "id;email;plan\nA1;a@x.io;free\n")
    assert job["headers"] == ["id", "email", "plan"]


def test_incomplete_mapping_is_rejected(client, workspace):
    job = upload(client, workspace["id"], GOOD_CSV)
    r = client.put(f"/workspaces/{workspace['id']}/imports/{job['id']}/mapping",
                   json={"mapping": {"Customer ID": "external_id"}})
    assert r.status_code == 422
    assert "Required fields not mapped: email, plan" in r.json()["detail"]["problems"][0]


def test_failed_records_can_be_fixed_and_committed(client, workspace, receiver):
    ws = workspace["id"]
    client.post(f"/workspaces/{ws}/webhooks", json={"url": "https://hooks.acme.example/in"})
    job = upload(client, ws, BAD_CSV)
    validated = _apply_suggested(client, ws, job).json()
    assert validated["status"] == "validated"
    # Row 3 is invalid on several fields; rows 1 and 4 share external_id C-001.
    assert (validated["valid_count"], validated["invalid_count"]) == (1, 3)

    invalid = client.get(f"/workspaces/{ws}/imports/{job['id']}/rows", params={"status": "invalid"}).json()
    by_row = {r["row_number"]: r for r in invalid}
    assert set(by_row) == {1, 3, 4}
    assert {e["field"] for e in by_row[3]["errors"]} == {"email", "plan", "mrr", "signup_date", "country"}
    assert "appears 2 times" in by_row[4]["errors"][0]["message"]

    base = f"/workspaces/{ws}/imports/{job['id']}/rows"
    client.patch(f"{base}/{by_row[3]['id']}", json={"values": {
        "email": "alan@acme.example", "plan": "pro", "mrr": "10", "signup_date": "2024-01-13", "country": "GB"}})
    fixed = client.patch(f"{base}/{by_row[4]['id']}", json={"values": {"external_id": "C-004"}}).json()
    assert fixed["is_valid"] and fixed["normalized"]["external_id"] == "C-004"

    summary = client.get(f"/workspaces/{ws}/imports/{job['id']}").json()
    assert (summary["valid_count"], summary["invalid_count"]) == (4, 0)

    committed = client.post(f"/workspaces/{ws}/imports/{job['id']}/commit").json()
    assert committed["status"] == "committed" and committed["committed_count"] == 4
    assert client.post(f"/workspaces/{ws}/imports/{job['id']}/commit").status_code == 409

    event = json.loads(receiver.requests[-1].content)
    assert event["event"] == "records.imported" and event["data"]["committed"] == 4


def test_credentials_are_shown_once_and_hashed(client, workspace):
    ws = workspace["id"]
    created = client.post(f"/workspaces/{ws}/credentials", json={"name": "Prod", "environment": "production"}).json()
    assert created["api_key"].startswith("oc_live_")
    listed = client.get(f"/workspaces/{ws}/credentials").json()
    assert "api_key" not in listed[0] and listed[0]["key_prefix"] == created["api_key"][:12]

    headers = {"Authorization": f"Bearer {created['api_key']}"}
    assert client.get("/api/v1/records", headers=headers).status_code == 200
    client.delete(f"/workspaces/{ws}/credentials/{created['id']}")
    r = client.get("/api/v1/records", headers=headers)
    assert r.status_code == 401 and "revoked" in r.json()["detail"]
    assert client.get("/api/v1/records").status_code == 401
    assert client.get("/api/v1/records", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_webhooks_are_signed_and_failures_recorded_and_retryable(client, workspace, receiver):
    ws = workspace["id"]
    ok = client.post(f"/workspaces/{ws}/webhooks", json={"url": "https://hooks.acme.example/ok"}).json()
    bad = client.post(f"/workspaces/{ws}/webhooks", json={"url": "https://hooks.acme.example/fail",
                                                          "events": ["integration.test"]}).json()
    assert client.post(f"/workspaces/{ws}/webhooks", json={"url": "https://x.io", "events": ["nope"]}).status_code == 422

    d = client.post(f"/workspaces/{ws}/webhooks/{ok['id']}/test").json()
    assert d["success"] and d["status_code"] == 200
    req = receiver.requests[-1]
    assert verify(ok["secret"], req.headers["x-onboarding-signature"], req.content)
    assert req.headers["x-onboarding-event"] == "integration.test"

    failed = client.post(f"/workspaces/{ws}/webhooks/{bad['id']}/test").json()
    assert not failed["success"] and failed["error"] == "Endpoint responded with HTTP 500"

    errors = client.get(f"/workspaces/{ws}/webhook-deliveries", params={"failed": True}).json()
    assert [e["id"] for e in errors] == [failed["id"]]
    retry = client.post(f"/workspaces/{ws}/webhook-deliveries/{failed['id']}/retry").json()
    assert retry["attempt"] == 2 and not retry["success"]


def test_test_run_reports_each_gap(client, workspace):
    run = client.post(f"/workspaces/{workspace['id']}/test-runs").json()
    assert not run["passed"]
    statuses = {c["key"]: c["status"] for c in run["checks"]}
    assert statuses == {"import": "failed", "credentials": "failed", "webhooks": "failed"}


def test_full_onboarding_to_go_live_and_monitoring(client, workspace, receiver):
    ws = workspace["id"]

    # Import + map + commit
    job = upload(client, ws, GOOD_CSV)
    assert _apply_suggested(client, ws, job).json()["invalid_count"] == 0
    client.post(f"/workspaces/{ws}/imports/{job['id']}/commit")

    # Integration config
    key = client.post(f"/workspaces/{ws}/credentials", json={"name": "Prod", "environment": "production"}).json()
    hook = client.post(f"/workspaces/{ws}/webhooks", json={"url": "https://hooks.acme.example/ok"}).json()

    # Go-live is blocked until tests pass and UAT is complete
    r = client.post(f"/workspaces/{ws}/go-live")
    assert r.status_code == 409
    assert any("UAT" in b for b in r.json()["detail"]["blockers"])

    run = client.post(f"/workspaces/{ws}/test-runs").json()
    assert run["passed"], run
    assert {c["status"] for c in run["checks"]} == {"passed"}

    uat = client.get(f"/workspaces/{ws}/uat").json()
    r = client.patch(f"/workspaces/{ws}/uat/{uat[0]['id']}", json={"done": True})
    assert r.status_code == 422  # sign-off needs a name
    for item in uat:
        r = client.patch(f"/workspaces/{ws}/uat/{item['id']}", json={"done": True, "completed_by": "Pat Customer"})
        assert r.json()["done"] and r.json()["completed_at"]

    detail = client.get(f"/workspaces/{ws}").json()
    assert detail["blockers"] == []
    assert all(s["complete"] for s in detail["steps"] if s["key"] != "live")

    live = client.post(f"/workspaces/{ws}/go-live").json()
    assert live["status"] == "live" and live["went_live_at"]
    assert json.loads(receiver.requests[-1].content)["event"] == "workspace.live"

    # Handover document
    doc = client.get(f"/workspaces/{ws}/handover").json()
    md = doc["markdown"]
    assert doc["filename"] == "acme-corp-handover.md"
    for expected in ["# Customer Handover — Acme Corp", "**LIVE**", "| Customer ID | `external_id` | yes |",
                     key["key_prefix"], hook["url"], "**PASSED**", "## 6. UAT sign-off (8/8)", "Pat Customer"]:
        assert expected in md, expected
    assert key["api_key"] not in md and hook["secret"] not in md
    dl = client.get(f"/workspaces/{ws}/handover.md")
    assert dl.headers["content-disposition"].endswith('acme-corp-handover.md"')

    # Post-launch traffic via the customer API
    headers = {"Authorization": f"Bearer {key['api_key']}"}
    r = client.post("/api/v1/records", headers=headers, json={"records": [
        {"external_id": "C-001", "email": "ada@new.example", "plan": "enterprise"},
        {"external_id": "C-010", "email": "new@acme.example", "plan": "free"},
        {"external_id": "C-011", "email": "broken"},
    ]})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 2 and body["rejected"][0]["index"] == 2
    r = client.post("/api/v1/records", headers=headers, json={"records": [{"email": "x"}]})
    assert r.status_code == 422
    records = client.get("/api/v1/records", headers=headers).json()["records"]
    assert len(records) == 3
    assert next(x for x in records if x["external_id"] == "C-001")["email"] == "ada@new.example"

    m = client.get(f"/workspaces/{ws}/monitoring").json()
    assert m["workspace_status"] == "live"
    assert m["records_total"] == 3
    assert m["api"]["requests"] == 3 and m["api"]["rejected"] == 1 and m["api"]["errors"] == 0
    assert m["webhooks"]["deliveries"] >= 4 and m["webhooks"]["failed"] == 0
    assert m["health"] == "healthy"
    assert len(m["series"]) == 24 and sum(b["requests"] for b in m["series"]) == 3
    assert m["recent_errors"][0]["kind"] == "api"

    assert client.post(f"/workspaces/{ws}/go-live").status_code == 409


def test_monitoring_flags_degraded_webhooks(client, workspace):
    ws = workspace["id"]
    hook = client.post(f"/workspaces/{ws}/webhooks", json={"url": "https://hooks.acme.example/fail"}).json()
    for _ in range(3):
        client.post(f"/workspaces/{ws}/webhooks/{hook['id']}/test")
    m = client.get(f"/workspaces/{ws}/monitoring").json()
    assert m["health"] == "down" and m["webhooks"]["failure_rate"] == 1.0
    assert all(e["kind"] == "webhook" for e in m["recent_errors"])


def test_cross_workspace_access_is_isolated(client, workspace):
    other = client.post("/workspaces", json={
        "name": "Other", "customer_contact_email": "o@other.example", "specialist_name": "Sam"}).json()
    job = upload(client, workspace["id"], GOOD_CSV)
    assert client.get(f"/workspaces/{other['id']}/imports/{job['id']}").status_code == 404
    item = client.get(f"/workspaces/{workspace['id']}/uat").json()[0]
    assert client.patch(f"/workspaces/{other['id']}/uat/{item['id']}", json={"notes": "x"}).status_code == 404


def test_skipped_records_fail_before_commit_and_warn_after(client, workspace):
    ws = workspace["id"]
    job = upload(client, ws, BAD_CSV)
    _apply_suggested(client, ws, job)
    check = lambda: next(c for c in client.post(f"/workspaces/{ws}/test-runs").json()["checks"] if c["key"] == "records")
    assert check()["status"] == "failed"
    client.post(f"/workspaces/{ws}/imports/{job['id']}/commit")
    assert check() == {"key": "records", "name": "Record validation", "status": "warning",
                       "detail": "3 of 4 records were skipped at commit"}
