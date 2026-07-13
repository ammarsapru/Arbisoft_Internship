import operator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict

from fin_analyst.mcp_server.schemas.finance import FinancialBundle
from fin_analyst.mcp_server.schemas.news import NewsImpactBundle
from fin_analyst.mcp_server.schemas.report import ReportOutput, ResolveTickerResult, ValidationFailure

NextStep = Literal["extraction", "news_impact", "formatting", "done", "aborted"]


class PipelineState(BaseModel):
    """Shared state passed between the supervisor and the three workers.
    Every worker's return is a typed field here, not raw conversation
    history - see docs/04-multi-agent-orchestration.md and
    docs/08-structured-outputs-guardrails.md."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    company_query: str
    period_query: str | None = None
    output_directory: str | None = None

    ticker_result: ResolveTickerResult | None = None
    financial_bundle: FinancialBundle | None = None
    news_impact_bundle: NewsImpactBundle | None = None
    report_output: ReportOutput | None = None

    validation_failures: Annotated[list[ValidationFailure], operator.add] = []
    next_step: NextStep = "extraction"
    retry_counts: dict[str, int] = {}
    final_message: str | None = None
