from fin_analyst.agents.state import PipelineState
from fin_analyst.agents.workers.formatting_worker import run_formatting_worker


async def test_relative_output_directory_is_rejected_before_any_llm_or_api_call():
    """The output_directory guard must trigger before touching
    state.financial_bundle's attributes or calling the LLM - this test
    passes financial_bundle=None (the PipelineState default) specifically
    to prove the rejection happens first; if the guard were ever moved
    after the bundle is used, this would raise AttributeError instead of
    returning the expected validation failure."""
    state = PipelineState(
        run_id="test-run",
        company_query="Apple",
        output_directory="relative/path/not/absolute",
    )

    result = await run_formatting_worker(state, tools_by_name={})

    assert result["next_step"] == "aborted"
    assert len(result["validation_failures"]) == 1
    failure = result["validation_failures"][0]
    assert failure.stage == "report_formatting"
    assert "absolute path" in failure.reason
    assert "relative/path/not/absolute" in failure.reason
