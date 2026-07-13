"""Worker B: News Impact Analyst.

Fetches news deterministically via the MCP tool, then makes exactly ONE
batched LLM call (strong tier) to classify every article's sentiment and
magnitude in a single `.with_structured_output()` call - not one call per
article - per docs/07-cost-latency-strategy.md.
"""

from datetime import datetime, timezone

from fin_analyst.agents.llm_schemas import NewsImpactJudgments
from fin_analyst.agents.mcp_tools import call_get_company_news
from fin_analyst.agents.models import get_strong_model
from fin_analyst.agents.prompts import NEWS_IMPACT_WORKER_SYSTEM_PROMPT
from fin_analyst.agents.state import PipelineState
from fin_analyst.agents.structured_call import safe_structured_call
from fin_analyst.mcp_server.schemas.common import parse_flexible_datetime
from fin_analyst.mcp_server.schemas.news import NewsImpactBundle, NewsImpactScore, compute_recency_weight
from fin_analyst.mcp_server.schemas.report import ValidationFailure


async def run_news_impact_worker(state: PipelineState, tools_by_name: dict) -> dict:
    bundle = state.financial_bundle
    ticker = bundle.ticker
    articles = await call_get_company_news(tools_by_name, ticker, bundle.company_name)

    reference_time = _parse_reference_close(bundle.summary.as_of)

    if not articles:
        return {
            "news_impact_bundle": NewsImpactBundle(
                ticker=ticker, reference_close_time=reference_time, articles_considered=0, scores=[]
            )
        }

    article_lines = "\n".join(
        f"[{i}] title: {a.title}\n    source: {a.source}\n    published: {a.published_at.isoformat()}\n    snippet: {a.snippet or ''}"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Company: {bundle.company_name} ({ticker})\n"
        f"Last market close: {reference_time.isoformat()}\n\n"
        f"Articles:\n{article_lines}\n\n"
        f"Return a judgment for every article index 0..{len(articles) - 1}."
    )

    model = get_strong_model(max_tokens=4096).with_structured_output(NewsImpactJudgments)
    messages = [("system", NEWS_IMPACT_WORKER_SYSTEM_PROMPT), ("human", prompt)]
    retry_messages = [
        ("system", NEWS_IMPACT_WORKER_SYSTEM_PROMPT + " Keep every rationale to one short sentence, well under 600 characters."),
        ("human", prompt),
    ]
    result: NewsImpactJudgments = await safe_structured_call(
        call=lambda: model.ainvoke(messages),
        retry_call=lambda: model.ainvoke(retry_messages),
        fallback=NewsImpactJudgments(judgments=[]),
    )

    judgments_by_index = {j.article_index: j for j in result.judgments}
    scores = []
    for i, article in enumerate(articles):
        judgment = judgments_by_index.get(i)
        if judgment is None:
            continue
        scores.append(
            NewsImpactScore(
                article_title=article.title,
                article_link=article.link,
                sentiment=judgment.sentiment,
                magnitude=judgment.magnitude,
                rationale=judgment.rationale,
                recency_weight=compute_recency_weight(article.published_at, reference_time),
            )
        )

    news_impact_bundle = NewsImpactBundle(
        ticker=ticker, reference_close_time=reference_time, articles_considered=len(articles), scores=scores
    )

    validation_failures = []
    if not scores:
        validation_failures.append(
            ValidationFailure(
                stage="news_impact",
                reason="Articles were fetched but the model returned no usable judgments.",
                is_recoverable=True,
            )
        )

    return {"news_impact_bundle": news_impact_bundle, "validation_failures": validation_failures}


def _parse_reference_close(as_of: str) -> datetime:
    if not as_of:
        return datetime.now(timezone.utc)
    return parse_flexible_datetime(as_of)
