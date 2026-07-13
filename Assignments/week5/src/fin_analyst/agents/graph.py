from langgraph.graph import END, StateGraph

from fin_analyst.agents.state import PipelineState
from fin_analyst.agents.supervisor import (
    route_after_extraction,
    route_after_formatting,
    route_after_news,
    validate_after_extraction,
    validate_after_formatting,
    validate_after_news,
)
from fin_analyst.agents.workers.extraction_worker import run_extraction_worker
from fin_analyst.agents.workers.formatting_worker import run_formatting_worker
from fin_analyst.agents.workers.news_impact_worker import run_news_impact_worker


def build_graph(tools_by_name: dict):
    """Supervisor + 3-worker pipeline: extraction -> validate -> news_impact
    -> validate -> formatting -> validate -> END. Every worker->supervisor
    edge is a validation gate (see docs/04-multi-agent-orchestration.md);
    any gate can short-circuit straight to END with next_step="aborted"."""
    graph = StateGraph(PipelineState)

    async def extraction_node(state: PipelineState) -> dict:
        return await run_extraction_worker(state, tools_by_name)

    async def news_impact_node(state: PipelineState) -> dict:
        return await run_news_impact_worker(state, tools_by_name)

    async def formatting_node(state: PipelineState) -> dict:
        return await run_formatting_worker(state, tools_by_name)

    graph.add_node("extraction", extraction_node)
    graph.add_node("validate_extraction", validate_after_extraction)
    graph.add_node("news_impact", news_impact_node)
    graph.add_node("validate_news", validate_after_news)
    graph.add_node("formatting", formatting_node)
    graph.add_node("validate_formatting", validate_after_formatting)

    graph.set_entry_point("extraction")
    graph.add_edge("extraction", "validate_extraction")
    graph.add_conditional_edges("validate_extraction", route_after_extraction, {"news_impact": "news_impact", "aborted": END})
    graph.add_edge("news_impact", "validate_news")
    graph.add_conditional_edges("validate_news", route_after_news, {"formatting": "formatting", "aborted": END})
    graph.add_edge("formatting", "validate_formatting")
    graph.add_conditional_edges("validate_formatting", route_after_formatting, {"done": END})

    return graph.compile()
