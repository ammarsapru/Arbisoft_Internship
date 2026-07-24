from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from collections import Counter, OrderedDict
from contextlib import closing
from pathlib import Path

from backend.app.graph.models import (
    AnalysisReport,
    EdgeKind,
    GraphEdge,
    GraphNode,
    NodeKind,
)
from backend.app.config import settings
from backend.app.observability import log_event, traced
from backend.app.onboarding.models import (
    ArchitectureInsight,
    ArchitectureReport,
    ChallengeAnswer,
    ChallengeOption,
    ChallengeResult,
    CodeJourney,
    ContributionMission,
    DeveloperRole,
    GroundedAnswer,
    GroundedCitation,
    GroundedQuestion,
    JourneyStep,
    RevisionChange,
    RevisionReport,
    StoredChallenge,
    SymbolSearchResponse,
    SymbolSearchResult,
    TourChallenge,
    TourEvidenceFile,
    TourPlan,
    TourRequest,
    TourStep,
)

logger = logging.getLogger(__name__)

ROLE_KEYWORDS: dict[DeveloperRole, tuple[str, ...]] = {
    DeveloperRole.GENERAL: ("main", "app", "core", "config", "api", "cli"),
    DeveloperRole.BACKEND: (
        "api",
        "route",
        "service",
        "model",
        "database",
        "db",
        "handler",
        "core",
    ),
    DeveloperRole.SECURITY: (
        "auth",
        "security",
        "permission",
        "session",
        "token",
        "middleware",
        "credential",
        "sign",
        "serializer",
        "digest",
        "salt",
    ),
    DeveloperRole.QA: (
        "test",
        "fixture",
        "conftest",
        "mock",
        "integration",
        "assert",
    ),
}


class TourStateStore:
    def __init__(self, max_tours: int = 100, path: Path | None = None) -> None:
        self.max_tours = max_tours
        self.path = (path or settings.state_path).resolve()
        self._challenges: OrderedDict[str, dict[str, StoredChallenge]] = OrderedDict()
        self._mastered: dict[str, set[str]] = {}
        self._mastered_concepts: dict[str, set[str]] = {}
        self._attempts: dict[str, tuple[int, int]] = {}
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS onboarding_tours ("
            "tour_id TEXT PRIMARY KEY, challenges_json TEXT NOT NULL, "
            "mastered_json TEXT NOT NULL, mastered_concepts_json TEXT NOT NULL, "
            "successes INTEGER NOT NULL, attempts INTEGER NOT NULL, "
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        return connection

    def _persist(self, tour_id: str) -> None:
        successes, attempts = self._attempts[tour_id]
        payload = {
            key: value.model_dump(mode="json")
            for key, value in self._challenges[tour_id].items()
        }
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO onboarding_tours(tour_id, challenges_json, "
                "mastered_json, mastered_concepts_json, successes, attempts, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(tour_id) "
                "DO UPDATE SET challenges_json = excluded.challenges_json, "
                "mastered_json = excluded.mastered_json, "
                "mastered_concepts_json = excluded.mastered_concepts_json, "
                "successes = excluded.successes, attempts = excluded.attempts, "
                "updated_at = CURRENT_TIMESTAMP",
                (
                    tour_id, json.dumps(payload),
                    json.dumps(sorted(self._mastered[tour_id])),
                    json.dumps(sorted(self._mastered_concepts[tour_id])),
                    successes, attempts,
                ),
            )
            connection.commit()

    def _restore(self, tour_id: str) -> bool:
        if tour_id in self._challenges:
            return True
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT challenges_json, mastered_json, mastered_concepts_json, "
                "successes, attempts FROM onboarding_tours WHERE tour_id = ?",
                (tour_id,),
            ).fetchone()
        if row is None:
            return False
        self._challenges[tour_id] = {
            key: StoredChallenge.model_validate(value)
            for key, value in json.loads(row[0]).items()
        }
        self._mastered[tour_id] = set(json.loads(row[1]))
        self._mastered_concepts[tour_id] = set(json.loads(row[2]))
        self._attempts[tour_id] = (int(row[3]), int(row[4]))
        return True

    def put(self, tour_id: str, challenges: dict[str, StoredChallenge]) -> None:
        with self._lock:
            self._challenges[tour_id] = challenges
            self._mastered[tour_id] = set()
            self._mastered_concepts[tour_id] = set()
            self._attempts[tour_id] = (0, 0)
            while len(self._challenges) > self.max_tours:
                removed, _ = self._challenges.popitem(last=False)
                self._mastered.pop(removed, None)
                self._mastered_concepts.pop(removed, None)
                self._attempts.pop(removed, None)
            self._persist(tour_id)

    def answer(self, tour_id: str, answer: ChallengeAnswer) -> ChallengeResult:
        with self._lock:
            self._restore(tour_id)
            challenge = self._challenges.get(tour_id, {}).get(answer.challenge_id)
            if challenge is None:
                raise KeyError(answer.challenge_id)
            correct = answer.selected_node_id == challenge.correct_node_id
            successes, attempts = self._attempts[tour_id]
            attempts += 1
            if correct:
                successes += 1
                if challenge.correct_node_id:
                    self._mastered[tour_id].add(challenge.correct_node_id)
            self._attempts[tour_id] = (successes, attempts)
            self._persist(tour_id)
            return ChallengeResult(
                correct=correct,
                explanation=challenge.explanation,
                mastered_node_ids=sorted(self._mastered[tour_id]),
                score=successes / attempts,
                mastered_concept_ids=sorted(self._mastered_concepts[tour_id]),
            )

    def challenge(self, tour_id: str, challenge_id: str) -> StoredChallenge:
        with self._lock:
            self._restore(tour_id)
            challenge = self._challenges.get(tour_id, {}).get(challenge_id)
            if challenge is None:
                raise KeyError(challenge_id)
            return challenge

    def record_evaluation(
        self,
        tour_id: str,
        challenge: StoredChallenge,
        *,
        correct: bool,
        explanation: str,
        score: float,
        mastered_concepts: list[str],
        remediation: str | None,
    ) -> ChallengeResult:
        with self._lock:
            self._restore(tour_id)
            if tour_id not in self._challenges:
                raise KeyError(tour_id)
            successes, attempts = self._attempts[tour_id]
            attempts += 1
            if correct:
                successes += 1
                if challenge.node_id:
                    self._mastered[tour_id].add(challenge.node_id)
            allowed = set(challenge.expected_concepts)
            self._mastered_concepts[tour_id].update(
                concept for concept in mastered_concepts if concept in allowed
            )
            self._attempts[tour_id] = (successes, attempts)
            self._persist(tour_id)
            return ChallengeResult(
                correct=correct,
                explanation=explanation,
                mastered_node_ids=sorted(self._mastered[tour_id]),
                mastered_concept_ids=sorted(self._mastered_concepts[tour_id]),
                score=max(0.0, min(score, 1.0)),
                remediation=remediation,
            )


tour_states = TourStateStore()


class OnboardingService:
    def __init__(self, report: AnalysisReport) -> None:
        self.report = report
        self.nodes = {node.id: node for node in report.nodes}
        self.edges = report.edges
        self.modules = [
            node for node in report.nodes if node.kind == NodeKind.MODULE
        ]
        self.degree = Counter[str]()
        self.outgoing = Counter[str]()
        self.incoming = Counter[str]()
        self.children = Counter[str]()
        for edge in self.edges:
            self.degree[edge.source] += 1
            self.degree[edge.target] += 1
            self.outgoing[edge.source] += 1
            self.incoming[edge.target] += 1
            if edge.kind == EdgeKind.CONTAINS:
                self.children[edge.source] += 1

    def _role_score(self, node: GraphNode, role: DeveloperRole) -> float:
        name = node.qualified_name.lower()
        keyword_score = sum(
            16 for keyword in ROLE_KEYWORDS[role] if keyword in name
        )
        centrality = min(self.degree[node.id], 30) * 0.8
        support_code_penalty = (
            -35
            if role != DeveloperRole.QA
            and any(
                part in name
                for part in (
                    "test",
                    "fixture",
                    "conftest",
                    "benchmark",
                    "docs",
                    "example",
                    "script",
                )
            )
            else 0
        )
        package_depth_penalty = max(0, name.count(".") - 3) * 0.5
        return (
            keyword_score
            + centrality
            + support_code_penalty
            - package_depth_penalty
        )

    @traced("tour.plan")
    def plan_tour(self, request: TourRequest) -> TourPlan:
        if not self.modules:
            raise ValueError("The analysis contains no source modules to tour")
        desired_steps = max(4, min(10, request.minutes // 3 + 2))
        ranked = sorted(
            self.modules,
            key=lambda node: (
                -self._role_score(node, request.role),
                node.qualified_name,
            ),
        )
        selected: list[GraphNode] = []
        seen_packages: set[str] = set()
        for node in ranked:
            top_package = node.qualified_name.split(".")[0]
            if top_package in seen_packages and len(selected) < 2:
                continue
            selected.append(node)
            seen_packages.add(top_package)
            if len(selected) >= desired_steps:
                break
        tour_id = uuid.uuid4().hex
        challenges: dict[str, StoredChallenge] = {}
        steps: list[TourStep] = []
        option_pool = ranked[: max(8, desired_steps)]
        for index, node in enumerate(selected, start=1):
            options = [node]
            options.extend(
                candidate
                for candidate in option_pool
                if candidate.id != node.id
                and candidate.id not in {option.id for option in options}
            )
            options = options[:4]
            challenge_id = hashlib.sha256(
                f"{tour_id}:{node.id}".encode()
            ).hexdigest()[:16]
            challenge = None
            if index > 1:
                challenge = TourChallenge(
                    id=challenge_id,
                    prompt=(
                        f"Which module was selected for step {index} of your "
                        f"{request.role.value} route?"
                    ),
                    options=[
                        ChallengeOption(
                            node_id=option.id,
                            label=option.qualified_name,
                            kind=option.kind.value,
                        )
                        for option in sorted(
                            options, key=lambda option: option.qualified_name
                        )
                    ],
                )
                challenges[challenge_id] = StoredChallenge(
                    correct_node_id=node.id,
                    explanation=(
                        f"{node.qualified_name} is the evidenced module for this "
                        "step. Selecting it demonstrates that you can relocate "
                        "the concept in the graph."
                    ),
                )
            steps.append(
                TourStep(
                    index=index,
                    title=(
                        f"Start with {node.name}"
                        if index == 1
                        else f"Trace {node.name}"
                    ),
                    node_id=node.id,
                    node_kind=node.kind.value,
                    objective=(
                        f"Understand the role of {node.qualified_name} in relation "
                        f"to: {request.goal}."
                    ),
                    explanation=(
                        f"This module has {self.incoming[node.id]} incoming and "
                        f"{self.outgoing[node.id]} outgoing graph relationships, "
                        f"and contains {self.children[node.id]} indexed symbols."
                    ),
                    why_selected=(
                        f"Ranked for the {request.role.value} route using "
                        "architectural centrality and role-specific naming evidence."
                    ),
                    evidence=node.span,
                    challenge=challenge,
                    files=(
                        [
                            TourEvidenceFile(
                                path=node.span.path,
                                start_line=node.span.start_line,
                                end_line=node.span.end_line,
                                node_id=node.id,
                                reason="Primary module selected by the static route ranking.",
                            )
                        ]
                        if node.span
                        else []
                    ),
                )
            )
        tour_states.put(tour_id, challenges)
        plan = TourPlan(
            id=tour_id,
            analysis_id=self.report.analysis_id or "",
            role=request.role,
            goal=request.goal,
            experience=request.experience,
            estimated_minutes=request.minutes,
            steps=steps,
            planning_basis=[
                "Verified module identities and source spans",
                "Import and containment graph centrality",
                f"Role keywords for {request.role.value}",
                "Repository-specific package diversity",
            ],
        )
        log_event(
            logger,
            logging.INFO,
            "tour.plan_created",
            "Adaptive onboarding tour created",
            analysis_id=self.report.analysis_id,
            tour_id=tour_id,
            role=request.role,
            step_count=len(steps),
            node_ids=[step.node_id for step in steps],
        )
        return plan

    @traced("architecture.inspect")
    def architecture_report(self) -> ArchitectureReport:
        module_ids = {module.id for module in self.modules}
        adjacency: dict[str, list[str]] = {module_id: [] for module_id in module_ids}
        for edge in self.edges:
            if (
                edge.kind == EdgeKind.IMPORTS
                and edge.source in module_ids
                and edge.target in module_ids
            ):
                adjacency[edge.source].append(edge.target)
        cycles = self._strongly_connected(adjacency)
        insights: list[ArchitectureInsight] = []
        for component in cycles[:20]:
            evidence = [
                self.nodes[node_id].span
                for node_id in component
                if self.nodes[node_id].span
            ]
            names = [self.nodes[node_id].qualified_name for node_id in component]
            insights.append(
                ArchitectureInsight(
                    id=hashlib.sha256("|".join(sorted(component)).encode()).hexdigest()[:16],
                    severity="warning",
                    category="import_cycle",
                    title=f"Import cycle across {len(component)} modules",
                    explanation=" → ".join(names[:5]),
                    node_ids=component,
                    evidence=evidence,
                )
            )
        ranked = sorted(
            self.modules,
            key=lambda node: (-self.degree[node.id], node.qualified_name),
        )
        hotspot_threshold = max(12, int(len(self.modules) ** 0.5 * 2))
        hotspots = [
            node for node in ranked if self.degree[node.id] >= hotspot_threshold
        ][:10]
        for node in hotspots:
            insights.append(
                ArchitectureInsight(
                    id=hashlib.sha256(f"hotspot:{node.id}".encode()).hexdigest()[:16],
                    severity="info",
                    category="high_connectivity",
                    title=f"{node.name} is an architectural hotspot",
                    explanation=(
                        f"{node.qualified_name} participates in "
                        f"{self.degree[node.id]} graph relationships."
                    ),
                    node_ids=[node.id],
                    evidence=[node.span] if node.span else [],
                )
            )
        return ArchitectureReport(
            analysis_id=self.report.analysis_id or "",
            insights=insights,
            import_cycle_count=len(cycles),
            hotspot_count=len(hotspots),
        )

    def _strongly_connected(self, adjacency: dict[str, list[str]]) -> list[list[str]]:
        """Iterative Kosaraju traversal that is safe for very deep graphs."""
        visited: set[str] = set()
        finishing_order: list[str] = []
        for start in adjacency:
            if start in visited:
                continue
            stack: list[tuple[str, bool]] = [(start, False)]
            while stack:
                node, expanded = stack.pop()
                if expanded:
                    finishing_order.append(node)
                    continue
                if node in visited:
                    continue
                visited.add(node)
                stack.append((node, True))
                for target in adjacency.get(node, []):
                    if target not in visited:
                        stack.append((target, False))

        reverse: dict[str, list[str]] = {node: [] for node in adjacency}
        for source, targets in adjacency.items():
            for target in targets:
                reverse.setdefault(target, []).append(source)

        assigned: set[str] = set()
        components: list[list[str]] = []
        for start in reversed(finishing_order):
            if start in assigned:
                continue
            component: list[str] = []
            stack = [start]
            assigned.add(start)
            while stack:
                node = stack.pop()
                component.append(node)
                for target in reverse.get(node, []):
                    if target not in assigned:
                        assigned.add(target)
                        stack.append(target)
            if len(component) > 1:
                components.append(component)
        return sorted(components, key=lambda item: (-len(item), sorted(item)))

    @traced("mission.generate")
    def contribution_mission(
        self, role: DeveloperRole
    ) -> ContributionMission:
        if not self.modules:
            raise ValueError("The analysis contains no source modules for a mission")
        production_modules = [
            node
            for node in self.modules
            if not any(
                marker in node.qualified_name.lower()
                for marker in ("test", "fixture", "conftest", "__init__")
            )
        ]
        ranked = sorted(
            production_modules,
            key=lambda node: (
                abs(self.degree[node.id] - 4),
                -self._role_score(node, role),
                node.qualified_name,
            ),
        )
        target = ranked[0] if ranked else self.modules[0]
        neighbors = {
            edge.target if edge.source == target.id else edge.source
            for edge in self.edges
            if edge.source == target.id or edge.target == target.id
        }
        test_files = sorted(
            {
                self.nodes[node_id].span.path
                for node_id in neighbors
                if node_id in self.nodes
                and self.nodes[node_id].span
                and "test" in self.nodes[node_id].qualified_name.lower()
            }
        )
        suggested_files = [target.span.path] if target.span else []
        suggested_files.extend(test_files[:3])
        return ContributionMission(
            analysis_id=self.report.analysis_id or "",
            title=f"Build confidence around {target.name}",
            risk="low",
            target_node=target,
            rationale=(
                f"{target.qualified_name} is role-relevant but has a bounded "
                f"static blast radius of {len(neighbors)} neighboring nodes."
            ),
            suggested_files=suggested_files,
            blast_radius_node_ids=sorted(neighbors),
            checklist=[
                "Read the target module and identify its public behavior.",
                "Locate an existing test or usage pattern in a neighboring module.",
                "Write down one behavior that lacks an explicit regression check.",
                "Keep the proposed change inside the evidenced blast radius.",
            ],
            definition_of_done=[
                "The intended behavior is described in plain language.",
                "At least one relevant test or call site is cited by file and line.",
                "The proposed change does not introduce a new module dependency.",
            ],
            validation_checks=[
                "Target file and symbol exist in the analyzed revision.",
                "Static blast radius was calculated from graph relationships.",
                (
                    "A neighboring test file was identified."
                    if test_files
                    else "No neighboring test file was identified; user validation is required."
                ),
            ],
            confidence=0.7 if test_files else 0.5,
        )

    @traced("search.symbols")
    def search(self, query: str, limit: int = 20) -> SymbolSearchResponse:
        normalized = query.strip().lower()
        scored: list[SymbolSearchResult] = []
        for node in self.report.nodes:
            name = node.name.lower()
            qualified = node.qualified_name.lower()
            if normalized not in qualified:
                continue
            score = (
                1.0
                if name == normalized
                else 0.9
                if name.startswith(normalized)
                else 0.7
                if normalized in name
                else 0.5
            )
            scored.append(SymbolSearchResult(node=node, score=score))
        scored.sort(
            key=lambda result: (
                -result.score,
                result.node.qualified_name,
            )
        )
        return SymbolSearchResponse(query=query, results=scored[:limit])

    @traced("qa.answer")
    def answer(self, request: GroundedQuestion) -> GroundedAnswer:
        normalized = request.question.lower()
        stop_words = {
            "where",
            "what",
            "which",
            "how",
            "is",
            "are",
            "the",
            "a",
            "an",
            "handled",
            "implemented",
            "located",
            "code",
            "for",
            "does",
        }
        terms = [
            term.strip(".,?!:;()[]{}\"'")
            for term in normalized.split()
            if term.strip(".,?!:;()[]{}\"'") not in stop_words
            and len(term.strip(".,?!:;()[]{}\"'")) >= 2
        ]
        scored: list[tuple[float, GraphNode]] = []
        asks_for_support_code = any(
            term in {"test", "tests", "fixture", "benchmark", "docs", "example"}
            for term in terms
        )
        for node in self.report.nodes:
            if not node.span:
                continue
            haystack = f"{node.name} {node.qualified_name}".lower()
            matches = sum(term in haystack for term in terms)
            if not matches:
                continue
            exact = sum(term == node.name.lower() for term in terms)
            support_penalty = (
                0
                if asks_for_support_code
                or not any(
                    marker in haystack
                    for marker in (
                        ".test",
                        ".tests",
                        "fixture",
                        "benchmark",
                        ".docs",
                        ".example",
                    )
                )
                else -5
            )
            score = (
                matches * 2
                + exact * 3
                + min(self.degree[node.id], 20) * 0.02
                + support_penalty
            )
            scored.append((score, node))
        scored.sort(key=lambda item: (-item[0], item[1].qualified_name))
        selected = [node for _, node in scored[:5]]
        if not selected:
            return GroundedAnswer(
                question=request.question,
                answer=(
                    "I could not locate a source-backed symbol matching that "
                    "question, so I will not invent an answer."
                ),
                citations=[],
                refused=True,
                basis="No indexed symbol names matched the meaningful query terms.",
            )
        citations = [
            GroundedCitation(
                node_id=node.id,
                qualified_name=node.qualified_name,
                kind=node.kind.value,
                span=node.span,
            )
            for node in selected
            if node.span
        ]
        primary = citations[0]
        alternatives = ", ".join(
            citation.qualified_name for citation in citations[1:3]
        )
        answer = (
            f"The strongest source-backed match is {primary.qualified_name} "
            f"in {primary.span.path} at line {primary.span.start_line}."
        )
        if alternatives:
            answer += f" Related matches include {alternatives}."
        return GroundedAnswer(
            question=request.question,
            answer=answer,
            citations=citations,
            refused=False,
            basis=(
                "Ranked exact and partial symbol-name matches, then used graph "
                "connectivity only as a tie-breaker."
            ),
        )

    @traced("journey.trace")
    def journey(self, start_node_id: str, max_steps: int = 20) -> CodeJourney:
        if start_node_id not in self.nodes:
            raise KeyError(start_node_id)
        adjacency: dict[str, list[tuple[GraphEdge, str, str]]] = {}
        priority = {
            EdgeKind.MAY_CALL: 0,
            EdgeKind.INSTANTIATES: 1,
            EdgeKind.IMPORTS: 2,
            EdgeKind.CONTAINS: 3,
        }
        for edge in self.edges:
            adjacency.setdefault(edge.source, []).append(
                (edge, edge.target, edge.kind.value)
            )
            reverse_relation = {
                EdgeKind.MAY_CALL: "called_by",
                EdgeKind.INSTANTIATES: "instantiated_by",
                EdgeKind.IMPORTS: "imported_by",
                EdgeKind.CONTAINS: "contained_by",
            }[edge.kind]
            adjacency.setdefault(edge.target, []).append(
                (edge, edge.source, reverse_relation)
            )
        for connections in adjacency.values():
            connections.sort(
                key=lambda item: (priority[item[0].kind], item[1], item[2])
            )
        visited = {start_node_id}
        queue: list[tuple[str, str | None, GraphEdge | None, str | None]] = [
            (start_node_id, None, None, None)
        ]
        steps: list[JourneyStep] = []
        cursor = 0
        while cursor < len(queue) and len(steps) < max_steps:
            node_id, parent_id, via, relation = queue[cursor]
            cursor += 1
            node = self.nodes[node_id]
            steps.append(
                JourneyStep(
                    index=len(steps) + 1,
                    node=node,
                    from_node_id=parent_id,
                    relationship=relation,
                    evidence=via.evidence.span if via else node.span,
                )
            )
            for edge, target_id, target_relation in adjacency.get(node_id, []):
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append(
                        (target_id, node_id, edge, target_relation)
                    )
        return CodeJourney(
            analysis_id=self.report.analysis_id or "",
            start_node_id=start_node_id,
            steps=steps,
            truncated=cursor < len(queue),
        )

    @traced("revision.compare")
    def compare(self, previous: AnalysisReport) -> RevisionReport:
        def modules(report: AnalysisReport) -> dict[str, GraphNode]:
            return {
                node.qualified_name: node
                for node in report.nodes
                if node.kind == NodeKind.MODULE and node.span is not None
            }

        current_modules = modules(self.report)
        previous_modules = modules(previous)
        current_names = set(current_modules)
        previous_names = set(previous_modules)

        def change(kind: str, node: GraphNode) -> RevisionChange:
            return RevisionChange(
                change=kind,
                qualified_name=node.qualified_name,
                path=node.span.path if node.span else "",
                node_id=node.id if kind != "removed" else None,
            )

        added = [
            change("added", current_modules[name])
            for name in sorted(current_names - previous_names)
        ]
        removed = [
            change("removed", previous_modules[name])
            for name in sorted(previous_names - current_names)
        ]
        modified = [
            change("modified", current_modules[name])
            for name in sorted(current_names & previous_names)
            if current_modules[name].metadata.get("content_sha256")
            != previous_modules[name].metadata.get("content_sha256")
        ]
        unchanged_count = len(current_names & previous_names) - len(modified)
        refresher = [
            f"Review {item.qualified_name} ({item.path})"
            for item in [*modified, *added][:10]
        ]
        if removed:
            refresher.append(
                f"Confirm callers no longer depend on {removed[0].qualified_name}"
            )
        return RevisionReport(
            analysis_id=self.report.analysis_id or "",
            base_analysis_id=previous.analysis_id or "",
            added=added,
            modified=modified,
            removed=removed,
            unchanged_count=unchanged_count,
            refresher=refresher,
        )
