"""Contextual Missing-Data engine — the zero-raw-nulls guardrail.

Every metric the API returns is either a real number with status REPORTED,
or an explicit envelope explaining WHY it is unavailable. The frontend never
has to guess what "-" means."""
from __future__ import annotations

import math
from typing import Any

REPORTED = "REPORTED"
LISTED_RECENT = "LISTED-RECENTLY-UNAVAILABLE"
NOT_APPLICABLE = "NOT-APPLICABLE-FOR-SECTOR"
NOT_DISCLOSED = "NOT-DISCLOSED-BY-COMPANY"
SOURCE_ISSUE = "SOURCE-UNAVAILABLE-RETRY-LATER"


def _env(value: Any, status: str, note: str) -> dict:
    # JSON has no NaN/Infinity. A single bad source cell used to serialize as
    # `nan` and take the whole endpoint down with a 500, so never let a
    # non-finite number escape inside a status envelope.
    if isinstance(value, float) and not math.isfinite(value):
        return {
            "value": None,
            "status": SOURCE_ISSUE,
            "note": ("The free public source returned an invalid number for this "
                     "metric. Retry shortly — it is left blank rather than shown "
                     "as a made-up value."),
        }
    return {"value": value, "status": status, "note": note}


def reported(value: Any, note: str = "Reported as of the latest available data.") -> dict:
    return _env(value, REPORTED, note)


def unavailable(status: str, note: str) -> dict:
    return _env(None, status, note)


def listed_recently(listing_date: str | None, metric: str) -> dict:
    extra = f' (listed {listing_date})' if listing_date else ""
    return unavailable(
        LISTED_RECENT,
        f"{metric} is not available yet: the company listed recently{extra}, "
        "so long-history metrics have not accumulated enough periods. "
        "Value appears as soon as the next reported period closes.")


def not_applicable(metric: str, sector: str) -> dict:
    return unavailable(
        NOT_APPLICABLE,
        f"{metric} is not applicable for the {sector} sector — companies there "
        "do not carry the underlying line item, so any number would be misleading.")


def not_disclosed(metric: str) -> dict:
    return unavailable(
        NOT_DISCLOSED,
        f"{metric} is not disclosed by the company in its latest public filings. "
        "It is intentionally left blank rather than estimated.")


def source_issue(what: str) -> dict:
    return unavailable(
        SOURCE_ISSUE,
        f"Live {what} could not be fetched from the free public source right now "
        "(the exchange throttles aggressive clients). Use the Refresh action — "
        "values will populate on a successful retry.")


def unwrap(env: dict | None, default=None):
    if not env:
        return default
    return env.get("value")
