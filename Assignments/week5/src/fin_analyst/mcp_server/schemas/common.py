import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import Field

TickerSymbol = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")]
Percentage = Annotated[float, Field(ge=-100.0, le=100000.0)]
Magnitude = Annotated[int, Field(ge=1, le=5)]
Confidence = Literal["high", "medium", "low"]
Direction = Literal["Up", "Down", "Flat"]
Sentiment = Literal["positive", "negative", "neutral"]
StageStatus = Literal["pending", "running", "validated", "failed"]

FinanceWindow = Literal["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"]
FINANCE_WINDOWS: tuple[FinanceWindow, ...] = ("1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX")

_NUMERIC_RE = re.compile(r"-?[\d,]+\.?\d*")


def parse_numeric(raw: str | float | int | None) -> float | None:
    """Best-effort numeric extraction from SerpApi's formatted strings.

    Handles "$313.39", "4.60T", "37.91", "16.6%", "—" (em dash = missing).
    Returns None rather than raising when the value can't be interpreted —
    financial line items are frequently "—" for a metric that doesn't apply
    to a given company/period, and that is a legitimate, expected outcome,
    not an error.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = raw.strip()
    if not text or text in {"—", "-", "N/A", "n/a"}:
        return None

    multiplier = 1.0
    suffix = text[-1].upper()
    if suffix in {"T", "B", "M", "K"} and _NUMERIC_RE.match(text.rstrip("TBMK%").strip("$")):
        multiplier = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}[suffix]
        text = text[:-1]

    match = _NUMERIC_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group().replace(",", "")) * multiplier
    except ValueError:
        return None


def parse_flexible_datetime(raw: str) -> datetime:
    """Normalizes SerpApi's inconsistent date formats to a tz-aware datetime.

    Google News gives ISO 8601 (`2026-07-08T20:30:00Z`) via `iso_date`, but
    also relative strings ("19 minutes ago") in embedded news blocks, and
    Google Finance gives a human-readable format ("Jul 08 2026, 08:30:00 PM
    UTC-04:00"). This tries ISO first, then falls back to "now" for relative
    strings we can't precisely resolve without a reference clock at parse
    time — callers needing exact recency should prefer the iso_date field
    when available rather than relying on this fallback branch.
    """
    text = raw.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass

    cleaned = re.sub(r"UTC([+-]\d{2}):?(\d{2})?", r"\1\2", text).replace(",", "")
    for fmt in ("%b %d %Y %I:%M:%S %p %z", "%m/%d/%Y %I:%M %p %z"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    return datetime.now(timezone.utc)
