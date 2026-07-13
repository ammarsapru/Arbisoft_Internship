"""Thin typed wrappers around the LangChain StructuredTools loaded from the
MCP server, so worker code deals in Pydantic domain objects, not raw MCP
content blocks. Confirmed live (2026-07-09): langchain-mcp-adapters returns
tool results as `[{"type": "text", "text": "<json>"}]` - this module is the
one place that JSON-unwrapping happens.
"""

import json
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from fin_analyst.mcp_server.schemas.finance import FinancialBundle, MarketSnapshot
from fin_analyst.mcp_server.schemas.news import NewsArticle
from fin_analyst.mcp_server.schemas.report import ResolveTickerResult

T = TypeVar("T", bound=BaseModel)

_resolve_ticker_adapter: TypeAdapter = TypeAdapter(ResolveTickerResult)


def _block_text(item: Any) -> str:
    return item["text"] if isinstance(item, dict) else item.text


def _unwrap(raw: Any) -> Any:
    """Unwraps a single-object MCP tool result. Confirmed live (2026-07-09):
    a tool returning one Pydantic object comes back as ONE content block
    whose text is the full JSON object - but a tool returning `list[T]`
    comes back as ONE content block PER list element (see `_unwrap_list`),
    not a single block containing a JSON array. Using this function on a
    list-returning tool silently decodes only the first element."""
    if isinstance(raw, list):
        text = _block_text(raw[0])
    elif isinstance(raw, dict):
        text = raw.get("text", raw)
    else:
        text = raw
    return json.loads(text) if isinstance(text, str) else text


def _unwrap_list(raw: Any) -> list[Any]:
    """Unwraps a list-returning MCP tool result - one content block per
    element, per the module docstring."""
    if not isinstance(raw, list):
        return [_unwrap(raw)]
    return [json.loads(_block_text(item)) for item in raw]


async def call_resolve_ticker(tools_by_name: dict, company_name: str) -> ResolveTickerResult:
    raw = await tools_by_name["resolve_ticker"].ainvoke({"company_name": company_name})
    return _resolve_ticker_adapter.validate_python(_unwrap(raw))


async def call_get_market_snapshot(tools_by_name: dict) -> MarketSnapshot:
    raw = await tools_by_name["get_market_snapshot"].ainvoke({})
    return MarketSnapshot.model_validate(_unwrap(raw))


async def call_get_stock_financials(
    tools_by_name: dict,
    ticker: str,
    exchange: str,
    company_name: str,
    window: str,
    requested_period_text: str | None,
    period_caveat: str | None,
) -> FinancialBundle:
    raw = await tools_by_name["get_stock_financials"].ainvoke(
        {
            "ticker": ticker,
            "exchange": exchange,
            "company_name": company_name,
            "window": window,
            "requested_period_text": requested_period_text,
            "period_caveat": period_caveat,
        }
    )
    return FinancialBundle.model_validate(_unwrap(raw))


async def call_get_company_news(tools_by_name: dict, ticker: str, company_name: str) -> list[NewsArticle]:
    raw = await tools_by_name["get_company_news"].ainvoke({"ticker": ticker, "company_name": company_name})
    return [NewsArticle.model_validate(item) for item in _unwrap_list(raw)]
