from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# Configure isolation before test modules import backend.app.config. Without this,
# temporary test sessions can evict real development analyses from the bounded store.
_TEST_STATE = tempfile.TemporaryDirectory(prefix="waypoint-pytest-")
_TEST_ROOT = Path(_TEST_STATE.name)
os.environ["WAYPOINT_STATE_PATH"] = str(_TEST_ROOT / "waypoint-test.sqlite3")
os.environ["ONBOARD_TRACE_PATH"] = str(_TEST_ROOT / "waypoint-test.jsonl")
os.environ["ONBOARD_TRACE_FILE"] = "0"
os.environ["WAYPOINT_PROVIDER_STARTUP_PROBE"] = "0"


_UNIT_TEST_MODULES = {
    "test_analyzer.py",
    "test_issues.py",
    "test_observability.py",
    "test_polyglot_analyzer.py",
    "test_provider.py",
    "test_questions.py",
    "test_repository_import.py",
}
_INTEGRATION_TEST_MODULES = {
    "test_agent.py",
    "test_api.py",
    "test_mcp_server.py",
    "test_model_comparison.py",
    "test_onboarding.py",
    "test_semantic_tools.py",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Make suite boundaries executable and reject silently unclassified tests."""
    for item in items:
        filename = Path(str(item.path)).name
        if filename in _UNIT_TEST_MODULES:
            item.add_marker(pytest.mark.unit)
        elif filename in _INTEGRATION_TEST_MODULES:
            item.add_marker(pytest.mark.integration)
        else:
            raise pytest.UsageError(
                f"Test module {filename!r} is not classified as unit or integration"
            )
