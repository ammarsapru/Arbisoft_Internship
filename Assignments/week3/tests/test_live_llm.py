"""Live LLM contract tests (marked 'live', skipped by default).

Run with:  uv run pytest -m live

These call the real local model several times and assert that every response
survives schema validation and gets a grounding report. If the model starts
breaking the JSON contract, these tests fail — that is their job. They skip
automatically when Ollama is not running or the chat model is not pulled.
"""

import json
from pathlib import Path

import pytest
import requests

from chunking import get_chunks
from extract_pdf import load_pdf_pages
from get_embeddings import get_qwen_embed
from rag_pipeline import DEFAULT_LLM_MODEL, answer_question
from store_utils import build_vector_store

pytestmark = pytest.mark.live

OLLAMA_URL = "http://localhost:11434"
NUM_RUNS = 3


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
def eval_questions():
    path = Path(__file__).parent.parent / "data" / "eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


@requires_llm
def test_constrained_output_always_validates(store, eval_questions):
    """With constrained decoding, every run must produce schema-valid JSON."""
    failures = []
    for q in eval_questions[:NUM_RUNS]:
        record = answer_question(q["question"], store, save=False, constrained=True)
        if record["status"] != "ok":
            failures.append({"question": q["question"], "error": record["error"]})
    assert not failures, f"LLM broke the schema: {failures}"


@requires_llm
def test_every_valid_answer_gets_grounding_report(store, eval_questions):
    record = answer_question(eval_questions[0]["question"], store, save=False)
    assert record["status"] == "ok"
    assert "grounding" in record
    assert set(record["grounding"]["checks"]) == {
        "citation_pages",
        "quotes_grounded",
        "numbers_grounded",
        "citations_required",
    }
    assert record["self_check"]["ran"] in {True, False}
    if record["self_check"]["ran"]:
        assert record["self_check"]["verdict"] in {"VERIFIED", "REJECT"} or record[
            "self_check"
        ]["verdict"].startswith("ambiguous:")


@requires_llm
def test_unconstrained_output_is_still_validated(store, eval_questions):
    """Without constrained decoding the model may or may not break the schema;
    either way the pipeline must classify the outcome instead of crashing."""
    record = answer_question(
        eval_questions[0]["question"], store, save=False, constrained=False
    )
    assert record["status"] in {"ok", "schema_error"}
    assert record["raw_output"]
