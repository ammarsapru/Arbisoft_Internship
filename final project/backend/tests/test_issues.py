from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.graph.analyzer import RepositoryAnalyzer
from backend.app.agent.issues import FindingStore
from backend.app.graph.models import SourceSpan
from backend.app.graph.store import analysis_sessions
from backend.app.issues.models import ProposedIssue
from backend.app.issues.service import GitHubIssueService, repository_identity


class GitHubIssueServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / ".waypoint-managed").write_text(
            "https://github.com/example/project.git", encoding="utf-8"
        )
        (self.root / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        report = RepositoryAnalyzer().analyze(self.root)
        stored = analysis_sessions.create(self.root, report)
        self.session = analysis_sessions.get(stored.analysis_id)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_repository_identity_uses_managed_clone_marker(self) -> None:
        self.assertEqual(repository_identity(self.root), "example/project")

    def test_workspace_filters_pull_requests_from_issue_results(self) -> None:
        issue = {
            "number": 7,
            "title": "A real issue",
            "state": "open",
            "html_url": "https://github.com/example/project/issues/7",
            "user": {"login": "maintainer"},
            "labels": [{"name": "bug"}],
            "assignees": [],
            "comments": 2,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "closed_at": None,
        }
        pull_request = dict(issue, number=8, pull_request={"url": "example"})
        service = GitHubIssueService(self.session)
        with patch.object(service, "_request", return_value=[issue, pull_request]):
            report = service.workspace()
        self.assertTrue(report.github_connected)
        self.assertEqual(report.repository, "example/project")
        self.assertEqual([item.number for item in report.github_issues], [7])

    def test_ai_findings_restore_from_sqlite(self) -> None:
        database = self.root / "findings.sqlite3"
        finding = ProposedIssue(
            id="finding-1",
            source="ai_finding",
            severity="medium",
            category="testing",
            title="Missing boundary coverage",
            explanation="The boundary has no focused test.",
            confidence=0.8,
            evidence=[SourceSpan(
                path="app.py", start_line=1, start_column=0,
                end_line=2, end_column=0,
            )],
            suggested_approach=["Add a focused test", "Run the suite"],
        )
        FindingStore(database).put(self.session.id, [finding])
        self.assertEqual(
            FindingStore(database).get(self.session.id), [finding]
        )


if __name__ == "__main__":
    unittest.main()
