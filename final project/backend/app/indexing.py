from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


CODE_EXTENSIONS = {
    ".cjs", ".cts", ".java", ".js", ".jsx", ".mjs", ".mts",
    ".py", ".ts", ".tsx", ".html", ".htm", ".css",
}
CONTEXT_EXTENSIONS = {
    ".gradle", ".json", ".kts", ".md", ".mdx", ".properties",
    ".toml", ".txt", ".xml", ".yaml", ".yml",
}
CONTEXT_NAMES = {
    ".env.example", "dockerfile", "gradlew", "justfile", "makefile", "mvnw",
}
SKIPPED_DIRECTORIES = {
    ".agents", ".codex", ".git", ".hg", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".venv", ".waypoint-clones", ".waypoint-data",
    "__pycache__", "build", "dist", "node_modules",
    "site-packages", "venv",
}


@dataclass(frozen=True, slots=True)
class IndexedFileState:
    path: str
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    fingerprint: str
    files: tuple[IndexedFileState, ...]

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(item.path for item in self.files)


def repository_snapshot(root: Path, max_files: int = 5_000) -> RepositorySnapshot:
    """Return a deterministic content snapshot of files Waypoint can retrieve."""
    resolved_root = root.resolve()
    states: list[IndexedFileState] = []
    for current_root, directories, filenames in os.walk(resolved_root, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if name not in SKIPPED_DIRECTORIES
            and not (Path(current_root) / name).is_symlink()
        )
        for filename in sorted(filenames):
            candidate = Path(current_root) / filename
            if candidate.is_symlink():
                continue
            if (
                candidate.suffix.lower() not in CODE_EXTENSIONS | CONTEXT_EXTENSIONS
                and candidate.name.lower() not in CONTEXT_NAMES
            ):
                continue
            try:
                relative = candidate.resolve().relative_to(resolved_root).as_posix()
                content = candidate.read_bytes()
            except (OSError, ValueError):
                continue
            states.append(IndexedFileState(
                path=relative,
                content_sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            ))
            if len(states) >= max_files:
                break
        if len(states) >= max_files:
            break
    states.sort(key=lambda item: item.path)
    digest = hashlib.sha256()
    for item in states:
        digest.update(item.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.content_sha256.encode("ascii"))
        digest.update(b"\0")
    return RepositorySnapshot(digest.hexdigest(), tuple(states))
