#!/usr/bin/env python3
"""
CLI Chat Application using OpenRouter API
Supports single-model and multi-model (all 3 simultaneously) chat.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import requests

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    raise SystemExit("Set the OPENROUTER_API_KEY environment variable before running.")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS: Dict[str, Dict] = {
    "1": {
        "id": "openai/gpt-oss-120b:free",
        "name": "GPT-OSS 120B",
        "color": "\033[34m",
    },
    "2": {
        "id": "google/gemma-4-31b-it:free",
        "name": "Gemma 4 31B-IT",
        "color": "\033[32m",
    },
    "3": {
        "id": "nvidia/nemotron-nano-9b-v2:free",
        "name": "Nemotron Nano 9B",
        "color": "\033[33m",
    },
}

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
RED = "\033[31m"
DIM = "\033[2m"


# â”€â”€ UI helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def clear_line() -> None:
    print("\r" + " " * 60 + "\r", end="", flush=True)


def print_header() -> None:
    print(f"\n{BOLD}{CYAN}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—")
    print("â•‘     OpenRouter CLI Chat  (v1.0)          â•‘")
    print(f"â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•{RESET}\n")


def print_models() -> None:
    print(f"{BOLD}Available models:{RESET}")
    for key, m in MODELS.items():
        print(f"  {m['color']}{key}. {m['name']}{RESET}  {DIM}({m['id']}){RESET}")
    print(f"  {BOLD}all{RESET} â€“ query all three simultaneously\n")


def print_help() -> None:
    print(f"\n{BOLD}Commands:{RESET}")
    cmds = [
        ("/models", "List available models"),
        ("/switch", "Switch active model(s) and reset history"),
        ("/clear", "Clear conversation history"),
        ("/history", "Print conversation history"),
        ("/help", "Show this help"),
        ("/exit", "Quit"),
    ]
    for cmd, desc in cmds:
        print(f"  {CYAN}{cmd:<12}{RESET} {desc}")
    print()


def print_response(result: Dict) -> None:
    color = result["color"]
    name = result["name"]
    secs = result["elapsed"]
    bar = "â”€" * max(0, 42 - len(name))
    print(f"\n{color}{BOLD}â”Œâ”€ {name}  ({secs:.2f}s) {bar}â”{RESET}")
    if result["error"]:
        print(f"  {RED}Error: {result['error']}{RESET}")
    else:
        for line in result["content"].split("\n"):
            print(f"  {line}")
    print(f"{color}{BOLD}â””{'â”€' * 52}â”˜{RESET}")


# â”€â”€ API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def call_model(model_id: str, name: str, color: str, messages: List[Dict]) -> Dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openrouter-cli",
        "X-Title": "OpenRouter CLI Chat",
    }
    start = time.time()
    try:
        resp = requests.post(
            BASE_URL,
            headers=headers,
            json={"model": model_id, "messages": messages},
            timeout=90,
        )
        elapsed = time.time() - start
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return {"name": name, "color": color, "content": content,
                "elapsed": elapsed, "error": None}
    except requests.exceptions.Timeout:
        return {"name": name, "color": color, "content": None,
                "elapsed": time.time() - start, "error": "Request timed out after 90s"}
    except Exception as exc:
        return {"name": name, "color": color, "content": None,
                "elapsed": time.time() - start, "error": str(exc)}


# â”€â”€ Model selection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def select_models() -> List[str]:
    print_models()
    while True:
        choice = input(f"{BOLD}Select model(s) [1/2/3/all]: {RESET}").strip().lower()
        if choice == "all":
            return list(MODELS.keys())
        if choice in MODELS:
            return [choice]
        print(f"{RED}Invalid â€“ enter 1, 2, 3, or 'all'.{RESET}")


# â”€â”€ Main loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def main() -> None:
    print_header()
    print(f"Type {CYAN}/help{RESET} for commands.\n")

    selected_keys = select_models()
    histories: Dict[str, List[Dict]] = {k: [] for k in selected_keys}

    if len(selected_keys) == 1:
        k = selected_keys[0]
        print(f"\n{BOLD}Chatting with: {MODELS[k]['color']}{MODELS[k]['name']}{RESET}\n")
    else:
        names = ", ".join(
            f"{MODELS[k]['color']}{MODELS[k]['name']}{RESET}" for k in selected_keys
        )
        print(f"\n{BOLD}Multi-model mode:{RESET} {names}\n")

    while True:
        try:
            user_input = input(f"{BOLD}You:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{CYAN}Goodbye!{RESET}")
            break

        if not user_input:
            continue

        # â”€â”€ commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd == "/exit":
                print(f"{CYAN}Goodbye!{RESET}")
                break
            elif cmd == "/help":
                print_help()
            elif cmd == "/models":
                print_models()
            elif cmd == "/switch":
                selected_keys = select_models()
                histories = {k: [] for k in selected_keys}
                print(f"{CYAN}Switched. History cleared.{RESET}")
                if len(selected_keys) == 1:
                    k = selected_keys[0]
                    print(
                        f"{BOLD}Chatting with: "
                        f"{MODELS[k]['color']}{MODELS[k]['name']}{RESET}\n"
                    )
                else:
                    names = ", ".join(
                        f"{MODELS[k]['color']}{MODELS[k]['name']}{RESET}"
                        for k in selected_keys
                    )
                    print(f"{BOLD}Multi-model mode:{RESET} {names}\n")
            elif cmd == "/clear":
                histories = {k: [] for k in selected_keys}
                print(f"{CYAN}History cleared.{RESET}")
            elif cmd == "/history":
                if all(not h for h in histories.values()):
                    print(f"{CYAN}No history yet.{RESET}")
                else:
                    for k in selected_keys:
                        print(
                            f"\n{BOLD}{MODELS[k]['color']}"
                            f"{MODELS[k]['name']} history:{RESET}"
                        )
                        for msg in histories[k]:
                            if msg["role"] == "user":
                                prefix = f"  {BOLD}You:{RESET}  "
                            else:
                                prefix = f"  {MODELS[k]['color']}Bot:{RESET}  "
                            snippet = msg["content"][:120].replace("\n", " ")
                            ellipsis = "â€¦" if len(msg["content"]) > 120 else ""
                            print(f"{prefix}{snippet}{ellipsis}")
            else:
                print(f"{RED}Unknown command '{cmd}'. Type /help.{RESET}")
            continue

        # â”€â”€ send to model(s) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        for k in selected_keys:
            histories[k].append({"role": "user", "content": user_input})

        if len(selected_keys) == 1:
            k = selected_keys[0]
            m = MODELS[k]
            print(f"{DIM}Thinkingâ€¦{RESET}", end="", flush=True)
            result = call_model(m["id"], m["name"], m["color"], histories[k])
            clear_line()
            print_response(result)
            if result["content"]:
                histories[k].append({"role": "assistant", "content": result["content"]})
        else:
            print(f"{DIM}Querying all models in parallelâ€¦{RESET}", flush=True)
            bucket: Dict[str, Dict] = {}
            with ThreadPoolExecutor(max_workers=3) as ex:
                futs = {
                    ex.submit(
                        call_model,
                        MODELS[k]["id"],
                        MODELS[k]["name"],
                        MODELS[k]["color"],
                        list(histories[k]),
                    ): k
                    for k in selected_keys
                }
                for fut in as_completed(futs):
                    k = futs[fut]
                    bucket[k] = fut.result()
                    bucket[k]["key"] = k

            for k in selected_keys:
                result = bucket[k]
                print_response(result)
                if result["content"]:
                    histories[k].append({"role": "assistant", "content": result["content"]})

        print()


if __name__ == "__main__":
    main()

