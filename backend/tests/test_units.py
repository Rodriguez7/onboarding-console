import time

from app.mapping import mapping_problems, suggest_mapping
from app.platform_schema import validate_record
from app.webhooks import sign, verify


def test_suggest_mapping_matches_aliases_and_fuzzy_headers():
    s = suggest_mapping(["Customer ID", "E-mail", "Surname", "Subscripton Plan", "favourite colour"])
    assert s["Customer ID"] == {"field": "external_id", "confidence": 1.0}
    assert s["E-mail"]["field"] == "email"
    assert s["Surname"]["field"] == "last_name"
    assert s["Subscripton Plan"]["field"] == "plan"  # typo still matched
    assert 0 < s["Subscripton Plan"]["confidence"] < 1
    assert s["favourite colour"]["field"] is None


def test_suggest_mapping_assigns_each_field_once():
    s = suggest_mapping(["email", "Email Address"])
    fields = [v["field"] for v in s.values()]
    assert fields.count("email") == 1


def test_mapping_problems():
    headers = ["a", "b", "c"]
    assert mapping_problems({"a": "external_id", "b": "email", "c": "plan"}, headers) == []
    problems = mapping_problems({"a": "email", "b": "email", "z": "nope"}, headers)
    text = " ".join(problems)
    assert "Unknown source columns: z" in text
    assert "Unknown platform fields: nope" in text
    assert "mapped more than once: email" in text
    assert "Required fields not mapped: external_id, plan" in text


def test_validate_record_normalizes_values():
    normalized, errors = validate_record({
        "external_id": " X1 ", "email": "Ada@Example.COM", "plan": "PRO", "mrr": "$1,250.50",
        "signup_date": "03/02/2023", "country": "gb", "phone": "+1 (555) 010-9999",
    })
    assert errors == []
    assert normalized == {
        "external_id": "X1", "email": "ada@example.com", "plan": "pro", "mrr": 1250.5,
        "signup_date": "2023-03-02", "country": "GB", "phone": "+15550109999",
    }


def test_validate_record_reports_every_problem():
    _, errors = validate_record({"email": "nope", "plan": "gold", "mrr": "-1", "signup_date": "2999-01-01",
                                 "country": "USA", "phone": "12"})
    fields = {e["field"] for e in errors}
    assert fields == {"external_id", "email", "plan", "mrr", "signup_date", "country", "phone"}


def test_webhook_signature_roundtrip():
    body = b'{"hello":"world"}'
    header = sign("whsec_x", int(time.time()), body)
    assert verify("whsec_x", header, body)
    assert not verify("whsec_other", header, body)
    assert not verify("whsec_x", header, body + b" ")
    assert not verify("whsec_x", sign("whsec_x", int(time.time()) - 3600, body), body)
    assert not verify("whsec_x", "garbage", body)
