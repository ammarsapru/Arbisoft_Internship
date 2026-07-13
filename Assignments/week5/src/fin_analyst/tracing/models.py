from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Layer = Literal["mcp_tool", "agent_node", "llm_call"]
Status = Literal["ok", "error"]

# Published per-million-token pricing (USD), used only for run-level cost
# estimation in the trace/cost report - see docs/07-cost-latency-strategy.md.
MODEL_PRICING_USD_PER_MILLION = {
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
}


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    layer: Layer
    actor: str
    input_summary: dict[str, Any] = {}
    output_summary: dict[str, Any] = {}
    latency_ms: float
    status: Status
    error_detail: str | None = None

    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def estimated_cost_usd(self) -> float | None:
        if not self.model_name or self.input_tokens is None or self.output_tokens is None:
            return None
        pricing = MODEL_PRICING_USD_PER_MILLION.get(self.model_name)
        if pricing is None:
            return None
        return (self.input_tokens * pricing["input"] + self.output_tokens * pricing["output"]) / 1_000_000
