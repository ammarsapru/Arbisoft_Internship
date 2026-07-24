# Coverage gate

The required threshold is **70% over `backend.app` with branch coverage enabled**.
`pyproject.toml` enforces the gate with `pytest-cov`; a run fails when total coverage is
below 70%.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The verified baseline on July 24, 2026 is:

- 73 tests passed, including HTML/CSS, session-restoration, and model-comparison tests;
- 75.25% combined branch-aware backend coverage;
- 78.8% line coverage and 62.0% branch coverage when viewed separately;
- XML output: `.waypoint-data/coverage.xml`.
- annotated source report: `.waypoint-data/coverage-html/index.html`;
- readable summary: `verification/results/coverage-report.md`.

The percentage must be regenerated after changes. The XML file is an artifact, not a
source file, and remains under application-managed data.

Focused test commands can bypass the global threshold while debugging:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_provider.py `
  --no-cov
```

The final full-suite command must never use `--no-cov`.

The whole-backend result is not used as a substitute for the rubric's core-logic target.
`verification/core-features.json` defines five core product features, and
`core_coverage_report.py` fails unless every feature and the weighted aggregate are each at
least 70%. The current core aggregate is 82.81%; the unified detailed table is embedded in
`verification/results/coverage-report.md`.

Convert an existing XML artifact into Markdown with:

```powershell
.\.venv\Scripts\python.exe -m verification.scripts.coverage_report
```
