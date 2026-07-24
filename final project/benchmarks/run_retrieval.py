from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from backend.app.agent.retrieval import RepositoryRetrievalIndex
from backend.app.graph.analyzer import RepositoryAnalyzer
from backend.app.graph.store import AnalysisSession
from backend.app.indexing import repository_snapshot


def evaluate(repository: Path, cases_path: Path) -> dict[str, object]:
    root = repository.resolve()
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    report = RepositoryAnalyzer().analyze(root).model_copy(
        update={"analysis_id": "retrieval-benchmark"}
    )
    snapshot = repository_snapshot(root)
    session = AnalysisSession(
        id="retrieval-benchmark",
        root=root,
        report=report,
        source_paths=snapshot.paths,
        revision_fingerprint=snapshot.fingerprint,
    )
    with tempfile.TemporaryDirectory() as directory:
        index_started = time.perf_counter()
        index = RepositoryRetrievalIndex(
            session, database_path=Path(directory) / "retrieval.sqlite3",
            snapshot=snapshot,
        )
        index_ms = (time.perf_counter() - index_started) * 1000
        results = []
        reciprocal_ranks: list[float] = []
        latencies: list[float] = []
        recall_5 = 0
        recall_10 = 0
        for case in cases:
            started = time.perf_counter()
            retrieved = index.search(case["question"], limit=10)
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            paths = [item["path"] for item in retrieved]
            expected = set(case["expected_paths"])
            first_rank = next(
                (rank for rank, path in enumerate(paths, 1) if path in expected),
                None,
            )
            if any(path in expected for path in paths[:5]):
                recall_5 += 1
            if any(path in expected for path in paths[:10]):
                recall_10 += 1
            reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
            results.append({
                "question": case["question"],
                "expected_paths": sorted(expected),
                "retrieved_paths": paths,
                "first_relevant_rank": first_rank,
                "latency_ms": round(latency, 3),
            })
    count = max(1, len(cases))
    return {
        "repository": str(root),
        "case_count": len(cases),
        "index_ms": round(index_ms, 3),
        "recall_at_5": round(recall_5 / count, 4),
        "recall_at_10": round(recall_10 / count, 4),
        "mean_reciprocal_rank": round(statistics.mean(reciprocal_ranks), 4),
        "mean_query_ms": round(statistics.mean(latencies), 3),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Waypoint code retrieval")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument(
        "--cases", type=Path,
        default=Path(__file__).with_name("retrieval_cases.json"),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = evaluate(arguments.repository, arguments.cases)
    payload = json.dumps(result, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
