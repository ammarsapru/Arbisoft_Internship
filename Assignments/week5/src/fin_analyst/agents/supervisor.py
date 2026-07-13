"""Supervisor validation gates - one per worker hand-off.

Extraction and News Impact gates use a strong-tier LLM call for the
semantic relevance check described in docs/08-structured-outputs-guardrails.md
(does this data actually correspond to the requested company?). The
post-formatting gate is a deterministic check instead of another LLM call:
by that point there's no further worker to route to, and "did a non-empty
file get written" doesn't need judgment - a cost-conscious choice per
docs/07-cost-latency-strategy.md, not an inconsistency.
"""

import os
from pathlib import Path

from fin_analyst.agents.llm_schemas import SupervisorDecision
from fin_analyst.agents.models import get_strong_model
from fin_analyst.agents.prompts import SUPERVISOR_VALIDATION_PROMPT
from fin_analyst.agents.state import PipelineState
from fin_analyst.agents.structured_call import safe_structured_call
from fin_analyst.mcp_server.schemas.report import ValidationFailure


async def _llm_validate(company_query: str, stage: str, result_summary: str) -> SupervisorDecision:
    model = get_strong_model(max_tokens=256).with_structured_output(SupervisorDecision)
    prompt = SUPERVISOR_VALIDATION_PROMPT.format(company_query=company_query, stage=stage, result_summary=result_summary)
    retry_prompt = prompt + "\n\nIMPORTANT: keep `reason` to a single short sentence, well under 600 characters."

    return await safe_structured_call(
        call=lambda: model.ainvoke(prompt),
        retry_call=lambda: model.ainvoke(retry_prompt),
        fallback=SupervisorDecision(proceed=True, reason=f"Validation formatting issue at stage {stage}; proceeding with worker output."),
    )


async def validate_after_extraction(state: PipelineState) -> dict:
    if state.next_step == "aborted":
        return {}

    bundle = state.financial_bundle
    ticker = state.ticker_result
    summary = (
        f"Resolved ticker {ticker.ticker} ('{ticker.display_name}') via {ticker.resolved_via} "
        f"with confidence={ticker.confidence}. Financial bundle company_name='{bundle.company_name}', "
        f"price={bundle.summary.price} {bundle.summary.currency}, "
        f"num statements={len(bundle.statements)}, num price points={len(bundle.price_history)}."
    )
    decision = await _llm_validate(state.company_query, "financial_extraction", summary)

    if not decision.proceed:
        return {
            "validation_failures": [ValidationFailure(stage="financial_extraction", reason=decision.reason, is_recoverable=True)],
            "next_step": "aborted",
            "final_message": f"Stopped after financial data extraction: {decision.reason}",
        }
    return {"next_step": "news_impact"}


async def validate_after_news(state: PipelineState) -> dict:
    news = state.news_impact_bundle
    summary = (
        f"Considered {news.articles_considered} articles, produced {len(news.scores)} impact scores, "
        f"aggregate_impact_score={news.aggregate_impact_score}."
    )
    decision = await _llm_validate(state.company_query, "news_impact", summary)

    if not decision.proceed:
        return {
            "validation_failures": [ValidationFailure(stage="news_impact", reason=decision.reason, is_recoverable=True)],
            "next_step": "aborted",
            "final_message": f"Stopped after news impact analysis: {decision.reason}",
        }
    return {"next_step": "formatting"}


async def validate_after_formatting(state: PipelineState) -> dict:
    report = state.report_output
    path_ok = report is not None and Path(report.file_path).exists() and os.path.getsize(report.file_path) > 0

    if not path_ok:
        return {
            "validation_failures": [
                ValidationFailure(stage="report_formatting", reason="Report file was not written or is empty.", is_recoverable=False)
            ],
            "next_step": "aborted",
            "final_message": "Report formatting did not produce a valid output file.",
        }
    return {"next_step": "done"}


def route_after_extraction(state: PipelineState) -> str:
    return "news_impact" if state.next_step == "news_impact" else "aborted"


def route_after_news(state: PipelineState) -> str:
    return "formatting" if state.next_step == "formatting" else "aborted"


def route_after_formatting(state: PipelineState) -> str:
    return "done"
