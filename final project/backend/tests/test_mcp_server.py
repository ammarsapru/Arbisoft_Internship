from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.mcp_server import clone_and_analyze_github_repository, mcp


class McpServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_exposes_safe_repository_capabilities(self) -> None:
        tool_names = {tool.name for tool in await mcp.list_tools()}
        self.assertTrue({
            "analyze_local_repository",
            "search_repository",
            "read_source",
            "find_symbols",
            "get_repository_overview",
            "get_dependency_impact",
            "get_index_status",
            "ask_repository",
        }.issubset(tool_names))
        resource_uris = {
            str(resource.uriTemplate)
            for resource in await mcp.list_resource_templates()
        }
        self.assertTrue(any("summary" in uri for uri in resource_uris))
        prompt_names = {prompt.name for prompt in await mcp.list_prompts()}
        self.assertIn("explain_repository", prompt_names)

    def test_github_tool_passes_validated_repository_name_to_analysis(self) -> None:
        with (
            patch(
                "backend.app.mcp_server.GitHubRepositoryCloner.clone",
                return_value=Path("backend/tests").resolve(),
            ),
            patch("backend.app.mcp_server._analyze", return_value={"ok": True}) as analyze,
        ):
            result = clone_and_analyze_github_repository(
                "https://github.com/example/project"
            )
        self.assertEqual(result, {"ok": True})
        analyze.assert_called_once_with(Path("backend/tests").resolve(), "project")


if __name__ == "__main__":
    unittest.main()
