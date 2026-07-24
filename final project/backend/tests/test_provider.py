from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app.agent.provider import (
    ModelProviderRouter,
    OpenRouterMessages,
    ProviderMessages,
    is_billing_or_capacity_error,
)


class BillingError(RuntimeError):
    status_code = 402


class ModelProviderTests(unittest.TestCase):
    def test_billing_and_capacity_errors_are_recognized(self) -> None:
        self.assertTrue(is_billing_or_capacity_error(BillingError("payment required")))
        self.assertTrue(is_billing_or_capacity_error(RuntimeError("credit balance is low")))
        self.assertTrue(is_billing_or_capacity_error(RuntimeError("rate limit exceeded")))
        self.assertFalse(is_billing_or_capacity_error(ValueError("invalid tool input")))

    def test_runtime_billing_failure_switches_to_claude_code(self) -> None:
        router = ModelProviderRouter()
        router.active_provider = "anthropic-api"
        router._initialized = True
        api = SimpleNamespace(
            messages=SimpleNamespace(create=Mock(side_effect=BillingError("no credits")))
        )
        fallback_response = SimpleNamespace(content=[SimpleNamespace(type="tool_use")])
        router._claude_code.messages.create = Mock(return_value=fallback_response)

        def activate(reason: str, exc: BaseException, *, probe: bool) -> None:
            self.assertIn("billing", reason)
            self.assertIsInstance(exc, BillingError)
            self.assertFalse(probe)
            router.active_provider = "claude-code"

        with patch.object(router, "_anthropic_client", return_value=api), patch.object(
            router, "activate_claude_code", side_effect=activate
        ):
            response = ProviderMessages(router).create(messages=[])

        self.assertIs(response, fallback_response)
        router._claude_code.messages.create.assert_called_once_with(messages=[])

    def test_non_capacity_model_error_is_not_hidden_by_fallback(self) -> None:
        router = ModelProviderRouter()
        router.active_provider = "anthropic-api"
        api = SimpleNamespace(
            messages=SimpleNamespace(create=Mock(side_effect=ValueError("bad request")))
        )
        with patch.object(router, "_anthropic_client", return_value=api):
            with self.assertRaisesRegex(ValueError, "bad request"):
                ProviderMessages(router).create(messages=[])

    def test_openrouter_adapter_translates_tools_and_response(self) -> None:
        configured = SimpleNamespace(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.example/api/v1",
            openrouter_timeout_seconds=30,
            agent_max_output_tokens=2000,
        )
        http_response = Mock(status_code=200, text="")
        http_response.json.return_value = {
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "function": {
                            "name": "find_symbols",
                            "arguments": '{"query":"router"}',
                        },
                    }],
                },
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 14, "cost": 0},
        }
        with patch("backend.app.agent.provider.settings", configured), patch(
            "backend.app.agent.provider.httpx.post", return_value=http_response
        ) as post:
            response = OpenRouterMessages().create(
                _waypoint_model="cohere/north-mini-code:free",
                _waypoint_role="investigation",
                max_tokens=500,
                system="Investigate with tools.",
                messages=[{"role": "user", "content": "Find the router."}],
                tools=[{
                    "name": "find_symbols",
                    "description": "Find symbols.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }],
                tool_choice={"type": "auto"},
            )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "cohere/north-mini-code:free")
        self.assertEqual(payload["tools"][0]["function"]["name"], "find_symbols")
        self.assertEqual(response.content[0].name, "find_symbols")
        self.assertEqual(response.content[0].input, {"query": "router"})
        self.assertEqual(response.waypoint_role, "investigation")
        self.assertEqual(response.usage.input_tokens, 120)

    def test_dual_router_sends_forced_submission_to_synthesis_model(self) -> None:
        configured = SimpleNamespace(
            model_architecture="dual",
            investigation_provider="openrouter",
            investigation_model="cohere/north-mini-code:free",
            synthesis_provider="claude-code",
            synthesis_model="claude-fable-5",
        )
        router = ModelProviderRouter()
        expected = SimpleNamespace(content=[])
        router._claude_code.messages.create = Mock(return_value=expected)
        with patch("backend.app.agent.provider.settings", configured):
            response = ProviderMessages(router).create(
                messages=[],
                tool_choice={"type": "tool", "name": "submit_answer"},
            )

        self.assertIs(response, expected)
        routed = router._claude_code.messages.create.call_args.kwargs
        self.assertEqual(routed["_waypoint_role"], "synthesis")
        self.assertEqual(routed["_waypoint_model"], "claude-fable-5")


if __name__ == "__main__":
    unittest.main()
