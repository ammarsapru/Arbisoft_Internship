"""Hallucination (groundedness) checks for validated RAG answers.

A schema-valid answer can still be a hallucination: the JSON parses fine but
the content was invented. These checks compare the answer against the actual
retrieved context:

  check_citation_pages   - every cited page must be one of the pages that were
                           actually retrieved (the model cannot cite evidence
                           it never saw).
  check_quotes_grounded  - every citation quote must appear (after whitespace/
                           case normalization) in the retrieved text for that
                           page. Fabricated quotes are the classic RAG
                           hallucination.
  check_numbers_grounded - every number in the answer must appear somewhere in
                           the retrieved context. Invented figures are the most
                           damaging hallucination in financial Q&A.
  check_citations_required - if the answer claims sufficient context
                           (insufficient_context=False) it must cite at least
                           one source. Without this check, an answer with zero
                           citations and zero numbers passes the three checks
                           above VACUOUSLY -- they have nothing to check, so
                           they report no issues, and pure fabricated prose
                           (e.g. a recipe, a capital city) registers as
                           "grounded" even though no grounding was ever
                           verified. Confirmed in practice: adversarial
                           questions like "What is the capital city of
                           France?" got citations=[] and grounded=True before
                           this check existed.

grounding_report() bundles all checks into one dict that gets saved alongside
each answer.
"""

import re

from langchain_core.documents import Document

from schemas import RAGAnswer

_WS_RE = re.compile(r"\s+")
# numbers incl. $51.2, 2,859, 43.5%, 83,700
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace so quote matching survives PDF spacing."""
    return _WS_RE.sub(" ", text.lower()).strip()


def normalize_number(token: str) -> str:
    """Strip thousands separators so '51,200' matches '51200'."""
    return token.replace(",", "")


def check_citation_pages(answer: RAGAnswer, retrieved: list[Document]) -> list[str]:
    retrieved_pages = {doc.metadata["page"] for doc in retrieved}
    return [
        f"cited page {c.page} was not among retrieved pages {sorted(retrieved_pages)}"
        for c in answer.citations
        if c.page not in retrieved_pages
    ]


def check_quotes_grounded(answer: RAGAnswer, retrieved: list[Document]) -> list[str]:
    issues = []
    for c in answer.citations:
        page_text = normalize(
            " ".join(
                doc.page_content for doc in retrieved if doc.metadata["page"] == c.page
            )
        )
        if normalize(c.quote) not in page_text:
            issues.append(
                f"quote not found in retrieved text of page {c.page}: {c.quote[:80]!r}"
            )
    return issues


def check_numbers_grounded(answer: RAGAnswer, retrieved: list[Document]) -> list[str]:
    context_numbers = {
        normalize_number(tok)
        for doc in retrieved
        for tok in _NUMBER_RE.findall(doc.page_content)
    }
    issues = []
    for token in _NUMBER_RE.findall(answer.answer):
        if normalize_number(token) not in context_numbers:
            issues.append(f"number {token!r} in answer does not appear in retrieved context")
    return issues


def check_citations_required(answer: RAGAnswer) -> list[str]:
    if not answer.insufficient_context and not answer.citations:
        return ["answer claims sufficient context but provides zero citations"]
    return []


def grounding_report(answer: RAGAnswer, retrieved: list[Document]) -> dict:
    checks = {
        "citation_pages": check_citation_pages(answer, retrieved),
        "quotes_grounded": check_quotes_grounded(answer, retrieved),
        "numbers_grounded": check_numbers_grounded(answer, retrieved),
        "citations_required": check_citations_required(answer),
    }
    all_issues = [issue for issues in checks.values() for issue in issues]
    return {
        "grounded": not all_issues,
        "num_issues": len(all_issues),
        "checks": checks,
    }
