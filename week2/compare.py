#!/usr/bin/env python3
"""
OpenRouter model comparison and metrics report generator.

Runs the same benchmark prompts against three free-tier OpenRouter models,
records latency/token/error metrics, saves raw JSON, and writes a Markdown
metrics report.

Data structures are defined as Pydantic models so every API response is
validated at runtime and the JSON output schema is always consistent.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional

import requests
from pydantic import BaseModel, Field, field_validator

# ── Constants ─────────────────────────────────────────────────────────────────

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

if not API_KEY:
    raise SystemExit("Set OPENROUTER_API_KEY environment variable before running.")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

REQUEST_RETRIES = int(os.environ.get("OPENROUTER_RETRIES", "2"))
RETRY_BASE_SECONDS = float(os.environ.get("OPENROUTER_RETRY_BASE_SECONDS", "15"))
CALL_DELAY_SECONDS = float(os.environ.get("OPENROUTER_CALL_DELAY_SECONDS", "2"))


# ── Pydantic models ───────────────────────────────────────────────────────────
#
# Using Pydantic (industry standard) gives us:
#   - Runtime type validation on every API response (catches schema drift)
#   - .model_dump() / .model_dump_json() for consistent serialisation
#   - Self-documenting JSON schema via .model_json_schema()
#   - Computed properties (succeeded, throughput) co-located with the data


class ModelConfig(BaseModel):
    """One of the three models under evaluation."""
    id: str
    name: str


class FairnessConfig(BaseModel):
    """
    Parameters applied identically to every model call.

    Rationale (from HELM and LLM-as-Judge literature):
      max_tokens  — caps response length so verbosity cannot inflate perceived quality
      temperature — 0 = greedy decoding; deterministic and reproducible across runs
      system      — identical system prompt removes prompt-sensitivity variance
                    (MMLU scores shift ±10 % from prompt wording alone)
    """
    max_tokens: int = Field(600, gt=0)
    temperature: float = Field(0.0, ge=0.0, le=2.0)
    system: str


class EvalCategory(BaseModel):
    """
    One of the five evaluation categories, each targeting a distinct cognitive skill.
    Inspired by established academic benchmarks (GSM8K, HumanEval, MMLU, IFEval, BIG-Bench).
    """
    id: str
    name: str
    what_it_tests: str
    inspiration: str
    output_constraint: str
    prompts: List[str] = Field(..., min_length=10, max_length=10)

    @field_validator("prompts")
    @classmethod
    def exactly_ten_prompts(cls, v: List[str]) -> List[str]:
        if len(v) != 10:
            raise ValueError(f"Each category must have exactly 10 prompts, got {len(v)}")
        return v

    def to_benchmark_prompts(self) -> List["BenchmarkPrompt"]:
        """Attach the output_constraint to every prompt in this category."""
        return [
            BenchmarkPrompt(
                category=self.id,
                category_name=self.name,
                prompt=f"{p}\n\n{self.output_constraint}",
            )
            for p in self.prompts
        ]


class BenchmarkPrompt(BaseModel):
    """A single prompt ready to be sent to the API (base prompt + constraint appended)."""
    category: str
    category_name: str = ""
    prompt: str


class ModelResult(BaseModel):
    """The outcome of one model call — success or failure, with all timing data."""
    model: str
    model_id: str
    response: Optional[str] = None
    elapsed_seconds: float = Field(..., ge=0)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and bool(self.response)

    @property
    def throughput(self) -> Optional[float]:
        """Completion tokens per second — None when token count unavailable."""
        if self.completion_tokens and self.elapsed_seconds > 0:
            return self.completion_tokens / self.elapsed_seconds
        return None


class PromptComparison(BaseModel):
    """All three model results for a single prompt."""
    category: str
    category_name: str = ""
    prompt: str
    results: List[ModelResult]


class BenchmarkRun(BaseModel):
    """
    Complete output of one benchmark execution — suitable for JSON serialisation
    and for downstream analysis tools that can import this module.
    """
    generated_at: str
    fairness_config: FairnessConfig
    model_ids: List[str]
    categories: List[EvalCategory]
    comparisons: List[PromptComparison]

    def to_json(self, **kwargs) -> str:
        return self.model_dump_json(indent=2, **kwargs)


# ── Static configuration instances ────────────────────────────────────────────

FAIRNESS_CONFIG = FairnessConfig(
    max_tokens=600,
    temperature=0,
    system=(
        "You are a precise, helpful assistant. Follow all output format "
        "instructions exactly. Do not add preamble or filler."
    ),
)

MODELS: List[ModelConfig] = [
    ModelConfig(id="openai/gpt-oss-120b:free",       name="GPT-OSS 120B"),
    ModelConfig(id="google/gemma-4-31b-it:free",      name="Gemma 4 31B-IT"),
    ModelConfig(id="nvidia/nemotron-nano-9b-v2:free", name="Nemotron Nano 9B"),
]

# ── Evaluation suite ──────────────────────────────────────────────────────────
#
# Design principles (from HELM, IFEval, GSM8K research):
#   1. Each category tests a DISTINCT cognitive capability — no overlap.
#   2. Every prompt has an OUTPUT FORMAT CONSTRAINT so responses are structurally
#      comparable across models (removes format-driven scoring variance).
#   3. Prompts are culturally neutral — no region-specific names, currencies, foods.
#      (GSM8K research shows LLaMA 8B accuracy drops 19 pp on non-US variants.)
#   4. max_tokens=600 and temperature=0 (FAIRNESS_CONFIG) applied to all calls.
#   5. All models are queried sequentially per prompt to avoid parallel rate-limit
#      collisions on the same free-tier key.

EVAL_CATEGORIES: List[EvalCategory] = [
    EvalCategory(
        id="math_reasoning",
        name="Mathematical Reasoning",
        what_it_tests="Multi-step arithmetic, algebra, geometry, combinatorics",
        inspiration="GSM8K, MATH benchmark",
        output_constraint=(
            "Show step-by-step working. "
            "Put the final answer on its own line as: ANSWER: [numeric value] [unit if applicable]"
        ),
        prompts=[
            "Three people share $2,400 in ratio 3:5:4. How much does the largest share receive?",
            "A rectangle has perimeter 54 cm. Its length is twice its width. What is its area?",
            (
                "A shop buys a jacket for $80, marks it up 35%, "
                "then discounts the marked price by 20%. What is the final sale price?"
            ),
            (
                "Pipe A fills a tank in 6 hours. Pipe B drains it in 9 hours. "
                "Both open on an empty tank. How long to fill it completely?"
            ),
            (
                "A $20,000 car depreciates by 15% of current value each year. "
                "What is its value after 3 years, rounded to the nearest dollar?"
            ),
            "How many three-digit integers are divisible by both 4 and 6?",
            (
                "Mix 12% and 4% saline solutions to make 40 litres of 8% saline. "
                "How many litres of the 12% solution are used?"
            ),
            (
                "In a class of 30 students, 18 play football, 14 play cricket, "
                "and 6 play neither. How many play both?"
            ),
            (
                "A ladder makes a 60-degree angle with the ground and its foot is "
                "3 m from the wall. How long is the ladder?"
            ),
            (
                "Two trains start 300 km apart: one at 09:00 at 80 km/h, "
                "one at 09:30 at 100 km/h. At what time do they meet?"
            ),
        ],
    ),
    EvalCategory(
        id="logical_reasoning",
        name="Logical & Deductive Reasoning",
        what_it_tests="Syllogisms, conditionals, puzzles, sequence patterns, set logic",
        inspiration="BIG-Bench, LogiQA, Winogrande",
        output_constraint=(
            "Reason step by step. "
            "Put the conclusion on its own line as: ANSWER: [your conclusion]"
        ),
        prompts=[
            (
                "All mammals are warm-blooded. Dolphins are mammals. Warm-blooded animals have "
                "four-chambered hearts. Snakes are not warm-blooded. "
                "Can we conclude snakes do not have four-chambered hearts? Explain."
            ),
            (
                "On an island, Knights always tell truth and Knaves always lie. "
                "A says: 'We are both Knaves.' What are A and B?"
            ),
            "Find the next number and the rule: 2, 6, 12, 20, 30, 42, ?",
            (
                "If it is raining, Alex carries an umbrella. Alex is not carrying one. "
                "What follows? Name the logical form used."
            ),
            (
                "Solve the wolf, goat, cabbage river crossing: the boat holds the farmer and one "
                "item; the wolf eats the goat and the goat eats the cabbage if left alone."
            ),
            (
                "Tom is older than Sam. Sam is older than Jake. Jake is older than Priya. "
                "Is Tom necessarily oldest? Who is definitely youngest?"
            ),
            (
                "All squares are rectangles. Some rectangles are rhombuses. "
                "No rhombuses are circles. Which must be true? A) All squares are rhombuses. "
                "B) A square can be a rhombus. C) No squares are circles."
            ),
            (
                "Everyone who owns a cat owns a dog. Some dog owners are vegetarian. "
                "Mia owns a cat. Can we conclude Mia is vegetarian?"
            ),
            (
                "Three switches outside a room each control one of three bulbs inside. "
                "You may enter the room only once. How do you identify each switch?"
            ),
            (
                "Five cards — red, blue, green, yellow, white — are in a row. "
                "Green is immediately left of white; red is position 3; blue is left of red; "
                "yellow is not at either end. What is the order?"
            ),
        ],
    ),
    EvalCategory(
        id="code_generation",
        name="Code Generation & Algorithmic Problem Solving",
        what_it_tests="Algorithm implementation, correctness, edge-case handling, code clarity",
        inspiration="HumanEval, MBPP, LeetCode-style benchmarks",
        output_constraint=(
            "Provide Python 3 code only — no prose before or after the code block. "
            "Include a one-line docstring. "
            "End with exactly 2 assert statements that verify correct behaviour."
        ),
        prompts=[
            "Implement binary search on a sorted list of integers. Return the index or -1.",
            (
                "Write a function that checks whether a string is a palindrome, "
                "ignoring case and non-alphanumeric characters."
            ),
            "Implement merge sort on a list of integers and return the sorted list.",
            (
                "Return all unique value pairs from a list of integers that add up to a target sum."
            ),
            (
                "Detect whether a directed graph "
                "(given as an adjacency-list dict) contains a cycle."
            ),
            "Return the nth Fibonacci number using dynamic programming, not recursion.",
            "Determine whether brackets (), {}, [] in a string are balanced.",
            "Merge overlapping intervals given as [start, end] pairs; return sorted result.",
            "Convert an integer from 1 to 3999 to its Roman numeral representation.",
            (
                "Find the length of the longest consecutive integer sequence in an unsorted list. "
                "Example: [100, 4, 200, 1, 3, 2] -> 4 (sequence 1,2,3,4)."
            ),
        ],
    ),
    EvalCategory(
        id="factual_knowledge",
        name="Factual & Technical Knowledge",
        what_it_tests=(
            "Computer science fundamentals — tests precision and conciseness of recall, "
            "not essay-writing ability"
        ),
        inspiration="MMLU (CS track), TriviaQA",
        output_constraint=(
            "Answer in exactly 2 to 3 sentences. "
            "Do not use bullet points or numbered lists."
        ),
        prompts=[
            (
                "What are the four ACID properties of a database transaction, "
                "and why does each matter?"
            ),
            "What is the difference between a process and a thread in an operating system?",
            "State the CAP theorem. Can a distributed system satisfy all three properties at once?",
            (
                "What does Big-O notation measure? "
                "What are quicksort's average-case and worst-case time complexities?"
            ),
            (
                "What is the difference between symmetric and asymmetric encryption? "
                "Give one real-world example of each."
            ),
            "What is a foreign key in a relational database, and what constraint does it enforce?",
            "What is virtual memory in an operating system, and what problem does it solve?",
            "What is a deadlock in an operating system? Name one necessary condition for it.",
            (
                "What is the difference between compiled and interpreted programming languages? "
                "Give one example of each."
            ),
            (
                "What does the OSI model describe, how many layers does it have, "
                "and which layer is responsible for end-to-end communication between applications?"
            ),
        ],
    ),
    EvalCategory(
        id="instruction_following",
        name="Instruction Following & Constraint Adherence",
        what_it_tests=(
            "Precise format compliance, constraint counting, and label adherence "
            "— tests whether models follow multi-part rules without drifting"
        ),
        inspiration="IFEval (Google), FollowBench",
        output_constraint=(
            "Follow every constraint in the prompt exactly. "
            "Deviation from any stated rule counts as a failure."
        ),
        prompts=[
            (
                "List exactly 5 Python built-in functions. Number them 1 to 5. "
                "Each description must be exactly 8 words. "
                "Format: [number]. [function name]: [8-word description]"
            ),
            (
                "Explain what an API is. Constraints: "
                "(a) exactly 3 sentences, "
                "(b) must include the word 'interface', "
                "(c) must include the word 'contract'."
            ),
            (
                "Write a haiku about databases. Output only: "
                "TITLE: [title] LINE1: [5 syllables] LINE2: [7 syllables] LINE3: [5 syllables]"
            ),
            (
                "Compare SQL and NoSQL in exactly 2 sentences. "
                "Sentence 1 must begin with 'SQL'. Sentence 2 must begin with 'NoSQL'. "
                "Write nothing else."
            ),
            (
                "Explain recursion using a metaphor. Hard constraints: "
                "(1) no more than 35 words total, "
                "(2) the metaphor must include the word 'mirror'."
            ),
            (
                "Rewrite 'The server crashed' in three registers. "
                "Use exactly these labels on separate lines: FORMAL: / TECHNICAL: / CASUAL:"
            ),
            (
                "Answer with a single integer and nothing else: "
                "How many bytes are in one kibibyte (KiB)?"
            ),
            (
                "Give 3 tips for writing clean code. Each tip must start with an action verb. "
                "Format: TIP 1: [verb ...] TIP 2: [verb ...] TIP 3: [verb ...]"
            ),
            (
                "Translate this into plain English then Python pseudocode: "
                "'For each element in the collection, if the element satisfies the predicate, "
                "append it to the output sequence.' "
                "Use labels: PLAIN: [text] PSEUDOCODE: [code]"
            ),
            (
                "Name 4 sorting algorithms as a table. "
                "Exact headers: Algorithm | Average Time Complexity | Stable? "
                "No other text before or after the table."
            ),
        ],
    ),
]


# ── API helpers ───────────────────────────────────────────────────────────────


def retry_wait_seconds(response: requests.Response, attempt: int) -> float:
    """Respect the Retry-After header when present; fall back to exponential backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after).replace(tzinfo=None)
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                return max(0.0, (retry_at - now_utc).total_seconds())
            except Exception:
                pass
    return RETRY_BASE_SECONDS * (attempt + 1)


def call_model(model: ModelConfig, prompt: str) -> ModelResult:
    """
    Call one model on one prompt and return a validated ModelResult.

    Retries on HTTP 429 up to REQUEST_RETRIES times, honouring the
    Retry-After header so we don't hammer the free-tier rate limiter.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openrouter-compare",
        "X-Title": "OpenRouter Model Comparison",
    }
    payload = {
        "model": model.id,
        "messages": [
            {"role": "system", "content": FAIRNESS_CONFIG.system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": FAIRNESS_CONFIG.max_tokens,
        "temperature": FAIRNESS_CONFIG.temperature,
    }
    start = time.time()
    try:
        response = None
        for attempt in range(REQUEST_RETRIES + 1):
            response = requests.post(BASE_URL, headers=headers, json=payload, timeout=90)
            if response.status_code != 429 or attempt == REQUEST_RETRIES:
                break
            wait = retry_wait_seconds(response, attempt)
            print(f"  {model.name}: 429 rate limit; retrying in {wait:.1f}s")
            time.sleep(wait)

        elapsed = time.time() - start
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        message = (choices[0].get("message", {}) if choices else {})
        content = message.get("content")
        if not content:
            raise ValueError("Empty response content")
        usage = data.get("usage", {})
        return ModelResult(
            model=model.name,
            model_id=model.id,
            response=content,
            elapsed_seconds=round(elapsed, 3),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    except Exception as exc:
        return ModelResult(
            model=model.name,
            model_id=model.id,
            elapsed_seconds=round(time.time() - start, 3),
            error=str(exc),
        )


# ── Benchmark runner ──────────────────────────────────────────────────────────


def run_benchmark(prompts: List[BenchmarkPrompt]) -> List[PromptComparison]:
    """Run every prompt against every model sequentially and return typed results."""
    comparisons: List[PromptComparison] = []
    total = len(prompts)
    for i, item in enumerate(prompts, 1):
        print(f"\n[{i}/{total}] {item.category_name or item.category}")
        print(f"  {item.prompt.splitlines()[0][:110]}")
        results: List[ModelResult] = []
        for model in MODELS:
            result = call_model(model, item.prompt)
            tok = result.completion_tokens or "n/a"
            tps = f"{result.throughput:.1f} tok/s" if result.throughput else ""
            status = "OK" if result.succeeded else "ERROR"
            print(f"  {model.name}: {status} {result.elapsed_seconds:.2f}s "
                  f"tokens={tok} {tps}")
            if result.error:
                print(f"    {result.error[:180]}")
            results.append(result)
            if CALL_DELAY_SECONDS:
                time.sleep(CALL_DELAY_SECONDS)
        comparisons.append(PromptComparison(
            category=item.category,
            category_name=item.category_name,
            prompt=item.prompt,
            results=results,
        ))
    return comparisons


# ── Serialisation ─────────────────────────────────────────────────────────────


def save_results(
    comparisons: List[PromptComparison],
    output_file: str,
) -> None:
    """Persist raw results as JSON using Pydantic's serialiser."""
    run = BenchmarkRun(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        fairness_config=FAIRNESS_CONFIG,
        model_ids=[m.id for m in MODELS],
        categories=EVAL_CATEGORIES,
        comparisons=comparisons,
    )
    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write(run.to_json())


# ── Metrics report ────────────────────────────────────────────────────────────


def _avg(values: Iterable[float]) -> Optional[float]:
    lst = list(values)
    return sum(lst) / len(lst) if lst else None


def _fmt(value: Optional[float], digits: int = 2) -> str:
    return f"{value:.{digits}f}" if value is not None else "n/a"


def save_metrics_report(
    comparisons: List[PromptComparison],
    output_file: str,
) -> None:
    """Write a Markdown metrics report with per-model and per-category tables."""
    # Aggregate stats using ModelResult's typed properties
    stats = {
        m.name: {"times": [], "tokens": [], "errors": 0, "calls": 0}
        for m in MODELS
    }
    by_category = {
        cat.id: {
            m.name: {"times": [], "tokens": [], "errors": 0, "calls": 0}
            for m in MODELS
        }
        for cat in EVAL_CATEGORIES
    }
    errors = []

    for n, comp in enumerate(comparisons, 1):
        for result in comp.results:
            name = result.model
            stats[name]["calls"] += 1
            if comp.category in by_category:
                by_category[comp.category][name]["calls"] += 1
            if not result.succeeded:
                stats[name]["errors"] += 1
                if comp.category in by_category:
                    by_category[comp.category][name]["errors"] += 1
                errors.append((n, comp.category, name, result.error or "unknown"))
                continue
            stats[name]["times"].append(result.elapsed_seconds)
            if result.completion_tokens:
                stats[name]["tokens"].append(result.completion_tokens)
            if comp.category in by_category:
                by_category[comp.category][name]["times"].append(result.elapsed_seconds)
                if result.completion_tokens:
                    by_category[comp.category][name]["tokens"].append(result.completion_tokens)

    lines = [
        "# Metrics Report",
        "",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "## Evaluation Design",
        "",
        "| Category | Prompts | Inspired by | What it tests |",
        "|---|---:|---|---|",
    ]
    for cat in EVAL_CATEGORIES:
        lines.append(
            f"| {cat.name} | {len(cat.prompts)} "
            f"| {cat.inspiration} | {cat.what_it_tests} |"
        )

    lines.extend([
        "",
        "## Fairness Constraints",
        "",
        "| Constraint | Value | Why |",
        "|---|---|---|",
        f"| `max_tokens` | `{FAIRNESS_CONFIG.max_tokens}` "
        "| Caps response length — prevents verbosity bias (HELM) |",
        f"| `temperature` | `{FAIRNESS_CONFIG.temperature}` "
        "| Greedy decoding — deterministic, reproducible (GSM8K standard) |",
        "| System prompt | Identical for all models "
        "| Removes prompt-sensitivity variance (±10 pp on MMLU) |",
        "| Output constraint | Baked into every prompt "
        "| Structurally comparable responses (IFEval methodology) |",
        "| Cultural neutrality | No region-specific content "
        "| Avoids the 19 pp accuracy drop on non-US GSM8K variants |",
        "",
        "## Run Configuration",
        "",
        f"- Prompts evaluated: `{len(comparisons)}`",
        f"- Model calls attempted: `{len(comparisons) * len(MODELS)}`",
        f"- Retry attempts on 429: `{REQUEST_RETRIES}`",
        f"- Delay between calls: `{CALL_DELAY_SECONDS}` s",
        "",
        "## Overall Model Metrics",
        "",
        "| Model | OK / Calls | Errors | Avg Latency (s) | Avg Tokens | Throughput (tok/s) |",
        "|---|---:|---:|---:|---:|---:|",
    ])

    for m in MODELS:
        s = stats[m.name]
        avg_lat = _avg(s["times"])
        avg_tok = _avg(s["tokens"])
        tput = (
            sum(s["tokens"]) / sum(s["times"])
            if s["tokens"] and s["times"] else None
        )
        lines.append(
            f"| {m.name} "
            f"| {len(s['times'])} / {s['calls']} "
            f"| {s['errors']} "
            f"| {_fmt(avg_lat)} "
            f"| {_fmt(avg_tok, 1)} "
            f"| {_fmt(tput, 1)} |"
        )

    lines.extend([
        "",
        "## Latency by Category (avg seconds, ok/calls)",
        "",
        f"| Category | {' | '.join(m.name for m in MODELS)} |",
        f"|---{'|---:' * len(MODELS)}|",
    ])
    for cat in EVAL_CATEGORIES:
        row = [cat.name]
        for m in MODELS:
            s = by_category[cat.id][m.name]
            avg = _avg(s["times"])
            cell = (
                f"{avg:.2f}s ({len(s['times'])}/{s['calls']} ok)"
                if avg is not None
                else f"n/a (0/{s['calls']} ok)"
            )
            row.append(cell)
        lines.append("| " + " | ".join(row) + " |")

    lines.extend([
        "",
        "## Throughput by Category (completion tok/s)",
        "",
        f"| Category | {' | '.join(m.name for m in MODELS)} |",
        f"|---{'|---:' * len(MODELS)}|",
    ])
    for cat in EVAL_CATEGORIES:
        row = [cat.name]
        for m in MODELS:
            s = by_category[cat.id][m.name]
            tput = (
                sum(s["tokens"]) / sum(s["times"])
                if s["tokens"] and s["times"] else None
            )
            row.append(_fmt(tput, 1) if tput else "n/a")
        lines.append("| " + " | ".join(row) + " |")

    if errors:
        lines.extend([
            "",
            "## Errors",
            "",
            "| # | Category | Model | Error (truncated) |",
            "|---:|---|---|---|",
        ])
        for num, cat, mdl, err in errors:
            safe = str(err).replace("|", "/").replace("\n", " ")[:180]
            lines.append(f"| {num} | {cat} | {mdl} | {safe} |")

    lines.append("")
    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run OpenRouter model comparison benchmark."
    )
    parser.add_argument(
        "--category", choices=[cat.id for cat in EVAL_CATEGORIES],
        help="Run only prompts from this category.",
    )
    parser.add_argument(
        "--limit", type=int,
        help="Run only the first N selected prompts.",
    )
    parser.add_argument("--output-json", default="comparison_output.json")
    parser.add_argument("--report", default="metrics_report.md")
    return parser.parse_args()


def select_prompts(args: argparse.Namespace) -> List[BenchmarkPrompt]:
    prompts = [
        p
        for cat in EVAL_CATEGORIES
        for p in cat.to_benchmark_prompts()
    ]
    if args.category:
        prompts = [p for p in prompts if p.category == args.category]
    if args.limit:
        prompts = prompts[: args.limit]
    return prompts


def main() -> None:
    args = parse_args()
    prompts = select_prompts(args)
    if not prompts:
        raise SystemExit("No prompts selected.")

    print("OpenRouter Model Comparison")
    print(f"Models    : {', '.join(m.name for m in MODELS)}")
    print(f"Prompts   : {len(prompts)}")
    print(f"max_tokens: {FAIRNESS_CONFIG.max_tokens}  temperature: {FAIRNESS_CONFIG.temperature}")

    comparisons = run_benchmark(prompts)
    save_results(comparisons, args.output_json)
    save_metrics_report(comparisons, args.report)
    print(f"\nRaw JSON  -> {args.output_json}")
    print(f"Report    -> {args.report}")


if __name__ == "__main__":
    main()
