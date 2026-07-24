from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeKind(str, Enum):#enum enforces string on all the variables below, this class is used to define all the values a graphnode could be and it allows for ease of enforcement and validity
    REPOSITORY = "repository"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class EdgeKind(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    MAY_CALL = "may_call"
    INSTANTIATES = "instantiates"


class EvidenceStatus(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


class SourceSpan(BaseModel):
    model_config = ConfigDict(frozen=True)#this ensures that the variables below cannot be modified from outside here from within the codebase

    path: str
    start_line: int = Field(ge=1)
    start_column: int = Field(ge=0)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=0)
#to change it we would have to create a new model like
# updated = evidence.model_copy(update = {"confidence":0.5})

class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: EvidenceStatus
    span: SourceSpan
    syntax: str
    resolution: str
    confidence: float = Field(ge=0.0, le=1.0)#ge is freater then and le is less then


class GraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: NodeKind
    name: str
    qualified_name: str
    module: str | None = None
    span: SourceSpan | None = None
    signature: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    target: str
    kind: EdgeKind
    evidence: Evidence
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnresolvedReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    reference: str
    reference_kind: str
    evidence: Evidence
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None


class AnalysisStats(BaseModel):
    files_discovered: int
    files_parsed: int
    files_skipped: int
    parse_failures: int
    node_count: int
    edge_count: int
    unresolved_count: int
    duration_ms: float


class AnalysisReport(BaseModel):
    analysis_id: str | None = None
    view: str = "full"
    repository_root: str
    repository_name: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    unresolved_references: list[UnresolvedReference]
    diagnostics: list[AnalysisDiagnostic]
    stats: AnalysisStats


class GraphNeighborhood(BaseModel):
    center_node_id: str
    depth: int = Field(ge=0)
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphSummary(BaseModel):
    analysis_id: str
    node_counts: dict[str, int]
    edge_counts: dict[str, int]
    evidence_counts: dict[str, int]
    top_connected_nodes: list[dict[str, str | int]]
