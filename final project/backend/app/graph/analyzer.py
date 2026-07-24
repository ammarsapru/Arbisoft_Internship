from __future__ import annotations

import ast
import hashlib
import logging
import os
import time
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.graph.models import (
    AnalysisDiagnostic,
    AnalysisReport,
    AnalysisStats,
    EdgeKind,
    Evidence,
    EvidenceStatus,
    GraphEdge,
    GraphNode,
    NodeKind,
    SourceSpan,
    UnresolvedReference,
)
from backend.app.graph.polyglot import PolyglotGraphBuilder, SUPPORTED_EXTENSIONS
from backend.app.observability import log_event, traced

logger = logging.getLogger(__name__)

_SKIPPED_DIRECTORIES = {
    ".agents",
    ".codex",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
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


def _stable_id(*parts: object) -> str:
    material = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _span(relative_path: str, node: ast.AST) -> SourceSpan:
    start_line = max(1, getattr(node, "lineno", 1))
    start_column = max(0, getattr(node, "col_offset", 0))
    end_line = max(start_line, getattr(node, "end_lineno", start_line))
    end_column = max(0, getattr(node, "end_col_offset", start_column))
    return SourceSpan(
        path=relative_path,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _module_name(relative_path: Path) -> str:
    without_suffix = relative_path.with_suffix("")
    parts = list(without_suffix.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else "__root__"


def _source_roots(repository_root: Path) -> tuple[Path, ...]:
    """Return import roots in priority order for common Python layouts."""
    candidates: list[Path] = []
    src = repository_root / "src"
    if src.is_dir():
        candidates.append(src.resolve())
    candidates.append(repository_root.resolve())
    return tuple(candidates)


def _module_relative_path(
    repository_root: Path,
    source_path: Path,
    import_roots: tuple[Path, ...],
) -> Path:
    resolved = source_path.resolve()
    for import_root in import_roots:
        try:
            return resolved.relative_to(import_root)
        except ValueError:
            continue
    return resolved.relative_to(repository_root.resolve())


def _syntax(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


@dataclass(slots=True)
class ParsedModule:
    path: Path
    relative_path: str
    module_name: str
    tree: ast.Module | None
    module_node_id: str
    imported_modules: dict[str, str] = field(default_factory=dict)
    imported_symbols: dict[str, tuple[str, str]] = field(default_factory=dict)


class GraphAccumulator:
    def __init__(self, max_unresolved_call_details: int) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.unresolved: list[UnresolvedReference] = []
        self.unresolved_total = 0
        self.stored_unresolved_calls = 0
        self.max_unresolved_call_details = max_unresolved_call_details
        self.diagnostics: list[AnalysisDiagnostic] = []

    @traced("graph.add_node")
    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node
        log_event(
            logger,
            logging.DEBUG,
            "graph.node_added",
            "Graph node added",
            node_id=node.id,
            kind=node.kind,
            qualified_name=node.qualified_name,
            span=node.span,
        )

    @traced("graph.add_edge")
    def add_edge(self, edge: GraphEdge) -> None:
        self.edges[edge.id] = edge
        log_event(
            logger,
            logging.DEBUG,
            "graph.edge_added",
            "Graph edge added",
            edge_id=edge.id,
            kind=edge.kind,
            source=edge.source,
            target=edge.target,
            evidence_status=edge.evidence.status,
            resolution=edge.evidence.resolution,
        )

    @traced("graph.add_unresolved")
    def add_unresolved(self, reference: UnresolvedReference) -> None:
        self.unresolved_total += 1
        should_store = reference.reference_kind != "call" or (
            self.stored_unresolved_calls < self.max_unresolved_call_details
        )
        if should_store:
            self.unresolved.append(reference)
            if reference.reference_kind == "call":
                self.stored_unresolved_calls += 1
        log_event(
            logger,
            logging.DEBUG,
            "graph.reference_unresolved",
            "Reference could not be resolved without guessing",
            source=reference.source,
            reference=reference.reference,
            reference_kind=reference.reference_kind,
            span=reference.evidence.span,
            resolution=reference.evidence.resolution,
        )


class DefinitionVisitor(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        graph: GraphAccumulator,
        repository_node_id: str,
    ) -> None:
        self.module = module
        self.graph = graph
        self.parents: list[GraphNode] = [
            graph.nodes[module.module_node_id]
        ]
        self.qualifier_parts: list[str] = []
        self.repository_node_id = repository_node_id

    def _add_definition(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        kind: NodeKind,
        signature: str | None,
    ) -> GraphNode:
        qualified_name = ".".join(
            [self.module.module_name, *self.qualifier_parts, node.name]
        )
        span = _span(self.module.relative_path, node)
        graph_node = GraphNode(
            id=_stable_id(kind, qualified_name, span.path, span.start_line),
            kind=kind,
            name=node.name,
            qualified_name=qualified_name,
            module=self.module.module_name,
            span=span,
            signature=signature,
            metadata={"language": "python"},
        )
        self.graph.add_node(graph_node)
        parent = self.parents[-1]
        evidence = Evidence(
            status=EvidenceStatus.VERIFIED,
            span=span,
            syntax=f"{kind.value} {node.name}",
            resolution="AST lexical containment",
            confidence=1.0,
        )
        self.graph.add_edge(
            GraphEdge(
                id=_stable_id(EdgeKind.CONTAINS, parent.id, graph_node.id),
                source=parent.id,
                target=graph_node.id,
                kind=EdgeKind.CONTAINS,
                evidence=evidence,
            )
        )
        return graph_node

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        graph_node = self._add_definition(node, NodeKind.CLASS, None)
        self.parents.append(graph_node)
        self.qualifier_parts.append(node.name)
        self.generic_visit(node)
        self.qualifier_parts.pop()
        self.parents.pop()

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        parent_is_class = self.parents[-1].kind == NodeKind.CLASS
        kind = NodeKind.METHOD if parent_is_class else NodeKind.FUNCTION
        try:
            signature = ast.unparse(node.args)
        except Exception:
            signature = None
        graph_node = self._add_definition(node, kind, signature)
        self.parents.append(graph_node)
        self.qualifier_parts.append(node.name)
        self.generic_visit(node)
        self.qualifier_parts.pop()
        self.parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)


class RelationshipVisitor(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        graph: GraphAccumulator,
        modules: dict[str, ParsedModule],
        symbols: dict[tuple[str, str], list[GraphNode]],
    ) -> None:
        self.module = module
        self.graph = graph
        self.modules = modules
        self.symbols = symbols
        self.scope_parts: list[str] = []
        self.source_stack: list[str] = [module.module_node_id]
        self.receiver_bindings: list[dict[str, GraphNode]] = [{}]

    def _current_package(self) -> list[str]:
        module_parts = self.module.module_name.split(".")
        is_package = self.module.path.name == "__init__.py"
        return module_parts if is_package else module_parts[:-1]

    def _from_base(self, node: ast.ImportFrom) -> str:
        package = self._current_package()
        if node.level:
            climb = max(0, node.level - 1)
            package = package[: max(0, len(package) - climb)]
        elif node.module:
            package = []
        module_parts = node.module.split(".") if node.module else []
        return ".".join([*package, *module_parts])

    def _import_edge(
        self, node: ast.AST, target_module: str, resolution: str
    ) -> None:
        target = self.modules[target_module]
        span = _span(self.module.relative_path, node)
        self.graph.add_edge(
            GraphEdge(
                id=_stable_id(
                    EdgeKind.IMPORTS,
                    self.module.module_node_id,
                    target.module_node_id,
                    span.start_line,
                    _syntax(node),
                ),
                source=self.module.module_node_id,
                target=target.module_node_id,
                kind=EdgeKind.IMPORTS,
                evidence=Evidence(
                    status=EvidenceStatus.VERIFIED,
                    span=span,
                    syntax=_syntax(node),
                    resolution=resolution,
                    confidence=1.0,
                ),
            )
        )

    def visit_Import(self, node: ast.Import) -> Any:
        internal_roots = {name.split(".", 1)[0] for name in self.modules}
        for alias in node.names:
            if alias.name in self.modules:
                local_name = alias.asname or alias.name.split(".")[0]
                self.module.imported_modules[local_name] = alias.name
                self._import_edge(node, alias.name, "Exact internal module import")
            else:
                self._record_unresolved(
                    node,
                    alias.name,
                    "import",
                    "Import does not match an indexed internal module",
                    metadata={
                        "external": alias.name.split(".", 1)[0] not in internal_roots,
                        "package": alias.name.split(".", 1)[0],
                    },
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        base = self._from_base(node)
        internal_roots = {name.split(".", 1)[0] for name in self.modules}
        for alias in node.names:
            candidate_module = ".".join(filter(None, [base, alias.name]))
            local_name = alias.asname or alias.name
            if candidate_module in self.modules:
                self.module.imported_modules[local_name] = candidate_module
                self._import_edge(
                    node,
                    candidate_module,
                    "Resolved imported name as internal submodule",
                )
            elif base in self.modules:
                self._import_edge(
                    node,
                    base,
                    "Resolved from-import base as internal module",
                )
                self.module.imported_symbols[local_name] = (base, alias.name)
            else:
                self._record_unresolved(
                    node,
                    _syntax(node),
                    "import",
                    "From-import base and candidate submodule are not internal",
                    metadata={
                        "external": bool(base)
                        and node.level == 0
                        and base.split(".", 1)[0] not in internal_roots,
                        "package": base.split(".", 1)[0] if base else alias.name,
                    },
                )

    def _definition_node(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
    ) -> GraphNode | None:
        qualified = ".".join(
            [self.module.module_name, *self.scope_parts, node.name]
        )
        candidates = self.symbols.get((self.module.module_name, qualified), [])
        if not candidates:
            return None
        return next(
            (
                candidate
                for candidate in candidates
                if candidate.span
                and candidate.span.start_line == getattr(node, "lineno", -1)
            ),
            candidates[0],
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        graph_node = self._definition_node(node)
        self.scope_parts.append(node.name)
        if graph_node:
            self.source_stack.append(graph_node.id)
        self.generic_visit(node)
        if graph_node:
            self.source_stack.pop()
        self.scope_parts.pop()

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        graph_node = self._definition_node(node)
        self.scope_parts.append(node.name)
        if graph_node:
            self.source_stack.append(graph_node.id)
        self.receiver_bindings.append({})
        for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            if isinstance(argument.annotation, ast.Name):
                target, _ = self._resolve_named_symbol(argument.annotation.id)
                if target is not None and target.kind == NodeKind.CLASS:
                    self.receiver_bindings[-1][argument.arg] = target
        self.generic_visit(node)
        self.receiver_bindings.pop()
        if graph_node:
            self.source_stack.pop()
        self.scope_parts.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)

    def _resolve_named_symbol(self, name: str) -> tuple[GraphNode | None, str]:
        imported = self.module.imported_symbols.get(name)
        if imported:
            candidates = self.symbols.get(imported, [])
            if len(candidates) == 1:
                return candidates[0], "Resolved imported symbol alias"
        candidates = self.symbols.get((self.module.module_name, name), [])
        if len(candidates) == 1:
            return candidates[0], "Resolved unique same-module symbol"
        return None, "Bare call target is not uniquely resolvable"

    def _unique_imported_member(self, name: str) -> GraphNode | None:
        """Conservatively recover an unknown receiver from internal imports.

        This remains an inference: it is accepted only when exactly one function or
        method with this name exists across the source module's internal imports.
        """
        module_names = set(self.module.imported_modules.values()) | {
            module_name
            for module_name, _symbol_name in self.module.imported_symbols.values()
        }
        candidates = {
            candidate.id: candidate
            for module_name in module_names
            for candidate in self.symbols.get((module_name, name), [])
            if candidate.kind in {NodeKind.FUNCTION, NodeKind.METHOD}
        }
        return next(iter(candidates.values())) if len(candidates) == 1 else None

    def _resolve_call(
        self, node: ast.Call
    ) -> tuple[GraphNode | None, str, float]:
        function = node.func
        if isinstance(function, ast.Name):
            target, resolution = self._resolve_named_symbol(function.id)
            return target, resolution, 0.8
        if isinstance(function, ast.Attribute) and isinstance(
            function.value, ast.Name
        ):
            base = function.value.id
            if base in self.module.imported_modules:
                target_module = self.module.imported_modules[base]
                candidates = self.symbols.get(
                    (target_module, function.attr), []
                )
                if len(candidates) == 1:
                    return candidates[0], "Resolved attribute on imported module", 0.8
            if base in {"self", "cls"}:
                class_parts = self.scope_parts[:-1]
                if class_parts:
                    qualified = ".".join(
                        [self.module.module_name, *class_parts, function.attr]
                    )
                    candidates = self.symbols.get(
                        (self.module.module_name, qualified), []
                    )
                    if len(candidates) == 1:
                        return candidates[0], "Resolved method on lexical class", 0.8
            bound_type = self.receiver_bindings[-1].get(base)
            if bound_type is not None:
                qualified = f"{bound_type.qualified_name}.{function.attr}"
                candidates = self.symbols.get(
                    (bound_type.module or self.module.module_name, qualified), []
                )
                if len(candidates) == 1:
                    return (
                        candidates[0],
                        "Resolved method through locally constructed or annotated receiver",
                        0.8,
                    )
            recovered = self._unique_imported_member(function.attr)
            if recovered is not None:
                return (
                    recovered,
                    "Conservatively inferred unique matching member across internal imports",
                    0.55,
                )
            return None, "Attribute receiver type is not statically established", 0.0
        if isinstance(function, ast.Attribute):
            recovered = self._unique_imported_member(function.attr)
            if recovered is not None:
                return (
                    recovered,
                    "Conservatively inferred dynamic receiver from unique internal imported member",
                    0.5,
                )
        return None, "Dynamic call expression is not statically resolvable", 0.0

    def visit_Assign(self, node: ast.Assign) -> Any:
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            constructed, _ = self._resolve_named_symbol(node.value.func.id)
            if constructed is not None and constructed.kind == NodeKind.CLASS:
                for assignment_target in node.targets:
                    if isinstance(assignment_target, ast.Name):
                        self.receiver_bindings[-1][assignment_target.id] = constructed
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        if isinstance(node.target, ast.Name) and isinstance(node.annotation, ast.Name):
            declared, _ = self._resolve_named_symbol(node.annotation.id)
            if declared is not None and declared.kind == NodeKind.CLASS:
                self.receiver_bindings[-1][node.target.id] = declared
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        target, resolution, confidence = self._resolve_call(node)
        source = self.source_stack[-1]
        span = _span(self.module.relative_path, node)
        if target:
            relationship = (
                EdgeKind.INSTANTIATES
                if target.kind == NodeKind.CLASS
                else EdgeKind.MAY_CALL
            )
            self.graph.add_edge(
                GraphEdge(
                    id=_stable_id(
                        relationship,
                        source,
                        target.id,
                        span.start_line,
                        span.start_column,
                    ),
                    source=source,
                    target=target.id,
                    kind=relationship,
                    evidence=Evidence(
                        status=EvidenceStatus.INFERRED,
                        span=span,
                        syntax=_syntax(node),
                        resolution=(
                            f"{resolution}; resolved class construction"
                            if relationship == EdgeKind.INSTANTIATES
                            else resolution
                        ),
                        confidence=confidence,
                    ),
                    metadata={
                        "call_site_kind": (
                            "instantiation"
                            if relationship == EdgeKind.INSTANTIATES
                            else "call"
                        )
                    },
                )
            )
        else:
            self._record_unresolved(
                node,
                _syntax(node.func),
                "call",
                resolution,
                source=source,
            )
        self.generic_visit(node)

    def _record_unresolved(
        self,
        node: ast.AST,
        reference: str,
        reference_kind: str,
        resolution: str,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.graph.add_unresolved(
            UnresolvedReference(
                source=source or self.module.module_node_id,
                reference=reference,
                reference_kind=reference_kind,
                evidence=Evidence(
                    status=EvidenceStatus.UNRESOLVED,
                    span=_span(self.module.relative_path, node),
                    syntax=_syntax(node),
                    resolution=resolution,
                    confidence=0.0,
                ),
                metadata=metadata or {},
            )
        )


class RepositoryAnalyzer:
    def __init__(
        self,
        *,
        max_files: int | None = None,
        max_file_bytes: int | None = None,
        max_unresolved_call_details: int | None = None,
    ) -> None:
        self.max_files = max_files or settings.max_repository_files
        self.max_file_bytes = max_file_bytes or settings.max_python_file_bytes
        self.max_unresolved_call_details = (
            settings.max_unresolved_call_details
            if max_unresolved_call_details is None
            else max_unresolved_call_details
        )

    @traced("parser.discover_files")
    def discover_source_files(self, root: Path) -> list[Path]:
        discovered: list[Path] = []
        resolved_root = root.resolve()
        clone_root = settings.clone_root.resolve()
        supported = {".py", *SUPPORTED_EXTENSIONS}
        for current_root, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current_root)
            retained_directories: list[str] = []
            for directory in sorted(directories):
                candidate_directory = current_path / directory
                if directory in _SKIPPED_DIRECTORIES or candidate_directory.is_symlink():
                    continue
                try:
                    resolved_directory = candidate_directory.resolve()
                except OSError:
                    continue
                if (
                    resolved_root != clone_root
                    and clone_root.is_relative_to(resolved_root)
                    and (
                        resolved_directory == clone_root
                        or resolved_directory.is_relative_to(clone_root)
                    )
                ):
                    continue
                retained_directories.append(directory)
            directories[:] = retained_directories
            for filename in sorted(filenames):
                path = current_path / filename
                if path.suffix.lower() not in supported:
                    continue
                relative = path.relative_to(root)
                try:
                    resolved_path = path.resolve()
                    resolved_path.relative_to(resolved_root)
                except (OSError, ValueError):
                    log_event(
                        logger,
                        logging.WARNING,
                        "security.source_path_rejected",
                        "Source path skipped because it resolves outside the repository",
                        path=relative,
                    )
                    continue
                if path.is_symlink() or not resolved_path.is_file():
                    log_event(
                        logger,
                        logging.WARNING,
                        "security.source_path_rejected",
                        "Source path skipped because symbolic and non-file entries are not analyzed",
                        path=relative,
                    )
                    continue
                discovered.append(path)
                if len(discovered) > self.max_files:
                    raise ValueError(
                        f"Repository exceeds the {self.max_files} supported source file limit"
                    )
        discovered.sort(key=lambda item: item.as_posix())
        log_event(
            logger,
            logging.INFO,
            "parser.discovery_completed",
            "Multi-language repository discovery completed",
            root=root,
            file_count=len(discovered),
            extensions=sorted({path.suffix.lower() for path in discovered}),
        )
        return discovered

    def discover_python_files(self, root: Path) -> list[Path]:
        """Compatibility helper retained for callers that explicitly want Python."""
        return [
            path
            for path in self.discover_source_files(root)
            if path.suffix.lower() == ".py"
        ]

    @traced("parser.parse_file")
    def _parse_file(
        self,
        root: Path,
        path: Path,
        graph: GraphAccumulator,
        import_roots: tuple[Path, ...],
    ) -> ParsedModule | None:
        relative = path.relative_to(root)
        relative_string = relative.as_posix()
        size = path.stat().st_size
        log_event(
            logger,
            logging.DEBUG,
            "parser.file_started",
            "Parsing Python file",
            path=relative_string,
            size_bytes=size,
        )
        if size > self.max_file_bytes:
            graph.diagnostics.append(
                AnalysisDiagnostic(
                    severity="warning",
                    code="file_too_large",
                    message=(
                        f"File is {size} bytes; limit is {self.max_file_bytes}"
                    ),
                    path=relative_string,
                )
            )
            log_event(
                logger,
                logging.WARNING,
                "parser.file_skipped",
                "Python file exceeds configured byte limit",
                path=relative_string,
                size_bytes=size,
                limit_bytes=self.max_file_bytes,
            )
            return None
        try:
            with tokenize.open(path) as source_file:
                source = source_file.read()
            tree = ast.parse(source, filename=relative_string)
        except (OSError, UnicodeError, SyntaxError) as exc:
            graph.diagnostics.append(
                AnalysisDiagnostic(
                    severity="error",
                    code="parse_failed",
                    message=f"{type(exc).__name__}: {exc}",
                    path=relative_string,
                    line=getattr(exc, "lineno", None),
                )
            )
            log_event(
                logger,
                logging.ERROR,
                "parser.file_failed",
                "Python file could not be parsed",
                path=relative_string,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                line=getattr(exc, "lineno", None),
            )
            return None
        module_relative = _module_relative_path(root, path, import_roots)
        module_name = _module_name(module_relative)
        module_span = SourceSpan(
            path=relative_string,
            start_line=1,
            start_column=0,
            end_line=max(1, len(source.splitlines())),
            end_column=0,
        )
        module_node = GraphNode(
            id=_stable_id(NodeKind.MODULE, module_name, relative_string),
            kind=NodeKind.MODULE,
            name=relative.stem,
            qualified_name=module_name,
            module=module_name,
            span=module_span,
            metadata={
                "language": "python",
                "size_bytes": size,
                "content_sha256": hashlib.sha256(
                    source.encode("utf-8")
                ).hexdigest(),
            },
        )
        graph.add_node(module_node)
        log_event(
            logger,
            logging.INFO,
            "parser.file_completed",
            "Python file parsed successfully",
            path=relative_string,
            module=module_name,
            ast_statement_count=len(tree.body),
        )
        return ParsedModule(
            path=path,
            relative_path=relative_string,
            module_name=module_name,
            tree=tree,
            module_node_id=module_node.id,
        )

    @traced("parser.analyze_repository")
    def analyze(self, repository_root: Path) -> AnalysisReport:
        started = time.perf_counter()
        root = repository_root.expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Repository path does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Repository path is not a directory: {root}")
        log_event(
            logger,
            logging.INFO,
            "parser.analysis_started",
            "Repository analysis started",
            repository_root=root,
            max_files=self.max_files,
            max_file_bytes=self.max_file_bytes,
        )
        graph = GraphAccumulator(self.max_unresolved_call_details)
        import_roots = _source_roots(root)
        log_event(
            logger,
            logging.INFO,
            "parser.source_roots_detected",
            "Language source roots selected for module-name resolution",
            repository_root=root,
            import_roots=import_roots,
        )
        repository_node = GraphNode(
            id=_stable_id(NodeKind.REPOSITORY, root.name, root),
            kind=NodeKind.REPOSITORY,
            name=root.name,
            qualified_name=root.name,
            metadata={"root": str(root)},
        )
        graph.add_node(repository_node)
        files = self.discover_source_files(root)
        python_files = [path for path in files if path.suffix.lower() == ".py"]
        modules: dict[str, ParsedModule] = {}
        skipped = 0
        for path in python_files:
            parsed = self._parse_file(root, path, graph, import_roots)
            if parsed is None:
                skipped += 1
                continue
            if parsed.module_name in modules:
                existing = modules[parsed.module_name]
                graph.diagnostics.append(
                    AnalysisDiagnostic(
                        severity="warning",
                        code="duplicate_module_name",
                        message=(
                            f"Module name {parsed.module_name!r} also maps to "
                            f"{existing.relative_path}; keeping the first file"
                        ),
                        path=parsed.relative_path,
                    )
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "parser.duplicate_module_name",
                    "Multiple files resolve to the same Python module name",
                    module=parsed.module_name,
                    existing_path=existing.relative_path,
                    duplicate_path=parsed.relative_path,
                )
                graph.nodes.pop(parsed.module_node_id, None)
                skipped += 1
                continue
            modules[parsed.module_name] = parsed
            module_node = graph.nodes[parsed.module_node_id]
            graph.add_edge(
                GraphEdge(
                    id=_stable_id(
                        EdgeKind.CONTAINS, repository_node.id, module_node.id
                    ),
                    source=repository_node.id,
                    target=module_node.id,
                    kind=EdgeKind.CONTAINS,
                    evidence=Evidence(
                        status=EvidenceStatus.VERIFIED,
                        span=module_node.span,
                        syntax=parsed.relative_path,
                        resolution="File discovered beneath repository root",
                        confidence=1.0,
                    ),
                )
            )
            if parsed.tree is not None:
                DefinitionVisitor(parsed, graph, repository_node.id).visit(
                    parsed.tree
                )
                parsed.tree = None

        polyglot = PolyglotGraphBuilder(root, graph, self.max_file_bytes)
        for path in files:
            if path.suffix.lower() == ".py":
                continue
            parsed = polyglot.parse_file(path)
            if parsed is None:
                skipped += 1
                continue
            polyglot.attach_module(parsed, repository_node)

        symbols: dict[tuple[str, str], list[GraphNode]] = {}
        for node in graph.nodes.values():
            if node.module and node.kind in {
                NodeKind.CLASS,
                NodeKind.FUNCTION,
                NodeKind.METHOD,
            }:
                symbols.setdefault((node.module, node.name), []).append(node)
                symbols.setdefault(
                    (node.module, node.qualified_name), []
                ).append(node)

        for module in modules.values():
            try:
                with tokenize.open(module.path) as source_file:
                    relationship_source = source_file.read()
                relationship_tree = ast.parse(
                    relationship_source, filename=module.relative_path
                )
            except (OSError, UnicodeError, SyntaxError) as exc:
                graph.diagnostics.append(
                    AnalysisDiagnostic(
                        severity="error",
                        code="relationship_reparse_failed",
                        message=f"{type(exc).__name__}: {exc}",
                        path=module.relative_path,
                        line=getattr(exc, "lineno", None),
                    )
                )
                log_event(
                    logger,
                    logging.ERROR,
                    "parser.relationship_reparse_failed",
                    "Previously parsed file failed during relationship pass",
                    path=module.relative_path,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                )
                continue
            RelationshipVisitor(module, graph, modules, symbols).visit(
                relationship_tree
            )
        polyglot.resolve_relationships()
        omitted_unresolved_calls = max(
            0,
            graph.unresolved_total - len(graph.unresolved),
        )
        if omitted_unresolved_calls:
            graph.diagnostics.append(
                AnalysisDiagnostic(
                    severity="info",
                    code="unresolved_call_details_truncated",
                    message=(
                        f"Omitted {omitted_unresolved_calls} unresolved call "
                        "details after reaching the configured storage limit; "
                        "the total remains available in analysis statistics"
                    ),
                )
            )
            log_event(
                logger,
                logging.WARNING,
                "graph.unresolved_details_truncated",
                "Unresolved call details were bounded for repository scale",
                total_unresolved=graph.unresolved_total,
                stored_details=len(graph.unresolved),
                omitted_calls=omitted_unresolved_calls,
                call_detail_limit=self.max_unresolved_call_details,
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        parse_failures = sum(
            diagnostic.code == "parse_failed" for diagnostic in graph.diagnostics
        )
        report = AnalysisReport(
            repository_root=str(root),
            repository_name=root.name,
            nodes=sorted(graph.nodes.values(), key=lambda node: node.id),
            edges=sorted(graph.edges.values(), key=lambda edge: edge.id),
            unresolved_references=graph.unresolved,
            diagnostics=graph.diagnostics,
            stats=AnalysisStats(
                files_discovered=len(files),
                files_parsed=len(modules) + len(polyglot.modules),
                files_skipped=skipped,
                parse_failures=parse_failures,
                node_count=len(graph.nodes),
                edge_count=len(graph.edges),
                unresolved_count=graph.unresolved_total,
                duration_ms=duration_ms,
            ),
        )
        log_event(
            logger,
            logging.INFO,
            "parser.analysis_completed",
            "Repository analysis completed",
            repository_root=root,
            stats=report.stats,
            diagnostic_count=len(report.diagnostics),
        )
        return report
