from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from backend.app.agent.retrieval import RepositoryIndexStore, RepositoryRetrievalIndex
from backend.app.agent.service import RepositoryAgentService, TOOLS
from backend.app.agent.onboarding import RepositoryOnboardingAgent
from backend.app.agent.provider import model_provider_router
from backend.app.agent.memory import ConversationStore
from backend.app.graph.analyzer import RepositoryAnalyzer
from backend.app.graph.store import AnalysisSessionStore, analysis_sessions
from backend.app.onboarding.models import DeveloperRole, GroundedQuestion, TourRequest


class RepositoryAgentTests(unittest.TestCase):
    def test_chunk_identity_distinguishes_symbols_that_share_a_span(self) -> None:
        first = RepositoryRetrievalIndex._chunk_id(
            "src/app.ts", 10, 12, "function", "symbol-one"
        )
        second = RepositoryRetrievalIndex._chunk_id(
            "src/app.ts", 10, 12, "function", "symbol-two"
        )
        self.assertNotEqual(first, second)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "README.md").write_text(
            "# Greeting service\n\nA small API that returns greetings.\n",
            encoding="utf-8",
        )
        (self.root / "app.py").write_text(
            "def greet(name: str) -> str:\n"
            "    return f'Hello {name}'\n",
            encoding="utf-8",
        )
        report = RepositoryAnalyzer().analyze(self.root)
        stored = analysis_sessions.create(self.root, report)
        self.session = analysis_sessions.get(stored.analysis_id)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_retrieval_searches_symbols_and_reads_bounded_lines(self) -> None:
        index = RepositoryRetrievalIndex(self.session)
        results = index.search("greet", limit=5)
        self.assertTrue(results)
        self.assertEqual(results[0]["path"], "app.py")
        source = index.read("app.py", 1, 500)
        self.assertEqual(source["end_line"], 2)
        self.assertIn("1 | def greet", source["content"])
        with self.assertRaises(ValueError):
            index.read("../outside.py")

    def test_retrieval_index_persists_revision_and_supports_filters(self) -> None:
        database = self.root / "index" / "code.sqlite3"
        first = RepositoryRetrievalIndex(self.session, database_path=database)
        status = first.status()
        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["files"], 2)
        self.assertGreaterEqual(status["symbols"], 3)
        self.assertEqual(status["vectors"], status["chunks"])
        self.assertTrue(first.search("greeting service", languages=["documentation"]))
        self.assertEqual(
            first.search("greet", path_prefixes=["missing/"], limit=5), []
        )

        with patch.object(
            RepositoryRetrievalIndex,
            "_build_chunks",
            side_effect=AssertionError("persistent chunks should be reused"),
        ):
            reopened = RepositoryRetrievalIndex(
                self.session, database_path=database, snapshot=first.snapshot
            )
        self.assertEqual(reopened.revision_id, first.revision_id)
        self.assertEqual(len(reopened.chunks), len(first.chunks))

    def test_hybrid_search_handles_related_word_forms(self) -> None:
        index = RepositoryRetrievalIndex(
            self.session, database_path=self.root / "hybrid.sqlite3"
        )
        results = index.search("greetings", limit=5)
        self.assertTrue(any(item["path"] == "app.py" for item in results))

    def test_index_store_refreshes_changed_repository_under_same_analysis(self) -> None:
        store = RepositoryIndexStore(max_indexes=2)
        first = store.get(self.session)
        (self.root / "app.py").write_text(
            "def greet(name: str) -> str:\n"
            "    return f'Hello {name}'\n\n"
            "def farewell(name: str) -> str:\n"
            "    return f'Goodbye {name}'\n",
            encoding="utf-8",
        )
        second = store.get(self.session)
        self.assertNotEqual(second.revision_id, first.revision_id)
        self.assertTrue(second.find_symbols("farewell")["results"])
        self.assertEqual(second.session.id, self.session.id)

    def test_agent_uses_tools_and_returns_only_validated_citations(self) -> None:
        search = SimpleNamespace(
            type="tool_use",
            id="tool-search",
            name="search_repository",
            input={"query": "greet", "limit": 5},
        )
        submit = SimpleNamespace(
            type="tool_use",
            id="tool-submit",
            name="submit_answer",
            input={
                "answer": "The service exposes a greet function.",
                "basis": "The function definition and return statement support this.",
                "refused": False,
                "citations": [
                    {
                        "path": "app.py",
                        "start_line": 1,
                        "end_line": 2,
                        "title": "Greeting implementation",
                        "relevance": "Defines and returns the greeting.",
                    }
                ],
                "suggested_questions": ["Who calls greet?"],
            },
        )
        responses = [
            SimpleNamespace(
                content=[search],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            ),
            SimpleNamespace(
                content=[submit],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=20, output_tokens=10),
            ),
        ]
        client = SimpleNamespace(
            messages=SimpleNamespace(create=Mock(side_effect=responses))
        )
        fake_settings = SimpleNamespace(
            anthropic_api_key="configured",
            model_name="claude-sonnet-5",
            agent_max_output_tokens=4000,
            agent_max_tool_rounds=5,
        )
        agent = RepositoryAgentService(self.session)
        with patch("backend.app.agent.service.settings", fake_settings), patch.object(
            agent, "_client", return_value=client
        ):
            answer = agent.answer(GroundedQuestion(question="What does this service do?"))
        self.assertEqual(answer.provider, "claude-sonnet-5")
        self.assertEqual(
            [activity.tool for activity in answer.tool_trace],
            ["search_repository"],
        )
        self.assertIsNotNone(answer.conversation_id)
        self.assertEqual([item.span.path for item in answer.citations], ["app.py"])
        self.assertEqual(answer.inspected_file_count, 2)
        self.assertNotIn("README.md", [item.span.path for item in answer.citations])
        self.assertEqual(client.messages.create.call_count, 2)

    def test_focused_symbol_question_preloads_usage_evidence(self) -> None:
        symbol = next(
            node for node in self.session.report.nodes if node.name == "greet"
        )
        submit = SimpleNamespace(
            type="tool_use",
            id="tool-submit",
            name="submit_answer",
            input={
                "answer": "`greet` implements the repository greeting behavior.",
                "basis": "The selected symbol and its source define the behavior.",
                "refused": False,
                "citations": [{
                    "path": "app.py",
                    "start_line": 1,
                    "end_line": 2,
                    "title": "Selected greeting symbol",
                    "relevance": "Defines the selected function.",
                }],
                "suggested_questions": [],
            },
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(
                create=Mock(return_value=SimpleNamespace(
                    content=[submit],
                    stop_reason="tool_use",
                    usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                ))
            )
        )
        fake_settings = SimpleNamespace(
            anthropic_api_key="configured",
            model_name="claude-sonnet-5",
            agent_max_output_tokens=4000,
            agent_max_tool_rounds=5,
        )
        agent = RepositoryAgentService(self.session)
        with patch("backend.app.agent.service.settings", fake_settings), patch.object(
            agent, "_client", return_value=client
        ):
            answer = agent.answer(GroundedQuestion(
                question="How is this used?",
                focus_node_id=symbol.id,
                conversation_scope="inspector",
            ))
        dispatched = next(
            message["content"]
            for message in client.messages.create.call_args.kwargs["messages"]
            if message.get("role") == "user"
            and "SELECTED SYMBOL USAGE" in str(message.get("content"))
        )
        self.assertIn("SELECTED SYMBOL USAGE", dispatched)
        self.assertIn(symbol.qualified_name, dispatched)
        self.assertEqual(answer.tool_trace[0].tool, "get_symbol_relationships")
        self.assertEqual(answer.citations[0].span.path, "app.py")

    def test_precise_tools_return_bounded_source_evidence(self) -> None:
        tool_names = {tool["name"] for tool in TOOLS}
        self.assertTrue(
            {
                "get_repository_overview",
                "get_feature_evidence",
                "find_entry_points",
                "get_backend_architecture",
                "get_file_structure",
                "get_symbol_relationships",
                "find_related_tests",
                "get_dependency_impact",
                "get_project_configuration",
                "get_analysis_diagnostics",
                "find_symbols",
                "get_index_status",
            }.issubset(tool_names)
        )
        agent = RepositoryAgentService(self.session)
        overview = agent.semantic.repository_overview()
        self.assertEqual(overview["repository_name"], self.root.name)
        self.assertEqual(overview["languages"], {"python": 1})
        self.assertTrue(overview["evidence"])
        entry_points = agent.semantic.entry_points()
        self.assertTrue(
            any(item["path"] == "app.py" for item in entry_points["candidates"])
        )
        structure = agent.semantic.file_structure("app.py")
        self.assertTrue(
            any(item["name"] == "greet" for item in structure["symbols"])
        )

    def test_broad_question_runs_precise_tools_in_one_round_then_forces_answer(self) -> None:
        overview_tool = SimpleNamespace(
            type="tool_use",
            id="tool-overview",
            name="get_repository_overview",
            input={},
        )
        entry_tool = SimpleNamespace(
            type="tool_use",
            id="tool-entry",
            name="find_entry_points",
            input={"limit": 5},
        )
        submit = SimpleNamespace(
            type="tool_use",
            id="tool-submit",
            name="submit_answer",
            input={
                "answer": "This is a small greeting service with a documented API.",
                "basis": "The README and application entry point establish its purpose.",
                "refused": False,
                "citations": [
                    {
                        "path": "README.md",
                        "start_line": 1,
                        "end_line": 2,
                        "title": "Repository overview",
                        "relevance": "Names and describes the greeting service.",
                    }
                ],
                "suggested_questions": [],
            },
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(
                create=Mock(
                    side_effect=[
                        SimpleNamespace(
                            content=[overview_tool, entry_tool],
                            stop_reason="tool_use",
                            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                        ),
                        SimpleNamespace(
                            content=[submit],
                            stop_reason="tool_use",
                            usage=SimpleNamespace(input_tokens=20, output_tokens=10),
                        ),
                    ]
                )
            )
        )
        fake_settings = SimpleNamespace(
            anthropic_api_key="configured",
            model_name="claude-sonnet-5",
            agent_max_output_tokens=4000,
            agent_max_tool_rounds=3,
        )
        agent = RepositoryAgentService(self.session)
        with patch("backend.app.agent.service.settings", fake_settings), patch.object(
            agent, "_client", return_value=client
        ):
            answer = agent.answer(
                GroundedQuestion(question="What is this repository and where does it start?")
            )
        self.assertEqual(answer.provider, "claude-sonnet-5")
        self.assertEqual(
            [activity.tool for activity in answer.tool_trace],
            ["get_repository_overview", "find_entry_points"],
        )
        self.assertEqual(client.messages.create.call_count, 2)
        second_call = client.messages.create.call_args_list[1].kwargs
        self.assertEqual(
            second_call["tool_choice"],
            {"type": "tool", "name": "submit_answer"},
        )
        tool_results = next(
            message["content"]
            for message in reversed(second_call["messages"])
            if message["role"] == "user" and isinstance(message["content"], list)
        )
        self.assertEqual(len(tool_results), 2)

    def test_answer_bounded_reads_valid_proposed_citation_before_accepting(self) -> None:
        submit = SimpleNamespace(
            type="tool_use",
            id="tool-submit-recovered",
            name="submit_answer",
            input={
                "answer": "The repository is a greeting service.",
                "basis": "The README explicitly describes the service.",
                "refused": False,
                "citations": [{
                    "path": "README.md",
                    "start_line": 1,
                    "end_line": 3,
                    "title": "Repository overview",
                    "relevance": "Describes the greeting service.",
                }],
                "suggested_questions": [],
            },
        )
        client = SimpleNamespace(messages=SimpleNamespace(create=Mock(
            return_value=SimpleNamespace(
                content=[submit],
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                waypoint_provider="test:model",
            )
        )))
        fake_settings = SimpleNamespace(
            model_name="test-model",
            agent_max_output_tokens=2000,
            agent_max_tool_rounds=1,
            investigation_rounds=0,
            synthesis_max_attempts=1,
        )
        agent = RepositoryAgentService(self.session)
        with (
            patch("backend.app.agent.service.settings", fake_settings),
            patch.object(
                type(model_provider_router),
                "dual_role_enabled",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(agent, "_client", return_value=client),
        ):
            answer = agent.answer(GroundedQuestion(question="What is this repository?"))

        self.assertEqual(answer.provider, "test:model")
        self.assertEqual(answer.citations[0].span.path, "README.md")

    def test_mission_forces_structured_submission_before_round_limit(self) -> None:
        target = next(
            node
            for node in self.session.report.nodes
            if node.name == "greet" and node.span is not None
        )
        search = SimpleNamespace(
            type="tool_use",
            id="tool-search",
            name="search_repository",
            input={"query": "greet", "limit": 5},
        )
        submit = SimpleNamespace(
            type="tool_use",
            id="tool-submit",
            name="submit_contribution_mission",
            input={
                "title": "Add greeting coverage",
                "risk": "Low - the change is isolated to focused test coverage.",
                "target_node_id": target.id,
                "rationale": "A contained backend behavior with a clear seam.",
                "suggested_files": ["app.py"],
                "checklist": ["Review greet", "Add focused coverage"],
                "definition_of_done": ["Tests pass", "Behavior is documented"],
            },
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(
                create=Mock(
                    side_effect=[
                        SimpleNamespace(content=[search]),
                        SimpleNamespace(content=[submit]),
                    ]
                )
            )
        )
        fake_settings = SimpleNamespace(
            model_name="claude-sonnet-5",
            agent_max_output_tokens=4000,
            agent_max_tool_rounds=2,
        )
        request = TourRequest(role=DeveloperRole.BACKEND, goal="")
        self.assertIn("backend architecture", request.goal)
        agent = RepositoryOnboardingAgent(self.session)
        with patch("backend.app.agent.onboarding.settings", fake_settings), patch.object(
            agent.repository_agent, "_client", return_value=client
        ):
            mission = agent.mission(request)
        self.assertEqual(mission.target_node.id, target.id)
        self.assertEqual(mission.risk, "low")
        second_call = client.messages.create.call_args_list[1].kwargs
        self.assertEqual(
            second_call["tool_choice"],
            {"type": "tool", "name": "submit_contribution_mission"},
        )

    def test_onboarding_bounded_reads_valid_proposed_evidence_before_accepting(self) -> None:
        submit = SimpleNamespace(
            type="tool_use",
            id="tool-submit-tour",
            name="submit_onboarding_tour",
            input={
                "steps": [
                    {
                        "title": "Read the overview",
                        "objective": "Understand the service purpose.",
                        "explanation": "The README introduces the behavior.",
                        "why_selected": "It provides the intended product context.",
                        "files": [{
                            "path": "README.md",
                            "start_line": 1,
                            "end_line": 3,
                            "reason": "Repository overview",
                        }],
                        "challenge_prompt": "What does the service return?",
                        "expected_concepts": ["greeting"],
                    },
                    {
                        "title": "Read the implementation",
                        "objective": "Trace the greeting implementation.",
                        "explanation": "The function returns the greeting.",
                        "why_selected": "It is the production implementation.",
                        "files": [{
                            "path": "app.py",
                            "start_line": 1,
                            "end_line": 2,
                            "reason": "Greeting function",
                        }],
                        "challenge_prompt": "Which function implements the behavior?",
                        "expected_concepts": ["greet"],
                    },
                ],
                "planning_basis": ["Repository documentation and source"],
            },
        )
        client = SimpleNamespace(messages=SimpleNamespace(create=Mock(
            return_value=SimpleNamespace(
                content=[submit],
                waypoint_provider="test:model",
            )
        )))
        fake_settings = SimpleNamespace(
            model_name="test-model",
            agent_max_output_tokens=4000,
            agent_max_tool_rounds=1,
            investigation_rounds=0,
            synthesis_max_attempts=1,
        )
        agent = RepositoryOnboardingAgent(self.session)
        with (
            patch("backend.app.agent.onboarding.settings", fake_settings),
            patch.object(
                type(model_provider_router),
                "dual_role_enabled",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(agent.repository_agent, "_client", return_value=client),
        ):
            tour = agent.plan(TourRequest(role=DeveloperRole.BACKEND))

        self.assertEqual(len(tour.steps), 2)
        self.assertEqual(tour.provider, "test:model")
        self.assertEqual(tour.steps[0].files[0].path, "README.md")

    def test_conversation_history_persists_across_store_instances(self) -> None:
        database = self.root / "state" / "waypoint.sqlite3"
        first_store = ConversationStore(database)
        conversation = first_store.get_or_create(self.session.id, None, "ask")
        first_store.append_turn(
            conversation,
            "Where is greet?",
            "It is in app.py.",
            '{"provider":"test","citations":[]}',
        )
        onboarding = first_store.get_or_create(
            self.session.id, None, "onboarding"
        )
        first_store.append_turn(
            onboarding,
            "Why start here?",
            "It is the entry point.",
        )

        reopened_store = ConversationStore(database)
        reopened = reopened_store.get_or_create(
            self.session.id, conversation.id, "ask"
        )
        self.assertEqual(
            reopened_store.history(reopened),
            [
                {"role": "user", "content": "Where is greet?"},
                {"role": "assistant", "content": "It is in app.py."},
            ],
        )
        self.assertEqual(reopened_store.latest(self.session.id, "ask"), reopened)
        self.assertEqual(
            reopened_store.latest(self.session.id, "onboarding"), onboarding
        )
        transcript = reopened_store.transcript(reopened)
        self.assertEqual(transcript[1]["role"], "assistant")
        self.assertEqual(
            transcript[1]["answer_json"],
            '{"provider":"test","citations":[]}',
        )
        with self.assertRaises(ValueError):
            reopened_store.get_or_create(
                self.session.id, conversation.id, "onboarding"
            )

    def test_analysis_session_can_be_restored_from_local_state(self) -> None:
        database = self.root / "state" / "analysis.sqlite3"
        fake_settings = SimpleNamespace(
            state_path=database,
            allowed_root=self.root,
        )
        report = RepositoryAnalyzer().analyze(self.root)
        with patch("backend.app.graph.store.settings", fake_settings):
            first_store = AnalysisSessionStore(max_sessions=5)
            stored = first_store.create(self.root, report)
            reopened_store = AnalysisSessionStore(max_sessions=5)
            restored = reopened_store.get(stored.analysis_id)
        self.assertEqual(restored.root, self.root.resolve())
        self.assertEqual(restored.report.analysis_id, stored.analysis_id)
        self.assertIn("app.py", restored.source_paths)


if __name__ == "__main__":
    unittest.main()
