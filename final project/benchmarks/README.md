# External repository benchmarks

This suite validates the analyzer against shallow clones of established Python
repositories. Clones live outside the application workspace by default at
`C:\tmp\waypoint-benchmarks`.

The benchmark verifies:

- Parse success and performance
- Unique, stable node and edge identities
- Valid graph endpoints
- Valid source spans
- Evidence-status invariants
- Correct package names for flat and `src/` layouts
- Known architectural modules, classes, methods, and functions
- First-party import resolution

Run:

```powershell
.\.venv\Scripts\python.exe benchmarks\run_repositories.py `
  --fixtures-root C:\tmp\waypoint-benchmarks `
  --output benchmarks\results
```

Use `--repository flask` to run one fixture. Results are written as JSON and
Markdown so changes in analyzer quality can be reviewed rather than inferred
from node counts alone.

## Retrieval benchmark

The local retrieval benchmark measures file Recall@5, Recall@10, mean reciprocal
rank, indexing time, and query latency against known evidence files:

```powershell
.\.venv\Scripts\python.exe benchmarks\run_retrieval.py `
  --repository . `
  --output benchmarks\results\retrieval-latest.json
```

Add repository-specific cases by supplying another JSON file with `--cases`.
