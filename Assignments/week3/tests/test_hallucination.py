"""Tests for the hallucination (groundedness) detectors.

Each test fabricates a specific kind of hallucination and asserts the
detector flags it — and that fully grounded answers pass clean.
"""

from langchain_core.documents import Document

from hallucination import (
    check_citation_pages,
    check_citations_required,
    check_numbers_grounded,
    check_quotes_grounded,
    grounding_report,
)
from schemas import RAGAnswer

RETRIEVED = [
    Document(
        page_content="In fiscal 2023, NIKE, Inc. achieved record Revenues of $51.2 billion, "
        "which increased 10% on a reported basis.",
        metadata={"page": 30},
    ),
    Document(
        page_content="Gross margin decreased 250 basis points to 43.5% for fiscal 2023.",
        metadata={"page": 33},
    ),
]


def make_answer(**overrides) -> RAGAnswer:
    payload = {
        "answer": "Revenues were $51.2 billion, up 10%.",
        "citations": [{"page": 30, "quote": "record Revenues of $51.2 billion"}],
        "confidence": 0.9,
        "insufficient_context": False,
    }
    payload.update(overrides)
    return RAGAnswer.model_validate(payload)


def test_grounded_answer_passes_all_checks():
    report = grounding_report(make_answer(), RETRIEVED)
    assert report["grounded"] is True
    assert report["num_issues"] == 0


def test_citing_a_page_the_model_never_saw_is_flagged():
    answer = make_answer(citations=[{"page": 99, "quote": "record Revenues"}])
    issues = check_citation_pages(answer, RETRIEVED)
    assert len(issues) == 1
    assert "99" in issues[0]


def test_fabricated_quote_is_flagged():
    answer = make_answer(
        citations=[{"page": 30, "quote": "revenues exploded to one trillion dollars"}]
    )
    issues = check_quotes_grounded(answer, RETRIEVED)
    assert len(issues) == 1


def test_quote_matching_survives_whitespace_and_case():
    answer = make_answer(
        citations=[{"page": 30, "quote": "Record   revenues of\n$51.2 Billion"}]
    )
    assert check_quotes_grounded(answer, RETRIEVED) == []


def test_invented_number_in_answer_is_flagged():
    answer = make_answer(answer="Revenues were $63.9 billion in fiscal 2023.")
    issues = check_numbers_grounded(answer, RETRIEVED)
    assert any("63.9" in issue for issue in issues)


def test_number_with_thousands_separator_matches():
    docs = [Document(page_content="approximately 83,700 employees", metadata={"page": 8})]
    answer = make_answer(
        answer="NIKE had about 83,700 employees.",
        citations=[{"page": 8, "quote": "approximately 83,700 employees"}],
    )
    assert check_numbers_grounded(answer, docs) == []


def test_report_aggregates_multiple_hallucinations():
    answer = make_answer(
        answer="Revenues were $99.9 billion.",
        citations=[{"page": 99, "quote": "made up quote"}],
    )
    report = grounding_report(answer, RETRIEVED)
    assert report["grounded"] is False
    assert report["num_issues"] >= 3  # bad page, bad quote, bad number


def test_answering_with_zero_citations_is_flagged():
    # the vacuous-pass hole: no citations, no numbers -> the other three
    # checks have nothing to check and silently pass. Confirmed live:
    # "What is the capital city of France?" got citations=[] and
    # grounded=True before this check existed.
    answer = make_answer(
        answer="The capital city of France is Paris.",
        citations=[],
        insufficient_context=False,
    )
    issues = check_citations_required(answer)
    assert len(issues) == 1
    report = grounding_report(answer, RETRIEVED)
    assert report["grounded"] is False


def test_empty_citations_allowed_when_refusing():
    answer = make_answer(
        answer="The context does not contain this information.",
        citations=[],
        confidence=0.1,
        insufficient_context=True,
    )
    assert check_citations_required(answer) == []
    report = grounding_report(answer, RETRIEVED)
    assert report["grounded"] is True


def test_grounded_answer_with_citations_is_not_flagged_by_citations_required():
    assert check_citations_required(make_answer()) == []
