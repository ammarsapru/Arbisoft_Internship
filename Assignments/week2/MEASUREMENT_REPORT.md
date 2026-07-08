# Measurement Report — OpenRouter Model Comparison

This document explains what `compare.py` measures, what it tests, and how — separate
from `metrics_report.md`, which is the auto-generated *output* of a specific run.
Read this to understand the methodology; read `metrics_report.md` for actual numbers.

## 1. What is being tested

Three free-tier OpenRouter models are evaluated against the same 50 prompts:

| Model | Model ID |
|---|---|
| GPT-OSS 120B | `openai/gpt-oss-120b:free` |
| Gemma 4 31B-IT | `google/gemma-4-31b-it:free` |
| Nemotron Nano 9B | `nvidia/nemotron-nano-9b-v2:free` |

The 50 prompts are split into 5 categories of 10 prompts each, each targeting a
distinct cognitive capability so results in one category can't be conflated with
another:

| Category | What it tests | Modeled on |
|---|---|---|
| Mathematical Reasoning | Multi-step arithmetic, algebra, geometry, combinatorics | GSM8K, MATH benchmark |
| Logical & Deductive Reasoning | Syllogisms, conditionals, puzzles, sequence patterns, set logic | BIG-Bench, LogiQA, Winogrande |
| Code Generation & Algorithmic Problem Solving | Algorithm implementation, correctness, edge-case handling | HumanEval, MBPP, LeetCode-style |
| Factual & Technical Knowledge | Precision/conciseness of CS fundamentals recall | MMLU (CS track), TriviaQA |
| Instruction Following & Constraint Adherence | Exact format compliance, constraint counting, label adherence | IFEval (Google), FollowBench |

Prompts are written to be culturally neutral (no region-specific names, currencies,
or foods) since GSM8K research shows accuracy on math word problems can shift by
double digits on non-US-flavoured variants of the same question — that's a
confound we don't want mixed into the results.

## 2. What is being measured

Every model call produces a `ModelResult` with:

| Field | What it captures | How |
|---|---|---|
| `elapsed_seconds` | Total wall-clock time for the call | `time.time()` before the request, after the stream closes |
| `ttft_seconds` | Time to first token | Timestamp at the first non-empty streamed chunk, minus the start time |
| `prompt_tokens` / `completion_tokens` / `total_tokens` | Token accounting | Read from the `usage` field OpenRouter attaches to the final streamed chunk (requires `"usage": {"include": true}` in the request) |
| `throughput` (derived) | Completion tokens per second **of generation only** | `completion_tokens / (elapsed_seconds - ttft_seconds)` — TTFT is subtracted out so network/queue latency before generation starts doesn't get counted as "slow generation" |
| `followed_constraint` | Did the response satisfy the category's rule? | See §3 — meaning differs by category |
| `error` | Failure reason, if any | Exception message (HTTP error, timeout, empty response, embedded API error) |

Responses are streamed (`stream=True`) specifically so TTFT can be captured — a
non-streaming call only tells you when the *entire* response arrived, with no
way to observe when generation actually started.

## 3. How correctness/compliance is checked

This is the part most benchmarking scripts skip: checking not just that a
response arrived, but whether it actually did what was asked. The rigor differs
by category, and that difference is deliberate — it reflects what can be
verified mechanically without introducing new sources of error.

### Real correctness checks (verified against ground truth or execution)

- **Mathematical Reasoning** — every prompt (except the train-meeting-time one,
  where the correct answer is a clock time and too format-ambiguous to string-match
  reliably) has a hand-computed expected numeric answer. The model's `ANSWER:` line
  is parsed for its first number and compared to the expected value within a 2%
  tolerance (to absorb legitimate rounding differences, e.g. $12,282 vs $12,283 on
  a depreciation problem). This checks the model got the *right number*, not just
  that it produced *a* number.
- **Code Generation** — the returned code (including its own `assert` statements)
  is **actually executed** in a subprocess with a 5-second timeout. A prompt only
  passes if the code runs and every assert holds. This replaced an earlier, weaker
  check that only confirmed two `assert` lines existed textually — a model could
  satisfy that while writing code that doesn't even parse.
  - Caveat: this executes model-generated code locally. There's a timeout but no
    further sandboxing (no network or filesystem restriction). This mirrors how
    HumanEval-style benchmarks work generally, but is worth knowing if you ever
    point this script at a less-trusted model.
- **Instruction Following** — each of the 10 prompts has a unique, hand-written
  constraint (exact word counts, required substrings, specific labels on separate
  lines, sentence-start words, table headers). Each gets its own dedicated checker
  function rather than a shared pattern, because IFEval-style prompts are
  one-off by construction. One prompt (bytes in a KiB) doubles as a correctness
  check since the constraint *is* the correct answer (`1024`, and nothing else).
  - Two of the ten are partially checked: haiku syllable counts and "must start
    with an action verb" aren't verifiable without a syllable-counting or
    part-of-speech library, so those two check label/structure presence only,
    not the full constraint.

### Shape-only checks (format verified, correctness is not)

- **Logical & Deductive Reasoning** and **Factual & Technical Knowledge** only
  check that a response has the right *shape* — an `ANSWER:` line exists for
  logical reasoning; exactly 2–3 sentences with no bullets for factual knowledge.
  Whether the conclusion or fact is actually *correct* is not verified.
- **This is a deliberate, stated limitation, not an oversight.** Grading these
  reliably requires either hand-curated reference answers per logic puzzle (real
  risk of the grader itself being wrong, which would silently mis-score every
  model against bad ground truth) or an LLM-as-judge pass (adds cost and its own
  bias). Both are legitimate follow-ups; neither was rushed into this version to
  avoid introducing unreliable ground truth.

## 4. Fairness controls (why the comparison is apples-to-apples)

| Control | Value | Why |
|---|---|---|
| `temperature` | `0` | Greedy decoding — removes sampling randomness as a confound, so differences in output are attributable to the model, not luck |
| `max_tokens` | `600` | Caps every model at the same ceiling so a naturally verbose model can't out-score a concise one on raw length |
| System prompt | Identical across all three models | Prompt-sensitivity research shows wording alone can shift benchmark scores by double-digit percentage points; an identical system prompt removes that as a variable |
| Output constraint | Baked into every prompt's text | Makes responses structurally comparable — every model is asked for the same shape of answer |
| Sequential calls | Models are queried one at a time per prompt (not in parallel) | Avoids triggering parallel rate-limit collisions on a single free-tier API key |

Caveat worth knowing: "temperature=0 → fully reproducible" is aspirational on
hosted inference, not guaranteed — batched GPU inference can still introduce
small run-to-run variation even at temperature 0. This is a known property of
hosted LLM APIs, not a bug in this script.

## 5. Handling OpenRouter's free-tier rate limits

Free-tier (`:free`) models share limited capacity across all OpenRouter users,
not just this script's own request rate — so 429s are expected, especially on
popular models. Three mechanisms handle this:

1. **Retry with backoff** — on a 429, the script waits (honoring the server's
   `Retry-After` header when present, otherwise `15s × attempt`) and retries up
   to `OPENROUTER_RETRIES` (default 2) times before giving up on that call.
2. **Circuit breaker** — if all 3 models fail on the *same* prompt, the run stops
   immediately rather than continuing to grind through prompts that are highly
   likely to fail the same way (rate limiting doesn't resolve prompt-to-prompt).
3. **Interrupt-safe** — a manual Ctrl+C is caught and treated the same as the
   circuit breaker: whatever was collected so far is still saved.

In both stop cases, `main()` still calls `save_results()` and
`save_metrics_report()` on the partial data — a cut-short run always produces a
usable (if smaller) JSON + report rather than nothing.

## 6. Prompt selection (`--limit` and `--category`)

- `--category <id>` restricts the run to one category's 10 prompts.
- `--limit N` (with no `--category`) distributes `N` **evenly across all 5
  categories** via round-robin, not a flat slice of the first `N` prompts. Since
  prompts are stored grouped by category, a flat slice would only ever sample
  from `math_reasoning` (and maybe `logical_reasoning`) for any `N < 40`,
  silently excluding the other three categories from a "representative" partial
  run. `--limit 20` now gives 4 prompts per category; `--limit 22` gives 5 from
  the first two categories and 4 from the rest (remainder distributed to the
  earliest categories).

## 7. Output artifacts

| File | Contents |
|---|---|
| `comparison_output.json` | Full raw data: every prompt, every model's response text, every timing/token/correctness field, per the `BenchmarkRun` Pydantic schema |
| `metrics_report.md` | Human-readable aggregates: per-model latency/TTFT/throughput/token averages, per-category latency and throughput breakdowns, per-category constraint/correctness compliance, and a table of every error encountered |
