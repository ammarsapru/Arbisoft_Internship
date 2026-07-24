from __future__ import annotations

import hashlib
import logging
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from tree_sitter import Language, Node, Parser
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_html
import tree_sitter_css

from backend.app.graph.models import (
    AnalysisDiagnostic,
    EdgeKind,
    Evidence,
    EvidenceStatus,
    GraphEdge,
    GraphNode,
    NodeKind,
    SourceSpan,
    UnresolvedReference,
)
from backend.app.observability import log_event, traced

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".java",
    ".html",
    ".htm",
    ".css",
}

_JS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
_CLASS_TYPES = {
    "class",
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
_JS_FUNCTION_TYPES = {"function_declaration", "generator_function_declaration"}
_JS_METHOD_TYPES = {"method_definition", "method_signature", "abstract_method_signature"}
_JAVA_METHOD_TYPES = {"method_declaration", "constructor_declaration"}


def _stable_id(*parts: object) -> str:
    material = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _text(source: bytes, node: Node | None, limit: int = 2_000) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")[:limit]


def _span(path: str, node: Node) -> SourceSpan:
    start_row, start_column = node.start_point
    end_row, end_column = node.end_point
    return SourceSpan(
        path=path,
        start_line=start_row + 1,
        start_column=start_column,
        end_line=max(start_row + 1, end_row + 1),
        end_column=end_column,
    )


def _node_key(node: Node) -> tuple[int, int, str]:
    return (node.start_byte, node.end_byte, node.type)


def _descendants(node: Node, types: set[str]) -> Iterable[Node]:
    if node.type in types:
        yield node
    for child in node.named_children:
        yield from _descendants(child, types)


def _strip_source_extension(value: str) -> str:
    lowered = value.lower()
    for suffix in (".d.ts", ".tsx", ".mts", ".cts", ".jsx", ".mjs", ".cjs", ".html", ".htm", ".css", ".ts", ".js"):
        if lowered.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _path_key(relative_path: str) -> str:
    value = _strip_source_extension(relative_path.replace("\\", "/"))
    if value.endswith("/index"):
        value = value[:-6]
    return value.strip("/") or "__root__"


def _qualified_path(path_key: str) -> str:
    return path_key.replace("/", ".")


def _language_name(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".java":
        return "java"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".css":
        return "css"
    if suffix in {".ts", ".mts", ".cts"}:
        return "typescript"
    if suffix == ".tsx":
        return "tsx"
    if suffix == ".jsx":
        return "jsx"
    return "javascript"


def _language(language: str) -> Language:
    if language == "java":
        return Language(tree_sitter_java.language())
    if language == "html":
        return Language(tree_sitter_html.language())
    if language == "css":
        return Language(tree_sitter_css.language())
    if language == "typescript":
        return Language(tree_sitter_typescript.language_typescript())
    if language in {"tsx", "jsx"}:
        # The TSX grammar accepts JSX and TypeScript syntax, making it suitable for both.
        return Language(tree_sitter_typescript.language_tsx())
    return Language(tree_sitter_javascript.language())


@dataclass(slots=True)
class PolyglotModule:
    path: Path
    relative_path: str
    path_key: str
    module_name: str
    language: str
    source: bytes
    root: Node
    module_node_id: str
    definition_nodes: dict[tuple[int, int, str], GraphNode] = field(default_factory=dict)
    imported_modules: dict[str, str] = field(default_factory=dict)
    imported_symbols: dict[str, tuple[str, str]] = field(default_factory=dict)
    receiver_types: dict[tuple[str, str], str] = field(default_factory=dict)


class PolyglotGraphBuilder:
    """Tree-sitter extractors that emit Waypoint's language-neutral graph schema."""

    def __init__(self, root: Path, graph: Any, max_file_bytes: int) -> None:
        self.root = root
        self.graph = graph
        self.max_file_bytes = max_file_bytes
        self.modules: list[PolyglotModule] = []
        self.modules_by_path: dict[str, PolyglotModule] = {}
        self.modules_by_name: dict[str, PolyglotModule] = {}
        self.symbols: dict[tuple[str, str], list[GraphNode]] = {}

    @traced("parser.polyglot.parse_file")
    def parse_file(self, path: Path) -> PolyglotModule | None:
        relative = path.relative_to(self.root).as_posix()
        size = path.stat().st_size
        language = _language_name(path)
        log_event(
            logger,
            logging.DEBUG,
            "parser.file_started",
            "Parsing Tree-sitter source file",
            path=relative,
            language=language,
            size_bytes=size,
        )
        if size > self.max_file_bytes:
            self.graph.diagnostics.append(
                AnalysisDiagnostic(
                    severity="warning",
                    code="file_too_large",
                    message=f"File is {size} bytes; limit is {self.max_file_bytes}",
                    path=relative,
                )
            )
            return None
        try:
            source = path.read_bytes()
            source.decode("utf-8")
            tree = Parser(_language(language)).parse(source)
        except (OSError, UnicodeError, ValueError) as exc:
            self.graph.diagnostics.append(
                AnalysisDiagnostic(
                    severity="error",
                    code="parse_failed",
                    message=f"{type(exc).__name__}: {exc}",
                    path=relative,
                )
            )
            log_event(
                logger,
                logging.ERROR,
                "parser.file_failed",
                "Tree-sitter source file could not be parsed",
                path=relative,
                language=language,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            return None

        path_key = _path_key(relative)
        module_name = self._java_module_name(source, tree.root_node, path) if language == "java" else _qualified_path(path_key)
        line_count = max(1, len(source.decode("utf-8").splitlines()))
        module_span = SourceSpan(
            path=relative,
            start_line=1,
            start_column=0,
            end_line=line_count,
            end_column=0,
        )
        module_node = GraphNode(
            id=_stable_id(NodeKind.MODULE, language, module_name, relative),
            kind=NodeKind.MODULE,
            name=path.stem,
            qualified_name=module_name,
            module=module_name,
            span=module_span,
            metadata={
                "language": language,
                "size_bytes": size,
                "content_sha256": hashlib.sha256(source).hexdigest(),
                "tree_sitter_has_error": tree.root_node.has_error,
            },
        )
        self.graph.add_node(module_node)
        module = PolyglotModule(
            path=path,
            relative_path=relative,
            path_key=path_key,
            module_name=module_name,
            language=language,
            source=source,
            root=tree.root_node,
            module_node_id=module_node.id,
        )
        self.modules.append(module)
        self.modules_by_path[path_key] = module
        self.modules_by_name[module_name] = module
        if tree.root_node.has_error:
            self.graph.diagnostics.append(
                AnalysisDiagnostic(
                    severity="warning",
                    code="parse_recovered",
                    message=(
                        f"Tree-sitter recovered a partial {language} syntax tree; "
                        "extracted nodes remain source-backed but may be incomplete"
                    ),
                    path=relative,
                )
            )
        log_event(
            logger,
            logging.INFO,
            "parser.file_completed",
            "Tree-sitter source file parsed successfully",
            path=relative,
            language=language,
            module=module_name,
            recovered_from_errors=tree.root_node.has_error,
        )
        return module

    @staticmethod
    def _java_module_name(source: bytes, root: Node, path: Path) -> str:
        package = next(
            (child for child in root.named_children if child.type == "package_declaration"),
            None,
        )
        if package is None:
            return path.stem
        package_text = _text(source, package).removeprefix("package").rstrip("; ").strip()
        return f"{package_text}.{path.stem}" if package_text else path.stem

    def attach_module(self, module: PolyglotModule, repository_node: GraphNode) -> None:
        module_node = self.graph.nodes[module.module_node_id]
        self.graph.add_edge(
            GraphEdge(
                id=_stable_id(EdgeKind.CONTAINS, repository_node.id, module_node.id),
                source=repository_node.id,
                target=module_node.id,
                kind=EdgeKind.CONTAINS,
                evidence=Evidence(
                    status=EvidenceStatus.VERIFIED,
                    span=module_node.span,
                    syntax=module.relative_path,
                    resolution=f"{module.language} file discovered beneath repository root",
                    confidence=1.0,
                ),
            )
        )
        if module.language in {"html", "css"}:
            self._extract_declarative_definitions(module)
        else:
            self._extract_definitions(module)

    @staticmethod
    def _offset_span(module: PolyglotModule, start: int, end: int) -> SourceSpan:
        before = module.source[:start].decode("utf-8", errors="replace")
        matched = module.source[start:end].decode("utf-8", errors="replace")
        start_line = before.count("\n") + 1
        start_column = len(before.rsplit("\n", 1)[-1])
        end_line = start_line + matched.count("\n")
        end_column = len(matched.rsplit("\n", 1)[-1]) if "\n" in matched else start_column + len(matched)
        return SourceSpan(path=module.relative_path, start_line=start_line, start_column=start_column, end_line=end_line, end_column=end_column)

    def _add_declarative_symbol(self, module: PolyglotModule, name: str, start: int, end: int, declaration_type: str) -> None:
        module_node = self.graph.nodes[module.module_node_id]
        span = self._offset_span(module, start, end)
        qualified = f"{module.module_name}.{name}"
        node = GraphNode(
            id=_stable_id(NodeKind.CLASS, module.language, qualified, span.start_line),
            kind=NodeKind.CLASS,
            name=name,
            qualified_name=qualified,
            module=module.module_name,
            span=span,
            metadata={"language": module.language, "declaration_type": declaration_type},
        )
        if node.id in self.graph.nodes:
            return
        self.graph.add_node(node)
        self.graph.add_edge(GraphEdge(
            id=_stable_id(EdgeKind.CONTAINS, module_node.id, node.id),
            source=module_node.id,
            target=node.id,
            kind=EdgeKind.CONTAINS,
            evidence=Evidence(status=EvidenceStatus.VERIFIED, span=span, syntax=name, resolution="Tree-sitter-validated declarative structure", confidence=1.0),
        ))

    def _extract_declarative_definitions(self, module: PolyglotModule) -> None:
        text = module.source.decode("utf-8", errors="replace")
        if module.language == "html":
            for match in re.finditer(r"<([A-Za-z][\w:-]*)([^<>]*)>", text):
                tag, attributes = match.group(1).lower(), match.group(2)
                identifier = re.search(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", attributes, re.I)
                if identifier:
                    self._add_declarative_symbol(module, f"#{identifier.group(1)}", match.start(), match.end(), f"html_{tag}_id")
                classes = re.search(r"\bclass\s*=\s*['\"]([^'\"]+)['\"]", attributes, re.I)
                if classes:
                    for class_name in classes.group(1).split():
                        self._add_declarative_symbol(module, f".{class_name}", match.start(), match.end(), f"html_{tag}_class")
        else:
            for match in re.finditer(r"(?m)([^@{}][^{}]*)\{", text):
                for selector in match.group(1).split(","):
                    normalized = " ".join(selector.split()).strip()
                    if normalized and len(normalized) <= 160:
                        self._add_declarative_symbol(module, normalized, match.start(), match.end(), "css_selector")

    def _resolve_asset_module(self, module: PolyglotModule, reference: str) -> PolyglotModule | None:
        clean = reference.split("?", 1)[0].split("#", 1)[0]
        if not clean or clean.startswith(("http://", "https://", "//", "data:")):
            return None
        base = posixpath.dirname(module.relative_path)
        candidate = _path_key(posixpath.normpath(posixpath.join(base, clean)))
        return self.modules_by_path.get(candidate)

    def _extract_declarative_relationships(self, module: PolyglotModule) -> None:
        text = module.source.decode("utf-8", errors="replace")
        if module.language == "html":
            matches = re.finditer(r"\b(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", text, re.I)
        else:
            matches = re.finditer(r"@import\s+(?:url\()?\s*['\"]([^'\"]+)['\"]", text, re.I)
        for match in matches:
            reference = match.group(1)
            target = self._resolve_asset_module(module, reference)
            span = self._offset_span(module, match.start(), match.end())
            if target is not None:
                target_node = self.graph.nodes[target.module_node_id]
                self.graph.add_edge(GraphEdge(
                    id=_stable_id(EdgeKind.IMPORTS, module.module_node_id, target.module_node_id, span.start_line, reference),
                    source=module.module_node_id,
                    target=target.module_node_id,
                    kind=EdgeKind.IMPORTS,
                    evidence=Evidence(status=EvidenceStatus.VERIFIED, span=span, syntax=match.group(0), resolution="Resolved local HTML/CSS asset reference", confidence=1.0),
                ))
            elif reference.startswith(("http://", "https://", "//")):
                self.graph.add_unresolved(UnresolvedReference(
                    source=module.module_node_id,
                    reference=reference,
                    reference_kind="import",
                    evidence=Evidence(status=EvidenceStatus.UNRESOLVED, span=span, syntax=match.group(0), resolution="External web asset", confidence=0.0),
                    metadata={"external": True, "package": reference},
                ))

    def _definition(self, module: PolyglotModule, node: Node, parent: GraphNode) -> tuple[NodeKind, str, str | None] | None:
        name_node = node.child_by_field_name("name")
        if node.type in _CLASS_TYPES:
            name = _text(module.source, name_node)
            if not name and node.parent and node.parent.type == "export_statement":
                name = "default"
            if name:
                return NodeKind.CLASS, name, None
        if module.language == "java" and node.type in _JAVA_METHOD_TYPES and name_node is not None:
            parameters = node.child_by_field_name("parameters")
            return NodeKind.METHOD, _text(module.source, name_node), _text(module.source, parameters)
        if module.language != "java" and node.type in _JS_FUNCTION_TYPES:
            parameters = node.child_by_field_name("parameters")
            kind = NodeKind.METHOD if parent.kind == NodeKind.CLASS else NodeKind.FUNCTION
            name = _text(module.source, name_node)
            if not name and node.parent and node.parent.type == "export_statement":
                name = "default"
            if name:
                return kind, name, _text(module.source, parameters)
        if module.language != "java" and node.type in _JS_METHOD_TYPES and name_node is not None:
            parameters = node.child_by_field_name("parameters")
            return NodeKind.METHOD, _text(module.source, name_node), _text(module.source, parameters)
        if module.language != "java" and node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value is not None and value.type in {"arrow_function", "function_expression", "generator_function"}:
                variable = node.child_by_field_name("name")
                if variable is not None and variable.type in {"identifier", "property_identifier"}:
                    parameters = value.child_by_field_name("parameters")
                    kind = NodeKind.METHOD if parent.kind == NodeKind.CLASS else NodeKind.FUNCTION
                    return kind, _text(module.source, variable), _text(module.source, parameters)
        if module.language != "java" and node.type in {"public_field_definition", "field_definition"}:
            value = node.child_by_field_name("value")
            variable = node.child_by_field_name("name")
            if value is not None and variable is not None and value.type in {"arrow_function", "function_expression"}:
                parameters = value.child_by_field_name("parameters")
                return NodeKind.METHOD, _text(module.source, variable), _text(module.source, parameters)
        return None

    def _extract_definitions(self, module: PolyglotModule) -> None:
        module_node = self.graph.nodes[module.module_node_id]

        def walk(node: Node, parent: GraphNode, qualifiers: list[str]) -> None:
            definition = self._definition(module, node, parent)
            next_parent = parent
            next_qualifiers = qualifiers
            if definition is not None:
                kind, name, signature = definition
                source_span = _span(module.relative_path, node)
                qualified = ".".join([module.module_name, *qualifiers, name])
                graph_node = GraphNode(
                    id=_stable_id(kind, module.language, qualified, source_span.path, source_span.start_line),
                    kind=kind,
                    name=name,
                    qualified_name=qualified,
                    module=module.module_name,
                    span=source_span,
                    signature=signature or None,
                    metadata={"language": module.language, "declaration_type": node.type},
                )
                self.graph.add_node(graph_node)
                self.graph.add_edge(
                    GraphEdge(
                        id=_stable_id(EdgeKind.CONTAINS, parent.id, graph_node.id),
                        source=parent.id,
                        target=graph_node.id,
                        kind=EdgeKind.CONTAINS,
                        evidence=Evidence(
                            status=EvidenceStatus.VERIFIED,
                            span=source_span,
                            syntax=f"{node.type} {name}",
                            resolution="Tree-sitter lexical containment",
                            confidence=1.0,
                        ),
                    )
                )
                module.definition_nodes[_node_key(node)] = graph_node
                next_parent = graph_node
                next_qualifiers = [*qualifiers, name]
            for child in node.named_children:
                walk(child, next_parent, next_qualifiers)

        walk(module.root, module_node, [])

    def _index_symbols(self) -> None:
        self.symbols.clear()
        for module in self.modules:
            for node in module.definition_nodes.values():
                self.symbols.setdefault((module.module_name, node.name), []).append(node)
                self.symbols.setdefault((module.module_name, node.qualified_name), []).append(node)

    def _resolve_js_module(self, module: PolyglotModule, specifier: str) -> PolyglotModule | None:
        if not specifier.startswith("."):
            return None
        base = posixpath.dirname(_strip_source_extension(module.relative_path))
        candidate = _strip_source_extension(posixpath.normpath(posixpath.join(base, specifier)))
        return self.modules_by_path.get(candidate) or self.modules_by_path.get(candidate.rstrip("/") + "/index")

    def _add_import(self, module: PolyglotModule, target: PolyglotModule, node: Node, resolution: str) -> None:
        source_span = _span(module.relative_path, node)
        self.graph.add_edge(
            GraphEdge(
                id=_stable_id(EdgeKind.IMPORTS, module.module_node_id, target.module_node_id, source_span.start_line, _text(module.source, node)),
                source=module.module_node_id,
                target=target.module_node_id,
                kind=EdgeKind.IMPORTS,
                evidence=Evidence(
                    status=EvidenceStatus.VERIFIED,
                    span=source_span,
                    syntax=_text(module.source, node),
                    resolution=resolution,
                    confidence=1.0,
                ),
            )
        )

    @staticmethod
    def _javascript_package(specifier: str) -> str:
        if specifier.startswith("@"):
            return "/".join(specifier.split("/")[:2])
        if specifier.startswith("node:"):
            return specifier
        return specifier.split("/", 1)[0]

    @staticmethod
    def _java_package(reference: str) -> str:
        parts = reference.removesuffix(".*").split(".")
        package_parts: list[str] = []
        for part in parts:
            if part and part[0].isupper():
                break
            package_parts.append(part)
        return ".".join(package_parts) or reference

    def _unresolved(
        self,
        module: PolyglotModule,
        source_id: str,
        node: Node,
        reference: str,
        kind: str,
        resolution: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.graph.add_unresolved(
            UnresolvedReference(
                source=source_id,
                reference=reference,
                reference_kind=kind,
                evidence=Evidence(
                    status=EvidenceStatus.UNRESOLVED,
                    span=_span(module.relative_path, node),
                    syntax=_text(module.source, node),
                    resolution=resolution,
                    confidence=0.0,
                ),
                metadata=metadata or {},
            )
        )

    def _extract_js_import(self, module: PolyglotModule, node: Node) -> None:
        source_node = node.child_by_field_name("source")
        if source_node is None:
            return
        specifier = _text(module.source, source_node).strip("'\"")
        target = self._resolve_js_module(module, specifier)
        if target is None:
            external = not specifier.startswith(".")
            self._unresolved(
                module,
                module.module_node_id,
                node,
                specifier,
                "import",
                "External ECMAScript package import" if external else "Relative import cannot be mapped to an indexed module",
                metadata={
                    "external": external,
                    "package": self._javascript_package(specifier) if external else specifier,
                },
            )
            return
        self._add_import(module, target, node, "Resolved relative ECMAScript module import")
        clause = next((child for child in node.named_children if child.type == "import_clause"), None)
        if clause is None:
            return
        direct_identifiers = [child for child in clause.named_children if child.type == "identifier"]
        if direct_identifiers:
            local = _text(module.source, direct_identifiers[0])
            class_candidates = [item for item in target.definition_nodes.values() if item.kind == NodeKind.CLASS]
            if len(class_candidates) == 1:
                module.imported_symbols[local] = (target.module_name, class_candidates[0].name)
        for spec in _descendants(clause, {"import_specifier"}):
            original = spec.child_by_field_name("name")
            alias = spec.child_by_field_name("alias")
            if original is not None:
                module.imported_symbols[_text(module.source, alias or original)] = (target.module_name, _text(module.source, original))
        namespace = next(_descendants(clause, {"namespace_import"}), None)
        if namespace is not None:
            identifiers = [child for child in namespace.named_children if child.type == "identifier"]
            if identifiers:
                module.imported_modules[_text(module.source, identifiers[-1])] = target.module_name

    def _extract_js_require(self, module: PolyglotModule, node: Node) -> bool:
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None or _text(module.source, function) != "require" or arguments is None:
            return False
        string_node = next(_descendants(arguments, {"string"}), None)
        if string_node is None:
            return True
        specifier = _text(module.source, string_node).strip("'\"")
        target = self._resolve_js_module(module, specifier)
        if target is None:
            external = not specifier.startswith(".")
            self._unresolved(
                module,
                module.module_node_id,
                node,
                specifier,
                "import",
                "External CommonJS package require" if external else "Relative CommonJS require cannot be mapped to an indexed module",
                metadata={
                    "external": external,
                    "package": self._javascript_package(specifier) if external else specifier,
                },
            )
            return True
        self._add_import(module, target, node, "Resolved relative CommonJS require")
        declarator = node.parent if node.parent and node.parent.type == "variable_declarator" else None
        name_node = declarator.child_by_field_name("name") if declarator else None
        if name_node is None:
            return True
        if name_node.type == "identifier":
            module.imported_modules[_text(module.source, name_node)] = target.module_name
        elif name_node.type == "object_pattern":
            for child in name_node.named_children:
                if child.type in {"shorthand_property_identifier_pattern", "identifier"}:
                    name = _text(module.source, child)
                    module.imported_symbols[name] = (target.module_name, name)
                elif child.type == "pair_pattern":
                    key = child.child_by_field_name("key")
                    value = child.child_by_field_name("value")
                    if key is not None and value is not None:
                        module.imported_symbols[_text(module.source, value)] = (target.module_name, _text(module.source, key))
        return True

    def _extract_js_reexport(self, module: PolyglotModule, node: Node) -> None:
        source_node = node.child_by_field_name("source")
        if source_node is None:
            return
        specifier = _text(module.source, source_node).strip("'\"")
        target = self._resolve_js_module(module, specifier)
        if target is None:
            external = not specifier.startswith(".")
            self._unresolved(
                module,
                module.module_node_id,
                node,
                specifier,
                "import",
                "External ECMAScript package re-export" if external else "Relative re-export cannot be mapped to an indexed module",
                metadata={
                    "external": external,
                    "package": self._javascript_package(specifier) if external else specifier,
                },
            )
            return
        self._add_import(module, target, node, "Resolved ECMAScript re-export to indexed module")

    def _extract_java_import(self, module: PolyglotModule, node: Node) -> None:
        raw = _text(module.source, node).removeprefix("import").rstrip("; ").strip()
        raw = raw.removeprefix("static ").strip()
        wildcard = raw.endswith(".*")
        candidate = raw[:-2] if wildcard else raw
        if wildcard:
            targets = [
                item
                for name, item in self.modules_by_name.items()
                if name.startswith(candidate + ".")
                and name.count(".") == candidate.count(".") + 1
            ]
            if targets:
                for target_item in targets:
                    self._add_import(module, target_item, node, "Resolved Java wildcard import to indexed source type")
                    module.imported_modules[target_item.module_name.rsplit(".", 1)[-1]] = target_item.module_name
                return
        target = self.modules_by_name.get(candidate)
        imported_member: str | None = None
        if target is None and "." in candidate:
            base, member = candidate.rsplit(".", 1)
            target = self.modules_by_name.get(base)
            if target is not None:
                imported_member = member
        if target is None:
            internal_prefixes = {
                ".".join(name.split(".")[:2])
                for name in self.modules_by_name
                if "." in name
            }
            candidate_prefix = ".".join(candidate.split(".")[:2])
            external = candidate_prefix not in internal_prefixes
            self._unresolved(
                module,
                module.module_node_id,
                node,
                raw,
                "import",
                "External Java package import" if external else "Java import is in the repository namespace but does not match an indexed source type",
                metadata={
                    "external": external,
                    "package": self._java_package(raw),
                },
            )
            return
        self._add_import(module, target, node, "Resolved Java import to indexed source type")
        type_name = target.module_name.rsplit(".", 1)[-1]
        module.imported_modules[type_name] = target.module_name
        if imported_member:
            module.imported_symbols[imported_member] = (target.module_name, imported_member)

    def _resolve_symbol(self, module_name: str, name: str) -> GraphNode | None:
        candidates = self.symbols.get((module_name, name), [])
        return candidates[0] if len(candidates) == 1 else None

    def _resolve_member(
        self, module_name: str, class_name: str, member_name: str
    ) -> GraphNode | None:
        candidates = [
            candidate
            for candidate in self.symbols.get((module_name, member_name), [])
            if candidate.qualified_name.endswith(f".{class_name}.{member_name}")
        ]
        return candidates[0] if len(candidates) == 1 else None

    def _unique_imported_member(
        self, module: PolyglotModule, name: str
    ) -> GraphNode | None:
        """Infer an unknown receiver only from one unique internal imported member."""
        module_names = set(module.imported_modules.values()) | {
            module_name
            for module_name, _symbol_name in module.imported_symbols.values()
        }
        candidates = {
            candidate.id: candidate
            for module_name in module_names
            for candidate in self.symbols.get((module_name, name), [])
            if candidate.kind in {NodeKind.FUNCTION, NodeKind.METHOD}
        }
        return next(iter(candidates.values())) if len(candidates) == 1 else None

    def _definition_context(self, module: PolyglotModule, node: Node, source_id: str, class_id: str | None) -> tuple[str, str | None]:
        definition = module.definition_nodes.get(_node_key(node))
        if definition is None:
            return source_id, class_id
        return definition.id, definition.id if definition.kind == NodeKind.CLASS else class_id

    def _collect_java_receiver_types(self, module: PolyglotModule) -> None:
        def walk(node: Node, source_id: str, class_id: str | None) -> None:
            source_id, class_id = self._definition_context(module, node, source_id, class_id)
            if node.type in {"field_declaration", "local_variable_declaration"}:
                type_node = node.child_by_field_name("type")
                owner = class_id if node.type == "field_declaration" else source_id
                if type_node is not None and owner:
                    for declarator in _descendants(node, {"variable_declarator"}):
                        name_node = declarator.child_by_field_name("name")
                        if name_node is not None:
                            module.receiver_types[(owner, _text(module.source, name_node))] = _text(module.source, type_node)
            if node.type == "formal_parameter":
                type_node = node.child_by_field_name("type")
                name_node = node.child_by_field_name("name")
                if type_node is not None and name_node is not None:
                    module.receiver_types[(source_id, _text(module.source, name_node))] = _text(module.source, type_node)
            for child in node.named_children:
                walk(child, source_id, class_id)

        walk(module.root, module.module_node_id, None)

    def _call_target(
        self,
        module: PolyglotModule,
        node: Node,
        source_id: str,
        class_id: str | None,
    ) -> tuple[GraphNode | None, str, str, float]:
        if module.language == "java":
            name_node = node.child_by_field_name("name")
            name = _text(module.source, name_node)
            object_node = node.child_by_field_name("object")
            if object_node is None:
                if class_id:
                    class_node = self.graph.nodes.get(class_id)
                    if class_node:
                        target = self._resolve_symbol(module.module_name, name)
                        if target:
                            return target, name, "Resolved unqualified Java method in the same source type", 0.8
                return self._resolve_symbol(module.module_name, name), name, "Resolved unique same-file Java method", 0.8
            receiver = _text(module.source, object_node)
            if receiver == "this" and class_id:
                return self._resolve_symbol(module.module_name, name), f"this.{name}", "Resolved method on lexical Java class", 0.8
            target_module_name = module.imported_modules.get(receiver)
            if target_module_name is None:
                receiver_type = module.receiver_types.get((source_id, receiver))
                if receiver_type is None and class_id:
                    receiver_type = module.receiver_types.get((class_id, receiver))
                if receiver_type:
                    target_module_name = module.imported_modules.get(receiver_type)
                    if target_module_name is None:
                        same_package = module.module_name.rsplit(".", 1)[0] + "." + receiver_type
                        if same_package in self.modules_by_name:
                            target_module_name = same_package
            if target_module_name:
                return self._resolve_symbol(target_module_name, name), f"{receiver}.{name}", "Resolved Java receiver using imported or declared static type", 0.8
            recovered = self._unique_imported_member(module, name)
            if recovered is not None:
                return recovered, f"{receiver}.{name}", "Conservatively inferred unique matching Java member across internal imports", 0.55
            return None, f"{receiver}.{name}", "Java receiver type is not statically established", 0.0

        function = node.child_by_field_name("function")
        if function is None:
            return None, _text(module.source, node), "Call has no named function expression", 0.0
        if function.type == "identifier":
            name = _text(module.source, function)
            imported = module.imported_symbols.get(name)
            if imported:
                return self._resolve_symbol(*imported), name, "Resolved imported ECMAScript symbol alias", 0.8
            return self._resolve_symbol(module.module_name, name), name, "Resolved unique same-module symbol", 0.8
        if function.type in {"member_expression", "subscript_expression"}:
            object_node = function.child_by_field_name("object")
            property_node = function.child_by_field_name("property")
            receiver = _text(module.source, object_node)
            name = _text(module.source, property_node)
            if receiver == "this" and class_id:
                return self._resolve_symbol(module.module_name, name), f"this.{name}", "Resolved method on lexical class", 0.8
            target_module_name = module.imported_modules.get(receiver)
            if target_module_name:
                return self._resolve_symbol(target_module_name, name), f"{receiver}.{name}", "Resolved member on imported ECMAScript namespace", 0.8
            receiver_type = module.receiver_types.get((source_id, receiver))
            if receiver_type is None and class_id:
                receiver_type = module.receiver_types.get((class_id, receiver))
            if receiver_type:
                imported_type = module.imported_symbols.get(receiver_type)
                target_module_name = (
                    imported_type[0]
                    if imported_type
                    else module.imported_modules.get(receiver_type)
                )
                if target_module_name:
                    target = self._resolve_member(
                        target_module_name, receiver_type, name
                    )
                    if target:
                        return (
                            target,
                            f"{receiver}.{name}",
                            "Resolved member through locally constructed receiver",
                            0.8,
                        )
            recovered = self._unique_imported_member(module, name)
            if recovered is not None:
                return recovered, f"{receiver}.{name}", "Conservatively inferred unique matching ECMAScript member across internal imports", 0.55
            return None, f"{receiver}.{name}", "Member receiver type is not statically established", 0.0
        return None, _text(module.source, function), "Dynamic call expression is not statically resolvable", 0.0

    def _constructor_target(
        self, module: PolyglotModule, node: Node
    ) -> tuple[GraphNode | None, str, str]:
        constructor = (
            node.child_by_field_name("constructor")
            or node.child_by_field_name("type")
        )
        if constructor is None:
            return None, _text(module.source, node), "Construction has no named type"
        name = _text(module.source, constructor).split("<", 1)[0].strip()
        short_name = name.rsplit(".", 1)[-1]
        imported = module.imported_symbols.get(short_name)
        if imported:
            target = self._resolve_symbol(imported[0], imported[1])
            if target and target.kind == NodeKind.CLASS:
                return target, name, "Resolved imported class construction"
        target_module = module.imported_modules.get(short_name)
        if target_module:
            target = self._resolve_symbol(target_module, short_name)
            if target and target.kind == NodeKind.CLASS:
                return target, name, "Resolved imported type construction"
        target = self._resolve_symbol(module.module_name, short_name)
        if target and target.kind == NodeKind.CLASS:
            return target, name, "Resolved same-module class construction"
        return None, name, "Constructed type is not uniquely resolvable"

    def _add_instantiation(
        self, module: PolyglotModule, node: Node, source_id: str
    ) -> GraphNode | None:
        target, reference, resolution = self._constructor_target(module, node)
        if target is None:
            self._unresolved(
                module, source_id, node, reference, "instantiation", resolution
            )
            return None
        source_span = _span(module.relative_path, node)
        self.graph.add_edge(
            GraphEdge(
                id=_stable_id(
                    EdgeKind.INSTANTIATES,
                    source_id,
                    target.id,
                    source_span.start_line,
                    source_span.start_column,
                ),
                source=source_id,
                target=target.id,
                kind=EdgeKind.INSTANTIATES,
                evidence=Evidence(
                    status=EvidenceStatus.INFERRED,
                    span=source_span,
                    syntax=_text(module.source, node),
                    resolution=resolution,
                    confidence=0.82,
                ),
                metadata={"call_site_kind": "instantiation"},
            )
        )
        return target

    def _add_call(self, module: PolyglotModule, node: Node, source_id: str, class_id: str | None) -> None:
        target, reference, resolution, confidence = self._call_target(
            module, node, source_id, class_id
        )
        source_span = _span(module.relative_path, node)
        if target is None:
            self._unresolved(module, source_id, node, reference, "call", resolution)
            return
        self.graph.add_edge(
            GraphEdge(
                id=_stable_id(EdgeKind.MAY_CALL, source_id, target.id, source_span.start_line, source_span.start_column),
                source=source_id,
                target=target.id,
                kind=EdgeKind.MAY_CALL,
                evidence=Evidence(
                    status=EvidenceStatus.INFERRED,
                    span=source_span,
                    syntax=_text(module.source, node),
                    resolution=resolution,
                    confidence=confidence,
                ),
            )
        )

    def _extract_relationships(self, module: PolyglotModule) -> None:
        if module.language in {"html", "css"}:
            self._extract_declarative_relationships(module)
            return
        if module.language == "java":
            for node in _descendants(module.root, {"import_declaration"}):
                self._extract_java_import(module, node)
            self._collect_java_receiver_types(module)
            call_types = {"method_invocation"}
        else:
            for node in _descendants(module.root, {"import_statement"}):
                self._extract_js_import(module, node)
            for node in _descendants(module.root, {"export_statement"}):
                if node.child_by_field_name("source") is not None:
                    self._extract_js_reexport(module, node)
            require_calls = {
                _node_key(node)
                for node in _descendants(module.root, {"call_expression"})
                if self._extract_js_require(module, node)
            }
            call_types = {"call_expression"}

        def walk(node: Node, source_id: str, class_id: str | None) -> None:
            source_id, class_id = self._definition_context(module, node, source_id, class_id)
            if node.type in {"new_expression", "object_creation_expression"}:
                constructed = self._add_instantiation(module, node, source_id)
                parent = node.parent
                if constructed is not None and parent is not None and parent.type == "variable_declarator":
                    name_node = parent.child_by_field_name("name")
                    if name_node is not None:
                        module.receiver_types[
                            (source_id, _text(module.source, name_node))
                        ] = constructed.name
            if node.type in call_types and (
                module.language == "java" or _node_key(node) not in require_calls
            ):
                self._add_call(module, node, source_id, class_id)
            for child in node.named_children:
                walk(child, source_id, class_id)

        walk(module.root, module.module_node_id, None)

    @traced("parser.polyglot.relationships")
    def resolve_relationships(self) -> None:
        self._index_symbols()
        for module in self.modules:
            self._extract_relationships(module)
        log_event(
            logger,
            logging.INFO,
            "parser.polyglot_relationships_completed",
            "JavaScript, TypeScript, and Java relationships extracted",
            module_count=len(self.modules),
            language_counts={
                language: sum(item.language == language for item in self.modules)
                for language in sorted({item.language for item in self.modules})
            },
        )
