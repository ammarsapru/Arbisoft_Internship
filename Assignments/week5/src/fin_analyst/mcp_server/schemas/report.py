from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from fin_analyst.mcp_server.schemas.common import Confidence, TickerSymbol
from fin_analyst.mcp_server.schemas.finance import FinancialBundle
from fin_analyst.mcp_server.schemas.news import NewsImpactBundle


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TickerCandidate(Domain):
    ticker: TickerSymbol
    exchange: str
    display_name: str
    source: Literal["google_finance", "web_search"]


class Resolved(Domain):
    outcome: Literal["resolved"] = "resolved"
    ticker: TickerSymbol
    exchange: str
    display_name: str
    confidence: Confidence
    resolved_via: Literal["google_finance", "web_search"]


class Ambiguous(Domain):
    outcome: Literal["ambiguous"] = "ambiguous"
    query: str
    candidates: list[TickerCandidate]


class NotPubliclyListed(Domain):
    outcome: Literal["not_listed"] = "not_listed"
    query: str
    reason: str


class LookupFailed(Domain):
    outcome: Literal["failed"] = "failed"
    query: str
    reason: str


ResolveTickerResult = Annotated[
    Union[Resolved, Ambiguous, NotPubliclyListed, LookupFailed],
    Field(discriminator="outcome"),
]


class ValidationFailure(Domain):
    """Typed failure passed through PipelineState instead of a raised
    exception — see docs/08-structured-outputs-guardrails.md."""

    stage: Literal["ticker_resolution", "financial_extraction", "news_impact", "report_formatting"]
    reason: str
    is_recoverable: bool = True
    raw_payload_summary: str | None = None


class CompanyReportBundle(Domain):
    """The payload served back by the finance-report://{ticker} MCP
    resource — the combined, already-computed output of the tool calls,
    cached so the resource read itself makes no live API calls."""

    ticker: TickerSymbol
    company_name: str
    financials: FinancialBundle
    news_impact: NewsImpactBundle | None = None
    generated_at: str


class ReportOutput(Domain):
    file_path: str
    ticker: TickerSymbol
    company_name: str
    executive_summary: str
    sheet_names: list[str]


class ReportGenerated(Domain):
    """Success outcome of generate_financial_report - wraps the same
    ReportOutput the CLI pipeline produces, plus the pipeline's own run_id
    so the full supervisor+worker trace can be independently replayed via
    `uv run python -m fin_analyst.tracing.replay <pipeline_run_id>`."""

    outcome: Literal["generated"] = "generated"
    pipeline_run_id: str
    report: ReportOutput


class ReportAborted(Domain):
    """The pipeline ran but a supervisor validation gate stopped it before
    a report was produced (e.g. company not publicly listed, or a
    resolved ticker failed the semantic relevance check) - an expected,
    typed outcome, not a tool error. See docs/08-structured-outputs-guardrails.md."""

    outcome: Literal["aborted"] = "aborted"
    pipeline_run_id: str
    stage: str
    reason: str


GenerateReportResult = Annotated[
    Union[ReportGenerated, ReportAborted],
    Field(discriminator="outcome"),
]
