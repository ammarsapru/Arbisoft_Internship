"""Unit tests for the retrieval quality metrics with hand-computed values."""

import math

import pytest

from retrieval_eval import (
    dcg_at_k,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RETRIEVED = [7, 30, 30, 12, 35]  # pages of top-5 chunks, duplicates possible


def test_hit_at_k():
    assert hit_at_k(RETRIEVED, [30, 35], k=1) == 0.0  # first hit at rank 2
    assert hit_at_k(RETRIEVED, [30, 35], k=2) == 1.0
    assert hit_at_k(RETRIEVED, [99], k=5) == 0.0


def test_recall_at_k():
    assert recall_at_k(RETRIEVED, [30, 35], k=3) == 0.5   # only 30 found
    assert recall_at_k(RETRIEVED, [30, 35], k=5) == 1.0   # both found
    assert recall_at_k(RETRIEVED, [99, 100], k=5) == 0.0


def test_recall_counts_unique_pages_not_chunks():
    # page 30 retrieved twice must not double-count
    assert recall_at_k([30, 30], [30, 35], k=2) == 0.5


def test_reciprocal_rank():
    assert reciprocal_rank(RETRIEVED, [30], k=5) == 0.5        # rank 2
    assert reciprocal_rank(RETRIEVED, [7], k=5) == 1.0         # rank 1
    assert reciprocal_rank(RETRIEVED, [35], k=5) == pytest.approx(0.2)  # rank 5
    assert reciprocal_rank(RETRIEVED, [35], k=3) == 0.0        # outside top-3
    assert reciprocal_rank(RETRIEVED, [99], k=5) == 0.0


def test_recall_rejects_empty_ground_truth():
    with pytest.raises(ValueError):
        recall_at_k(RETRIEVED, [], k=5)


def test_precision_at_k():
    # top-1 = [7]: 0 relevant / 1
    assert precision_at_k(RETRIEVED, [30, 35], k=1) == 0.0
    # top-3 = [7, 30, 30]: 2 relevant / 3
    assert precision_at_k(RETRIEVED, [30, 35], k=3) == pytest.approx(2 / 3)
    # top-5 = [7, 30, 30, 12, 35]: 3 relevant / 5 (duplicates each count)
    assert precision_at_k(RETRIEVED, [30, 35], k=5) == pytest.approx(0.6)
    assert precision_at_k(RETRIEVED, [99], k=5) == 0.0


def test_precision_counts_duplicate_chunks_unlike_recall():
    # page 30 retrieved twice DOES double-count for precision, unlike recall
    assert precision_at_k([30, 30], [30, 35], k=2) == 1.0


def test_dcg_at_k():
    # rank1=7(rel0), rank2=30(rel1)/log2(3), rank3=30(rel1)/log2(4)
    expected = 1.0 / math.log2(3) + 1.0 / math.log2(4)
    assert dcg_at_k(RETRIEVED, [30, 35], k=3) == pytest.approx(expected)
    assert dcg_at_k(RETRIEVED, [99], k=5) == 0.0


def test_ndcg_at_k():
    # dcg@5: rank2 (30) + rank3 (30) + rank5 (35), all binary relevance 1
    dcg = 1.0 / math.log2(3) + 1.0 / math.log2(4) + 1.0 / math.log2(6)
    # ideal: 2 expected pages placed at rank 1 and 2
    idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
    assert ndcg_at_k(RETRIEVED, [30, 35], k=5) == pytest.approx(dcg / idcg)
    # a perfect ranking scores 1.0
    assert ndcg_at_k([30, 35], [30, 35], k=2) == pytest.approx(1.0)
    # no relevant results anywhere -> 0.0
    assert ndcg_at_k(RETRIEVED, [99], k=5) == 0.0


def test_ndcg_rejects_empty_ground_truth():
    with pytest.raises(ValueError):
        ndcg_at_k(RETRIEVED, [], k=5)
