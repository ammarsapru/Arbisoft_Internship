import time
import uuid
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from fin_analyst.tracing.tracer import get_current_run_id, write_event
from fin_analyst.tracing.models import TraceEvent


class TracingCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler capturing agent_node and llm_call layer
    events, so agent-side tracing hooks into the framework's own event
    stream instead of hand-wrapping every node/tool function - see
    docs/06-agent-debugging.md.
    """

    def __init__(self):
        self._starts: dict[UUID, dict[str, Any]] = {}

    def _write(self, run_id_key: UUID, layer: str, actor: str, status: str, output: Any = None, error: str | None = None,
               input_tokens: int | None = None, output_tokens: int | None = None, model_name: str | None = None) -> None:
        start_info = self._starts.pop(run_id_key, {})
        latency_ms = (time.perf_counter() - start_info.get("start", time.perf_counter())) * 1000
        event = TraceEvent(
            run_id=get_current_run_id(),
            event_id=uuid.uuid4().hex[:12],
            layer=layer,
            actor=actor,
            input_summary={"preview": str(start_info.get("input"))[:400]},
            output_summary={"preview": str(output)[:400]},
            latency_ms=latency_ms,
            status=status,
            error_detail=error,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        write_event(event)

    def on_chain_start(self, serialized, inputs, *, run_id, **kwargs):
        name = (serialized or {}).get("name", "chain")
        self._starts[run_id] = {"start": time.perf_counter(), "input": inputs, "name": name}

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        name = self._starts.get(run_id, {}).get("name", "chain")
        self._write(run_id, "agent_node", name, "ok", output=outputs)

    def on_chain_error(self, error, *, run_id, **kwargs):
        name = self._starts.get(run_id, {}).get("name", "chain")
        self._write(run_id, "agent_node", name, "error", error=str(error))

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = (serialized or {}).get("name", "tool")
        self._starts[run_id] = {"start": time.perf_counter(), "input": input_str, "name": name}

    def on_tool_end(self, output, *, run_id, **kwargs):
        name = self._starts.get(run_id, {}).get("name", "tool")
        self._write(run_id, "agent_node", f"tool:{name}", "ok", output=output)

    def on_tool_error(self, error, *, run_id, **kwargs):
        name = self._starts.get(run_id, {}).get("name", "tool")
        self._write(run_id, "agent_node", f"tool:{name}", "error", error=str(error))

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        model = (serialized or {}).get("kwargs", {}).get("model", "unknown-model")
        self._starts[run_id] = {"start": time.perf_counter(), "input": prompts, "name": model}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        model = (serialized or {}).get("kwargs", {}).get("model", "unknown-model")
        self._starts[run_id] = {"start": time.perf_counter(), "input": messages, "name": model}

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs):
        start_info = self._starts.get(run_id, {})
        model_name = start_info.get("name", "unknown-model")
        usage = (response.llm_output or {}).get("usage") or {}
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")

        if input_tokens is None and response.generations:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            usage_meta = getattr(msg, "usage_metadata", None) if msg else None
            if usage_meta:
                input_tokens = usage_meta.get("input_tokens")
                output_tokens = usage_meta.get("output_tokens")

        text_out = response.generations[0][0].text if response.generations and response.generations[0] else ""
        self._write(
            run_id, "llm_call", model_name, "ok", output=text_out,
            input_tokens=input_tokens, output_tokens=output_tokens, model_name=model_name,
        )

    def on_llm_error(self, error, *, run_id, **kwargs):
        start_info = self._starts.get(run_id, {})
        self._write(run_id, "llm_call", start_info.get("name", "unknown-model"), "error", error=str(error))
