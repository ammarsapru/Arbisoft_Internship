from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.observability import register_function_hook, traced


class FunctionHookTests(unittest.TestCase):
    def test_traced_function_emits_pre_post_and_error_hooks(self) -> None:
        events: list[tuple[str, dict]] = []
        unregister = register_function_hook(
            lambda phase, payload: events.append((phase, dict(payload)))
        )

        @traced("test.hooked")
        def hooked(value: int, fail: bool = False) -> dict[str, int]:
            if fail:
                raise ValueError("expected failure")
            return {"produced": value * 2}

        fake_settings = SimpleNamespace(trace_functions=True, log_value_limit=1200)
        try:
            with patch("backend.app.observability.settings", fake_settings):
                self.assertEqual(hooked(3), {"produced": 6})
                with self.assertRaises(ValueError):
                    hooked(4, fail=True)
        finally:
            unregister()

        self.assertEqual([phase for phase, _ in events], ["pre", "post", "pre", "error"])
        self.assertEqual(events[0][1]["arguments"]["value"], 3)
        self.assertEqual(events[1][1]["result"], {"produced": 6})
        self.assertEqual(events[-1][1]["exception_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
