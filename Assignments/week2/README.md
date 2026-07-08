# Week 2 – OpenRouter CLI Chat & Model Comparison

A command-line chat application and benchmarking tool built on the [OpenRouter](https://openrouter.ai) API, comparing three free-tier large language models side-by-side.

---

## Project Structure

```
week2/
├── chat.py              # Interactive CLI chat app
├── compare.py           # Benchmark & comparison runner
├── model_comparison.md  # Analysis: speed, quality, use-case fit
└── README.md            # This file
```

---

## Models

| Model ID | Provider | Parameters |
|----------|----------|------------|
| `openai/gpt-oss-120b:free` | OpenAI (OSS) | ~120B |
| `google/gemma-4-31b-it:free` | Google DeepMind | ~31B |
| `nvidia/nemotron-nano-9b-v2:free` | NVIDIA | ~9B |

---

## Setup

**Requirement:** Python 3.8+

```bash
pip install requests
```

Set your OpenRouter API key (optional — a default key is already embedded):

```bash
# Windows PowerShell
$env:OPENROUTER_API_KEY = "your-key-here"

# macOS / Linux
export OPENROUTER_API_KEY="your-key-here"
```

---

## Usage

### `chat.py` — Interactive CLI Chat

```bash
python chat.py
```

At startup, choose which model(s) to use:

```
Select model(s) [1/2/3/all]:
  1 – GPT-OSS 120B only
  2 – Gemma 4 31B-IT only
  3 – Nemotron Nano 9B only
  all – query all three simultaneously (responses printed side-by-side)
```

In **all** mode, your message is sent to all three models in parallel via `ThreadPoolExecutor`. Each model maintains its own independent conversation history.

**In-session commands:**

| Command | Action |
|---------|--------|
| `/models` | List all available models |
| `/switch` | Pick different model(s); resets history |
| `/clear` | Clear conversation history |
| `/history` | Print conversation history |
| `/help` | Show command list |
| `/exit` | Quit |

**Example (all-models mode):**

```
You: What is a closure in programming?

┌─ GPT-OSS 120B  (14.3s) ───────────────────────────────┐
  A closure is a function that retains access to variables
  from its enclosing scope even after that scope has exited…
└────────────────────────────────────────────────────────┘

┌─ Gemma 4 31B-IT  (9.7s) ──────────────────────────────┐
  In programming, a closure is a combination of a function
  and the lexical environment in which that function was declared…
└────────────────────────────────────────────────────────┘

┌─ Nemotron Nano 9B  (4.2s) ────────────────────────────┐
  A closure is a function bundled with its surrounding state…
└────────────────────────────────────────────────────────┘
```

---

### `compare.py` — Benchmark & Comparison Tool

```bash
# Interactive menu
python compare.py

# Pass a prompt directly from the command line
python compare.py "Explain the CAP theorem."
```

**Menu options:**

```
1  Run full benchmark (5 diverse prompts)
2  Enter a custom prompt
3  Pick a single benchmark prompt interactively
```

All three models are queried in parallel. Results are printed to the terminal and optionally saved to `comparison_output.json`.

**Benchmark prompt categories:** reasoning · coding · creative · factual · analysis

---

## Linting

### Installation

```bash
pip install flake8 pylint
```

Both tools install to `~/.local/bin` (Linux/macOS) or `%APPDATA%\Python\Python3xx\Scripts` (Windows). Add that directory to your `PATH` if the executables are not found, or invoke via `python -m flake8` / `python -m pylint`.

### Running flake8

```bash
python -m flake8 chat.py compare.py --max-line-length=100
```

### Issues Found and Resolved

The following violations were identified and fixed across both files:

#### `chat.py`

| Line(s) | Code | Description | Fix Applied |
|---------|------|-------------|-------------|
| 8 | F401 | `import sys` imported but unused | Removed |
| 14 | E501 | API key assignment line 123 chars (> 100) | Split with `os.environ.get(key, default)` across 3 lines |
| 35–39 | E221 | Multiple spaces before `=` on ANSI constant block (`RESET  =`, `BOLD   =`, …) | Removed alignment spaces |
| 47, 52, 58, 72 | E302 | Expected 2 blank lines before top-level function, found 1 | Added second blank line before each function |
| 49 | F541 | `f"║ … ║"` — f-string with no `{}` placeholders | Dropped `f` prefix, made plain string |
| 74–76 | E221 | Multiple spaces before `=` in `print_response` locals (`name  =`, `secs  =`, `bar   =`) | Removed alignment spaces |
| 108, 110 | E501 | Return dict literals in `call_model` exceeded 100 chars | Broken onto two lines each |
| 171, 183, 209 | E501 | Long `join()` / `print()` lines in `main` | Wrapped with parentheses |

#### `compare.py`

| Line(s) | Code | Description | Fix Applied |
|---------|------|-------------|-------------|
| 19–20 | E221 + E501 | `API_KEY  =` with alignment space; line 124 chars | Removed space, split across 3 lines |
| 32–49 | E501 | Five prompt strings exceeded 100 chars (up to 205 chars) | Wrapped as parenthesised implicit string concatenation |
| 39 | — | **Data corruption**: key was `"categ   …   ory"` (spaces inserted mid-word by linter) | Restored to `"category"` |
| 52–59 | E221 | Multiple spaces before `=` on ANSI constant block | Removed alignment spaces |
| 84–95 | E221 | Aligned spaces in `call_model` return dict keys (`"model":   `, `"id":      `, `data    =`) | Removed alignment spaces |
| 130–132 | E221 | `name  =`, `secs  =`, `bar2  =` in `run_comparison` | Removed alignment spaces |
| 212 | E501 | `save_results` function signature 122 chars | Wrapped arguments with closing `)` on its own line |
| 255–256 | F541 | Two `print(f"  …\n")` with no placeholders | Dropped `f` prefix |
| 290–291 | E501 | `input(f"Save full results…")` line 102 chars | Wrapped with outer parentheses |

### Final Result

```
$ python -m flake8 chat.py compare.py --max-line-length=100
$                                      ← zero violations
```

---

## Model Comparison Summary

See [model_comparison.md](model_comparison.md) for the full analysis. Quick reference:

| Metric | GPT-OSS 120B | Gemma 4 31B | Nemotron Nano 9B |
|--------|-------------|-------------|-----------------|
| Speed | 3rd (slowest) | 2nd | 1st (fastest) |
| Overall quality | 1st | 2nd | 3rd |
| Best for | Complex reasoning, code, creative | General Q&A, explanations | Fastest prototyping |
| Avg latency | ~12–25s | ~8–15s | ~4–8s |
| Avg response length | High | Medium | Low |
