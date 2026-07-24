# Tested evidence

## Unit tests

Unit tests cover graph models, Python and polyglot analyzers, retrieval/vector scoring,
provider adapters, model routing, output validation, memory, observability hooks,
repository URL validation, onboarding questions, and issue synthesis.

Relevant files live in `backend/tests/test_*.py`. Model calls are replaced with typed
fixtures so unit tests are repeatable and free.

## Integration tests

Integration tests combine real FastAPI routes, temporary repositories, repository
analysis, SQLite session/index persistence, source reads, graph queries, conversation
state, and MCP functions. They validate component boundaries without external models.

## Browser E2E

Playwright checks the complete browser layout and HTTP integration. Static repository
analysis is real; model endpoints are mocked in the deterministic browser suite so CI
does not depend on provider availability. The separate live scenario covers real model
behavior.

## Commands

```powershell
# Unit + integration + enforced coverage
.\.venv\Scripts\python.exe -m pytest

# Frontend typecheck and production bundle
Set-Location frontend
npm.cmd run build
Set-Location ..

# Browser E2E; start the production server on port 8766 first
npm.cmd --prefix frontend run test:e2e
```

This separation is intentional: deterministic tests prove application correctness;
live evaluation proves provider and agent behavior.
