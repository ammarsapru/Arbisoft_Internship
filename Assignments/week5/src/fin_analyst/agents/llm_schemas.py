"""Pydantic schemas used as `.with_structured_output()` targets for the
agent-layer LLM calls - kept separate from mcp_server/schemas because these
describe what the *model* is asked to produce (a subset of fields), not the
final domain objects (which also carry deterministically-computed fields
like recency_weight/composite_score - see mcp_server/schemas/news.py)."""

from pydantic import BaseModel, ConfigDict, Field

from fin_analyst.mcp_server.schemas.common import Magnitude, Sentiment


class Domain(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArticleImpactJudgment(Domain):
    article_index: int = Field(description="0-based index matching the article's position in the input list")
    sentiment: Sentiment
    magnitude: Magnitude
    rationale: str = Field(max_length=600, description="One brief sentence, well under 600 characters")


class NewsImpactJudgments(Domain):
    judgments: list[ArticleImpactJudgment]


class SupervisorDecision(Domain):
    proceed: bool = Field(description="True if the worker's output is valid and relevant enough to continue the pipeline")
    reason: str = Field(max_length=600, description="One brief sentence, well under 600 characters")
