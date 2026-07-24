from __future__ import annotations

import os
import tempfile
from pathlib import Path


# Configure isolation before test modules import backend.app.config. Without this,
# temporary test sessions can evict real development analyses from the bounded store.
_TEST_STATE = tempfile.TemporaryDirectory(prefix="waypoint-pytest-")
_TEST_ROOT = Path(_TEST_STATE.name)
os.environ["WAYPOINT_STATE_PATH"] = str(_TEST_ROOT / "waypoint-test.sqlite3")
os.environ["ONBOARD_TRACE_PATH"] = str(_TEST_ROOT / "waypoint-test.jsonl")
os.environ["ONBOARD_TRACE_FILE"] = "0"
os.environ["WAYPOINT_PROVIDER_STARTUP_PROBE"] = "0"
