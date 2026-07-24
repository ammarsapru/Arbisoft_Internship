from __future__ import annotations

import logging
import os
import json
import sqlite3
import threading
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from contextlib import closing

from backend.app.config import settings
from backend.app.indexing import repository_snapshot

from backend.app.graph.models import (
    AnalysisReport,
    GraphEdge,
    GraphNeighborhood,
    GraphNode,
    GraphSummary,
)
from backend.app.observability import log_event, traced

logger = logging.getLogger(__name__)

_CONTEXT_EXTENSIONS = {
    ".css",
    ".gradle",
    ".json",
    ".kts",
    ".md",
    ".mdx",
    ".properties",
    ".toml",
    ".txt",
    ".xml",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
}
_CONTEXT_NAMES = {
    ".env.example",
    "dockerfile",
    "gradlew",
    "justfile",
    "makefile",
    "mvnw",
}
_SKIPPED_CONTEXT_DIRECTORIES = {
    ".agents",
    ".codex",
    ".git",
    ".hg",
    ".venv",
    ".waypoint-clones",
    ".waypoint-data",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}


def _discover_context_paths(root: Path, limit: int = 500) -> set[str]:
    discovered: set[str] = set()
    resolved_root = root.resolve()
    for current_root, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in _SKIPPED_CONTEXT_DIRECTORIES
            and not (Path(current_root) / directory).is_symlink()
        )
        for filename in sorted(files):
            if len(discovered) >= limit:
                return discovered
            candidate = Path(current_root) / filename
            if candidate.is_symlink():
                continue
            if (
                candidate.suffix.lower() not in _CONTEXT_EXTENSIONS
                and candidate.name.lower() not in _CONTEXT_NAMES
            ):
                continue
            try:
                candidate.resolve().relative_to(resolved_root)
            except (OSError, ValueError):
                continue
            discovered.add(candidate.relative_to(root).as_posix())
    return discovered


@dataclass(frozen=True, slots=True)
class AnalysisSession:
    id: str
    root: Path
    report: AnalysisReport
    source_paths: frozenset[str]
    revision_fingerprint: str = ""


class AnalysisSessionStore:
    """Thread-safe bounded cache backed by restart-safe SQLite sessions."""

    def __init__(self, max_sessions: int = 50) -> None:
        self.max_sessions = max_sessions
        self._sessions: OrderedDict[str, AnalysisSession] = OrderedDict()
        self._lock = threading.RLock()

    def _persist(self, session: AnalysisSession) -> None:
        settings.state_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(settings.state_path, timeout=10)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_sessions (
                    id TEXT PRIMARY KEY,
                    root TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    source_paths_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revision_fingerprint TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(analysis_sessions)"
                ).fetchall()
            }
            if "revision_fingerprint" not in columns:
                connection.execute(
                    "ALTER TABLE analysis_sessions ADD COLUMN "
                    "revision_fingerprint TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "INSERT OR REPLACE INTO analysis_sessions("
                "id, root, report_json, source_paths_json, updated_at, "
                "revision_fingerprint"
                ") VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)",
                (
                    session.id,
                    str(session.root),
                    session.report.model_dump_json(),
                    json.dumps(sorted(session.source_paths)),
                    session.revision_fingerprint,
                ),
            )
            rows = connection.execute(
                "SELECT id FROM analysis_sessions ORDER BY updated_at DESC"
            ).fetchall()
            for (identifier,) in rows[self.max_sessions :]:
                connection.execute(
                    "DELETE FROM analysis_sessions WHERE id = ?", (identifier,)
                )
            connection.commit()

    def _restore(self, analysis_id: str) -> AnalysisSession | None:
        if not settings.state_path.is_file():
            return None
        with closing(sqlite3.connect(settings.state_path, timeout=10)) as connection:
            try:
                row = connection.execute(
                    "SELECT root, report_json, source_paths_json, "
                    "revision_fingerprint "
                    "FROM analysis_sessions WHERE id = ?",
                    (analysis_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                try:
                    legacy = connection.execute(
                        "SELECT root, report_json, source_paths_json "
                        "FROM analysis_sessions WHERE id = ?",
                        (analysis_id,),
                    ).fetchone()
                except sqlite3.OperationalError:
                    return None
                row = (*legacy, "") if legacy is not None else None
        if row is None:
            return None
        root = Path(row[0]).resolve()
        try:
            root.relative_to(settings.allowed_root)
        except ValueError:
            return None
        if not root.is_dir():
            return None
        try:
            report = AnalysisReport.model_validate_json(row[1])
            source_paths = frozenset(json.loads(row[2]))
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
        return AnalysisSession(
            id=analysis_id,
            root=root,
            report=report,
            source_paths=source_paths,
            revision_fingerprint=str(row[3] or ""),
        )

    def _make_session(
        self,
        analysis_id: str,
        root: Path,
        report: AnalysisReport,
    ) -> AnalysisSession:
        snapshot = repository_snapshot(
            root, int(getattr(settings, "max_repository_files", 5_000))
        )
        return AnalysisSession(
            id=analysis_id,
            root=root.resolve(),
            report=report.model_copy(update={"analysis_id": analysis_id}),
            source_paths=snapshot.paths,
            revision_fingerprint=snapshot.fingerprint,
        )

    @traced("graph.session.create")
    def create(self, root: Path, report: AnalysisReport) -> AnalysisReport:
        analysis_id = uuid.uuid4().hex
        session = self._make_session(analysis_id, root, report)
        stored_report = session.report
        parsed_source_paths = {
            node.span.path
            for node in stored_report.nodes
            if node.kind.value == "module" and node.span is not None
        }
        context_paths = set(session.source_paths) - parsed_source_paths
        evicted: list[str] = []
        with self._lock:
            self._sessions[analysis_id] = session
            self._sessions.move_to_end(analysis_id)
            while len(self._sessions) > self.max_sessions:
                removed_id, _ = self._sessions.popitem(last=False)
                evicted.append(removed_id)
        self._persist(session)
        log_event(
            logger,
            logging.INFO,
            "graph.session_created",
            "Analysis session stored for interactive navigation",
            analysis_id=analysis_id,
            repository_root=root,
            node_count=stored_report.stats.node_count,
            edge_count=stored_report.stats.edge_count,
            source_file_count=len(session.source_paths),
            parsed_source_file_count=len(parsed_source_paths),
            context_file_count=len(context_paths),
            evicted_sessions=evicted,
        )
        return stored_report

    @traced("graph.session.refresh")
    def refresh(
        self,
        analysis_id: str,
        root: Path,
        report: AnalysisReport,
    ) -> AnalysisSession:
        """Replace an analysis atomically while preserving its public identifier."""
        session = self._make_session(analysis_id, root, report)
        with self._lock:
            self._sessions[analysis_id] = session
            self._sessions.move_to_end(analysis_id)
        self._persist(session)
        log_event(
            logger,
            logging.INFO,
            "graph.session_refreshed",
            "Analysis session refreshed after repository content changed",
            analysis_id=analysis_id,
            revision_fingerprint=session.revision_fingerprint,
            node_count=session.report.stats.node_count,
            edge_count=session.report.stats.edge_count,
            source_file_count=len(session.source_paths),
        )
        return session

    @traced("graph.session.get")
    def get(self, analysis_id: str) -> AnalysisSession:
        with self._lock:
            session = self._sessions.get(analysis_id)
            if session is None:
                session = self._restore(analysis_id)
                if session is None:
                    raise KeyError(analysis_id)
                self._sessions[analysis_id] = session
                while len(self._sessions) > self.max_sessions:
                    self._sessions.popitem(last=False)
            self._sessions.move_to_end(analysis_id)
            return session

    @traced("graph.session.list")
    def list_recent(self) -> list[AnalysisSession]:
        """Return restart-safe analysis sessions, newest first."""
        if not settings.state_path.is_file():
            with self._lock:
                return list(reversed(self._sessions.values()))
        with closing(sqlite3.connect(settings.state_path, timeout=10)) as connection:
            try:
                identifiers = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT id FROM analysis_sessions ORDER BY updated_at DESC LIMIT ?",
                        (self.max_sessions,),
                    ).fetchall()
                ]
            except sqlite3.OperationalError:
                return []
        sessions: list[AnalysisSession] = []
        for identifier in identifiers:
            restored = self._restore(identifier)
            if restored is not None:
                sessions.append(restored)
        return sessions


class GraphQueryService:
    def __init__(self, report: AnalysisReport) -> None:
        self.report = report
        self.nodes = {node.id: node for node in report.nodes}
        self.edges = report.edges

    @traced("graph.query.neighborhood")
    def neighborhood(self, node_id: str, depth: int) -> GraphNeighborhood:
        if node_id not in self.nodes:
            raise KeyError(node_id)
        adjacency: dict[str, set[str]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.source, set()).add(edge.target)
            adjacency.setdefault(edge.target, set()).add(edge.source)
        visited = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, current_depth + 1))
        selected_edges = [
            edge
            for edge in self.edges
            if edge.source in visited and edge.target in visited
        ]
        return GraphNeighborhood(
            center_node_id=node_id,
            depth=depth,
            nodes=[self.nodes[item] for item in visited],
            edges=selected_edges,
        )

    @traced("graph.query.summary")
    def summary(self) -> GraphSummary:
        node_counts: dict[str, int] = {}
        edge_counts: dict[str, int] = {}
        evidence_counts: dict[str, int] = {}
        degree: dict[str, int] = {node_id: 0 for node_id in self.nodes}
        for node in self.nodes.values():
            node_counts[node.kind.value] = node_counts.get(node.kind.value, 0) + 1
        for edge in self.edges:
            edge_counts[edge.kind.value] = edge_counts.get(edge.kind.value, 0) + 1
            status = edge.evidence.status.value
            evidence_counts[status] = evidence_counts.get(status, 0) + 1
            degree[edge.source] = degree.get(edge.source, 0) + 1
            degree[edge.target] = degree.get(edge.target, 0) + 1
        ranked = sorted(degree.items(), key=lambda item: (-item[1], item[0]))[:10]
        return GraphSummary(
            analysis_id=self.report.analysis_id or "",
            node_counts=node_counts,
            edge_counts=edge_counts,
            evidence_counts=evidence_counts,
            top_connected_nodes=[
                {
                    "node_id": node_id,
                    "qualified_name": self.nodes[node_id].qualified_name,
                    "kind": self.nodes[node_id].kind.value,
                    "connections": connections,
                }
                for node_id, connections in ranked
            ],
        )

    @traced("graph.query.overview")
    def overview(self, full_graph_threshold: int = 4_000) -> AnalysisReport:
        """Return a browser-safe initial graph while retaining the full session."""
        if len(self.report.nodes) <= full_graph_threshold:
            return self.report.model_copy(update={"view": "full"})
        selected_ids = {
            node.id
            for node in self.report.nodes
            if node.kind.value in {"repository", "module"}
        }
        overview_edges = [
            edge
            for edge in self.edges
            if edge.source in selected_ids and edge.target in selected_ids
        ]
        overview = self.report.model_copy(
            update={
                "view": "overview",
                "nodes": [
                    node for node in self.report.nodes if node.id in selected_ids
                ],
                "edges": overview_edges,
                "unresolved_references": [
                    reference
                    for reference in self.report.unresolved_references
                    if reference.reference_kind == "import"
                ],
            }
        )
        log_event(
            logger,
            logging.INFO,
            "graph.overview_created",
            "Large graph projected to module-level browser overview",
            analysis_id=self.report.analysis_id,
            full_node_count=len(self.report.nodes),
            returned_node_count=len(overview.nodes),
            full_edge_count=len(self.report.edges),
            returned_edge_count=len(overview.edges),
            threshold=full_graph_threshold,
        )
        return overview


analysis_sessions = AnalysisSessionStore()
