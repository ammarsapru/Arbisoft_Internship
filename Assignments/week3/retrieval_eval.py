"""Measure and compare retrieval quality of embedding models.

Ground truth lives in eval_dataset.json: each question lists the 10-K pages
(0-indexed) that contain the answer. A retrieved chunk is relevant if its
source page is one of the expected pages.

Metrics (all computed at several k values, per question then averaged):
  hit_rate@k   - fraction of questions where at least one relevant chunk
                 appears in the top k results ("did retrieval find anything
                 useful at all?").
  recall@k     - fraction of a question's expected pages covered by the unique
                 pages of the top k results, averaged over questions ("how much
                 of the evidence did we surface?").
  precision@k  - fraction of the top k retrieved chunks whose page is
                 relevant ("how much of what we surfaced was useful?").
                 Unlike recall, duplicate chunks from the same relevant page
                 each count individually here, since precision judges each
                 retrieved slot on its own.
  mrr@k        - mean reciprocal rank of the first relevant chunk ("how high
                 up is the first useful result?").
  ndcg@k       - normalized discounted cumulative gain using binary
                 relevance (a page is either in expected_pages or not; this
                 dataset has no graded relevance judgments). Rewards
                 relevant pages appearing earlier, normalized against the
                 best possible ordering of the same expected pages.

Run:  uv run python retrieval_eval.py
"""

import json
import math
import time
from pathlib import Path

from langchain_core.documents import Document

from chunking import get_chunks
from extract_pdf import load_pdf_pages
from get_embeddings import get_qwen_embed, get_snowfl_embed
from store_utils import build_vector_store

K_VALUES = [1, 3, 5, 10]


# ---------------------------------------------------------------- metrics

def hit_at_k(retrieved_pages: list[int], expected_pages: list[int], k: int) -> float:
    """1.0 if any of the first k retrieved pages is relevant, else 0.0."""
    return 1.0 if any(p in expected_pages for p in retrieved_pages[:k]) else 0.0


def recall_at_k(retrieved_pages: list[int], expected_pages: list[int], k: int) -> float:
    """Fraction of expected pages present among the first k retrieved pages."""
    if not expected_pages:
        raise ValueError("expected_pages must not be empty")
    found = set(retrieved_pages[:k]) & set(expected_pages)
    return len(found) / len(set(expected_pages))


def reciprocal_rank(retrieved_pages: list[int], expected_pages: list[int], k: int) -> float:
    """1/rank of the first relevant result within the top k, or 0.0."""
    for rank, page in enumerate(retrieved_pages[:k], start=1):
        if page in expected_pages:
            return 1.0 / rank
    return 0.0


def precision_at_k(retrieved_pages: list[int], expected_pages: list[int], k: int) -> float:
    """Fraction of the first k retrieved chunks whose page is relevant.

    Each retrieved slot is judged independently, so a page retrieved twice
    (two chunks from the same page) counts twice here -- unlike recall,
    which counts unique pages only.
    """
    top_k = retrieved_pages[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for p in top_k if p in expected_pages)
    return relevant / len(top_k)


def dcg_at_k(retrieved_pages: list[int], expected_pages: list[int], k: int) -> float:
    """Discounted cumulative gain with binary relevance (1 if page relevant, else 0)."""
    return sum(
        1.0 / math.log2(rank + 1)
        for rank, page in enumerate(retrieved_pages[:k], start=1)
        if page in expected_pages
    )


def ndcg_at_k(retrieved_pages: list[int], expected_pages: list[int], k: int) -> float:
    """DCG@k normalized against the ideal ranking (all expected pages first).

    Binary relevance only -- this dataset has no graded relevance labels, so
    "ideal" means all of a question's expected pages retrieved consecutively
    at the top, up to k.
    """
    if not expected_pages:
        raise ValueError("expected_pages must not be empty")
    dcg = dcg_at_k(retrieved_pages, expected_pages, k)
    ideal_hits = min(k, len(expected_pages))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_model(store, questions: list[dict], k_values: list[int]) -> dict:
    """Run every eval question against a vector store and aggregate metrics."""
    max_k = max(k_values)
    per_question = []
    for q in questions:
        t0 = time.perf_counter()
        results = store.similarity_search(q["question"], k=max_k)
        elapsed = time.perf_counter() - t0
        retrieved_pages = [doc.metadata["page"] for doc in results]
        per_question.append(
            {
                "id": q["id"],
                "question": q["question"],
                "expected_pages": q["expected_pages"],
                "retrieved_pages": retrieved_pages,
                "query_seconds": round(elapsed, 3),
                "metrics": {
                    **{
                        f"hit@{k}": hit_at_k(retrieved_pages, q["expected_pages"], k)
                        for k in k_values
                    },
                    **{
                        f"precision@{k}": round(
                            precision_at_k(retrieved_pages, q["expected_pages"], k), 3
                        )
                        for k in k_values
                    },
                    **{
                        f"recall@{k}": round(
                            recall_at_k(retrieved_pages, q["expected_pages"], k), 3
                        )
                        for k in k_values
                    },
                    **{
                        f"mrr@{k}": round(
                            reciprocal_rank(retrieved_pages, q["expected_pages"], k), 3
                        )
                        for k in k_values
                    },
                    **{
                        f"ndcg@{k}": round(
                            ndcg_at_k(retrieved_pages, q["expected_pages"], k), 3
                        )
                        for k in k_values
                    },
                },
            }
        )

    summary = {}
    n = len(questions)
    for k in k_values:
        summary[f"hit_rate@{k}"] = round(
            sum(
                hit_at_k(pq["retrieved_pages"], pq["expected_pages"], k)
                for pq in per_question
            )
            / n,
            3,
        )
        summary[f"recall@{k}"] = round(
            sum(
                recall_at_k(pq["retrieved_pages"], pq["expected_pages"], k)
                for pq in per_question
            )
            / n,
            3,
        )
        summary[f"precision@{k}"] = round(
            sum(
                precision_at_k(pq["retrieved_pages"], pq["expected_pages"], k)
                for pq in per_question
            )
            / n,
            3,
        )
        summary[f"mrr@{k}"] = round(
            sum(
                reciprocal_rank(pq["retrieved_pages"], pq["expected_pages"], k)
                for pq in per_question
            )
            / n,
            3,
        )
        summary[f"ndcg@{k}"] = round(
            sum(
                ndcg_at_k(pq["retrieved_pages"], pq["expected_pages"], k)
                for pq in per_question
            )
            / n,
            3,
        )
    summary["avg_query_seconds"] = round(
        sum(pq["query_seconds"] for pq in per_question) / n, 3
    )
    return {"summary": summary, "per_question": per_question}


# ---------------------------------------------------------------- runner

def load_eval_dataset() -> list[dict]:
    path = Path(__file__).parent / "data" / "eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


def main() -> None:
    questions = load_eval_dataset()
    print(f"Loaded {len(questions)} eval questions")

    pdf_path = Path(__file__).parent / "data" / "nke-10k-2023.pdf"
    chunks = get_chunks(load_pdf_pages(str(pdf_path)))
    print(f"{len(chunks)} chunks to index")

    models = {
        "qwen3-embedding:0.6b": get_qwen_embed(),
        "snowflake-arctic-embed:latest": get_snowfl_embed(),
    }

    report = {"k_values": K_VALUES, "num_questions": len(questions), "models": {}}
    for name, embeddings in models.items():
        print("-------------------------")
        print(f"Indexing with {name}...")
        t0 = time.perf_counter()
        store = build_vector_store(embeddings, chunks)
        index_seconds = round(time.perf_counter() - t0, 1)
        print(f"Indexed in {index_seconds}s; evaluating...")
        result = evaluate_model(store, questions, K_VALUES)
        result["summary"]["index_seconds"] = index_seconds
        report["models"][name] = result
        print(json.dumps(result["summary"], indent=2))

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "retrieval_eval.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Full report written to {out_path}")

    print("\n===== COMPARISON =====")
    header = ["metric"] + list(report["models"].keys())
    print(" | ".join(f"{h:<32}" for h in header))
    metric_names = [f"hit_rate@{k}" for k in K_VALUES]
    metric_names += [f"precision@{k}" for k in K_VALUES]
    metric_names += [f"recall@{k}" for k in K_VALUES]
    metric_names += [f"mrr@{k}" for k in K_VALUES]
    metric_names += [f"ndcg@{k}" for k in K_VALUES]
    metric_names += ["avg_query_seconds", "index_seconds"]
    for m in metric_names:
        row = [m] + [
            str(report["models"][name]["summary"][m]) for name in report["models"]
        ]
        print(" | ".join(f"{c:<32}" for c in row))


if __name__ == "__main__":
    main()
