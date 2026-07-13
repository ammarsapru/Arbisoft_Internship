import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

from fin_analyst.config import get_settings
from fin_analyst.tracing.models import Layer, Status, TraceEvent

_current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@contextmanager
def run_context(run_id: str) -> Iterator[str]:
    token = _current_run_id.set(run_id)
    try:
        yield run_id
    finally:
        _current_run_id.reset(token)


def get_current_run_id() -> str:
    run_id = _current_run_id.get()
    if run_id is None:
        raise RuntimeError("No active trace run_id - wrap the call in `with run_context(run_id):`")
    return run_id


def _trace_path(run_id: str) -> Path:
    settings = get_settings()
    return settings.trace_log_dir / f"{run_id}.jsonl"


def write_event(event: TraceEvent) -> None:
    path = _trace_path(event.run_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")


def _summarize(value: Any, max_len: int = 400) -> dict[str, Any]:
    try:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > max_len:
        text = text[:max_len] + "...(truncated)"
    return {"preview": text}


@contextmanager
def traced_call(layer: Layer, actor: str, input_value: Any = None, model_name: str | None = None) -> Iterator[dict]:
    """Context manager that records a TraceEvent for one call. Yields a
    mutable dict the caller can fill in (`output`, `input_tokens`,
    `output_tokens`) before the block exits; latency/status/errors are
    captured automatically."""
    run_id = get_current_run_id()
    start = time.perf_counter()
    result: dict[str, Any] = {"output": None, "input_tokens": None, "output_tokens": None}
    status: Status = "ok"
    error_detail: str | None = None
    try:
        yield result
    except Exception as exc:
        status = "error"
        error_detail = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        event = TraceEvent(
            run_id=run_id,
            event_id=uuid.uuid4().hex[:12],
            layer=layer,
            actor=actor,
            input_summary=_summarize(input_value),
            output_summary=_summarize(result.get("output")),
            latency_ms=latency_ms,
            status=status,
            error_detail=error_detail,
            model_name=model_name,
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
        )
        write_event(event)


def load_run_events(run_id: str) -> list[TraceEvent]:
    path = _trace_path(run_id)
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(TraceEvent.model_validate_json(line))
    return events


def summarize_run_cost(run_id: str) -> dict[str, Any]:
    events = load_run_events(run_id)
    llm_events = [e for e in events if e.layer == "llm_call"]
    total_cost = sum(e.estimated_cost_usd or 0.0 for e in llm_events)
    total_input_tokens = sum(e.input_tokens or 0 for e in llm_events)
    total_output_tokens = sum(e.output_tokens or 0 for e in llm_events)
    return {
        "run_id": run_id,
        "total_events": len(events),
        "mcp_tool_calls": sum(1 for e in events if e.layer == "mcp_tool"),
        "agent_node_calls": sum(1 for e in events if e.layer == "agent_node"),
        "llm_calls": len(llm_events),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(total_cost, 6),
        "total_latency_ms": sum(e.latency_ms for e in events),
        "errors": [e.model_dump(mode="json") for e in events if e.status == "error"],
    }
