#!/usr/bin/env python3
"""
OpenRouter Model Comparison Tool
Sends the same prompt to all 3 models simultaneously and compares:
  - response time (speed)
  - response length
  - full output side-by-side
Results are saved to comparison_output.json and printed to the terminal.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional

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

DEFAULT_PROMPTS = [
    {
        "category": "reasoning",
        "prompt": (
            "A train travels 120 km in 1.5 hours, then stops for 20 minutes, "
            "then travels 80 km in 45 minutes. What is the average speed for "
            "the entire trip (including the stop)? Show your working."
        ),
    },
    {
        "category": "coding",
        "prompt": (
            "Write a Python function that finds all prime numbers up to n "
            "using the Sieve of Eratosthenes. Include a brief explanation "
            "of the algorithm."
        ),
    },
    {
        "category": "creative",
        "prompt": (
            "Write a short poem (8-12 lines) about the feeling of discovering "
            "a bug in production at 2am."
        ),
    },
    {
        "category": "factual",
        "prompt": (
            "Explain the difference between TCP and UDP in simple terms. "
            "When should you use each?"
        ),
    },
    {
        "category": "analysis",
        "prompt": (
            "What are the three most important trade-offs to consider when "
            "choosing between microservices and a monolithic architecture? "
            "Be concise."
        ),
    },
]

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
RED = "\033[31m"
DIM = "\033[2m"

MODEL_COLORS = [BLUE, GREEN, YELLOW]
MEDALS = ["1st", "2nd", "3rd"]


# -- API -----------------------------------------------------------------------


def call_model(model: Dict, prompt: str) -> Dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openrouter-compare",
        "X-Title": "OpenRouter Model Comparison",
    }
    start = time.time()
    try:
        resp = requests.post(
            BASE_URL,
            headers=headers,
            json={"model": model["id"], "messages": [{"role": "user", "content": prompt}]},
            timeout=90,
        )
        elapsed = time.time() - start
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
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
    except requests.exceptions.Timeout:
        return {
            "model": model["name"], "id": model["id"], "response": None,
            "elapsed": time.time() - start, "error": "Timeout (90s)",
            "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
        }
    except Exception as exc:
        return {
            "model": model["name"], "id": model["id"], "response": None,
            "elapsed": time.time() - start, "error": str(exc),
            "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
        }


# -- Single-prompt comparison --------------------------------------------------


def run_comparison(prompt: str, category: str = "custom") -> List[Dict]:
    bar = "=" * 62
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"  {BOLD}Category:{RESET} {category.upper()}")
    print(f"  {BOLD}Prompt:{RESET}   {prompt[:90]}{'...' if len(prompt) > 90 else ''}")
    print(f"{BOLD}{CYAN}{bar}{RESET}")
    print(f"{DIM}Querying all 3 models in parallel...{RESET}\n")

    results: List[Optional[Dict]] = [None] * len(MODELS)
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(call_model, model, prompt): idx for idx, model in enumerate(MODELS)}
        for fut in as_completed(futs):
            idx = futs[fut]
            results[idx] = fut.result()

    for i, result in enumerate(results):
        color = MODEL_COLORS[i]
        name = result["model"]
        secs = result["elapsed"]
        bar2 = "-" * max(0, 44 - len(name))

        print(f"{color}{BOLD}+- {name}  ({secs:.2f}s) {bar2}+{RESET}")

        if result["error"]:
            print(f"  {RED}Error: {result['error']}{RESET}")
        else:
            lines = result["response"].split("\n")
            preview_lines = lines[:15]
            for line in preview_lines:
                print(f"  {line}")
            remaining = len(lines) - len(preview_lines)
            if remaining > 0:
                print(f"  {DIM}... {remaining} more lines (see JSON output){RESET}")
            tokens = result.get("completion_tokens")
            if tokens:
                print(f"\n  {DIM}Completion tokens: {tokens}{RESET}")

        print(f"{color}{BOLD}+{'-' * 54}+{RESET}\n")

    return results


# -- Multi-prompt summary ------------------------------------------------------


def print_summary(all_results: List[List[Dict]]) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 62}{RESET}")
    print(f"  {BOLD}BENCHMARK SUMMARY{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 62}{RESET}\n")

    stats: Dict[str, Dict] = {
        m["name"]: {"times": [], "lengths": [], "errors": 0} for m in MODELS
    }
    for run in all_results:
        for result in run:
            name = result["model"]
            if result["error"]:
                stats[name]["errors"] += 1
            else:
                stats[name]["times"].append(result["elapsed"])
                stats[name]["lengths"].append(len(result["response"]))

    print(f"{BOLD}Average response time (lower = faster):{RESET}")
    speed_rows = []
    for name, s in stats.items():
        if s["times"]:
            avg = sum(s["times"]) / len(s["times"])
            speed_rows.append((avg, name))
    speed_rows.sort()
    for rank, (avg, name) in enumerate(speed_rows):
        color = MODEL_COLORS[[m["name"] for m in MODELS].index(name)]
        medal = MEDALS[rank] if rank < 3 else f"{rank + 1}th"
        print(f"  {medal:<4} {color}{name}{RESET}  {avg:.2f}s avg")

    print(f"\n{BOLD}Average response length (chars):{RESET}")
    len_rows = []
    for name, s in stats.items():
        if s["lengths"]:
            avg = sum(s["lengths"]) / len(s["lengths"])
            len_rows.append((avg, name))
    len_rows.sort(reverse=True)
    for rank, (avg, name) in enumerate(len_rows):
        color = MODEL_COLORS[[m["name"] for m in MODELS].index(name)]
        print(f"  {rank + 1}.  {color}{name}{RESET}  {avg:.0f} chars avg")

    any_errors = any(s["errors"] for s in stats.values())
    if any_errors:
        print(f"\n{BOLD}Errors:{RESET}")
        for name, s in stats.items():
            if s["errors"]:
                color = MODEL_COLORS[[m["name"] for m in MODELS].index(name)]
                print(f"  {color}{name}{RESET}  {RED}{s['errors']} error(s){RESET}")

    print()


# -- JSON output ---------------------------------------------------------------


def save_results(
    all_results: List[List[Dict]],
    prompts: List[Dict],
    output_file: str = "comparison_output.json",
) -> None:
    doc = {
        "generated_at": datetime.now().isoformat(),
        "models": [m["id"] for m in MODELS],
        "comparisons": [],
    }
    for results, p_info in zip(all_results, prompts):
        doc["comparisons"].append({
            "category": p_info.get("category", "custom"),
            "prompt": p_info["prompt"],
            "results": [
                {
                    "model": r["model"],
                    "model_id": r["id"],
                    "response": r["response"],
                    "elapsed_seconds": round(r["elapsed"], 3),
                    "completion_tokens": r["completion_tokens"],
                    "total_tokens": r["total_tokens"],
                    "error": r["error"],
                }
                for r in results
            ],
        })

    with open(output_file, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)

    print(f"{GREEN}{BOLD}Full responses saved to {output_file}{RESET}")


# -- Entry point ---------------------------------------------------------------


def main() -> None:
    print(f"\n{BOLD}{CYAN}OpenRouter Model Comparison Tool{RESET}")
    print(f"Models: {' | '.join(m['name'] for m in MODELS)}\n")

    if len(sys.argv) > 1:
        custom_prompt = " ".join(sys.argv[1:])
        prompts = [{"category": "custom", "prompt": custom_prompt}]
    else:
        print(f"{BOLD}Options:{RESET}")
        print(f"  1  Run full benchmark ({len(DEFAULT_PROMPTS)} diverse prompts)")
        print("  2  Enter a custom prompt")
        print("  3  Pick a single benchmark prompt interactively\n")

        choice = input(f"{BOLD}Choice [1/2/3]: {RESET}").strip()

        if choice == "1":
            prompts = DEFAULT_PROMPTS
        elif choice == "2":
            custom = input(f"{BOLD}Prompt: {RESET}").strip()
            if not custom:
                print(f"{RED}Empty prompt - exiting.{RESET}")
                sys.exit(1)
            prompts = [{"category": "custom", "prompt": custom}]
        elif choice == "3":
            print(f"\n{BOLD}Benchmark prompts:{RESET}")
            for i, p in enumerate(DEFAULT_PROMPTS, 1):
                print(f"  {i}. [{p['category'].upper()}] {p['prompt'][:70]}...")
            idx_str = input(
                f"\n{BOLD}Select [1-{len(DEFAULT_PROMPTS)}]: {RESET}"
            ).strip()
            try:
                prompts = [DEFAULT_PROMPTS[int(idx_str) - 1]]
            except (ValueError, IndexError):
                print(f"{RED}Invalid selection.{RESET}")
                sys.exit(1)
        else:
            print(f"{RED}Invalid choice.{RESET}")
            sys.exit(1)

    all_results: List[List[Dict]] = []
    for p_info in prompts:
        results = run_comparison(p_info["prompt"], p_info.get("category", "custom"))
        all_results.append(results)

    if len(prompts) > 1:
        print_summary(all_results)

    save = input(
        f"{BOLD}Save full results to comparison_output.json? [Y/n]: {RESET}"
    ).strip().lower()
    if save != "n":
        save_results(all_results, prompts)

    print(f"\n{CYAN}Done.{RESET}\n")


if __name__ == "__main__":
    main()
