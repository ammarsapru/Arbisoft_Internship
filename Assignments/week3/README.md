# LangChain RAG — Embedding Comparison, Structured Output & Hallucination Testing

A RAG pipeline over NIKE's fiscal 2023 10-K filing (`data/nke-10k-2023.pdf`, 107 pages)
that treats LLM output as an untrusted input: retrieval quality is **measured**
against ground truth, LLM answers are **schema-validated**, hallucinations are
**detected and recorded** rather than assumed away, and a bounded self-check
loop gives the model one chance to correct an unverifiable answer before a
deterministic refusal is used as the last resort.

Everything runs locally on [Ollama](https://ollama.com) — no cloud LLM API needed.

## Project layout

```
data/     source PDF + eval datasets (eval_dataset.json, adversarial_eval_dataset.json)
docs/     workflow.txt, constraints.txt, tracker.txt, langchain/pydantic explainers
results/  eval run outputs (gitignored) -- retrieval_eval.json, generation_eval.json,
          hallucination_eval.json, answers/answer-*.json
tests/    hermetic unit tests + live LLM contract tests
*.py      pipeline modules (flat, at project root -- see below)
```

## Architecture

```
data/nke-10k-2023.pdf
      |
extract_pdf.py        pypdf -> one Document per page (page number kept as metadata)
      |
chunking.py            RecursiveCharacterTextSplitter (1000 chars, 200 overlap) -> 516 chunks
      |
store_utils.py         batched + retrying embedding into InMemoryVectorStore
      |
      +--> retrieval_eval.py      compare embedding models on ground truth (data/eval_dataset.json)
      |
      +--> rag_pipeline.py        retrieve -> LLM (system+user prompt) -> JSON -> validate (schemas.py)
      |                                   -> self-check loop (retry-with-feedback, then deterministic refusal)
      |                                   -> hallucination checks (hallucination.py)
      |                                   -> save record to results/answers/
      |
      +--> generation_eval.py     faithfulness + correctness + relevance over data/eval_dataset.json
      |
      +--> hallucination_eval.py  refusal/hallucination rate over data/adversarial_eval_dataset.json
                                   (12 questions, 4 tiers of increasing topic distance from the 10-K)
```

| File | Role |
|---|---|
| `main.py` | Demo: build both embedding stores, run one query against each |
| `extract_pdf.py` | pypdf -> `Document` per page |
| `chunking.py` | `RecursiveCharacterTextSplitter` wrapper |
| `get_embeddings.py` | `OllamaEmbeddings` factories (qwen3-embedding, snowflake-arctic-embed) |
| `store_utils.py` | Batched embedding into `InMemoryVectorStore`, with retry (survives Ollama runner crashes) |
| `schemas.py` | Pydantic contract for LLM output (`RAGAnswer`) + strict `parse_llm_output()` gate |
| `rag_pipeline.py` | System+user prompt, structured-output generation, bounded self-check retry loop, save |
| `hallucination.py` | Groundedness checks on validated answers (citation pages, quotes, numbers, citations-required) |
| `generation_metrics.py` | `keyword_coverage`, `cosine_similarity` — pure helpers for generation_eval.py |
| `retrieval_eval.py` | hit_rate/precision/recall/MRR/NDCG @ k comparison of embedding models |
| `generation_eval.py` | faithfulness/correctness/relevance over real chat-model answers |
| `hallucination_eval.py` | refusal/hallucination rate over the adversarial (out-of-scope) question set |
| `data/eval_dataset.json` | 14 in-scope questions with hand-verified ground-truth pages + reference answers |
| `data/adversarial_eval_dataset.json` | 12 out-of-scope questions across 4 graduated topic-distance tiers |
| `tests/` | Hermetic unit test suite + live LLM contract tests |
| `docs/workflow.txt` | Full end-to-end pipeline walkthrough, stage by stage |
| `docs/constraints.txt` | Every constraint the pipeline enforces (hard gate vs. soft request vs. detector) |
| `docs/tracker.txt` | Full history of real eval runs, before/after every change made in this project |

## Setup

```powershell
# models
ollama pull qwen3-embedding:0.6b
ollama pull snowflake-arctic-embed:latest
ollama pull qwen2.5:1.5b          # chat model for the RAG pipeline (~1 GB)

# python deps
uv sync
```

The chat model is configurable: `RAG_LLM_MODEL=llama3.2:1b` (any Ollama chat
model) — set it in `.env` or the environment.

## 1. Measuring retrieval quality

**You cannot compare embedding models without ground truth.** `data/eval_dataset.json`
holds 14 questions about the 10-K; for each, the pages that actually contain
the answer were located by searching the extracted PDF text and verified by
hand (e.g. "revenues of $51.2 billion" appears on pages 30 and 35; "83,700
employees" on page 8). Pages are 0-indexed, matching the `page` metadata that
`extract_pdf.py` attaches to every chunk.

A retrieved chunk counts as *relevant* if its source page is in the question's
`expected_pages`. Five metrics, each at k = 1, 3, 5, 10 (binary relevance —
no graded relevance labels exist in this dataset, so NDCG uses the "ideal
ranking is all expected pages up front" normalization):

- **hit_rate@k** — share of questions with at least one relevant chunk in the
  top k. If the evidence isn't in the context window, the LLM can only hallucinate.
- **precision@k** — share of the top-k retrieved chunks that are relevant.
  Duplicate chunks from the same relevant page each count (unlike recall).
- **recall@k** — share of a question's expected pages covered by the top k
  (unique pages, so retrieving the same page twice doesn't double-count).
- **mrr@k** — mean reciprocal rank of the first relevant chunk.
- **ndcg@k** — rewards relevant chunks appearing earlier in the ranking.

Run the comparison (indexes the corpus once per model, then runs all
questions):

```powershell
uv run python retrieval_eval.py
```

Prints a side-by-side table and writes the full per-question report to
`results/retrieval_eval.json`.

**Latest real result:** `qwen3-embedding:0.6b` wins at every k on every metric
(e.g. hit_rate@5=0.857 / ndcg@5=0.806 vs. `snowflake-arctic-embed:latest`'s
0.714 / 0.488), despite being ~2x slower to index. It's the default embedding
model for the generation/hallucination pipeline (`get_qwen_embed()`).

## 2. Structured output pipeline: system prompt -> LLM -> JSON -> validate -> self-check -> save

The LLM must answer with exactly this JSON (defined in `schemas.py`):

```json
{
  "answer": "Revenues were $51.2 billion, up 10% ...",
  "citations": [{"page": 30, "quote": "record Revenues of $51.2 billion"}],
  "confidence": 0.9,
  "insufficient_context": false
}
```

**Prompt structure.** `rag_pipeline.py` sends two distinct messages, not one
concatenated string: a `SystemMessage` (persona, capabilities, hard
behavioral constraints, output contract — identical every call) and a
`HumanMessage` with clearly separated `### RETRIEVED CONTEXT` (each chunk
labeled with its page *and* cosine similarity score) and `### USER QUESTION`
sections. The system prompt explicitly names two refusal situations with
worked examples: the retrieved context lacks substance relevant to the
question, and the question is outside the system's domain entirely. See
`docs/constraints.txt` section 1 for the full text.

**Schema validation.** `parse_llm_output()` is the hard validation gate, and
it is deliberately hostile:

- **strict types** (`strict=True`): `"30"` is not a page number and `"no"` is
  not a boolean.
- **no extra fields** (`extra="forbid"`): a model that invents a `sources`
  field is hallucinating structure.
- **range checks**: `confidence` must be 0-1, pages non-negative, answer and
  quotes non-empty.
- The only tolerated deviation is a wrapping ```` ```json ```` fence, which is
  transport noise, not schema violation.

Anything else raises `SchemaValidationError` (which keeps the raw output for
debugging); the record gets `"status": "schema_error"` instead of being
dropped.

By default generation uses Ollama's **constrained decoding** (`format=` the
JSON schema), which makes the model structurally unable to emit invalid JSON.
`constrained=False` turns that off, to measure raw schema-break rates.

**Self-check retry loop.** A schema-valid answer that claims sufficient
context still isn't automatically trusted. `verify_answer()` — a second,
independent LLM call — checks whether the answer is actually responsive to
the specific question (not a different, real, but off-topic fact) and
genuinely supported by its citations (an answer with zero citations always
fails this). On rejection, the model gets **one retry** with the specific
rejection reason fed back (`MAX_ATTEMPTS = 2`); only if that retry also fails
does the pipeline fall back to a deterministic, code-built refusal — never a
model-generated one, so it can't fail the same way twice. An earlier,
simpler design that discarded zero-citation answers unconditionally (no
retry) was measured and rejected: it discarded 100% of otherwise-correct
in-scope answers, because this model frequently omits citations regardless
of whether its content is right. See `docs/tracker.txt` section 4 for the
full evidence trail.

Every answer is saved to `results/answers/answer-<timestamp>.json` with the
question, retrieved pages, every generation attempt (raw text + self-check
verdict), validated fields, timing, and the grounding report.

```powershell
uv run python rag_pipeline.py     # answers the first 3 eval questions end-to-end
```

## 3. Hallucination testing

Schema-valid is not the same as true. A validated answer can still cite pages
the model never saw, "quote" text that doesn't exist, invent numbers, or
claim a substantive answer while citing nothing at all. `hallucination.py`
checks every validated answer against the *actual retrieved context*:

| Check | Catches |
|---|---|
| `check_citation_pages` | citing a page that was not among the retrieved chunks |
| `check_quotes_grounded` | citation quotes that don't appear (whitespace/case-normalized) in the retrieved text of the cited page |
| `check_numbers_grounded` | any number in the answer that appears nowhere in the retrieved context |
| `check_citations_required` | claiming sufficient context (`insufficient_context=false`) while providing zero citations — closes a real vacuous-pass hole: with no citations and no numbers, the three checks above have nothing to inspect and silently pass, which let a pure-fabrication answer (e.g. "The capital city of France is Paris.") register as `grounded: true` before this check existed |

`grounding_report()` bundles the results (`grounded: true/false` + itemized
issues) and is saved with every answer.

**Adversarial / graduated-distance testing.** `data/adversarial_eval_dataset.json`
holds 12 questions across 4 tiers of increasing topic distance from the Nike
10-K (tier 1: same company/filing, fact just absent from the document —
tier 4: totally unrelated, e.g. "What is the capital city of France?").
Retrieval always returns the k nearest Nike chunks regardless of the query,
so a good pipeline must judge *relevance*, not just *presence* of retrieved
text. `hallucination_eval.py` runs the real pipeline against this set and
classifies each answer as `correctly_refused`, `hallucinated`, or
`answered_but_grounded` (answered an out-of-domain question by pivoting to a
real, correctly-cited NIKE fact instead of refusing).

```powershell
uv run python generation_eval.py       # faithfulness/correctness/relevance, in-scope questions
uv run python hallucination_eval.py    # refusal/hallucination rate, adversarial questions
```

**Latest real results** (qwen2.5:1.5b, current pipeline):

- Generation eval: `mean_faithfulness=0.571`, `mean_correctness_keyword_coverage=0.583`,
  `mean_correctness_semantic=0.712`, `mean_relevance_semantic=0.775`,
  `self_check_override_rate=0.071` (14/14 schema-valid).
- Hallucination eval: **`refusal_rate=1.0`, `hallucination_rate=0.0`,
  `answered_but_grounded_rate=0.0`** across all 12 adversarial questions and
  all 4 tiers.

This is the result of two additive fixes measured independently — splitting
the prompt into system+user took refusal_rate from 0% to 50% and
hallucination_rate from 58% to 8%; adding the citations-required check plus
the retry-with-feedback self-check loop closed the rest of the gap to 100%
refusal / 0% hallucination. Full before/after numbers for every change are
in `docs/tracker.txt`.

Known limits (documented on purpose): the regex-based checks are lexical, so
a paraphrased falsehood that reuses in-context numbers can still pass, and a
correct answer phrased with a derived number (e.g. "$2.9 billion" for
"$2,859 million") can be flagged as a false positive. `verify_answer()`'s
LLM-based judgment catches some of what the regex checks miss (e.g.
cross-entity misattribution), but the two don't always agree — see
`docs/tracker.txt` section 2 for a concrete divergence.

## 4. Tests

```powershell
uv run pytest              # hermetic suite (fast, no LLM needed) — 53 tests
uv run pytest -m live      # live LLM contract tests (needs Ollama + chat model) — 7 tests
```

- `tests/test_schemas.py` — ~18 parametrized broken payloads (prose instead
  of JSON, truncated JSON, missing/extra fields, wrong types, out-of-range
  confidence, string booleans, ...) must every one raise
  `SchemaValidationError`; valid payloads must pass.
- `tests/test_metrics.py` — hand-computed hit/precision/recall/MRR/NDCG
  cases, including the duplicate-page trap.
- `tests/test_generation_metrics.py` — hand-computed `keyword_coverage` /
  `cosine_similarity` cases.
- `tests/test_hallucination.py` — each detector (including
  `check_citations_required`) must flag its fabricated hallucination and
  stay silent on a fully grounded answer.
- `tests/test_live_llm.py` (marker: `live`) — calls the real model: with
  constrained decoding every response must validate; unconstrained responses
  must be classified `ok` or `schema_error`, never crash the pipeline.
- `tests/test_live_eval.py` (marker: `live`) — wires `generation_eval.py` and
  `hallucination_eval.py` to the real pipeline; asserts metrics land in
  valid ranges and every adversarial tier produces a valid classification.

Both suites are green as of the latest run.

## Known constraints

- `InMemoryVectorStore` means every run re-embeds the corpus (~516 chunks per
  model). Fine for evaluation; persist to a real vector DB for serving.
- Ollama occasionally crashes its model runner when hot-swapping models;
  `store_utils.build_vector_store` batches and retries to survive it.
- The self-check retry loop is bounded to one retry (`MAX_ATTEMPTS = 2`), not
  open-ended — a model that still can't produce a verifiable answer after one
  retry gets a deterministic refusal rather than more attempts.
- The relevance judgment for retrieval eval is page-level; a chunk from the
  right page that happens to miss the exact sentence still counts as a hit.
- See `docs/constraints.txt` for the complete, current list of what is and
  isn't enforced, and `docs/workflow.txt` for the full pipeline walkthrough.
