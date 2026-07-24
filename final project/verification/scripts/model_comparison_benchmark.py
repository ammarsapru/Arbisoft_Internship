from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx


DEFAULT_TASKS = [
    "What is this repository about? Highlight its top 10 features.",
    "Which files are the main application entry points, and why?",
    "How is the backend organized from HTTP entry point to business logic?",
    "Trace one important cross-file call path and explain the evidence.",
]


def _cell(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Two-model task benchmark",
        "",
        f"Analysis: `{payload['analysis_id']}`",
        "",
        "Both models received the same server-retrieved, frozen evidence for each task. "
        "They did not crawl the repository directly during this comparison.",
        "",
        "| Task | Model | Input tokens | Output tokens | Total tokens | Time (ms) | TTFT (ms) | Tool calls | Output chars | Citations |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, result in enumerate(payload["tasks"], 1):
        for answer in result.get("answers", []):
            lines.append(
                "| " + " | ".join(_cell(value) for value in [
                    f"{index}. {result['question']}",
                    f"{answer['provider']} / {answer['model']}",
                    answer.get("input_tokens"),
                    answer.get("output_tokens"),
                    answer.get("total_tokens"),
                    answer.get("duration_ms"),
                    answer.get("ttft_ms"),
                    answer.get("tool_calls"),
                    answer.get("output_characters"),
                    len(answer.get("citations", [])),
                ]) + " |"
            )
    lines += [
        "",
        "## Measurement limitations",
        "",
        "- `Time` is end-to-end model-call latency for a complete non-streaming response.",
        "- TTFT is `N/A`: the current providers do not stream this endpoint, so true time-to-first-token cannot be observed honestly.",
        "- Each model makes one forced structured-output tool call. Repository retrieval is performed once by the server before fan-out.",
        "- The application caps questions at 500 characters, evidence at 2–15 passages, and requested output at the configured `WAYPOINT_AGENT_MAX_OUTPUT_TOKENS` value.",
        "- Provider-reported usage is recorded as returned. Claude Code subscription usage may report cache-adjusted or unexpectedly small input counts and should not be treated as raw prompt length.",
        "",
    ]
    return "\n".join(lines)


def run(base_url: str, analysis_id: str, tasks: list[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=base_url, timeout=240) as client:
        for question in tasks:
            started = time.perf_counter()
            response = client.post(
                f"/api/v1/analyses/{analysis_id}/answer/compare",
                json={"question": question, "evidence_limit": 8},
            )
            response.raise_for_status()
            result = response.json()
            result["task_wall_time_ms"] = round((time.perf_counter() - started) * 1000, 3)
            results.append(result)
    return {"analysis_id": analysis_id, "tasks": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the same tasks across Waypoint's two configured models.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--task", action="append", dest="tasks")
    parser.add_argument("--confirm-live-model-usage", action="store_true")
    args = parser.parse_args()
    if not args.confirm_live_model_usage:
        raise SystemExit("Refusing to spend model quota without --confirm-live-model-usage")
    payload = run(args.base_url, args.analysis_id, args.tasks or DEFAULT_TASKS)
    output = Path("verification/results")
    output.mkdir(parents=True, exist_ok=True)
    (output / "model-comparison-benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output / "model-comparison-benchmark.md").write_text(_markdown(payload), encoding="utf-8")
    print(_markdown(payload))


if __name__ == "__main__":
    main()
