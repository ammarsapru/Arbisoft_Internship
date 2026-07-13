"""Hallucination evaluation via graduated out-of-scope queries.

Runs the REAL pipeline against adversarial_eval_dataset.json: questions
whose answers are NOT in the NIKE FY2023 10-K, at increasing topic distance
from the document (see that file's "tiers" for the definitions). Retrieval
always returns the top-k nearest Nike chunks regardless of the question, so
every question here should make the model set insufficient_context=true
rather than fabricate an answer from irrelevant context.

Per-question outcome classification:
  schema_error        - the LLM broke the JSON contract entirely.
  correctly_refused    - insufficient_context=true (the desired outcome).
  hallucinated          - insufficient_context=false AND the answer fails
                          grounding (cited/quoted/number content doesn't
                          trace back to the retrieved context) -- the model
                          answered confidently using content it invented.
                          This is the failure mode this eval exists to catch.
  answered_but_grounded - insufficient_context=false but grounding still
                          passed. This means the model found something in
                          the retrieved Nike chunks that technically
                          satisfies the grounding checks (e.g. it echoed a
                          real Nike number/quote) while answering an
                          off-topic question -- schema-valid and
                          "grounded" by the narrow citation/quote/number
                          checks, but still the wrong behavior for a
                          question the context can't actually answer.
                          Flagged separately because it's not caught by the
                          grounding checks alone.

Aggregated per tier so the report shows whether refusal reliability
degrades or improves as questions get further from the core knowledge base.

Run:  uv run python hallucination_eval.py
"""

import json
from pathlib import Path

from chunking import get_chunks
from extract_pdf import load_pdf_pages
from get_embeddings import get_qwen_embed
from rag_pipeline import answer_question
from store_utils import build_vector_store


def load_adversarial_dataset() -> dict:
    path = Path(__file__).parent / "data" / "adversarial_eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def classify(record: dict) -> str:
    if record["status"] != "ok":
        return "schema_error"
    if record["validated"]["insufficient_context"]:
        return "correctly_refused"
    if not record["grounding"]["grounded"]:
        return "hallucinated"
    return "answered_but_grounded"


def evaluate_question(q: dict, store) -> dict:
    record = answer_question(q["question"], store, save=False)
    outcome = classify(record)
    result = {
        "id": q["id"],
        "tier": q["tier"],
        "question": q["question"],
        "rationale": q["rationale"],
        "status": record["status"],
        "outcome": outcome,
    }
    if record["status"] == "ok":
        result["insufficient_context"] = record["validated"]["insufficient_context"]
        result["confidence"] = record["validated"]["confidence"]
        result["grounded"] = record["grounding"]["grounded"]
        result["answer"] = record["validated"]["answer"]
        result["self_check"] = record["self_check"]
    else:
        result["error"] = record["error"]
    return result


def summarize_tier(results: list[dict]) -> dict:
    n = len(results)
    outcomes = {}
    for r in results:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    self_check_overrides = sum(
        1 for r in results if r.get("self_check", {}).get("overridden")
    )
    return {
        "num_questions": n,
        "refusal_rate": round(outcomes.get("correctly_refused", 0) / n, 3) if n else 0.0,
        "hallucination_rate": round(outcomes.get("hallucinated", 0) / n, 3) if n else 0.0,
        "answered_but_grounded_rate": round(
            outcomes.get("answered_but_grounded", 0) / n, 3
        )
        if n
        else 0.0,
        "schema_error_rate": round(outcomes.get("schema_error", 0) / n, 3) if n else 0.0,
        "self_check_override_rate": round(self_check_overrides / n, 3) if n else 0.0,
        "outcome_counts": outcomes,
    }


def main() -> None:
    dataset = load_adversarial_dataset()
    questions = dataset["questions"]
    print(f"Loaded {len(questions)} adversarial questions across {len(dataset['tiers'])} tiers")

    pdf_path = Path(__file__).parent / "data" / "nke-10k-2023.pdf"
    chunks = get_chunks(load_pdf_pages(str(pdf_path)))
    embeddings = get_qwen_embed()
    store = build_vector_store(embeddings, chunks)
    print("Indexed. Running hallucination eval against the real pipeline...")

    results = []
    for q in questions:
        print(f"  [tier {q['tier']}] {q['id']}: {q['question']}")
        result = evaluate_question(q, store)
        results.append(result)
        print(f"    -> {result['outcome']}")

    by_tier: dict[str, list[dict]] = {}
    for r in results:
        by_tier.setdefault(str(r["tier"]), []).append(r)

    tier_summaries = {
        tier: {"description": dataset["tiers"][tier], **summarize_tier(rs)}
        for tier, rs in sorted(by_tier.items())
    }
    overall = summarize_tier(results)

    print("\n===== SUMMARY BY TIER =====")
    print(json.dumps(tier_summaries, indent=2))
    print("\n===== OVERALL =====")
    print(json.dumps(overall, indent=2))

    report = {
        "model": "qwen2.5:1.5b",
        "overall": overall,
        "by_tier": tier_summaries,
        "per_question": results,
    }
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "hallucination_eval.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Full report written to {out_path}")


if __name__ == "__main__":
    main()
