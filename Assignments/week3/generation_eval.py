"""Generation quality evaluation: correctness, relevance, faithfulness.

Runs the REAL pipeline (rag_pipeline.answer_question) against every question
in eval_dataset.json -- real retrieval, real Ollama chat model call, real
schema validation, real grounding checks. Nothing here is mocked.

Metrics per question (only computed when the LLM produced schema-valid JSON):
  faithfulness   - from hallucination.grounding_report(), already computed
                   inside answer_question(). 1.0 if the answer's citations/
                   numbers are all traceable to the retrieved context, else
                   0.0. This is "is the answer honest about its sources?"
  correctness    - two signals, since eval_dataset.json ships both:
                     keyword_coverage: fraction of the question's
                       "answer_keywords" that appear verbatim in the
                       generated answer (deterministic, no embedding call).
                     semantic_correctness: cosine similarity between the
                       generated answer's embedding and the human-written
                       "reference_answer"'s embedding (qwen3-embedding).
                   This is "does the answer match what a human said is
                   correct?" -- independent of whether it's grounded.
  relevance      - semantic_relevance: cosine similarity between the
                   question's embedding and the generated answer's
                   embedding. This is "does the answer address what was
                   asked?" -- independent of whether it's correct or
                   grounded. A fluent, grounded, wrong-topic answer scores
                   low here even if faithfulness is perfect.

Questions where the LLM broke the JSON schema get status="schema_error" and
no metrics -- tracked separately as schema_error_rate in the summary.

Run:  uv run python generation_eval.py
"""

import json
from pathlib import Path

from generation_metrics import cosine_similarity, keyword_coverage
from chunking import get_chunks
from extract_pdf import load_pdf_pages
from get_embeddings import get_qwen_embed
from rag_pipeline import answer_question
from store_utils import build_vector_store


def load_eval_dataset() -> list[dict]:
    path = Path(__file__).parent / "data" / "eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


def evaluate_question(q: dict, store, embeddings) -> dict:
    """Run one question through the real pipeline and score the result."""
    record = answer_question(q["question"], store, save=False)
    result = {
        "id": q["id"],
        "question": q["question"],
        "status": record["status"],
        "llm_seconds": record["llm_seconds"],
    }
    if record["status"] != "ok":
        result["error"] = record["error"]
        return result

    answer_text = record["validated"]["answer"]
    result["answer"] = answer_text
    result["reference_answer"] = q["reference_answer"]

    # faithfulness: reuse the grounding report already computed in-pipeline
    result["faithfulness"] = 1.0 if record["grounding"]["grounded"] else 0.0
    result["grounding_issues"] = record["grounding"]["num_issues"]
    result["self_check"] = record["self_check"]

    # correctness: keyword coverage (cheap) + semantic similarity to reference (embedding)
    result["correctness_keyword_coverage"] = round(
        keyword_coverage(answer_text, q["answer_keywords"]), 3
    )
    answer_vec = embeddings.embed_query(answer_text)
    reference_vec = embeddings.embed_query(q["reference_answer"])
    result["correctness_semantic"] = round(cosine_similarity(answer_vec, reference_vec), 3)

    # relevance: does the answer address the question, independent of correctness/grounding
    question_vec = embeddings.embed_query(q["question"])
    result["relevance_semantic"] = round(cosine_similarity(question_vec, answer_vec), 3)

    return result


def summarize(results: list[dict]) -> dict:
    n = len(results)
    ok = [r for r in results if r["status"] == "ok"]
    n_ok = len(ok)
    summary = {
        "num_questions": n,
        "num_ok": n_ok,
        "schema_error_rate": round((n - n_ok) / n, 3) if n else 0.0,
    }
    if n_ok:
        for key in (
            "faithfulness",
            "correctness_keyword_coverage",
            "correctness_semantic",
            "relevance_semantic",
        ):
            summary[f"mean_{key}"] = round(sum(r[key] for r in ok) / n_ok, 3)
        summary["mean_llm_seconds"] = round(sum(r["llm_seconds"] for r in results) / n, 3)
        overrides = sum(1 for r in ok if r["self_check"]["overridden"])
        summary["self_check_override_rate"] = round(overrides / n_ok, 3)
    return summary


def main() -> None:
    questions = load_eval_dataset()
    print(f"Loaded {len(questions)} eval questions")

    pdf_path = Path(__file__).parent / "data" / "nke-10k-2023.pdf"
    chunks = get_chunks(load_pdf_pages(str(pdf_path)))
    print(f"{len(chunks)} chunks to index")

    embeddings = get_qwen_embed()
    store = build_vector_store(embeddings, chunks)
    print("Indexed. Running generation eval against the real pipeline...")

    results = []
    for q in questions:
        print(f"  {q['id']}: {q['question'][:70]}...")
        result = evaluate_question(q, store, embeddings)
        results.append(result)
        if result["status"] == "ok":
            print(
                f"    faithfulness={result['faithfulness']} "
                f"correctness_kw={result['correctness_keyword_coverage']} "
                f"correctness_sem={result['correctness_semantic']} "
                f"relevance={result['relevance_semantic']}"
            )
        else:
            print(f"    SCHEMA ERROR: {result['error']}")

    summary = summarize(results)
    print("\n===== SUMMARY =====")
    print(json.dumps(summary, indent=2))

    report = {"model": "qwen2.5:1.5b", "summary": summary, "per_question": results}
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "generation_eval.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Full report written to {out_path}")


if __name__ == "__main__":
    main()
