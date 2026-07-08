"""Unit tests for generation-quality metric helpers (pure functions, no LLM/embeddings)."""

import pytest

from generation_metrics import cosine_similarity, keyword_coverage


def test_keyword_coverage_all_found():
    answer = "Revenues were $51.2 billion, up 10% on a reported basis and 16% currency-neutral."
    assert keyword_coverage(answer, ["51.2 billion", "10%", "16%"]) == 1.0


def test_keyword_coverage_partial():
    answer = "Revenues were $51.2 billion."
    assert keyword_coverage(answer, ["51.2 billion", "10%", "16%"]) == pytest.approx(1 / 3)


def test_keyword_coverage_none_found():
    answer = "The context does not contain this information."
    assert keyword_coverage(answer, ["51.2 billion", "10%"]) == 0.0


def test_keyword_coverage_empty_keyword_list():
    assert keyword_coverage("anything", []) == 1.0


def test_keyword_coverage_is_case_and_whitespace_insensitive():
    answer = "revenues were   51.2 BILLION dollars"
    assert keyword_coverage(answer, ["51.2 billion"]) == 1.0


def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector_is_zero_not_nan():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_similarity_scale_invariant():
    # Same direction, different magnitude -> still similarity 1.0
    assert cosine_similarity([2.0, 0.0], [10.0, 0.0]) == pytest.approx(1.0)
