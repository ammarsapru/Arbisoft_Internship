from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.graph.analyzer import RepositoryAnalyzer
from backend.app.onboarding.models import (
    ChallengeAnswer,
    DeveloperRole,
    GroundedQuestion,
    TourRequest,
)
from backend.app.onboarding.service import OnboardingService, TourStateStore, tour_states


class OnboardingServiceTests(unittest.TestCase):
    def test_two_hour_onboarding_budget_is_supported(self) -> None:
        self.assertEqual(TourRequest(minutes=120).minutes, 120)
        with self.assertRaises(ValueError):
            TourRequest(minutes=121)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        package = self.root / "app"
        tests = self.root / "tests"
        package.mkdir()
        tests.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "auth.py").write_text(
            "def verify_token(token: str) -> bool:\n"
            "    return bool(token)\n",
            encoding="utf-8",
        )
        (package / "routes.py").write_text(
            "from app.auth import verify_token\n\n"
            "def login(token: str) -> bool:\n"
            "    return verify_token(token)\n",
            encoding="utf-8",
        )
        (tests / "test_auth.py").write_text(
            "from app.auth import verify_token\n\n"
            "def test_verify():\n"
            "    assert verify_token('token')\n",
            encoding="utf-8",
        )
        self.report = RepositoryAnalyzer().analyze(self.root).model_copy(
            update={"analysis_id": "test-analysis"}
        )
        self.service = OnboardingService(self.report)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_role_specific_tours_are_grounded_and_different(self) -> None:
        security = self.service.plan_tour(
            TourRequest(role=DeveloperRole.SECURITY, goal="Review authentication")
        )
        qa = self.service.plan_tour(
            TourRequest(role=DeveloperRole.QA, goal="Understand test coverage")
        )
        self.assertTrue(security.steps)
        self.assertTrue(all(step.evidence for step in security.steps))
        self.assertNotEqual(
            [step.node_id for step in security.steps],
            [step.node_id for step in qa.steps],
        )

    def test_challenge_updates_mastery_score(self) -> None:
        plan = self.service.plan_tour(
            TourRequest(role=DeveloperRole.BACKEND, goal="Learn request routing")
        )
        challenge = next(
            step.challenge for step in plan.steps if step.challenge is not None
        )
        correct_node = next(
            step.node_id
            for step in plan.steps
            if step.challenge and step.challenge.id == challenge.id
        )
        result = tour_states.answer(
            plan.id,
            ChallengeAnswer(
                challenge_id=challenge.id,
                selected_node_id=correct_node,
            ),
        )
        self.assertTrue(result.correct)
        self.assertEqual(result.score, 1.0)
        self.assertIn(correct_node, result.mastered_node_ids)

    def test_tour_state_restores_from_sqlite(self) -> None:
        database = self.root / "tour-state.sqlite3"
        first = TourStateStore(path=database)
        plan = self.service.plan_tour(
            TourRequest(role=DeveloperRole.BACKEND, goal="Learn request routing")
        )
        challenges = tour_states._challenges[plan.id]
        first.put(plan.id, challenges)
        challenge_id = next(iter(challenges))
        restored = TourStateStore(path=database)
        self.assertEqual(
            restored.challenge(plan.id, challenge_id), challenges[challenge_id]
        )

    def test_architecture_mission_and_search_are_source_grounded(self) -> None:
        architecture = self.service.architecture_report()
        mission = self.service.contribution_mission(DeveloperRole.BACKEND)
        search = self.service.search("verify")
        self.assertEqual(architecture.analysis_id, "test-analysis")
        self.assertEqual(mission.risk, "low")
        self.assertTrue(mission.target_node.span)
        self.assertTrue(search.results)
        self.assertIn("verify", search.results[0].node.qualified_name)

    def test_grounded_answer_cites_source_and_refuses_unknowns(self) -> None:
        answer = self.service.answer(
            GroundedQuestion(question="Where is token verification handled?")
        )
        self.assertFalse(answer.refused)
        self.assertTrue(answer.citations)
        self.assertEqual(answer.citations[0].span.path, "app/auth.py")

        refusal = self.service.answer(
            GroundedQuestion(question="Where is quantum billing orchestration?")
        )
        self.assertTrue(refusal.refused)
        self.assertEqual(refusal.citations, [])

    def test_code_journey_is_bounded_and_source_grounded(self) -> None:
        start = self.service.search("login").results[0].node
        journey = self.service.journey(start.id, max_steps=5)
        self.assertEqual(journey.start_node_id, start.id)
        self.assertLessEqual(len(journey.steps), 5)
        self.assertEqual(journey.steps[0].node.id, start.id)
        self.assertTrue(all(step.evidence for step in journey.steps))

    def test_revision_comparison_detects_source_changes(self) -> None:
        previous = self.report.model_copy(update={"analysis_id": "previous"})
        (self.root / "app" / "auth.py").write_text(
            "def verify_token(token: str) -> bool:\n"
            "    return token.startswith('signed-')\n",
            encoding="utf-8",
        )
        current = RepositoryAnalyzer().analyze(self.root).model_copy(
            update={"analysis_id": "current"}
        )
        comparison = OnboardingService(current).compare(previous)
        self.assertEqual(
            [item.qualified_name for item in comparison.modified],
            ["app.auth"],
        )
        self.assertTrue(comparison.refresher)


if __name__ == "__main__":
    unittest.main()
