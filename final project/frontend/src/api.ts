import type {
  AnalysisReport,
  AnalysisSessionSummary,
  IndexStatus,
  ArchitectureReport,
  ChallengeResult,
  ContributionMission,
  CodeJourney,
  ConversationTranscript,
  GroundedAnswer,
  IssueTimeline,
  IssueWorkspaceReport,
  ProposedIssue,
  RevisionReport,
  GraphNeighborhood,
  SymbolUsage,
  SourceDocument,
  TourPlan,
  TourRequest,
} from "./types";

const makeRequestId = (action: string) =>
  `ui-${action}-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  window.fetch(
    typeof input === "string" && input.startsWith("/api")
      ? `${API_BASE}${input}`
      : input,
    init,
  );

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function analyzeRepository(
  repositoryPath: string,
): Promise<AnalysisReport> {
  const response = await fetch("/api/v1/analysis", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": makeRequestId("analyze"),
    },
    body: JSON.stringify({ repository_path: repositoryPath }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as AnalysisReport;
}

export async function analyzeGitHubRepository(
  repositoryUrl: string,
): Promise<AnalysisReport> {
  const response = await fetch("/api/v1/analysis/github", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": makeRequestId("github"),
    },
    body: JSON.stringify({ repository_url: repositoryUrl }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as AnalysisReport;
}

export async function fetchAnalysis(analysisId: string): Promise<AnalysisReport> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
    { headers: { "X-Request-ID": makeRequestId("restore-analysis") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AnalysisReport;
}

export async function fetchAnalyses(): Promise<AnalysisSessionSummary[]> {
  const response = await fetch("/api/v1/analyses", {
    headers: { "X-Request-ID": makeRequestId("list-analyses") },
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AnalysisSessionSummary[];
}

export async function fetchIndexStatus(
  analysisId: string,
): Promise<IndexStatus> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/index`,
    { headers: { "X-Request-ID": makeRequestId("index-status") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as IndexStatus;
}

export async function rebuildIndex(
  analysisId: string,
): Promise<IndexStatus> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/index/rebuild`,
    {
      method: "POST",
      headers: { "X-Request-ID": makeRequestId("index-rebuild") },
    },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as IndexStatus;
}

export async function fetchLatestConversation(
  analysisId: string,
  scope: "ask" | "onboarding" = "ask",
): Promise<ConversationTranscript> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/conversation/latest?scope=${scope}`,
    { headers: { "X-Request-ID": makeRequestId("conversation-history") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as ConversationTranscript;
}

export async function fetchSource(
  analysisId: string,
  path: string,
): Promise<SourceDocument> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/source?path=${encodeURIComponent(path)}`,
    {
      headers: { "X-Request-ID": makeRequestId("source") },
    },
  );
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as SourceDocument;
}

export async function fetchNeighborhood(
  analysisId: string,
  nodeId: string,
  depth = 1,
): Promise<GraphNeighborhood> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/nodes/${encodeURIComponent(nodeId)}/neighborhood?depth=${depth}`,
    {
      headers: { "X-Request-ID": makeRequestId("neighborhood") },
    },
  );
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as GraphNeighborhood;
}

export async function fetchSymbolUsage(
  analysisId: string,
  nodeId: string,
): Promise<SymbolUsage> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/nodes/${encodeURIComponent(nodeId)}/usage`,
    { headers: { "X-Request-ID": makeRequestId("symbol-usage") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as SymbolUsage;
}

export async function createTour(
  analysisId: string,
  request: TourRequest,
): Promise<TourPlan> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/tour`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": makeRequestId("tour"),
      },
      body: JSON.stringify(request),
    },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as TourPlan;
}

export async function answerChallenge(
  analysisId: string,
  tourId: string,
  challengeId: string,
  answer: { selected_node_id?: string; response?: string },
): Promise<ChallengeResult> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/tours/${encodeURIComponent(tourId)}/answers`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": makeRequestId("mastery"),
      },
      body: JSON.stringify({
        challenge_id: challengeId,
        ...answer,
      }),
    },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as ChallengeResult;
}

export async function fetchArchitecture(
  analysisId: string,
): Promise<ArchitectureReport> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/architecture`,
    { headers: { "X-Request-ID": makeRequestId("architecture") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as ArchitectureReport;
}

export async function fetchMission(
  analysisId: string,
  request: TourRequest,
): Promise<ContributionMission> {
  const response = await fetch(`/api/v1/analyses/${encodeURIComponent(analysisId)}/mission`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": makeRequestId("mission"),
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as ContributionMission;
}

export async function askRepository(
  analysisId: string,
  question: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
  conversationId: string | null = null,
  conversationScope: "ask" | "onboarding" | "inspector" = "ask",
  focusNodeId: string | null = null,
): Promise<GroundedAnswer> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/answer`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": makeRequestId("answer"),
      },
      body: JSON.stringify({
        question,
        history,
        conversation_id: conversationId,
        conversation_scope: conversationScope,
        focus_node_id: focusNodeId,
      }),
    },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as GroundedAnswer;
}

export async function fetchJourney(
  analysisId: string,
  nodeId: string,
  maxSteps = 20,
): Promise<CodeJourney> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/journey/${encodeURIComponent(nodeId)}?max_steps=${maxSteps}`,
    { headers: { "X-Request-ID": makeRequestId("journey") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as CodeJourney;
}

export async function compareAnalyses(
  analysisId: string,
  baseAnalysisId: string,
): Promise<RevisionReport> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/compare/${encodeURIComponent(baseAnalysisId)}`,
    { headers: { "X-Request-ID": makeRequestId("compare") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as RevisionReport;
}

export async function fetchIssues(
  analysisId: string,
  page = 1,
): Promise<IssueWorkspaceReport> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/issues?page=${page}&per_page=50`,
    { headers: { "X-Request-ID": makeRequestId("issues") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as IssueWorkspaceReport;
}

export async function fetchIssueTimeline(
  analysisId: string,
  issueNumber: number,
): Promise<IssueTimeline> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/issues/${issueNumber}/timeline`,
    { headers: { "X-Request-ID": makeRequestId("issue-timeline") } },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as IssueTimeline;
}

export async function investigateIssues(
  analysisId: string,
): Promise<ProposedIssue[]> {
  const response = await fetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/issues/investigate`,
    {
      method: "POST",
      headers: { "X-Request-ID": makeRequestId("issue-investigation") },
    },
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as ProposedIssue[];
}
