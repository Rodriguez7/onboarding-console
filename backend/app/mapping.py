"""Suggest how incoming CSV columns map onto the platform schema."""

import difflib
import re

from .platform_schema import FIELDS_BY_NAME, PLATFORM_SCHEMA, REQUIRED_FIELDS


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


_CANDIDATES: dict[str, str] = {}
for _f in PLATFORM_SCHEMA:
    for _alias in (_f.name, _f.label, *_f.aliases):
        _CANDIDATES.setdefault(_key(_alias), _f.name)


def suggest_mapping(headers: list[str]) -> dict[str, dict]:
    """Return ``{header: {"field": name | None, "confidence": 0..1}}``.

    Exact name/alias matches score 1.0; fuzzy matches score their similarity ratio. Each
    platform field is assigned at most once, to the strongest candidate.
    """
    scored: list[tuple[float, str, str]] = []
    for header in headers:
        key = _key(header)
        if key in _CANDIDATES:
            scored.append((1.0, header, _CANDIDATES[key]))
            continue
        close = difflib.get_close_matches(key, _CANDIDATES.keys(), n=1, cutoff=0.75)
        if close:
            ratio = difflib.SequenceMatcher(None, key, close[0]).ratio()
            scored.append((round(ratio, 2), header, _CANDIDATES[close[0]]))

    result: dict[str, dict] = {h: {"field": None, "confidence": 0.0} for h in headers}
    taken: set[str] = set()
    for confidence, header, field_name in sorted(scored, key=lambda s: -s[0]):
        if field_name in taken or result[header]["field"]:
            continue
        result[header] = {"field": field_name, "confidence": confidence}
        taken.add(field_name)
    return result


def mapping_problems(mapping: dict[str, str | None], headers: list[str]) -> list[str]:
    """Explain why a mapping can't be applied; empty list means it is usable."""
    problems: list[str] = []
    unknown_cols = [c for c in mapping if c not in headers]
    if unknown_cols:
        problems.append(f"Unknown source columns: {', '.join(unknown_cols)}")
    targets = [t for t in mapping.values() if t]
    bad = sorted({t for t in targets if t not in FIELDS_BY_NAME})
    if bad:
        problems.append(f"Unknown platform fields: {', '.join(bad)}")
    dupes = sorted({t for t in targets if targets.count(t) > 1})
    if dupes:
        problems.append(f"Fields mapped more than once: {', '.join(dupes)}")
    missing = [f for f in REQUIRED_FIELDS if f not in targets]
    if missing:
        problems.append(f"Required fields not mapped: {', '.join(missing)}")
    return problems
