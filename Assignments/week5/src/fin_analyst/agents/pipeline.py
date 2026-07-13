from fin_analyst.agents.graph import build_graph
from fin_analyst.agents.mcp_client import build_mcp_client
from fin_analyst.agents.models import get_tracing_handler
from fin_analyst.agents.state import PipelineState
from fin_analyst.config import get_settings
from fin_analyst.tracing.tracer import new_run_id, run_context


async def run_pipeline(
    company_query: str, period_query: str | None = None, output_directory: str | None = None
) -> tuple[PipelineState, str]:
    """Runs the full supervisor + 3-worker pipeline for one company query.
    Returns (final_state, run_id) so callers can both inspect the result
    and replay/cost-report the trace via `run_id`.

    `output_directory`, if given, MUST be an absolute path - MCP tool calls
    carry no ambient notion of "the caller's current directory", so a
    caller wanting the report written to its own working directory has to
    pass that directory explicitly. A relative path here would resolve
    against this server process's own cwd, not the caller's, silently
    defeating the point - see docs/connecting-other-clients.md."""
    run_id = new_run_id("pipeline")
    settings = get_settings()

    with run_context(run_id):
        client = build_mcp_client(run_id)
        tools = await client.get_tools()
        tools_by_name = {t.name: t for t in tools}

        graph = build_graph(tools_by_name)
        initial_state = PipelineState(
            run_id=run_id, company_query=company_query, period_query=period_query, output_directory=output_directory
        )

        result = await graph.ainvoke(
            initial_state,
            config={"recursion_limit": settings.recursion_limit, "callbacks": [get_tracing_handler()]},
        )
        final_state = PipelineState.model_validate(result)

    return final_state, run_id
