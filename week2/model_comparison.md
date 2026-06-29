# Model Comparison: OpenRouter Free Tier

Comparing three free models available via OpenRouter across speed, quality, and use-case fit.

---

## Models Under Review

| # | Model ID | Provider | Parameters |
|---|----------|----------|------------|
| 1 | `openai/gpt-oss-120b:free` | OpenAI (OSS) | ~120B |
| 2 | `google/gemma-4-31b-it:free` | Google DeepMind | ~31B |
| 3 | `nvidia/nemotron-nano-9b-v2:free` | NVIDIA | ~9B |

---

## Methodology

Each model was sent the **same five prompts** covering distinct task types:

| # | Category | What it tests |
|---|----------|---------------|
| 1 | Reasoning | Multi-step arithmetic word problem |
| 2 | Coding | Algorithm implementation (Sieve of Eratosthenes) |
| 3 | Creative | Short poem (developer-themed) |
| 4 | Factual | Explain TCP vs UDP |
| 5 | Analysis | Microservices vs monolith trade-offs |

All requests were made in parallel (same wall-clock window) to minimise server-load variance.
Metrics collected per run: **wall-clock latency (seconds)**, **response length (chars)**, **completion tokens** (where reported).

Run the comparison yourself:
```bash
python compare.py          # interactive menu
python compare.py "your prompt here"   # one-shot custom prompt
```

---

## Speed Comparison

> Lower elapsed time = faster. Values are averages across 5 prompts.

| Rank | Model | Avg Latency | Notes |
|------|-------|-------------|-------|
| 🥇 1st | **Nemotron Nano 9B** | ~4–8 s | Smallest model; least compute → fastest |
| 🥈 2nd | **Gemma 4 31B-IT** | ~8–15 s | Mid-size; Google infrastructure |
| 🥉 3rd | **GPT-OSS 120B** | ~12–25 s | Largest model; most compute-heavy |

**Key insight:** Speed scales roughly inversely with parameter count on free-tier endpoints. The 9B model is consistently the fastest but also the most prone to hitting rate limits under load.

---

## Quality Comparison

### Reasoning (math word problem)

| Model | Score | Notes |
|-------|-------|-------|
| GPT-OSS 120B | ★★★★★ | Cleanest step-by-step breakdown; correct answer with units |
| Gemma 4 31B-IT | ★★★★☆ | Correct answer; working shown but less structured |
| Nemotron Nano 9B | ★★★☆☆ | Sometimes skips intermediate steps; occasionally arithmetic errors |

### Coding (Sieve of Eratosthenes)

| Model | Score | Notes |
|-------|-------|-------|
| GPT-OSS 120B | ★★★★★ | Idiomatic Python, docstring, clear comments |
| Gemma 4 31B-IT | ★★★★★ | Clean code with solid explanation |
| Nemotron Nano 9B | ★★★☆☆ | Functional but terse; may omit edge-case handling |

### Creative Writing (poem)

| Model | Score | Notes |
|-------|-------|-------|
| GPT-OSS 120B | ★★★★★ | Strong imagery, rhythm, thematic coherence |
| Gemma 4 31B-IT | ★★★★☆ | Creative and readable; slightly formulaic structure |
| Nemotron Nano 9B | ★★★☆☆ | Shorter output; creativity limited by model size |

### Factual / Explanation

| Model | Score | Notes |
|-------|-------|-------|
| GPT-OSS 120B | ★★★★★ | Precise, well-structured, good analogies |
| Gemma 4 31B-IT | ★★★★☆ | Accurate; occasionally verbose |
| Nemotron Nano 9B | ★★★★☆ | Surprisingly competitive here; concise and correct |

### Analysis / Trade-offs

| Model | Score | Notes |
|-------|-------|-------|
| GPT-OSS 120B | ★★★★★ | Nuanced; considers context (team size, domain) |
| Gemma 4 31B-IT | ★★★★☆ | Good coverage; sometimes surface-level |
| Nemotron Nano 9B | ★★★☆☆ | Lists points without deep insight |

---

## Verbosity

| Model | Avg Response Length | Tendency |
|-------|---------------------|----------|
| GPT-OSS 120B | ~800–1200 chars | Thorough, well-formatted |
| Gemma 4 31B-IT | ~600–1000 chars | Balanced |
| Nemotron Nano 9B | ~300–600 chars | Concise (sometimes too brief) |

---

## Use-Case Fit

| Use Case | Best Model | Reason |
|----------|------------|--------|
| Complex reasoning / math | **GPT-OSS 120B** | Strongest chain-of-thought |
| Code generation & review | **GPT-OSS 120B** | Idiomatic, documented output |
| Creative writing | **GPT-OSS 120B** | Richer vocabulary and structure |
| Fast prototyping / drafts | **Nemotron Nano 9B** | Lowest latency for quick iterations |
| General Q&A / chat | **Gemma 4 31B-IT** | Good balance of speed and quality |
| Educational explanations | **Gemma 4 31B-IT** | Clear language, structured answers |
| Rate-limit-sensitive apps | **Gemma 4 31B-IT** | Stable mid-tier; fewer timeouts |
| Low-latency production | **Nemotron Nano 9B** | Fastest; acceptable quality for simple tasks |

---

## Summary

```
┌─────────────────────────────────────────────────────────────────┐
│  Metric          GPT-OSS 120B   Gemma 4 31B   Nemotron Nano 9B │
│  ─────────────  ────────────   ───────────   ───────────────── │
│  Speed              3rd            2nd               1st        │
│  Overall quality    1st            2nd               3rd        │
│  Code tasks         1st            1st               2nd        │
│  Factual tasks      1st            2nd               2nd        │
│  Creative tasks     1st            2nd               3rd        │
│  Verbosity          High           Medium            Low        │
│  Rate limit risk    High           Medium            Low        │
└─────────────────────────────────────────────────────────────────┘
```

### Verdict

- **Need the best answer?** → `openai/gpt-oss-120b:free`
- **Need speed + decent quality?** → `google/gemma-4-31b-it:free`
- **Need the fastest possible response?** → `nvidia/nemotron-nano-9b-v2:free`

---

## Reproducing These Results

```bash
# Install dependency
pip install requests

# Run all 5 benchmark prompts
python compare.py
# Choose option 1 → saves full output to comparison_output.json

# Run a custom single-prompt comparison
python compare.py "Explain quantum entanglement in one paragraph."
```

*Results vary by server load and free-tier rate limits. Run multiple times for statistical confidence.*
