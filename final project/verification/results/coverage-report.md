# Human-readable coverage report

## Overall result

| Metric | Result | Required gate | Status |
|---|---:|---:|---|
| Line coverage | 78.8% | 70.0% combined branch-aware gate | PASS |
| Branch coverage | 62.0% | Included in combined coverage.py total | Measured |

The enforced pytest value is coverage.py's combined statement/branch result. The XML exposes line and branch rates separately, which is why neither individual row is a replacement for the command's final total.

## Files needing the most attention

| File | Line coverage | Branch coverage |
|---|---:|---:|
| `backend/app/processes.py` | 33.9% | 0.0% |
| `backend/app/agent/provider.py` | 41.2% | 19.4% |
| `backend/app/issues/service.py` | 48.2% | 14.3% |
| `backend/app/agent/issues.py` | 50.8% | 4.5% |
| `backend/app/api/routes.py` | 60.8% | 22.7% |
| `backend/app/mcp_server.py` | 63.0% | 0.0% |
| `backend/app/agent/onboarding.py` | 70.9% | 51.6% |
| `backend/app/graph/store.py` | 77.3% | 57.7% |
| `backend/app/observability.py` | 77.5% | 64.5% |
| `backend/app/agent/service.py` | 77.7% | 60.0% |
| `backend/app/repository_import.py` | 81.1% | 83.3% |
| `backend/app/agent/retrieval.py` | 84.2% | 74.4% |
| `backend/app/main.py` | 85.2% | 50.0% |
| `backend/app/graph/polyglot.py` | 87.0% | 71.5% |
| `backend/app/onboarding/service.py` | 88.3% | 76.9% |
| `backend/app/graph/analyzer.py` | 88.7% | 72.7% |
| `backend/app/agent/comparison.py` | 89.6% | 64.3% |
| `backend/app/config.py` | 89.9% | 75.0% |
| `backend/app/onboarding/questions.py` | 90.0% | 70.0% |
| `backend/app/indexing.py` | 90.0% | 78.6% |

## How to inspect details

Open `.waypoint-data/coverage-html/index.html` for annotated source lines. Red lines were missed; yellow lines were partially covered branches; green lines were executed.
