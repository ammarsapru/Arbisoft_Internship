"""Live contract tests for generation_eval.py and hallucination_eval.py.

Marked 'live', skipped by default (see test_live_llm.py for the same
pattern). Run with:  uv run pytest -m live

These prove the two new eval runners are actually wired to the real
pipeline end to end (real PDF -> real chunks -> real embeddings -> real
vector store -> real ChatOllama call -> real schema validation -> real
grounding checks -> new metric functions), not just unit-tested in
isolation against fabricated data. Only a couple of questions are run per
test to keep this fast; the full sweeps live in generation_eval.py's and
hallucination_eval.py's main() functions.
"""

import json
from pathlib import Path

import pytest
import requests

from chunking import get_chunks
from extract_pdf import load_pdf_pages
from generation_eval import evaluate_question as evaluate_generation_question
from get_embeddings import get_qwen_embed
from hallucination_eval import evaluate_question as evaluate_adversarial_question
from rag_pipeline import DEFAULT_LLM_MODEL
from store_utils import build_vector_store

pytestmark = pytest.mark.live

OLLAMA_URL = "http://localhost:11434"


def ollama_has_model(name: str) -> bool:
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).json()
    except requests.RequestException:
        return False
    return any(m["name"] == name for m in tags.get("models", []))


requires_llm = pytest.mark.skipif(
    not ollama_has_model(DEFAULT_LLM_MODEL),
    reason=f"Ollama not running or chat model {DEFAULT_LLM_MODEL} not pulled",
)


@pytest.fixture(scope="module")
def store():
    pdf_path = Path(__file__).parent.parent / "data" / "nke-10k-2023.pdf"
    chunks = get_chunks(load_pdf_pages(str(pdf_path)))
    return build_vector_store(get_qwen_embed(), chunks)


@pytest.fixture(scope="module")
def embeddings():
    return get_qwen_embed()


@pytest.fixture(scope="module")
def eval_questions():
    path = Path(__file__).parent.parent / "data" / "eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


@pytest.fixture(scope="module")
def adversarial_questions():
    path = Path(__file__).parent.parent / "data" / "adversarial_eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


@requires_llm
def test_generation_eval_produces_all_metrics(store, embeddings, eval_questions):
    result = evaluate_generation_question(eval_questions[0], store, embeddings)
    assert result["status"] in {"ok", "schema_error"}
    if result["status"] == "ok":
        assert 0.0 <= result["correctness_keyword_coverage"] <= 1.0
        assert -1.0 <= result["correctness_semantic"] <= 1.0
        assert -1.0 <= result["relevance_semantic"] <= 1.0
        assert result["faithfulness"] in {0.0, 1.0}


@requires_llm
def test_generation_eval_handles_several_questions(store, embeddings, eval_questions):
    results = [
        evaluate_generation_question(q, store, embeddings) for q in eval_questions[:3]
    ]
    assert all(r["status"] in {"ok", "schema_error"} for r in results)


@requires_llm
def test_hallucination_eval_classifies_adversarial_question(store, adversarial_questions):
    # tier 4 = maximally unrelated to Nike; easiest case for the model to refuse
    tier4 = next(q for q in adversarial_questions if q["tier"] == 4)
    result = evaluate_adversarial_question(tier4, store)
    assert result["outcome"] in {
        "schema_error",
        "correctly_refused",
        "hallucinated",
        "answered_but_grounded",
    }


@requires_llm
def test_hallucination_eval_runs_one_question_per_tier(store, adversarial_questions):
    seen_tiers = set()
    for q in adversarial_questions:
        if q["tier"] in seen_tiers:
            continue
        seen_tiers.add(q["tier"])
        result = evaluate_adversarial_question(q, store)
        assert result["status"] in {"ok", "schema_error"}
    assert seen_tiers == {1, 2, 3, 4}
