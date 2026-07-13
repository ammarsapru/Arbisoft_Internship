# Metrics Report

Generated: `2026-07-08T05:31:28`

## Evaluation Design

| Category | Prompts | Inspired by | What it tests |
|---|---:|---|---|
| Mathematical Reasoning | 10 | GSM8K, MATH benchmark | Multi-step arithmetic, algebra, geometry, combinatorics |
| Logical & Deductive Reasoning | 10 | BIG-Bench, LogiQA, Winogrande | Syllogisms, conditionals, puzzles, sequence patterns, set logic |
| Code Generation & Algorithmic Problem Solving | 10 | HumanEval, MBPP, LeetCode-style benchmarks | Algorithm implementation, correctness, edge-case handling, code clarity |
| Factual & Technical Knowledge | 10 | MMLU (CS track), TriviaQA | Computer science fundamentals — tests precision and conciseness of recall, not essay-writing ability |
| Instruction Following & Constraint Adherence | 10 | IFEval (Google), FollowBench | Precise format compliance, constraint counting, and label adherence — tests whether models follow multi-part rules without drifting |

## Fairness Constraints

| Constraint | Value | Why |
|---|---|---|
| `max_tokens` | `600` | Caps response length — prevents verbosity bias (HELM) |
| `temperature` | `0.0` | Greedy decoding — deterministic, reproducible (GSM8K standard) |
| System prompt | Identical for all models | Removes prompt-sensitivity variance (±10 pp on MMLU) |
| Output constraint | Baked into every prompt | Structurally comparable responses (IFEval methodology) |
| Cultural neutrality | No region-specific content | Avoids the 19 pp accuracy drop on non-US GSM8K variants |

## Run Configuration

- Prompts evaluated: `1`
- Model calls attempted: `3`
- Retry attempts on 429: `2`
- Delay between calls: `2.0` s

## Overall Model Metrics

| Model | OK / Calls | Errors | Avg Latency (s) | Avg TTFT (s) | Avg Tokens | Gen Throughput (tok/s) | Constraint OK |
|---|---:|---:|---:|---:|---:|---:|---:|
| GPT-OSS 120B | 0 / 1 | 1 | n/a | n/a | n/a | n/a | n/a |
| Gemma 4 31B-IT | 0 / 1 | 1 | n/a | n/a | n/a | n/a | n/a |
| Nemotron Nano 9B | 0 / 1 | 1 | n/a | n/a | n/a | n/a | n/a |

## Latency by Category (avg seconds, ok/calls)

| Category | GPT-OSS 120B | Gemma 4 31B-IT | Nemotron Nano 9B |
|---|---:|---:|---:|
| Mathematical Reasoning | n/a (0/1 ok) | n/a (0/1 ok) | n/a (0/1 ok) |
| Logical & Deductive Reasoning | n/a (0/0 ok) | n/a (0/0 ok) | n/a (0/0 ok) |
| Code Generation & Algorithmic Problem Solving | n/a (0/0 ok) | n/a (0/0 ok) | n/a (0/0 ok) |
| Factual & Technical Knowledge | n/a (0/0 ok) | n/a (0/0 ok) | n/a (0/0 ok) |
| Instruction Following & Constraint Adherence | n/a (0/0 ok) | n/a (0/0 ok) | n/a (0/0 ok) |

## Throughput by Category (completion tok/s)

| Category | GPT-OSS 120B | Gemma 4 31B-IT | Nemotron Nano 9B |
|---|---:|---:|---:|
| Mathematical Reasoning | n/a | n/a | n/a |
| Logical & Deductive Reasoning | n/a | n/a | n/a |
| Code Generation & Algorithmic Problem Solving | n/a | n/a | n/a |
| Factual & Technical Knowledge | n/a | n/a | n/a |
| Instruction Following & Constraint Adherence | n/a | n/a | n/a |

## Constraint / Correctness Compliance by Category

(math_reasoning/code_generation/instruction_following = real correctness checks; logical_reasoning/factual_knowledge = format shape only — see code comments)

| Category | GPT-OSS 120B | Gemma 4 31B-IT | Nemotron Nano 9B |
|---|---:|---:|---:|
| Mathematical Reasoning | n/a | n/a | n/a |
| Logical & Deductive Reasoning | n/a | n/a | n/a |
| Code Generation & Algorithmic Problem Solving | n/a | n/a | n/a |
| Factual & Technical Knowledge | n/a | n/a | n/a |
| Instruction Following & Constraint Adherence | n/a | n/a | n/a |

## Errors

| # | Category | Model | Error (truncated) |
|---:|---|---|---|
| 1 | math_reasoning | GPT-OSS 120B | 429 Client Error: Too Many Requests for url: https://openrouter.ai/api/v1/chat/completions |
| 1 | math_reasoning | Gemma 4 31B-IT | 429 Client Error: Too Many Requests for url: https://openrouter.ai/api/v1/chat/completions |
| 1 | math_reasoning | Nemotron Nano 9B | Empty response content |
