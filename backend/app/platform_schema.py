"""The platform's customer record schema, plus validation/normalisation of incoming values.

Everything that enters the platform — CSV imports and the REST ingest API — goes through
`validate_record`, so both paths enforce identical rules.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

FieldType = Literal["string", "email", "phone", "enum", "number", "date", "country"]


@dataclass(frozen=True)
class PlatformField:
    name: str
    label: str
    type: FieldType
    required: bool = False
    description: str = ""
    options: tuple[str, ...] = ()
    aliases: tuple[str, ...] = field(default=())


PLATFORM_SCHEMA: tuple[PlatformField, ...] = (
    PlatformField("external_id", "External ID", "string", True, "Customer's own unique identifier",
                  aliases=("id", "customer_id", "account_id", "client_id", "ref", "reference")),
    PlatformField("email", "Email", "email", True, "Primary contact email",
                  aliases=("email_address", "contact_email", "e_mail", "mail")),
    PlatformField("first_name", "First name", "string", False,
                  aliases=("firstname", "given_name", "fname", "first")),
    PlatformField("last_name", "Last name", "string", False,
                  aliases=("lastname", "surname", "family_name", "lname", "last")),
    PlatformField("company", "Company", "string", False,
                  aliases=("company_name", "organization", "organisation", "account_name", "business")),
    PlatformField("phone", "Phone", "phone", False,
                  aliases=("phone_number", "telephone", "tel", "mobile", "cell")),
    PlatformField("plan", "Plan", "enum", True, "Subscription tier",
                  options=("free", "starter", "pro", "enterprise"),
                  aliases=("tier", "subscription", "subscription_plan", "package")),
    PlatformField("mrr", "MRR", "number", False, "Monthly recurring revenue",
                  aliases=("monthly_revenue", "revenue", "mrr_usd", "monthly_recurring_revenue")),
    PlatformField("signup_date", "Signup date", "date", False, "ISO date (YYYY-MM-DD)",
                  aliases=("created", "created_at", "start_date", "joined", "signup", "date_joined")),
    PlatformField("country", "Country", "country", False, "ISO 3166-1 alpha-2 code",
                  aliases=("country_code", "nation", "region")),
)

FIELDS_BY_NAME = {f.name: f for f in PLATFORM_SCHEMA}
REQUIRED_FIELDS = tuple(f.name for f in PLATFORM_SCHEMA if f.required)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_STRIP_RE = re.compile(r"[\s().\-]")
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d")


def _normalize(f: PlatformField, value: str) -> tuple[object, str | None]:
    """Return (normalized value, error message or None) for a non-empty value."""
    if f.type == "string":
        return value, None
    if f.type == "email":
        v = value.lower()
        return (v, None) if _EMAIL_RE.match(v) else (value, "is not a valid email address")
    if f.type == "phone":
        digits = _PHONE_STRIP_RE.sub("", value)
        if re.fullmatch(r"\+?\d{7,15}", digits):
            return digits, None
        return value, "must contain 7–15 digits"
    if f.type == "enum":
        v = value.lower()
        if v in f.options:
            return v, None
        return value, f"must be one of: {', '.join(f.options)}"
    if f.type == "number":
        try:
            n = float(value.replace(",", "").lstrip("$"))
        except ValueError:
            return value, "must be a number"
        if n < 0:
            return value, "must not be negative"
        return n, None
    if f.type == "date":
        for fmt in _DATE_FORMATS:
            try:
                d = datetime.strptime(value, fmt).date()
            except ValueError:
                continue
            if d > date.today():
                return value, "must not be in the future"
            return d.isoformat(), None
        return value, "must be a date (YYYY-MM-DD)"
    if f.type == "country":
        v = value.upper()
        return (v, None) if re.fullmatch(r"[A-Z]{2}", v) else (value, "must be a 2-letter ISO country code")
    raise AssertionError(f"unhandled field type {f.type}")


def validate_record(values: dict[str, object]) -> tuple[dict[str, object], list[dict[str, str]]]:
    """Validate a record keyed by platform field name.

    Returns the normalized record and a list of ``{"field", "message"}`` errors. Unknown keys
    are ignored; empty strings count as missing.
    """
    normalized: dict[str, object] = {}
    errors: list[dict[str, str]] = []
    for f in PLATFORM_SCHEMA:
        raw = values.get(f.name)
        text = "" if raw is None else str(raw).strip()
        if not text:
            if f.required:
                errors.append({"field": f.name, "message": f"{f.label} is required"})
            continue
        value, error = _normalize(f, text)
        normalized[f.name] = value
        if error:
            errors.append({"field": f.name, "message": f"{f.label} {error}"})
    return normalized, errors


def schema_as_dicts() -> list[dict]:
    return [
        {
            "name": f.name,
            "label": f.label,
            "type": f.type,
            "required": f.required,
            "description": f.description,
            "options": list(f.options),
        }
        for f in PLATFORM_SCHEMA
    ]
