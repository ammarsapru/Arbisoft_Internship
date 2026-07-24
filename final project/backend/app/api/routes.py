from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from backend.app.agent.issues import RepositoryIssueAgent
from backend.app.agent.comparison import ModelComparisonService
from backend.app.agent.memory import conversations
from backend.app.agent.onboarding import RepositoryOnboardingAgent
from backend.app.agent.retrieval import repository_indexes
from backend.app.agent.service import (
    AgentExecutionError,
    AgentUnavailableError,
    RepositoryAgentService,
)
from backend.app.config import settings
from backend.app.graph.analyzer import RepositoryAnalyzer
from backend.app.graph.models import AnalysisReport, GraphNeighborhood, GraphSummary
from backend.app.graph.store import AnalysisSession, GraphQueryService, analysis_sessions
from backend.app.issues.models import IssueTimeline, IssueWorkspaceReport, ProposedIssue
from backend.app.issues.service import GitHubIssueError, GitHubIssueService
from backend.app.observability import log_event, traced
from backend.app.onboarding.models import (
    ArchitectureReport,
    ChallengeAnswer,
    ChallengeResult,
    CodeJourney,
    ConversationTranscript,
    ConversationTurn,
    ContributionMission,
    GroundedAnswer,
    GroundedQuestion,
    ModelComparisonReport,
    ModelComparisonRequest,
    RevisionReport,
    TourPlan,
    TourRequest,
)
from backend.app.onboarding.service import OnboardingService, tour_states
from backend.app.repository_import import (
    GitCloneError,
    GitHubRepositoryCloner,
    GitUnavailableError,
    InvalidGitHubRepository,
    RepositoryImportError,
    parse_github_repository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


class AnalysisRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=2048)


class GitHubAnalysisRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=2048)

    @field_validator("repository_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        parse_github_repository(value)
        return value


class HealthResponse(BaseModel):
    status: str
    app: str
    allowed_root: str
    clone_root: str
    trace_functions: bool
    max_trace: bool


class SourceDocument(BaseModel):
    analysis_id: str
    path: str
    language: str
    content: str
    line_count: int
    size_bytes: int


class AnalysisSessionSummary(BaseModel):
    analysis_id: str
    repository_name: str
    repository_root: str
    files_parsed: int
    node_count: int
    edge_count: int


_SOURCE_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".java": "java",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".md": "markdown",
    ".mdx": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
}


github_cloner = GitHubRepositoryCloner(
    clone_root=settings.clone_root,
    allowed_root=settings.allowed_root,
    timeout_seconds=settings.clone_timeout_seconds,
    max_clone_bytes=settings.max_clone_bytes,
    max_clone_files=settings.max_clone_files,
    max_retained_clones=settings.max_retained_clones,
)


def _source_language(path: Path) -> str:
    return _SOURCE_LANGUAGES.get(path.suffix.lower(), "text")


def _session(analysis_id: str) -> AnalysisSession:
    try:
        return analysis_sessions.get(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis session was not found") from exc


def _read_source(session: AnalysisSession, source_path: str) -> SourceDocument:
    normalized = Path(source_path).as_posix().lstrip("/")
    if normalized not in session.source_paths:
        raise HTTPException(status_code=404, detail="Source file was not found")
    candidate = (session.root / normalized).resolve()
    try:
        candidate.relative_to(session.root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Source file was not found") from exc
    try:
        content = candidate.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Source file could not be read") from exc
    return SourceDocument(
        analysis_id=session.id,
        path=normalized,
        language=_source_language(candidate),
        content=content,
        line_count=len(content.splitlines()),
        size_bytes=len(content.encode("utf-8")),
    )


def _analyze(root: Path, repository_name: str | None = None) -> AnalysisReport:
    report = RepositoryAnalyzer().analyze(root)
    if repository_name:
        report = report.model_copy(update={"repository_name": repository_name})
    stored = analysis_sessions.create(root, report)
    session = analysis_sessions.get(stored.analysis_id or "")
    repository_indexes.get(session)
    return GraphQueryService(session.report).overview()


def _agent_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AgentUnavailableError):
        return HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is required for AI-generated repository answers",
        )
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/health", response_model=HealthResponse)
@traced("http.health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        allowed_root=str(settings.allowed_root),
        clone_root=str(settings.clone_root),
        trace_functions=settings.trace_functions,
        max_trace=settings.max_trace,
    )


@router.post("/analysis", response_model=AnalysisReport)
@traced("http.analysis")
async def analyze_repository(request: AnalysisRequest) -> AnalysisReport:
    requested = Path(request.repository_path).expanduser()
    resolved = requested.resolve() if requested.is_absolute() else (settings.allowed_root / requested).resolve()
    try:
        resolved.relative_to(settings.allowed_root)
    except ValueError as exc:
        log_event(logger, logging.WARNING, "security.repository_path_rejected", "Repository path rejected because it escapes the configured root", requested_path=request.repository_path, resolved_path=resolved, allowed_root=settings.allowed_root)
        raise HTTPException(status_code=403, detail="Repository path is outside the configured allowed root") from exc
    try:
        return await run_in_threadpool(_analyze, resolved)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analysis/github", response_model=AnalysisReport)
@traced("http.analysis_github")
async def analyze_github_repository(request: GitHubAnalysisRequest) -> AnalysisReport:
    identity = parse_github_repository(request.repository_url)
    try:
        root = await run_in_threadpool(github_cloner.clone, request.repository_url)
        return await run_in_threadpool(_analyze, root, identity.name)
    except InvalidGitHubRepository as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (GitCloneError, RepositoryImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}", response_model=AnalysisReport)
async def get_analysis(analysis_id: str) -> AnalysisReport:
    return GraphQueryService(_session(analysis_id).report).overview()


@router.get("/analyses", response_model=list[AnalysisSessionSummary])
async def list_analyses() -> list[AnalysisSessionSummary]:
    sessions = await run_in_threadpool(analysis_sessions.list_recent)
    return [
        AnalysisSessionSummary(
            analysis_id=session.id,
            repository_name=session.report.repository_name,
            repository_root=str(session.root),
            files_parsed=session.report.stats.files_parsed,
            node_count=session.report.stats.node_count,
            edge_count=session.report.stats.edge_count,
        )
        for session in sessions
    ]


@router.get("/analyses/{analysis_id}/summary", response_model=GraphSummary)
async def get_summary(analysis_id: str) -> GraphSummary:
    return GraphQueryService(_session(analysis_id).report).summary()


@router.get("/analyses/{analysis_id}/index")
async def get_index(analysis_id: str) -> dict[str, object]:
    index = await run_in_threadpool(repository_indexes.get, _session(analysis_id))
    return index.status()


@router.post("/analyses/{analysis_id}/index/rebuild")
async def rebuild_index(analysis_id: str) -> dict[str, object]:
    index = await run_in_threadpool(repository_indexes.rebuild, _session(analysis_id))
    return index.status()


@router.get("/analyses/{analysis_id}/conversation/latest", response_model=ConversationTranscript)
async def latest_conversation(analysis_id: str, scope: str = Query("ask", pattern="^(ask|onboarding|inspector)$")) -> ConversationTranscript:
    _session(analysis_id)
    conversation = conversations.latest(analysis_id, scope)
    if conversation is None:
        return ConversationTranscript(analysis_id=analysis_id, conversation_id=None, turns=[])
    turns: list[ConversationTurn] = []
    pending_question: str | None = None
    for item in conversations.transcript(conversation):
        if item["role"] == "user":
            pending_question = item["content"]
        elif pending_question is not None:
            raw = item.get("answer_json")
            try:
                answer = GroundedAnswer.model_validate_json(raw) if raw else GroundedAnswer(question=pending_question, answer=item["content"], citations=[], refused=False, basis="restored conversation", conversation_id=conversation.id)
            except ValueError:
                answer = GroundedAnswer(question=pending_question, answer=item["content"], citations=[], refused=False, basis="restored conversation", conversation_id=conversation.id)
            turns.append(ConversationTurn(question=pending_question, answer=answer))
            pending_question = None
    return ConversationTranscript(analysis_id=analysis_id, conversation_id=conversation.id, turns=turns)


@router.get("/analyses/{analysis_id}/source", response_model=SourceDocument)
async def get_source(analysis_id: str, path: str = Query(min_length=1, max_length=2048)) -> SourceDocument:
    return await run_in_threadpool(_read_source, _session(analysis_id), path)


@router.get("/analyses/{analysis_id}/nodes/{node_id}/neighborhood", response_model=GraphNeighborhood)
async def get_neighborhood(analysis_id: str, node_id: str, depth: int = Query(1, ge=1, le=3)) -> GraphNeighborhood:
    try:
        return GraphQueryService(_session(analysis_id).report).neighborhood(node_id, depth)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Graph node was not found") from exc


@router.get("/analyses/{analysis_id}/nodes/{node_id}/usage")
async def get_symbol_usage(analysis_id: str, node_id: str) -> dict[str, object]:
    session = _session(analysis_id)
    try:
        service = RepositoryAgentService(session)
        return await run_in_threadpool(service.semantic.symbol_relationships, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Graph node was not found") from exc


@router.post("/analyses/{analysis_id}/tour", response_model=TourPlan)
async def create_tour(analysis_id: str, request: TourRequest) -> TourPlan:
    session = _session(analysis_id)
    try:
        if RepositoryAgentService(session).available:
            return await run_in_threadpool(RepositoryOnboardingAgent(session).plan, request)
        return await run_in_threadpool(OnboardingService(session.report).plan_tour, request)
    except (AgentUnavailableError, AgentExecutionError) as exc:
        raise _agent_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyses/{analysis_id}/tours/{tour_id}/answers", response_model=ChallengeResult)
async def answer_challenge(analysis_id: str, tour_id: str, answer: ChallengeAnswer) -> ChallengeResult:
    session = _session(analysis_id)
    try:
        challenge = tour_states.challenge(tour_id, answer.challenge_id)
        if challenge.question_type == "free_text":
            return await run_in_threadpool(RepositoryOnboardingAgent(session).evaluate, tour_id, challenge, answer)
        return tour_states.answer(tour_id, answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Tour challenge was not found") from exc
    except (AgentUnavailableError, AgentExecutionError) as exc:
        raise _agent_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/architecture", response_model=ArchitectureReport)
async def get_architecture(analysis_id: str) -> ArchitectureReport:
    return OnboardingService(_session(analysis_id).report).architecture_report()


@router.post("/analyses/{analysis_id}/mission", response_model=ContributionMission)
async def get_mission(analysis_id: str, request: TourRequest) -> ContributionMission:
    session = _session(analysis_id)
    try:
        if RepositoryAgentService(session).available:
            return await run_in_threadpool(RepositoryOnboardingAgent(session).mission, request)
        return OnboardingService(session.report).contribution_mission(request.role)
    except (AgentUnavailableError, AgentExecutionError) as exc:
        raise _agent_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyses/{analysis_id}/answer", response_model=GroundedAnswer)
async def answer_repository_question(analysis_id: str, request: GroundedQuestion) -> GroundedAnswer:
    service = RepositoryAgentService(_session(analysis_id))
    if not service.available:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is required for AI-generated repository answers",
        )
    try:
        return await run_in_threadpool(service.answer, request)
    except (AgentUnavailableError, AgentExecutionError) as exc:
        raise _agent_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/analyses/{analysis_id}/answer/compare",
    response_model=ModelComparisonReport,
)
async def compare_repository_answers(
    analysis_id: str,
    request: ModelComparisonRequest,
) -> ModelComparisonReport:
    """Send one question and one frozen evidence bundle to both configured models."""
    try:
        return await run_in_threadpool(
            ModelComparisonService(_session(analysis_id)).compare,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _agent_error(exc) from exc


@router.get("/analyses/{analysis_id}/journey/{node_id}", response_model=CodeJourney)
async def get_journey(analysis_id: str, node_id: str, max_steps: int = Query(20, ge=1, le=100)) -> CodeJourney:
    try:
        return OnboardingService(_session(analysis_id).report).journey(node_id, max_steps)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Graph node was not found") from exc


@router.get("/analyses/{analysis_id}/compare/{base_analysis_id}", response_model=RevisionReport)
async def compare_analyses(analysis_id: str, base_analysis_id: str) -> RevisionReport:
    current = _session(analysis_id)
    previous = _session(base_analysis_id)
    return OnboardingService(current.report).compare(previous.report)


@router.get("/analyses/{analysis_id}/issues", response_model=IssueWorkspaceReport)
async def get_issues(analysis_id: str, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)) -> IssueWorkspaceReport:
    return await run_in_threadpool(GitHubIssueService(_session(analysis_id)).workspace, page, per_page)


@router.post("/analyses/{analysis_id}/issues/investigate", response_model=list[ProposedIssue])
async def investigate_issues(analysis_id: str) -> list[ProposedIssue]:
    session = _session(analysis_id)
    issue_service = GitHubIssueService(session)
    workspace = await run_in_threadpool(issue_service.workspace)
    try:
        return await run_in_threadpool(RepositoryIssueAgent(session).investigate, workspace.github_issues)
    except (AgentUnavailableError, AgentExecutionError) as exc:
        raise _agent_error(exc) from exc


@router.get("/analyses/{analysis_id}/issues/{issue_number}/timeline", response_model=IssueTimeline)
async def get_issue_timeline(analysis_id: str, issue_number: int) -> IssueTimeline:
    try:
        return await run_in_threadpool(GitHubIssueService(_session(analysis_id)).timeline, issue_number)
    except GitHubIssueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
