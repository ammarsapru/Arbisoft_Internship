"""Generation-quality metrics: correctness and relevance.

Faithfulness is already covered by hallucination.grounding_report() (does the
answer's content trace back to the retrieved context?). These two metrics
answer a different question: is the answer actually good, judged against a
human-written reference?

  keyword_coverage    - correctness proxy. Fraction of a question's expected
                         "answer_keywords" (from eval_dataset.json) that show
                         up verbatim (after normalization) in the generated
                         answer. Cheap, deterministic, no embedding call.
  cosine_similarity    - generic vector similarity, used by generation_eval.py
                         for two purposes: semantic correctness (answer vs.
                         reference_answer) and semantic relevance (answer vs.
                         the question itself). Kept here as a pure function so
                         it's unit-testable without a live embedding call.
"""

import numpy as np

from hallucination import normalize


def keyword_coverage(answer_text: str, keywords: list[str]) -> float:
    """Fraction of keywords found (case/whitespace-insensitive) in answer_text.

    Returns 1.0 for an empty keyword list (nothing to miss).
    """
    if not keywords:
        return 1.0
    haystack = normalize(answer_text)
    found = sum(1 for kw in keywords if normalize(kw) in haystack)
    return found / len(keywords)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors, in [-1.0, 1.0]. 0.0 if either is zero-length."""
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)
