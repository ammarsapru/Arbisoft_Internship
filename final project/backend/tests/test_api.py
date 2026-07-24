from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

from fastapi.testclient import TestClient

from backend.app.api.routes import router
from backend.app.main import app


class ApiTests(unittest.TestCase):
    def test_ui_api_contract_is_registered(self) -> None:
        registered = {
            getattr(route, "path", "")
            for route in router.routes
            if getattr(route, "path", "").startswith("/api/v1")
        }
        expected = {
            "/api/v1/health",
            "/api/v1/analysis",
            "/api/v1/analysis/github",
            "/api/v1/analyses",
            "/api/v1/analyses/{analysis_id}",
            "/api/v1/analyses/{analysis_id}/summary",
            "/api/v1/analyses/{analysis_id}/index",
            "/api/v1/analyses/{analysis_id}/index/rebuild",
            "/api/v1/analyses/{analysis_id}/conversation/latest",
            "/api/v1/analyses/{analysis_id}/source",
            "/api/v1/analyses/{analysis_id}/nodes/{node_id}/neighborhood",
            "/api/v1/analyses/{analysis_id}/nodes/{node_id}/usage",
            "/api/v1/analyses/{analysis_id}/tour",
            "/api/v1/analyses/{analysis_id}/tours/{tour_id}/answers",
            "/api/v1/analyses/{analysis_id}/architecture",
            "/api/v1/analyses/{analysis_id}/mission",
            "/api/v1/analyses/{analysis_id}/answer",
            "/api/v1/analyses/{analysis_id}/answer/compare",
            "/api/v1/analyses/{analysis_id}/journey/{node_id}",
            "/api/v1/analyses/{analysis_id}/compare/{base_analysis_id}",
            "/api/v1/analyses/{analysis_id}/issues",
            "/api/v1/analyses/{analysis_id}/issues/investigate",
            "/api/v1/analyses/{analysis_id}/issues/{issue_number}/timeline",
        }
        self.assertTrue(expected.issubset(registered), expected - registered)

    def test_health_exposes_diagnostic_mode(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/health", headers={"x-request-id": "health-test"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "health-test")
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("trace_functions", payload)
        self.assertIn("max_trace", payload)
        self.assertIn("clone_root", payload)

    def test_repository_path_cannot_escape_allowed_root(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/analysis",
                json={"repository_path": ".."},
                headers={"x-request-id": "escape-test"},
            )
        self.assertEqual(response.status_code, 403)

    def test_github_analysis_validates_then_analyzes_cloned_repository(self) -> None:
        with (
            patch(
                "backend.app.api.routes.github_cloner.clone",
                return_value=Path("backend/tests").resolve(),
            ) as clone,
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/v1/analysis/github",
                json={"repository_url": "https://github.com/example/project"},
                headers={"x-request-id": "github-analysis-test"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "github-analysis-test")
        self.assertEqual(response.json()["repository_name"], "project")
        self.assertGreater(response.json()["stats"]["files_parsed"], 0)
        clone.assert_called_once_with("https://github.com/example/project")

        with TestClient(app) as client:
            rejected = client.post(
                "/api/v1/analysis/github",
                json={"repository_url": "file:///C:/private/repository"},
            )
        self.assertEqual(rejected.status_code, 422)

    def test_analysis_session_supports_source_summary_and_neighborhood(self) -> None:
        with TestClient(app) as client:
            analysis_response = client.post(
                "/api/v1/analysis",
                json={"repository_path": "backend/tests"},
                headers={"x-request-id": "phase-one-analysis"},
            )
            self.assertEqual(analysis_response.status_code, 200)
            report = analysis_response.json()
            analysis_id = report["analysis_id"]
            self.assertTrue(analysis_id)

            sessions_response = client.get("/api/v1/analyses")
            self.assertEqual(sessions_response.status_code, 200)
            session = next(
                item for item in sessions_response.json()
                if item["analysis_id"] == analysis_id
            )
            self.assertEqual(session["repository_name"], "tests")
            self.assertGreater(session["files_parsed"], 0)

            summary_response = client.get(
                f"/api/v1/analyses/{analysis_id}/summary"
            )
            self.assertEqual(summary_response.status_code, 200)
            self.assertEqual(
                summary_response.json()["analysis_id"], analysis_id
            )

            index_response = client.get(
                f"/api/v1/analyses/{analysis_id}/index"
            )
            self.assertEqual(index_response.status_code, 200)
            self.assertEqual(index_response.json()["status"], "complete")
            self.assertEqual(
                index_response.json()["vectors"],
                index_response.json()["chunks"],
            )

            module = next(
                node
                for node in report["nodes"]
                if node["kind"] == "module"
                and node["span"]["path"] == "test_analyzer.py"
            )
            source_response = client.get(
                f"/api/v1/analyses/{analysis_id}/source",
                params={"path": "test_analyzer.py"},
            )
            self.assertEqual(source_response.status_code, 200)
            self.assertIn(
                "class RepositoryAnalyzerTests",
                source_response.json()["content"],
            )

            neighborhood_response = client.get(
                (
                    f"/api/v1/analyses/{analysis_id}/nodes/"
                    f"{module['id']}/neighborhood"
                ),
                params={"depth": 1},
            )
            self.assertEqual(neighborhood_response.status_code, 200)
            self.assertEqual(
                neighborhood_response.json()["center_node_id"], module["id"]
            )

            usage_response = client.get(
                f"/api/v1/analyses/{analysis_id}/nodes/{module['id']}/usage"
            )
            self.assertEqual(usage_response.status_code, 200)
            usage = usage_response.json()
            self.assertEqual(usage["symbol"]["node_id"], module["id"])
            self.assertIn("incoming", usage)
            self.assertIn("outgoing", usage)
            self.assertIn("related_files", usage)

            with patch(
                "backend.app.api.routes.RepositoryAgentService.available",
                new_callable=PropertyMock,
                return_value=False,
            ):
                answer_response = client.post(
                    f"/api/v1/analyses/{analysis_id}/answer",
                    json={"question": "Where is repository analysis tested?"},
                )
            self.assertEqual(answer_response.status_code, 503)
            self.assertIn("ANTHROPIC_API_KEY", answer_response.json()["detail"])

            journey_response = client.get(
                f"/api/v1/analyses/{analysis_id}/journey/{module['id']}",
                params={"max_steps": 5},
            )
            self.assertEqual(journey_response.status_code, 200)
            self.assertLessEqual(len(journey_response.json()["steps"]), 5)

            rejected_source = client.get(
                f"/api/v1/analyses/{analysis_id}/source",
                params={"path": "../../plan.md"},
            )
            self.assertEqual(rejected_source.status_code, 404)


if __name__ == "__main__":
    unittest.main()
