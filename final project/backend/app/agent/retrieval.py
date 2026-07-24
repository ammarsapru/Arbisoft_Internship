from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
import threading
import time
import tokenize
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.graph.models import GraphNode
from backend.app.graph.store import AnalysisSession, GraphQueryService
from backend.app.indexing import RepositorySnapshot, repository_snapshot
from backend.app.observability import log_event

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
logger = logging.getLogger(__name__)
INDEX_SCHEMA_VERSION = "2"


class LocalCodeVectorizer:
    """Deterministic sparse subword vectors for local fuzzy code retrieval."""

    dimensions = 768

    @classmethod
    def vectorize(cls, text: str) -> dict[int, float]:
        features: dict[int, float] = {}
        raw_words = _TOKEN.findall(text)
        words: list[str] = []
        for raw in raw_words:
            words.append(raw.lower())
            words.extend(
                part.lower()
                for part in re.findall(
                    r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+",
                    raw.replace("_", " "),
                )
                if len(part) > 1
            )
        for word in words:
            variants = {word}
            for suffix in ("ing", "tion", "ment", "ers", "ies", "ed", "es", "s"):
                if word.endswith(suffix) and len(word) > len(suffix) + 3:
                    variants.add(word[: -len(suffix)])
            padded = f"^{word}$"
            variants.update(
                padded[index:index + 3] for index in range(len(padded) - 2)
            )
            for feature in variants:
                bucket = int.from_bytes(
                    hashlib.blake2b(
                        feature.encode("utf-8"), digest_size=4
                    ).digest(),
                    "big",
                ) % cls.dimensions
                features[bucket] = features.get(bucket, 0.0) + 1.0
        norm = math.sqrt(sum(value * value for value in features.values())) or 1.0
        return {key: value / norm for key, value in features.items()}

    @staticmethod
    def similarity(left: dict[int, float], right: dict[int, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(key, 0.0) for key, value in left.items())


class PersistentCodeIndex:
    """SQLite persistence for revisioned chunks, symbols, edges, and FTS search."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS code_repositories (
                id TEXT PRIMARY KEY,
                canonical_root TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS code_revisions (
                id TEXT PRIMARY KEY,
                repository_id TEXT NOT NULL,
                analysis_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('building', 'complete', 'failed')),
                indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(repository_id, fingerprint),
                FOREIGN KEY (repository_id) REFERENCES code_repositories(id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS code_files (
                revision_id TEXT NOT NULL,
                path TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                PRIMARY KEY (revision_id, path),
                FOREIGN KEY (revision_id) REFERENCES code_revisions(id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS code_symbols (
                revision_id TEXT NOT NULL,
                id TEXT NOT NULL,
                path TEXT,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                qualified_name TEXT NOT NULL,
                signature TEXT,
                start_line INTEGER,
                end_line INTEGER,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY (revision_id, id),
                FOREIGN KEY (revision_id) REFERENCES code_revisions(id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS code_chunks (
                revision_id TEXT NOT NULL,
                id TEXT NOT NULL,
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                symbol_id TEXT,
                qualified_name TEXT,
                contextual_text TEXT NOT NULL,
                PRIMARY KEY (revision_id, id),
                FOREIGN KEY (revision_id) REFERENCES code_revisions(id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS code_edges (
                revision_id TEXT NOT NULL,
                id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_status TEXT NOT NULL,
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY (revision_id, id),
                FOREIGN KEY (revision_id) REFERENCES code_revisions(id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS code_chunk_vectors (
                revision_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                vectorizer TEXT NOT NULL,
                PRIMARY KEY (revision_id, chunk_id),
                FOREIGN KEY (revision_id) REFERENCES code_revisions(id)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_code_symbols_name
                ON code_symbols(revision_id, name, qualified_name);
            CREATE INDEX IF NOT EXISTS idx_code_edges_source
                ON code_edges(revision_id, source_id, kind);
            CREATE INDEX IF NOT EXISTS idx_code_edges_target
                ON code_edges(revision_id, target_id, kind);
            CREATE VIRTUAL TABLE IF NOT EXISTS code_chunks_fts USING fts5(
                revision_id UNINDEXED,
                chunk_id UNINDEXED,
                path,
                qualified_name,
                contextual_text,
                content,
                tokenize = 'unicode61 tokenchars _'
            );
            """
        )

    @staticmethod
    def repository_id(root: Path) -> str:
        return hashlib.sha256(str(root.resolve()).lower().encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def revision_id(repository_id: str, fingerprint: str) -> str:
        return hashlib.sha256(
            f"{repository_id}:{fingerprint}:{INDEX_SCHEMA_VERSION}".encode()
        ).hexdigest()[:24]

    def load_chunks(self, revision_id: str) -> list[SourceChunk] | None:
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            revision = connection.execute(
                "SELECT status FROM code_revisions WHERE id = ?", (revision_id,)
            ).fetchone()
            if revision is None or revision["status"] != "complete":
                return None
            rows = connection.execute(
                "SELECT id, path, start_line, end_line, kind, content, symbol_id, "
                "qualified_name FROM code_chunks WHERE revision_id = ? "
                "ORDER BY path, start_line, id",
                (revision_id,),
            ).fetchall()
            return [SourceChunk(**dict(row)) for row in rows]

    def publish(
        self,
        session: AnalysisSession,
        snapshot: RepositorySnapshot,
        revision_id: str,
        chunks: list[SourceChunk],
    ) -> None:
        repository_id = self.repository_id(session.root)
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO code_repositories(id, canonical_root, display_name) "
                "VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "display_name = excluded.display_name, updated_at = CURRENT_TIMESTAMP",
                (repository_id, str(session.root), session.report.repository_name),
            )
            existing = connection.execute(
                "SELECT status FROM code_revisions WHERE id = ?", (revision_id,)
            ).fetchone()
            if existing is not None and existing["status"] == "complete":
                connection.rollback()
                return
            connection.execute(
                "INSERT OR REPLACE INTO code_revisions("
                "id, repository_id, analysis_id, fingerprint, status, indexed_at"
                ") VALUES (?, ?, ?, ?, 'building', CURRENT_TIMESTAMP)",
                (revision_id, repository_id, session.id, snapshot.fingerprint),
            )
            for table in ("code_files", "code_symbols", "code_chunks", "code_edges"):
                connection.execute(f"DELETE FROM {table} WHERE revision_id = ?", (revision_id,))
            connection.execute(
                "DELETE FROM code_chunks_fts WHERE revision_id = ?", (revision_id,)
            )
            connection.executemany(
                "INSERT INTO code_files(revision_id, path, content_sha256, size_bytes) "
                "VALUES (?, ?, ?, ?)",
                ((revision_id, item.path, item.content_sha256, item.size_bytes) for item in snapshot.files),
            )
            connection.executemany(
                "INSERT INTO code_symbols(revision_id, id, path, kind, name, "
                "qualified_name, signature, start_line, end_line, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        revision_id, node.id, node.span.path if node.span else None,
                        node.kind.value, node.name, node.qualified_name, node.signature,
                        node.span.start_line if node.span else None,
                        node.span.end_line if node.span else None,
                        json.dumps(node.metadata, sort_keys=True, default=str),
                    )
                    for node in session.report.nodes
                ),
            )
            chunk_rows = [
                (
                    revision_id, chunk.id, chunk.path, chunk.start_line, chunk.end_line,
                    chunk.kind, chunk.content, chunk.symbol_id, chunk.qualified_name,
                    self._contextual_text(session, chunk),
                )
                for chunk in chunks
            ]
            connection.executemany(
                "INSERT INTO code_chunks(revision_id, id, path, start_line, end_line, "
                "kind, content, symbol_id, qualified_name, contextual_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                chunk_rows,
            )
            connection.executemany(
                "INSERT INTO code_chunks_fts(revision_id, chunk_id, path, qualified_name, "
                "contextual_text, content) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (row[0], row[1], row[2], row[8] or "", row[9], row[6])
                    for row in chunk_rows
                ),
            )
            connection.executemany(
                "INSERT INTO code_edges(revision_id, id, source_id, target_id, kind, "
                "confidence, evidence_status, path, start_line, end_line, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        revision_id, edge.id, edge.source, edge.target, edge.kind.value,
                        edge.evidence.confidence, edge.evidence.status.value,
                        edge.evidence.span.path, edge.evidence.span.start_line,
                        edge.evidence.span.end_line,
                        json.dumps(edge.metadata, sort_keys=True, default=str),
                    )
                    for edge in session.report.edges
                ),
            )
            connection.execute(
                "UPDATE code_revisions SET status = 'complete', indexed_at = CURRENT_TIMESTAMP "
                "WHERE id = ?", (revision_id,)
            )
            stale = connection.execute(
                "SELECT id FROM code_revisions WHERE repository_id = ? AND status = 'complete' "
                "ORDER BY indexed_at DESC", (repository_id,)
            ).fetchall()[3:]
            for row in stale:
                connection.execute("DELETE FROM code_chunks_fts WHERE revision_id = ?", (row["id"],))
                connection.execute("DELETE FROM code_revisions WHERE id = ?", (row["id"],))
            connection.commit()

    @staticmethod
    def _contextual_text(session: AnalysisSession, chunk: SourceChunk) -> str:
        identifier_text = " ".join(
            part.lower()
            for part in re.findall(
                r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+",
                f"{chunk.path} {chunk.qualified_name or ''}".replace("_", " "),
            )
            if len(part) > 1
        )
        return "\n".join(
            (
                f"Repository: {session.report.repository_name}",
                f"Path: {chunk.path}",
                f"Kind: {chunk.kind}",
                f"Symbol: {chunk.qualified_name or 'file content'}",
                f"Identifiers: {identifier_text}",
            )
        )

    def search(self, revision_id: str, query: str, limit: int) -> list[tuple[str, float]]:
        tokens = list(dict.fromkeys(_TOKEN.findall(query.lower())))
        if not tokens:
            return []
        expression = " OR ".join(f'"{token}"' for token in tokens)
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            rows = connection.execute(
                "SELECT chunk_id, bm25(code_chunks_fts, 0, 0, 2.5, 4.0, 1.5, 1.0) AS rank "
                "FROM code_chunks_fts WHERE code_chunks_fts MATCH ? AND revision_id = ? "
                "ORDER BY rank LIMIT ?",
                (expression, revision_id, max(1, min(limit, 200))),
            ).fetchall()
            return [(str(row["chunk_id"]), -float(row["rank"])) for row in rows]

    def ensure_vectors(
        self,
        revision_id: str,
        session: AnalysisSession,
        chunks: list[SourceChunk],
    ) -> None:
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            # Reuse vectors only when both stable chunk ID and exact source content
            # match a prior revision. This avoids recomputation without stale vectors.
            connection.execute(
                "INSERT OR IGNORE INTO code_chunk_vectors("
                "revision_id, chunk_id, vector_json, vectorizer) "
                "SELECT ?, current.id, vectors.vector_json, vectors.vectorizer "
                "FROM code_chunks AS current "
                "JOIN code_chunks AS previous ON previous.id = current.id "
                "AND previous.content = current.content "
                "AND previous.revision_id != current.revision_id "
                "JOIN code_chunk_vectors AS vectors "
                "ON vectors.revision_id = previous.revision_id "
                "AND vectors.chunk_id = previous.id "
                "WHERE current.revision_id = ? "
                "AND vectors.vectorizer = 'local-subword-v3'",
                (revision_id, revision_id),
            )
            existing = {
                str(row[0]) for row in connection.execute(
                    "SELECT chunk_id FROM code_chunk_vectors WHERE revision_id = ? "
                    "AND vectorizer = 'local-subword-v3'",
                    (revision_id,),
                ).fetchall()
            }
            missing = [chunk for chunk in chunks if chunk.id not in existing]
            if not missing:
                return
            connection.executemany(
                "INSERT OR REPLACE INTO code_chunk_vectors("
                "revision_id, chunk_id, vector_json, vectorizer) VALUES (?, ?, ?, ?)",
                (
                    (
                        revision_id,
                        chunk.id,
                        json.dumps(
                            LocalCodeVectorizer.vectorize(
                                f"{self._contextual_text(session, chunk)}\n{chunk.content}"
                            ),
                            separators=(",", ":"),
                        ),
                        "local-subword-v3",
                    )
                    for chunk in missing
                ),
            )
            connection.commit()

    def vector_search(
        self, revision_id: str, query: str, limit: int
    ) -> list[tuple[str, float]]:
        query_vector = LocalCodeVectorizer.vectorize(query)
        if not query_vector:
            return []
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            rows = connection.execute(
                "SELECT chunk_id, vector_json FROM code_chunk_vectors "
                "WHERE revision_id = ? AND vectorizer = 'local-subword-v3'",
                (revision_id,),
            ).fetchall()
        ranked: list[tuple[str, float]] = []
        for row in rows:
            raw = json.loads(str(row["vector_json"]))
            vector = {int(key): float(value) for key, value in raw.items()}
            score = LocalCodeVectorizer.similarity(query_vector, vector)
            if score > 0.02:
                ranked.append((str(row["chunk_id"]), score))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked[: max(1, min(limit, 200))]

    def status(self, revision_id: str) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            revision = connection.execute(
                "SELECT fingerprint, status, indexed_at FROM code_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
            if revision is None:
                return {"revision_id": revision_id, "status": "missing"}
            counts = {}
            for label, table in (
                ("files", "code_files"), ("symbols", "code_symbols"),
                ("chunks", "code_chunks"), ("edges", "code_edges"),
                ("vectors", "code_chunk_vectors"),
            ):
                counts[label] = int(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE revision_id = ?",
                    (revision_id,),
                ).fetchone()[0])
            return {
                "revision_id": revision_id,
                "fingerprint": str(revision["fingerprint"]),
                "status": str(revision["status"]),
                "indexed_at": str(revision["indexed_at"]),
                **counts,
            }

    def delete_revision(self, revision_id: str) -> None:
        with self._lock, closing(self._connect()) as connection:
            self._initialize(connection)
            connection.execute(
                "DELETE FROM code_chunks_fts WHERE revision_id = ?", (revision_id,)
            )
            connection.execute(
                "DELETE FROM code_revisions WHERE id = ?", (revision_id,)
            )
            connection.commit()


@dataclass(frozen=True, slots=True)
class SourceChunk:
    id: str
    path: str
    start_line: int
    end_line: int
    kind: str
    content: str
    symbol_id: str | None = None
    qualified_name: str | None = None

    def public(self, score: float | None = None) -> dict[str, Any]:
        value: dict[str, Any] = {
            "chunk_id": self.id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "kind": self.kind,
            "symbol_id": self.symbol_id,
            "qualified_name": self.qualified_name,
            "excerpt": self.content[:1600],
        }
        if score is not None:
            value["score"] = round(score, 4)
        return value


class RepositoryRetrievalIndex:
    """Persistent, source-span-aware lexical and graph retrieval for one revision."""

    def __init__(
        self,
        session: AnalysisSession,
        database_path: Path | None = None,
        snapshot: RepositorySnapshot | None = None,
    ) -> None:
        self.session = session
        self.nodes = {node.id: node for node in session.report.nodes}
        self._lines: dict[str, list[str]] = {}
        self.snapshot = snapshot or repository_snapshot(
            session.root, settings.max_repository_files
        )
        repository_id = PersistentCodeIndex.repository_id(session.root)
        self.revision_id = PersistentCodeIndex.revision_id(
            repository_id, self.snapshot.fingerprint
        )
        self.storage = PersistentCodeIndex(database_path or settings.state_path)
        restored = self.storage.load_chunks(self.revision_id)
        if restored is not None:
            self.chunks = restored
            log_event(
                logger,
                logging.INFO,
                "retrieval.index_restored",
                "Persistent repository retrieval index restored",
                analysis_id=session.id,
                revision_id=self.revision_id,
                chunk_count=len(self.chunks),
            )
        else:
            self.chunks = self._build_chunks()
            self.storage.publish(session, self.snapshot, self.revision_id, self.chunks)
            log_event(
                logger,
                logging.INFO,
                "retrieval.index_published",
                "Persistent repository retrieval index published",
                analysis_id=session.id,
                revision_id=self.revision_id,
                file_count=len(self.snapshot.files),
                chunk_count=len(self.chunks),
                node_count=len(session.report.nodes),
                edge_count=len(session.report.edges),
            )
        self.storage.ensure_vectors(
            self.revision_id, self.session, self.chunks
        )

    def _safe_lines(self, source_path: str) -> list[str]:
        if source_path in self._lines:
            return self._lines[source_path]
        if source_path not in self.session.source_paths:
            raise ValueError("Source path is not part of this analysis")
        resolved = (self.session.root / Path(source_path)).resolve()
        try:
            resolved.relative_to(self.session.root)
        except ValueError as exc:
            raise ValueError("Source path escapes the analyzed repository") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError("Indexed source file is unavailable")
        if resolved.stat().st_size > settings.max_python_file_bytes:
            raise ValueError("Source file exceeds the configured size limit")
        try:
            if resolved.suffix.lower() == ".py":
                with tokenize.open(resolved) as stream:
                    lines = stream.read().splitlines()
            else:
                lines = resolved.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"Source file could not be decoded: {exc}") from exc
        self._lines[source_path] = lines
        return lines

    @staticmethod
    def _chunk_id(
        path: str,
        start_line: int,
        end_line: int,
        kind: str,
        symbol_id: str = "",
    ) -> str:
        # Different symbols can legitimately share a span and kind (for example,
        # overloads and parser-emitted declarations). Include the stable graph ID
        # so one revision can always persist every symbol chunk uniquely.
        raw = f"{path}:{start_line}:{end_line}:{kind}:{symbol_id}".encode()
        return hashlib.sha256(raw).hexdigest()[:20]

    def _build_chunks(self) -> list[SourceChunk]:
        chunks: list[SourceChunk] = []
        covered_symbols: set[str] = set()
        for node in self.session.report.nodes:
            if not node.span or node.kind.value == "repository":
                continue
            try:
                lines = self._safe_lines(node.span.path)
            except ValueError:
                continue
            if not lines:
                continue
            start = max(1, node.span.start_line)
            end = min(len(lines), max(start, node.span.end_line))
            if node.kind.value == "module":
                end = min(end, start + 159)
            content = "\n".join(lines[start - 1 : end]).strip()
            if not content:
                continue
            chunks.append(
                SourceChunk(
                    id=self._chunk_id(
                        node.span.path,
                        start,
                        end,
                        node.kind.value,
                        node.id,
                    ),
                    path=node.span.path,
                    start_line=start,
                    end_line=end,
                    kind=node.kind.value,
                    content=content,
                    symbol_id=node.id,
                    qualified_name=node.qualified_name,
                )
            )
            covered_symbols.add(node.id)

        symbol_paths = {chunk.path for chunk in chunks}
        for path in sorted(self.session.source_paths):
            try:
                lines = self._safe_lines(path)
            except ValueError:
                continue
            if not lines:
                continue
            # Documentation/configuration and files without parsed definitions are
            # chunked by lines. Parsed source uses its language-neutral symbol chunks.
            if path in symbol_paths and Path(path).suffix.lower() in {
                ".py", ".js", ".jsx", ".mjs", ".cjs",
                ".ts", ".tsx", ".mts", ".cts", ".java",
            }:
                continue
            for offset in range(0, len(lines), 100):
                end_offset = min(len(lines), offset + 120)
                content = "\n".join(lines[offset:end_offset]).strip()
                if content:
                    chunks.append(
                        SourceChunk(
                            id=self._chunk_id(path, offset + 1, end_offset, "file"),
                            path=path,
                            start_line=offset + 1,
                            end_line=end_offset,
                            kind="file",
                            content=content,
                        )
                    )
                if end_offset == len(lines):
                    break
        return chunks

    def tree(self, prefix: str = "", limit: int = 300) -> dict[str, Any]:
        normalized = prefix.strip("/\\").lower()
        paths = [
            path
            for path in sorted(self.session.source_paths)
            if not normalized or path.lower().startswith(normalized)
        ]
        return {
            "paths": paths[: max(1, min(limit, 1000))],
            "total": len(paths),
            "truncated": len(paths) > limit,
        }

    @staticmethod
    def _is_test_path(path: str) -> bool:
        normalized = f"/{path.lower().replace(chr(92), '/')}"
        name = Path(path).name.lower()
        return (
            "/test/" in normalized or "/tests/" in normalized
            or "/__tests__/" in normalized or name.startswith("test_")
            or ".test." in name or ".spec." in name
        )

    @staticmethod
    def _language(path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix == ".java":
            return "java"
        if suffix in {".ts", ".tsx", ".mts", ".cts"}:
            return "typescript"
        if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
            return "javascript"
        return "documentation" if suffix in {".md", ".mdx", ".txt"} else "configuration"

    def search(
        self,
        query: str,
        limit: int = 12,
        *,
        path_prefixes: list[str] | None = None,
        kinds: list[str] | None = None,
        languages: list[str] | None = None,
        include_tests: bool = True,
    ) -> list[dict[str, Any]]:
        normalized = query.strip().lower()
        tokens = set(_TOKEN.findall(normalized))
        if not normalized:
            return []
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "retrieval.query_started",
            "Hybrid repository retrieval started",
            analysis_id=self.session.id,
            revision_id=self.revision_id,
            query=query,
            limit=limit,
            path_prefixes=path_prefixes or [],
            kinds=kinds or [],
            languages=languages or [],
            include_tests=include_tests,
            indexed_chunks=len(self.chunks),
        )
        prefixes = tuple(
            Path(value).as_posix().strip("/").lower()
            for value in (path_prefixes or []) if value.strip()
        )
        allowed_kinds = {value.lower() for value in (kinds or [])}
        allowed_languages = {value.lower() for value in (languages or [])}
        try:
            fts_results = self.storage.search(self.revision_id, normalized, 200)
            fts_ranks = {
                chunk_id: 1.0 / (60 + rank)
                for rank, (chunk_id, _score) in enumerate(fts_results, start=1)
            }
            vector_results = self.storage.vector_search(
                self.revision_id, normalized, 200
            )
            vector_ranks = {
                chunk_id: 1.0 / (60 + rank)
                for rank, (chunk_id, _score) in enumerate(vector_results, start=1)
            }
            log_event(
                logger,
                logging.INFO,
                "retrieval.candidates_generated",
                "Lexical and vector candidates generated",
                analysis_id=self.session.id,
                revision_id=self.revision_id,
                fts_candidates=len(fts_results),
                vector_candidates=len(vector_results),
                top_fts=fts_results[:20],
                top_vectors=vector_results[:20],
            )
        except sqlite3.Error as exc:
            log_event(
                logger,
                logging.WARNING,
                "retrieval.fts_fallback",
                "Persistent FTS query failed; falling back to in-memory scoring",
                revision_id=self.revision_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            fts_ranks = {}
            vector_ranks = {}
        ranked: list[tuple[float, SourceChunk]] = []
        for chunk in self.chunks:
            lowered_path = chunk.path.lower()
            if prefixes and not any(lowered_path.startswith(prefix) for prefix in prefixes):
                continue
            if allowed_kinds and chunk.kind.lower() not in allowed_kinds:
                continue
            if allowed_languages and self._language(chunk.path) not in allowed_languages:
                continue
            if not include_tests and self._is_test_path(chunk.path):
                continue
            haystack = " ".join(
                (
                    chunk.path,
                    chunk.qualified_name or "",
                    chunk.content,
                )
            ).lower()
            matched = sum(haystack.count(token) for token in tokens)
            fts_score = fts_ranks.get(chunk.id)
            vector_score = vector_ranks.get(chunk.id)
            if (
                not matched and normalized not in haystack
                and fts_score is None and vector_score is None
            ):
                continue
            score = (
                float(matched)
                + (fts_score or 0.0) * 120.0
                + (vector_score or 0.0) * 90.0
            )
            if normalized in haystack:
                score += 12.0
            if any(token in (chunk.qualified_name or "").lower() for token in tokens):
                score += 6.0
            if any(token in chunk.path.lower() for token in tokens):
                score += 3.0
            if chunk.kind in {"class", "function", "method"}:
                score += 5.0
            elif chunk.kind == "module":
                score += 2.0
            asks_for_tests = any(
                token in {"test", "tests", "testing", "fixture", "coverage"}
                for token in tokens
            )
            if self._is_test_path(chunk.path) and not asks_for_tests:
                score -= 6.0
            ranked.append((score, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line))

        # Add bounded structural context around the strongest symbol-backed seeds.
        scores = {chunk.id: score for score, chunk in ranked}
        chunks_by_symbol = {
            chunk.symbol_id: chunk for chunk in self.chunks if chunk.symbol_id
        }
        related_ids: set[str] = set()
        for _score, seed in ranked[:5]:
            if not seed.symbol_id:
                continue
            for edge in self.session.report.edges:
                if edge.source == seed.symbol_id:
                    related_ids.add(edge.target)
                elif edge.target == seed.symbol_id:
                    related_ids.add(edge.source)
        for symbol_id in related_ids:
            chunk = chunks_by_symbol.get(symbol_id)
            if chunk is None or chunk.id in scores:
                continue
            lowered_path = chunk.path.lower()
            if prefixes and not any(lowered_path.startswith(prefix) for prefix in prefixes):
                continue
            if allowed_kinds and chunk.kind.lower() not in allowed_kinds:
                continue
            if allowed_languages and self._language(chunk.path) not in allowed_languages:
                continue
            if not include_tests and self._is_test_path(chunk.path):
                continue
            scores[chunk.id] = max((scores.get(seed.id, 0.0) for _, seed in ranked[:5]), default=1.0) * 0.18
            ranked.append((scores[chunk.id], chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line))

        bounded = max(1, min(limit, 50))
        if len(tokens) >= 3:
            diverse: list[tuple[float, SourceChunk]] = []
            deferred: list[tuple[float, SourceChunk]] = []
            seen_paths: set[str] = set()
            for item in ranked:
                if item[1].path in seen_paths:
                    deferred.append(item)
                else:
                    diverse.append(item)
                    seen_paths.add(item[1].path)
            ranked = [*diverse, *deferred]
        selected = [chunk.public(score) for score, chunk in ranked[:bounded]]
        log_event(
            logger,
            logging.INFO,
            "retrieval.query_completed",
            "Hybrid repository retrieval completed",
            analysis_id=self.session.id,
            revision_id=self.revision_id,
            query=query,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            fused_candidates=len(scores),
            graph_related_symbols=len(related_ids),
            returned=len(selected),
            results=selected,
        )
        return selected

    def find_symbols(
        self,
        query: str,
        limit: int = 20,
        kinds: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized = query.strip().lower()
        allowed_kinds = {value.lower() for value in (kinds or [])}
        allowed_languages = {value.lower() for value in (languages or [])}
        ranked: list[tuple[float, GraphNode]] = []
        for node in self.nodes.values():
            if node.kind.value == "repository":
                continue
            if allowed_kinds and node.kind.value not in allowed_kinds:
                continue
            language = str(node.metadata.get("language", "")).lower()
            if allowed_languages and language not in allowed_languages:
                continue
            name = node.name.lower()
            qualified = node.qualified_name.lower()
            if normalized not in name and normalized not in qualified:
                continue
            score = 20.0 if name == normalized else 12.0 if name.startswith(normalized) else 6.0
            if qualified.endswith(f".{normalized}"):
                score += 4.0
            ranked.append((score, node))
        ranked.sort(key=lambda item: (-item[0], item[1].qualified_name))
        results = []
        for score, node in ranked[: max(1, min(limit, 100))]:
            results.append({
                "node_id": node.id,
                "kind": node.kind.value,
                "name": node.name,
                "qualified_name": node.qualified_name,
                "signature": node.signature,
                "language": node.metadata.get("language"),
                "path": node.span.path if node.span else None,
                "start_line": node.span.start_line if node.span else None,
                "end_line": node.span.end_line if node.span else None,
                "score": score,
            })
        return {"query": query, "revision_id": self.revision_id, "results": results, "count": len(results)}

    def status(self) -> dict[str, Any]:
        return self.storage.status(self.revision_id)

    def read(self, path: str, start_line: int = 1, end_line: int = 200) -> dict[str, Any]:
        lines = self._safe_lines(Path(path).as_posix())
        start = max(1, start_line)
        end = min(len(lines), max(start, end_line), start + 249)
        numbered = "\n".join(
            f"{number:>6} | {lines[number - 1]}" for number in range(start, end + 1)
        )
        return {
            "path": Path(path).as_posix(),
            "start_line": start,
            "end_line": end,
            "line_count": len(lines),
            "content": numbered,
        }

    def symbol(self, node_id: str) -> dict[str, Any]:
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError("Graph node was not found")
        neighbors = GraphQueryService(self.session.report).neighborhood(node_id, 1)
        return {
            "node": node.model_dump(mode="json"),
            "neighbors": [item.model_dump(mode="json") for item in neighbors.nodes],
            "edges": [item.model_dump(mode="json") for item in neighbors.edges],
        }

    def graph_neighborhood(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        neighborhood = GraphQueryService(self.session.report).neighborhood(
            node_id, max(1, min(depth, 3))
        )
        return neighborhood.model_dump(mode="json")

    def node_for_path(self, path: str) -> GraphNode | None:
        modules = [
            node
            for node in self.nodes.values()
            if node.span and node.span.path == path and node.kind.value == "module"
        ]
        return modules[0] if modules else None


class RepositoryIndexStore:
    """Thread-safe bounded cache so one analysis is indexed only once."""

    def __init__(self, max_indexes: int = 10) -> None:
        self.max_indexes = max_indexes
        self._indexes: OrderedDict[str, RepositoryRetrievalIndex] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, session: AnalysisSession) -> RepositoryRetrievalIndex:
        snapshot = repository_snapshot(session.root, settings.max_repository_files)
        if (
            session.revision_fingerprint
            and snapshot.fingerprint != session.revision_fingerprint
        ):
            log_event(
                logger,
                logging.INFO,
                "retrieval.repository_change_detected",
                "Repository changed since analysis; refreshing graph and index",
                analysis_id=session.id,
                previous_fingerprint=session.revision_fingerprint,
                current_fingerprint=snapshot.fingerprint,
            )
            from backend.app.graph.analyzer import RepositoryAnalyzer
            from backend.app.graph.store import analysis_sessions

            refreshed_report = RepositoryAnalyzer().analyze(session.root)
            session = analysis_sessions.refresh(
                session.id, session.root, refreshed_report
            )
            snapshot = repository_snapshot(
                session.root, settings.max_repository_files
            )
        repository_id = PersistentCodeIndex.repository_id(session.root)
        revision_id = PersistentCodeIndex.revision_id(
            repository_id, snapshot.fingerprint
        )
        with self._lock:
            existing = self._indexes.get(session.id)
            if existing is not None and existing.revision_id == revision_id:
                self._indexes.move_to_end(session.id)
                return existing
        created = RepositoryRetrievalIndex(session, snapshot=snapshot)
        with self._lock:
            existing = self._indexes.get(session.id)
            if existing is not None and existing.revision_id == revision_id:
                self._indexes.move_to_end(session.id)
                return existing
            self._indexes[session.id] = created
            while len(self._indexes) > self.max_indexes:
                self._indexes.popitem(last=False)
            return created

    def rebuild(self, session: AnalysisSession) -> RepositoryRetrievalIndex:
        from backend.app.graph.analyzer import RepositoryAnalyzer
        from backend.app.graph.store import analysis_sessions

        report = RepositoryAnalyzer().analyze(session.root)
        refreshed = analysis_sessions.refresh(session.id, session.root, report)
        snapshot = repository_snapshot(
            refreshed.root, settings.max_repository_files
        )
        repository_id = PersistentCodeIndex.repository_id(refreshed.root)
        revision_id = PersistentCodeIndex.revision_id(
            repository_id, snapshot.fingerprint
        )
        PersistentCodeIndex(settings.state_path).delete_revision(revision_id)
        with self._lock:
            self._indexes.pop(refreshed.id, None)
        return self.get(refreshed)


repository_indexes = RepositoryIndexStore()
