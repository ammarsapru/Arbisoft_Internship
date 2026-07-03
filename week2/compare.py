#!/usr/bin/env python3
"""
OpenRouter model comparison and metrics report generator.

Runs the same benchmark prompts against three free-tier OpenRouter models,
records latency/token/error metrics, saves raw JSON, and writes a Markdown
metrics report.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Optional

import requests


API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    raise SystemExit("Set the OPENROUTER_API_KEY environment variable before running.")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    {"id": "openai/gpt-oss-120b:free", "name": "GPT-OSS 120B"},
    {"id": "google/gemma-4-31b-it:free", "name": "Gemma 4 31B-IT"},
    {"id": "nvidia/nemotron-nano-9b-v2:free", "name": "Nemotron Nano 9B"},
]

FAIRNESS_CONFIG = {
    "max_tokens": 600,
    "temperature": 0,
    "system": (
        "You are a precise, helpful assistant. Follow all output format "
        "instructions exactly. Do not add preamble or filler."
    ),
}

REQUEST_RETRIES = int(os.environ.get("OPENROUTER_RETRIES", "2"))
RETRY_BASE_SECONDS = float(os.environ.get("OPENROUTER_RETRY_BASE_SECONDS", "15"))
CALL_DELAY_SECONDS = float(os.environ.get("OPENROUTER_CALL_DELAY_SECONDS", "2"))


EVAL_CATEGORIES = [
    {
        "id": "math_reasoning",
        "name": "Mathematical Reasoning",
        "what_it_tests": "Multi-step arithmetic, algebra, geometry, combinatorics",
        "inspiration": "GSM8K, MATH",
        "output_constraint": (
            "Show step-by-step working. Put the final answer on its own line "
            "as: ANSWER: [numeric value] [unit if applicable]"
        ),
        "prompts": [
            "Three people share $2,400 in the ratio 3:5:4. How much does the largest share receive?",
            "A rectangle has perimeter 54 cm. Its length is twice its width. What is its area?",
            "A shop buys a jacket for $80, marks it up 35%, then discounts the marked price by 20%. What is the sale price?",
            "Pipe A fills a tank in 6 hours. Pipe B drains it in 9 hours. Both open on an empty tank. How long to fill?",
            "A $20,000 car depreciates by 15% of current value yearly. What is its value after 3 years, rounded?",
            "How many three-digit integers are divisible by both 4 and 6?",
            "Mix 12% and 4% saline to make 40 litres of 8% saline. How many litres of 12% solution are used?",
            "In a class of 30, 18 play football, 14 play cricket, and 6 play neither. How many play both?",
            "A ladder makes a 60 degree angle with the ground and its foot is 3 m from the wall. How long is it?",
            "Two trains start 300 km apart: one at 09:00 at 80 km/h, one at 09:30 at 100 km/h. When do they meet?",
        ],
    },
    {
        "id": "logical_reasoning",
        "name": "Logical & Deductive Reasoning",
        "what_it_tests": "Syllogisms, conditionals, puzzles, sequence patterns",
        "inspiration": "BIG-Bench, LogiQA, Winogrande",
        "output_constraint": (
            "Reason step by step. Put the conclusion on its own line as: "
            "ANSWER: [your conclusion]"
        ),
        "prompts": [
            "All mammals are warm-blooded. Dolphins are mammals. Warm-blooded animals have four-chambered hearts. Snakes are not warm-blooded. Can we conclude snakes do not have four-chambered hearts?",
            "On an island, Knights always tell truth and Knaves always lie. A says: 'We are both Knaves.' What are A and B?",
            "Find the next number and rule: 2, 6, 12, 20, 30, 42, ?",
            "If it is raining, Alex carries an umbrella. Alex is not carrying one. What follows, and what logical form is used?",
            "Solve the wolf, goat, cabbage river crossing where the boat carries the farmer and one item.",
            "Tom is older than Sam. Sam is older than Jake. Jake is older than Priya. Is Tom oldest, and who is youngest?",
            "All squares are rectangles. Some rectangles are rhombuses. No rhombuses are circles. Which must be true: A all squares are rhombuses, B a square can be a rhombus, C no squares are circles?",
            "Everyone who owns a cat owns a dog. Some dog owners are vegetarian. Mia owns a cat. Can we conclude Mia is vegetarian?",
            "Three switches outside a room control three bulbs inside. You may enter once. How identify each switch?",
            "Cards red, blue, green, yellow, white are in a row. Green is immediately left of white; red is position 3; blue left of red; yellow not at either end. What order?",
        ],
    },
    {
        "id": "code_generation",
        "name": "Code Generation & Algorithmic Problem Solving",
        "what_it_tests": "Algorithm implementation, correctness, edge cases",
        "inspiration": "HumanEval, MBPP",
        "output_constraint": (
            "Provide Python 3 code only. Include a one-line docstring. End "
            "with exactly 2 assert statements."
        ),
        "prompts": [
            "Implement binary search on a sorted list of integers.",
            "Write a function that checks whether a string is a palindrome, ignoring case and non-alphanumeric characters.",
            "Implement merge sort on a list of integers.",
            "Return all unique value pairs in a list that add to a target sum.",
            "Detect whether a directed graph represented as adjacency lists contains a cycle.",
            "Return the nth Fibonacci number using dynamic programming.",
            "Determine whether brackets (), {}, [] in a string are balanced.",
            "Merge overlapping intervals represented as [start, end] pairs.",
            "Convert an integer from 1 to 3999 to a Roman numeral.",
            "Find the length of the longest consecutive integer sequence in an unsorted list.",
        ],
    },
    {
        "id": "factual_knowledge",
        "name": "Factual & Technical Knowledge",
        "what_it_tests": "Computer science fundamentals and concise recall",
        "inspiration": "MMLU, TriviaQA",
        "output_constraint": "Answer in exactly 2 to 3 sentences. No bullets or numbered lists.",
        "prompts": [
            "What are the four ACID properties of a database transaction, and why does each matter?",
            "What is the difference between a process and a thread in an operating system?",
            "State the CAP theorem. Can a distributed system satisfy all three properties at once?",
            "What does Big-O notation measure, and what are quicksort average and worst-case time complexities?",
            "What is the difference between symmetric and asymmetric encryption? Give one example of each.",
            "What is a foreign key in a relational database, and what constraint does it enforce?",
            "What is virtual memory in operating systems, and what problem does it solve?",
            "What is deadlock in an operating system? Name one necessary condition.",
            "What is the difference between compiled and interpreted languages? Give one example of each.",
            "What does the OSI model describe, how many layers does it have, and which layer handles end-to-end transfer?",
        ],
    },
    {
        "id": "instruction_following",
        "name": "Instruction Following & Constraint Adherence",
        "what_it_tests": "Format compliance, counting, and label adherence",
        "inspiration": "IFEval, FollowBench",
        "output_constraint": "Follow every constraint exactly. Any deviation counts as failure.",
        "prompts": [
            "List exactly 5 Python built-in functions. Number them 1 to 5. Each description must be exactly 8 words.",
            "Explain what an API is in exactly 3 sentences, including the words interface and contract.",
            "Write a haiku about databases with labels TITLE, LINE1, LINE2, LINE3 and no other text.",
            "Compare SQL and NoSQL in exactly 2 sentences. Sentence 1 begins SQL. Sentence 2 begins NoSQL.",
            "Explain recursion using a metaphor in no more than 35 words and include the word mirror.",
            "Rewrite 'The server crashed' using exactly the labels FORMAL, TECHNICAL, CASUAL.",
            "Answer with a single integer and nothing else: How many bytes are in one kibibyte?",
            "Give 3 tips for clean code. Each must begin with an action verb and labels TIP 1, TIP 2, TIP 3.",
            "Translate a filter operation into plain English and Python pseudocode using labels PLAIN and PSEUDOCODE.",
            "Name 4 sorting algorithms as a table with headers Algorithm, Average Time Complexity, Stable? only.",
        ],
    },
]


def default_prompts() -> List[Dict[str, str]]:
    return [
        {
            "category": cat["id"],
            "category_name": cat["name"],
            "prompt": f"{prompt}\n\n{cat['output_constraint']}",
        }
        for cat in EVAL_CATEGORIES
        for prompt in cat["prompts"]
    ]


def retry_wait_seconds(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after).replace(tzinfo=None)
                return max(0.0, (retry_at - datetime.utcnow()).total_seconds())
            except Exception:
                pass
    return RETRY_BASE_SECONDS * (attempt + 1)


def call_model(model: Dict[str, str], prompt: str) -> Dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openrouter-compare",
        "X-Title": "OpenRouter Model Comparison",
    }
    payload = {
        "model": model["id"],
        "messages": [
            {"role": "system", "content": FAIRNESS_CONFIG["system"]},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": FAIRNESS_CONFIG["max_tokens"],
        "temperature": FAIRNESS_CONFIG["temperature"],
    }
    start = time.time()
    try:
        response = None
        for attempt in range(REQUEST_RETRIES + 1):
            response = requests.post(BASE_URL, headers=headers, json=payload, timeout=90)
            if response.status_code != 429 or attempt == REQUEST_RETRIES:
                break
            wait = retry_wait_seconds(response, attempt)
            print(f"  {model['name']}: 429 rate limit; retrying in {wait:.1f}s")
            time.sleep(wait)

        elapsed = time.time() - start
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        content = message.get("content")
        usage = data.get("usage", {})
        if not content:
            raise ValueError("Empty response content")
        return {
            "model": model["name"],
            "id": model["id"],
            "response": content,
            "elapsed": elapsed,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "error": None,
        }
    except Exception as exc:
        return {
            "model": model["name"],
            "id": model["id"],
            "response": None,
            "elapsed": time.time() - start,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "error": str(exc),
        }


def run_benchmark(prompts: List[Dict[str, str]]) -> List[List[Dict]]:
    all_results: List[List[Dict]] = []
    total = len(prompts)
    for prompt_index, item in enumerate(prompts, 1):
        print(f"\n[{prompt_index}/{total}] {item.get('category_name', item['category'])}")
        print(item["prompt"].splitlines()[0][:110])
        run = []
        for model in MODELS:
            result = call_model(model, item["prompt"])
            status = "ERROR" if result["error"] else "OK"
            tokens = result.get("completion_tokens") or "n/a"
            print(f"  {model['name']}: {status} in {result['elapsed']:.2f}s, tokens={tokens}")
            if result["error"]:
                print(f"    {result['error'][:180]}")
            run.append(result)
            if CALL_DELAY_SECONDS:
                time.sleep(CALL_DELAY_SECONDS)
        all_results.append(run)
    return all_results


def save_results(all_results: List[List[Dict]], prompts: List[Dict], output_file: str) -> None:
    doc = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fairness_config": FAIRNESS_CONFIG,
        "models": [model["id"] for model in MODELS],
        "categories": [
            {
                "id": cat["id"],
                "name": cat["name"],
                "what_it_tests": cat["what_it_tests"],
                "inspiration": cat["inspiration"],
                "output_constraint": cat["output_constraint"],
            }
            for cat in EVAL_CATEGORIES
        ],
        "comparisons": [],
    }
    for prompt_info, results in zip(prompts, all_results):
        doc["comparisons"].append(
            {
                "category": prompt_info.get("category", "custom"),
                "prompt": prompt_info["prompt"],
                "results": [
                    {
                        "model": result["model"],
                        "model_id": result["id"],
                        "response": result["response"],
                        "elapsed_seconds": round(result["elapsed"], 3),
                        "completion_tokens": result["completion_tokens"],
                        "total_tokens": result["total_tokens"],
                        "error": result["error"],
                    }
                    for result in results
                ],
            }
        )
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, ensure_ascii=False)


def average(values: Iterable[float]) -> Optional[float]:
    values = list(values)
    return sum(values) / len(values) if values else None


def fmt_number(value: Optional[float], digits: int = 2) -> str:
    return f"{value:.{digits}f}" if value is not None else "n/a"


def save_metrics_report(all_results: List[List[Dict]], prompts: List[Dict], output_file: str) -> None:
    stats = {
        model["name"]: {"times": [], "tokens": [], "errors": 0, "calls": 0}
        for model in MODELS
    }
    by_category = {
        cat["id"]: {
            model["name"]: {"times": [], "tokens": [], "errors": 0, "calls": 0}
            for model in MODELS
        }
        for cat in EVAL_CATEGORIES
    }
    errors = []
    for prompt_number, (prompt_info, results) in enumerate(zip(prompts, all_results), 1):
        category = prompt_info.get("category", "custom")
        for result in results:
            name = result["model"]
            stats[name]["calls"] += 1
            if category in by_category:
                by_category[category][name]["calls"] += 1
            if result["error"]:
                stats[name]["errors"] += 1
                if category in by_category:
                    by_category[category][name]["errors"] += 1
                errors.append((prompt_number, category, name, result["error"]))
                continue
            stats[name]["times"].append(result["elapsed"])
            if result["completion_tokens"]:
                stats[name]["tokens"].append(result["completion_tokens"])
            if category in by_category:
                by_category[category][name]["times"].append(result["elapsed"])
                if result["completion_tokens"]:
                    by_category[category][name]["tokens"].append(result["completion_tokens"])

    lines = [
        "# Metrics Report",
        "",
        f"Generated at: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "## Run Configuration",
        "",
        f"- Prompts evaluated: `{len(prompts)}`",
        f"- Model calls attempted: `{len(prompts) * len(MODELS)}`",
        f"- Max tokens: `{FAIRNESS_CONFIG['max_tokens']}`",
        f"- Temperature: `{FAIRNESS_CONFIG['temperature']}`",
        f"- Retry attempts on 429: `{REQUEST_RETRIES}`",
        f"- Delay between calls: `{CALL_DELAY_SECONDS}` seconds",
        "",
        "## Overall Metrics",
        "",
        "| Model | Successful Calls | Errors | Avg Latency (s) | Avg Completion Tokens | Throughput (tok/s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        name = model["name"]
        item = stats[name]
        avg_latency = average(item["times"])
        avg_tokens = average(item["tokens"])
        throughput = sum(item["tokens"]) / sum(item["times"]) if item["tokens"] and item["times"] else None
        lines.append(
            f"| {name} | {len(item['times'])} / {item['calls']} | {item['errors']} | "
            f"{fmt_number(avg_latency, 2)} | "
            f"{fmt_number(avg_tokens, 1)} | "
            f"{fmt_number(throughput, 1)} |"
        )

    lines.extend([
        "",
        "## Latency by Category",
        "",
        "| Category | GPT-OSS 120B | Gemma 4 31B-IT | Nemotron Nano 9B |",
        "|---|---:|---:|---:|",
    ])
    for cat in EVAL_CATEGORIES:
        row = [cat["name"]]
        for model in MODELS:
            item = by_category[cat["id"]][model["name"]]
            avg_latency = average(item["times"])
            row.append(
                f"{avg_latency:.2f}s ({len(item['times'])}/{item['calls']} ok)"
                if avg_latency is not None
                else f"n/a (0/{item['calls']} ok)"
            )
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")

    if errors:
        lines.extend([
            "",
            "## Errors",
            "",
            "| Prompt # | Category | Model | Error |",
            "|---:|---|---|---|",
        ])
        for prompt_number, category, model, error in errors:
            lines.append(f"| {prompt_number} | {category} | {model} | {str(error).replace('|', '/').replace(chr(10), ' ')[:180]} |")

    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def select_prompts(args: argparse.Namespace) -> List[Dict[str, str]]:
    prompts = default_prompts()
    if args.category:
        prompts = [item for item in prompts if item["category"] == args.category]
    if args.limit:
        prompts = prompts[: args.limit]
    return prompts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenRouter model comparison benchmark.")
    parser.add_argument("--category", choices=[cat["id"] for cat in EVAL_CATEGORIES])
    parser.add_argument("--limit", type=int, help="Run only the first N selected prompts.")
    parser.add_argument("--output-json", default="comparison_output.json")
    parser.add_argument("--report", default="metrics_report.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompts = select_prompts(args)
    if not prompts:
        raise SystemExit("No prompts selected.")
    print("OpenRouter Model Comparison Tool")
    print(f"Models: {', '.join(model['name'] for model in MODELS)}")
    print(f"Prompts: {len(prompts)}")
    results = run_benchmark(prompts)
    save_results(results, prompts, args.output_json)
    save_metrics_report(results, prompts, args.report)
    print(f"\nSaved raw output to {args.output_json}")
    print(f"Saved metrics report to {args.report}")


if __name__ == "__main__":
    main()

