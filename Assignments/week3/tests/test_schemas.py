"""Schema validation tests.

These are the tests that MUST fail (i.e. parse_llm_output must raise) whenever
an LLM breaks the output contract. Each broken payload below is a failure mode
actually observed with small local models: prose instead of JSON, truncated
JSON, missing fields, wrong types, out-of-range values, invented extra fields.
"""

import json

import pytest

from schemas import RAGAnswer, SchemaValidationError, parse_llm_output

VALID = {
    "answer": "Revenues were $51.2 billion, up 10 percent.",
    "citations": [{"page": 30, "quote": "record Revenues of $51.2 billion"}],
    "confidence": 0.9,
    "insufficient_context": False,
}


# ------------------------------------------------------------ happy paths

def test_valid_payload_parses():
    answer = parse_llm_output(json.dumps(VALID))
    assert isinstance(answer, RAGAnswer)
    assert answer.confidence == 0.9
    assert answer.citations[0].page == 30


def test_markdown_fenced_json_is_tolerated():
    raw = "```json\n" + json.dumps(VALID) + "\n```"
    assert parse_llm_output(raw).answer == VALID["answer"]


def test_empty_citations_allowed_for_insufficient_context():
    payload = {
        "answer": "The context does not contain this information.",
        "citations": [],
        "confidence": 0.1,
        "insufficient_context": True,
    }
    assert parse_llm_output(json.dumps(payload)).insufficient_context is True


# ------------------------------------------------------------ broken outputs
# Every case here is an LLM "breaking the schema" and must raise.

def broken(**overrides):
    payload = {**VALID, **overrides}
    for key, value in list(payload.items()):
        if value is ...:
            del payload[key]
    return json.dumps(payload)


BROKEN_CASES = {
    "prose_not_json": "Sure! Nike's revenues were $51.2 billion in fiscal 2023.",
    "truncated_json": json.dumps(VALID)[:-25],
    "json_array_not_object": json.dumps([VALID]),
    "empty_string": "",
    "missing_answer": broken(answer=...),
    "missing_citations": broken(citations=...),
    "missing_confidence": broken(confidence=...),
    "empty_answer": broken(answer=""),
    "confidence_above_1": broken(confidence=1.5),
    "confidence_negative": broken(confidence=-0.1),
    "confidence_as_word": broken(confidence="high"),
    "citation_page_as_string": broken(citations=[{"page": "thirty", "quote": "x"}]),
    "citation_negative_page": broken(citations=[{"page": -4, "quote": "x"}]),
    "citation_empty_quote": broken(citations=[{"page": 30, "quote": ""}]),
    "citation_missing_quote": broken(citations=[{"page": 30}]),
    "citations_not_a_list": broken(citations="page 30"),
    "hallucinated_extra_field": broken(sources=["wikipedia"]),
    "citation_extra_field": broken(citations=[{"page": 30, "quote": "x", "url": "http://a"}]),
    "insufficient_context_as_string": broken(insufficient_context="no"),
}


@pytest.mark.parametrize("case", BROKEN_CASES, ids=BROKEN_CASES.keys())
def test_broken_llm_output_is_rejected(case):
    with pytest.raises(SchemaValidationError):
        parse_llm_output(BROKEN_CASES[case])


def test_error_keeps_raw_output_for_debugging():
    raw = "not json at all"
    with pytest.raises(SchemaValidationError) as excinfo:
        parse_llm_output(raw)
    assert excinfo.value.raw_output == raw
