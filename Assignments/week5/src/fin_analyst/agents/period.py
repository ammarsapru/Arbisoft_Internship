import re

from fin_analyst.mcp_server.schemas.common import FinanceWindow

_YEAR_RE = re.compile(r"(\d+)\s*y(ea)?r", re.IGNORECASE)
_MONTH_RE = re.compile(r"(\d+)\s*m(o|on|onth)?s?\b", re.IGNORECASE)
_DAY_RE = re.compile(r"(\d+)\s*d(ay)?s?\b", re.IGNORECASE)

_LONG_HORIZON_WORDS = ("all time", "all-time", "since ipo", "max", "entire history", "full history")


def parse_period(text: str | None) -> tuple[FinanceWindow, str | None]:
    """Map a free-text period ask to the nearest Google Finance `window`
    enum value, always returning a caveat string when the mapping isn't
    exact - see docs/05-tool-design-for-agents.md for why this lives at the
    agent layer rather than inside the MCP tool itself.

    Returns (resolved_window, caveat_or_None).
    """
    if not text or not text.strip():
        return "1Y", None

    lowered = text.strip().lower()

    if any(w in lowered for w in _LONG_HORIZON_WORDS):
        return "MAX", None

    year_match = _YEAR_RE.search(lowered)
    if year_match:
        years = int(year_match.group(1))
        if years <= 1:
            return "1Y", None
        if years <= 5:
            return "5Y", None
        return (
            "MAX",
            f"You asked for {years} years; Google Finance's longest available window is MAX, "
            f"which may not cover the full {years} years depending on the ticker's listing history - using MAX.",
        )

    month_match = _MONTH_RE.search(lowered)
    if month_match:
        months = int(month_match.group(1))
        if months <= 1:
            return "1M", None
        if months <= 6:
            return "6M", None
        return "1Y", None

    day_match = _DAY_RE.search(lowered)
    if day_match:
        days = int(day_match.group(1))
        return ("1D", None) if days <= 1 else ("5D", None)

    if "ytd" in lowered or "year to date" in lowered or "this year" in lowered:
        return "YTD", None

    return (
        "1Y",
        f"Couldn't parse '{text}' as a specific period; defaulted to the last 1 year of price history.",
    )
