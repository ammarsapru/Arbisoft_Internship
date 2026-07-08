# Arbisoft Internship

## Overview

This repository contains work completed during an internship at Arbisoft. The internship focuses on building foundational knowledge in Artificial Intelligence and Machine Learning, covering core concepts, algorithms, and practical implementations.

## Internship Scope

The internship covers AI/ML basics, including but not limited to:

- Fundamentals of machine learning
- Data structures and algorithms relevant to AI/ML
- Algorithm complexity and performance analysis
- Graph theory and traversal algorithms
- Sorting and searching algorithms
- Data manipulation and analysis with NumPy and Pandas
- Relational database design and SQL table relationships
- Hands-on SQL querying — schema design, joins, grouping, and subqueries
- LLM API integration and multi-model benchmarking
- Retrieval-augmented generation (RAG) — embeddings, vector search, and retrieval evaluation
- Structured LLM output validation and hallucination detection
- Agentic AI — tool use, memory, hooks, and multi-step agents with the Claude Agent SDK

## Repository Structure

### Assignments

Structured weekly assignments applying the concepts covered during the internship. Each week contains a self-contained project with its own README, code, tests, and documentation.

| Week | Topic | Key Deliverables | Status |
|---|---|---|:---:|
| [Week 1](Assignments/week1/) | Concrete Compressive Strength — regression and classification ML pipeline | Notebook, pytest tests, prompts log, evaluation metrics, confusion matrix | ✅ |
| [Week 2](Assignments/week2/) | OpenRouter CLI chat and multi-model benchmarking | CLI chat app, comparison tool, written model-quality analysis, flake8-clean code | ✅ |
| [Week 3](Assignments/week3/) | LangChain + Ollama RAG pipeline — structured output and hallucination testing | Retrieval eval (5 metrics × 2 embedding models), Pydantic-validated generation pipeline with a self-check retry loop, 12-question adversarial hallucination eval, 60-test suite | ✅ |
| [Week 4](Assignments/week4/) | Agentic AI with the Claude Agent SDK | Research agent (web search, memory, hooks, file-read plugin), travel-planning agent (flights/hotels, PDF intake, clarifying questions), unit tests | ✅ |

### Week 2 — OpenRouter CLI Chat & Model Comparison

A command-line chat application and benchmarking tool built on the [OpenRouter](https://openrouter.ai) API, comparing three free-tier LLMs side-by-side.

| File | Purpose |
|------|---------|
| [`chat.py`](Assignments/week2/chat.py) | Interactive CLI chat — single model or all 3 in parallel |
| [`compare.py`](Assignments/week2/compare.py) | Sends the same prompt to all 3 models; reports speed, token count, full output |
| [`model_comparison.md`](Assignments/week2/model_comparison.md) | Written analysis: speed ranking, quality scores per task type, use-case fit |

**Models compared:**

| Model | Provider | Params |
|-------|----------|--------|
| `openai/gpt-oss-120b:free` | OpenAI (OSS) | ~120B |
| `google/gemma-4-31b-it:free` | Google DeepMind | ~31B |
| `nvidia/nemotron-nano-9b-v2:free` | NVIDIA | ~9B |

**Code quality:** Both Python files lint clean under `flake8 --max-line-length=100` (0 violations). See [Assignments/week2/README.md](Assignments/week2/README.md) for the full list of issues found and resolved.

### Week 3 — LangChain + Ollama RAG Pipeline

A retrieval-augmented generation pipeline over NIKE's fiscal 2023 10-K filing, built entirely on local models via [Ollama](https://ollama.com) (no cloud LLM API). Treats LLM output as untrusted: retrieval quality is measured against hand-verified ground truth, generated answers are schema-validated, and hallucinations are actively tested for rather than assumed away.

| Component | Purpose |
|---|---|
| [`retrieval_eval.py`](Assignments/week3/retrieval_eval.py) | Compares two embedding models (`qwen3-embedding:0.6b`, `snowflake-arctic-embed:latest`) on hit_rate / precision / recall / MRR / NDCG @ k |
| [`rag_pipeline.py`](Assignments/week3/rag_pipeline.py) | System+user prompt structure, Pydantic-validated structured JSON output, and a bounded self-check retry loop that catches unverifiable or off-topic answers before falling back to a deterministic refusal |
| [`generation_eval.py`](Assignments/week3/generation_eval.py) | Measures faithfulness, correctness, and relevance of generated answers against 14 ground-truth questions |
| [`hallucination_eval.py`](Assignments/week3/hallucination_eval.py) | Runs 12 adversarial, out-of-scope questions across 4 tiers of increasing topic distance from the source document, to measure refusal vs. hallucination rate |
| [`tests/`](Assignments/week3/tests/) | 53 hermetic unit tests + 7 live LLM contract tests (60 total) |

**Key result:** two independent, measured fixes — restructuring the prompt into a system/user split, then adding a citations-required check plus a retry-with-feedback self-check loop — took the pipeline from a 0% refusal rate / 58% hallucination rate to **100% refusal / 0% hallucination** on the adversarial question set. The full before/after evidence for every change is in [`docs/tracker.txt`](Assignments/week3/docs/tracker.txt). See [Assignments/week3/README.md](Assignments/week3/README.md) for the full architecture, setup, and results.

### Week 4 — Agentic AI (Claude Agent SDK)

Hands-on work with the Claude Agent SDK: tool use, session memory, hooks, and multi-step agents.

| Folder / file | What it is |
|---|---|
| [`first-agent/`](Assignments/week4/first-agent/) | First experiments with the Claude Agent SDK: `query()` basics, message types, built-in WebSearch, remote MCP server (SerpApi) |
| [`research-agent/`](Assignments/week4/research-agent/) | Research agent with a SerpApi web-search skill, session memory, timestamped tool-call logging hook, `.txt`/`.pdf` file-read plugin, and a multi-hop demo |
| [`travel-agent/`](Assignments/week4/travel-agent/) | Flight research agent + interactive CLI: Google Flights / Google Hotels tools with constraint parameters (budget, dates, trip type), PDF/manual trip intake, clarifying questions, memory, hook logging |
| [`custom_api.py`](Assignments/week4/custom_api.py) | Original flight-search tool attempt — kept for reference; rewritten properly in `travel-agent/travel_agent.py` |
| [`topics.txt`](Assignments/week4/topics.txt) | Study notes covering all week-4 lecture topics, mapped to where each concept is implemented |

See [Assignments/week4/README.md](Assignments/week4/README.md) for setup and requirements.

### DSA_PRACTISE

This folder contains implementations of core data structures and algorithms in Python. These serve as the foundation for understanding how AI/ML algorithms work under the hood.

**Sorting Algorithms**
- Bubble Sort
- Selection Sort
- Insertion Sort
- Merge Sort
- Quick Sort

**Data Structures**
- Linked Lists
- Binary Trees

**Graph Algorithms**
- Undirected graphs using adjacency matrix
- Depth First Search (DFS)
- DFS on directed graphs
- Cyclic detection
- Dijkstra's algorithm (directed and undirected)

**Other**
- Fibonacci sequence implementations

### numpy_pandas_relationships

This folder covers data manipulation with NumPy and Pandas alongside relational database design in SQL.

**NumPy** (`numpy_tutorial.ipynb`)
- Array creation, data types, and memory layout
- Multi-dimensional arrays — shape, ndim, indexing, and slicing
- Element-wise operations, broadcasting, and scalar arithmetic
- Reshaping, flattening, transposing, and concatenation
- Axis-based aggregations (sum, mean, std) across 1D, 2D, and 3D arrays
- Linear algebra — dot product, determinant, inverse, eigenvalues
- Practical examples: image brightness simulation and student score analysis

**Pandas** (`Untitled-1.ipynb`, `pandas_practise.py`)
- DataFrames and Series — loading CSV data with `pd.read_csv`
- DataFrame exploration — `head`, `tail`, `info`, `describe`, `columns`, `index`
- Column selection, `iloc` row access, and boolean filtering

**SQL Relationships** (`relationships.sql`, `many_to_many.sql`)
- 12-table SQL Server schema demonstrating all relationship types
- One-to-One (1:1) — enforced via a `UNIQUE` foreign key
- One-to-Many (1:M) — e.g., Departments → Employees, Customers → Orders
- Many-to-Many (M:M) — Orders ↔ Products via a junction table

**Sample Data** (`orders.csv`)
- 40-row synthetic e-commerce dataset used across the Pandas exercises

### sql practise

Hands-on SQL practice in two parts — see [`sql practise/README.md`](sql%20practise/README.md) for full details.

**Palmer Penguin database** (`schema.sql`, `seed_data.sql`, `data/*.csv`)
- A 4-table relational database (`islands`, `species`, `researchers`, `observations`) built on the real Palmer Penguins dataset
- `SCENARIO.md`, `SETUP.md` (SQLite / PostgreSQL), 20 graded exercises in `EXERCISES.md`, and full solutions in `ANSWER_KEY.sql`
- Practice across the full lifecycle: `CREATE` → `INSERT` → `SELECT`/`JOIN`/`GROUP BY`/subqueries → `DELETE`

**Table relationships** (`relationships.sql`, `many_to_many.sql`)
- A 12-table SQL Server schema demonstrating One-to-One, One-to-Many, and Many-to-Many relationships
