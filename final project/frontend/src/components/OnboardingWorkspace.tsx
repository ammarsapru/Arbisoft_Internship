import { useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpenCheck,
  Check,
  CircleAlert,
  Crosshair,
  GraduationCap,
  LoaderCircle,
  MapPin,
  MessageSquareText,
  Send,
  Shield,
  Target,
  TestTube2,
} from "lucide-react";
import {
  answerChallenge,
  askRepository,
  createTour,
  fetchMission,
  fetchSource,
} from "../api";
import type {
  AnalysisReport,
  ChallengeResult,
  ContributionMission,
  DeveloperRole,
  ExperienceLevel,
  GroundedAnswer,
  SourceDocument,
  TourEvidenceFile,
  TourPlan,
} from "../types";
import { SourcePanel } from "./SourcePanel";
import { LazyMarkdownContent } from "./LazyMarkdownContent";

const roles: Array<{
  value: DeveloperRole;
  label: string;
  description: string;
  icon: typeof GraduationCap;
}> = [
  {
    value: "general",
    label: "Explorer",
    description: "Architecture-wide orientation",
    icon: GraduationCap,
  },
  {
    value: "backend",
    label: "Backend",
    description: "Routes, services, models, and state",
    icon: Crosshair,
  },
  {
    value: "security",
    label: "Security",
    description: "Trust boundaries and sensitive paths",
    icon: Shield,
  },
  {
    value: "qa",
    label: "Quality",
    description: "Tests, fixtures, and behavioral seams",
    icon: TestTube2,
  },
];

export function OnboardingWorkspace({
  report,
  onOpenNode,
  theme,
}: {
  report: AnalysisReport;
  onOpenNode: (nodeId: string) => void;
  theme: "light" | "dark";
}) {
  const [role, setRole] = useState<DeveloperRole>("general");
  const [experience, setExperience] = useState<ExperienceLevel>("new");
  const [goal, setGoal] = useState("Understand how this repository fits together");
  const [minutes, setMinutes] = useState(15);
  const [tour, setTour] = useState<TourPlan | null>(null);
  const [mission, setMission] = useState<ContributionMission | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [activeFile, setActiveFile] = useState<TourEvidenceFile | null>(null);
  const [tourSource, setTourSource] = useState<SourceDocument | null>(null);
  const [tourSourceLoading, setTourSourceLoading] = useState(false);
  const [tourSourceError, setTourSourceError] = useState<string | null>(null);
  const [tourQuestion, setTourQuestion] = useState("");
  const [tourAnswer, setTourAnswer] = useState<GroundedAnswer | null>(null);
  const [tourConversationId, setTourConversationId] = useState<string | null>(null);
  const [tourChatLoading, setTourChatLoading] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, ChallengeResult>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const first = tour?.steps[activeStep]?.files[0] ?? null;
    setActiveFile(first);
  }, [tour, activeStep]);

  useEffect(() => {
    if (!activeFile) {
      setTourSource(null);
      return;
    }
    let cancelled = false;
    setTourSourceLoading(true);
    setTourSourceError(null);
    fetchSource(report.analysis_id, activeFile.path)
      .then((result) => {
        if (!cancelled) setTourSource(result);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setTourSourceError(caught instanceof Error ? caught.message : "Source failed");
        }
      })
      .finally(() => {
        if (!cancelled) setTourSourceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [report.analysis_id, activeFile]);

  const generate = async () => {
    setLoading(true);
    setError(null);
    setResults({});
    try {
      const request = { role, experience, goal: goal.trim(), minutes };
      const [tourResult, missionResult] = await Promise.allSettled([
        createTour(report.analysis_id, request),
        fetchMission(report.analysis_id, request),
      ]);
      if (tourResult.status === "rejected") throw tourResult.reason;
      setTour(tourResult.value);
      setMission(
        missionResult.status === "fulfilled" ? missionResult.value : null,
      );
      setActiveStep(0);
      setTourAnswer(null);
      setTourConversationId(null);
      if (missionResult.status === "rejected") {
        const reason = missionResult.reason;
        setError(
          `Your onboarding route is ready. The optional contribution mission could not be generated: ${
            reason instanceof Error ? reason.message : "mission generation failed"
          }`,
        );
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Tour generation failed");
    } finally {
      setLoading(false);
    }
  };

  const askTour = async () => {
    if (!tour || !tourQuestion.trim() || tourChatLoading) return;
    const step = tour.steps[activeStep];
    const contextualQuestion = [
      `I am following an onboarding tour as a ${tour.role} developer.`,
      `My objective is: ${tour.goal}.`,
      `Current step: ${step.title}.`,
      activeFile ? `Current file: ${activeFile.path}.` : "",
      `Question: ${tourQuestion.trim()}`,
    ].filter(Boolean).join("\n");
    setTourChatLoading(true);
    try {
      const answer = await askRepository(
        report.analysis_id,
        contextualQuestion,
        [],
        tourConversationId,
        "onboarding",
      );
      setTourAnswer(answer);
      setTourConversationId(answer.conversation_id ?? tourConversationId);
      setTourQuestion("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Tour question failed");
    } finally {
      setTourChatLoading(false);
    }
  };

  const submitAnswer = async (challengeId: string) => {
    if (!tour || !answers[challengeId]) return;
    try {
      const result = await answerChallenge(
        report.analysis_id,
        tour.id,
        challengeId,
        tour.steps[activeStep].challenge?.question_type === "free_text"
          ? { response: answers[challengeId] }
          : { selected_node_id: answers[challengeId] },
      );
      setResults((current) => ({ ...current, [challengeId]: result }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Answer failed");
    }
  };

  const latestScore = Object.values(results).at(-1)?.score ?? 0;

  return (
    <main className="onboarding-workspace">
      <aside className="onboarding-config">
        <div className="onboarding-kicker">Adaptive route</div>
        <h2>Learn for the work you need to do.</h2>
        <p>
          The route is ranked from this repository’s graph—not a fixed tutorial.
        </p>

        <label className="form-label">Your role</label>
        <div className="role-grid">
          {roles.map((option) => {
            const Icon = option.icon;
            return (
              <button
                type="button"
                key={option.value}
                className={role === option.value ? "selected" : ""}
                onClick={() => setRole(option.value)}
              >
                <Icon size={17} />
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
              </button>
            );
          })}
        </div>

        <label className="form-label" htmlFor="tour-goal">
          Objective
        </label>
        <textarea
          id="tour-goal"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          rows={3}
        />

        <div className="config-row">
          <label>
            <span className="form-label">Experience</span>
            <select
              value={experience}
              onChange={(event) =>
                setExperience(event.target.value as ExperienceLevel)
              }
            >
              <option value="new">New to this stack</option>
              <option value="familiar">Familiar</option>
              <option value="expert">Expert</option>
            </select>
          </label>
          <label>
            <span className="form-label">Time budget</span>
            <select
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
            >
              <option value={5}>5 minutes</option>
              <option value={15}>15 minutes</option>
              <option value={30}>30 minutes</option>
              <option value={60}>60 minutes</option>
              <option value={90}>90 minutes</option>
              <option value={120}>2 hours</option>
            </select>
          </label>
        </div>

        <button
          type="button"
          className="generate-tour"
          onClick={() => void generate()}
          disabled={loading}
        >
          {loading ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <BookOpenCheck size={17} />
          )}
          Generate my route
        </button>
        {error && (
          <div className="onboarding-error">
            <CircleAlert size={15} /> {error}
          </div>
        )}
      </aside>

      <section className="tour-stage">
        {!tour ? (
          <div className="tour-empty">
            <GraduationCap size={36} />
            <h2>Your repository-specific route will appear here.</h2>
            <p>
              Choose a role and objective. Every resulting step will cite a real
              module and source span.
            </p>
          </div>
        ) : (
          <>
            <header className="tour-header">
              <div>
                <div className="onboarding-kicker">
                  {tour.role} · {tour.estimated_minutes} minutes
                </div>
                <h2>{tour.goal}</h2>
              </div>
              <div className="mastery-meter">
                <span>Mastery</span>
                <strong>{Math.round(latestScore * 100)}%</strong>
              </div>
            </header>
            <div className="tour-body">
              <nav className="tour-timeline" aria-label="Tour steps">
                {tour.steps.map((step, index) => (
                  <button
                    type="button"
                    key={step.node_id}
                    className={activeStep === index ? "active" : ""}
                    onClick={() => setActiveStep(index)}
                  >
                    <span>{step.index}</span>
                    <div>
                      <strong>{step.title}</strong>
                      <small>{step.evidence?.path}</small>
                    </div>
                  </button>
                ))}
              </nav>
              {tour.steps[activeStep] && (
                <article className="tour-step-card">
                  <div className="step-number">
                    Step {tour.steps[activeStep].index} of {tour.steps.length}
                  </div>
                  <h3>{tour.steps[activeStep].objective}</h3>
                  <p>{tour.steps[activeStep].explanation}</p>
                  <div className="why-selected">
                    <strong>Why this step</strong>
                    <span>{tour.steps[activeStep].why_selected}</span>
                  </div>
                  <div className="guided-files">
                    <div className="guided-files-heading">
                      <strong>Model-selected reading order</strong>
                      <span>{tour.steps[activeStep].files.length} files</span>
                    </div>
                    <div className="guided-file-tabs">
                      {tour.steps[activeStep].files.map((file, index) => (
                        <button
                          type="button"
                          key={`${file.path}:${file.start_line}`}
                          className={
                            activeFile?.path === file.path &&
                            activeFile.start_line === file.start_line
                              ? "active"
                              : ""
                          }
                          onClick={() => setActiveFile(file)}
                        >
                          <span>{index + 1}</span>
                          <div>
                            <strong>{file.path.split("/").at(-1)}</strong>
                            <small>{file.reason}</small>
                          </div>
                        </button>
                      ))}
                    </div>
                    <div className="guided-source-viewer">
                      <SourcePanel
                        source={tourSource}
                        span={
                          activeFile
                            ? {
                                path: activeFile.path,
                                start_line: activeFile.start_line,
                                start_column: 0,
                                end_line: activeFile.end_line,
                                end_column: 0,
                              }
                            : null
                        }
                        loading={tourSourceLoading}
                        error={tourSourceError}
                        theme={theme}
                      />
                    </div>
                  </div>
                  {tour.steps[activeStep].files[0]?.node_id && (
                    <button
                      type="button"
                      className="open-evidence"
                      onClick={() =>
                        onOpenNode(tour.steps[activeStep].files[0].node_id as string)
                      }
                    >
                      <MapPin size={15} />
                      {tour.steps[activeStep].evidence?.path}:L
                      {tour.steps[activeStep].evidence?.start_line}
                      <ArrowRight size={15} />
                    </button>
                  )}
                  <div className="tour-chat">
                    <div className="tour-chat-heading">
                      <MessageSquareText size={15} />
                      <strong>Ask about this step or the repository</strong>
                    </div>
                    {tourAnswer && (
                      <div className="tour-chat-answer">
                        <span>{tourAnswer.provider.replaceAll("-", " ")}</span>
                        <LazyMarkdownContent content={tourAnswer.answer} />
                        <div>
                          {tourAnswer.citations.map((citation) => (
                            <button
                              type="button"
                              key={`${citation.span.path}:${citation.span.start_line}`}
                              onClick={() =>
                                setActiveFile({
                                  path: citation.span.path,
                                  start_line: citation.span.start_line,
                                  end_line: citation.span.end_line,
                                  node_id: citation.node_id,
                                  reason: citation.relevance,
                                })
                              }
                            >
                              {citation.span.path}:L{citation.span.start_line}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="tour-chat-composer">
                      <textarea
                        rows={2}
                        value={tourQuestion}
                        placeholder="Ask why this file matters, trace a request, or clarify a concept…"
                        onChange={(event) => setTourQuestion(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.shiftKey) {
                            event.preventDefault();
                            void askTour();
                          }
                        }}
                      />
                      <button
                        type="button"
                        disabled={!tourQuestion.trim() || tourChatLoading}
                        onClick={() => void askTour()}
                      >
                        {tourChatLoading ? (
                          <LoaderCircle className="spin" size={15} />
                        ) : (
                          <Send size={15} />
                        )}
                      </button>
                    </div>
                  </div>
                  {tour.steps[activeStep].challenge && (
                    <div className="challenge-card">
                      <div className="challenge-label">Comprehension check</div>
                      <strong>{tour.steps[activeStep].challenge?.prompt}</strong>
                      {tour.steps[activeStep].challenge?.question_type === "free_text" ? (
                        <textarea
                          className="challenge-response"
                          rows={5}
                          value={answers[tour.steps[activeStep].challenge!.id] ?? ""}
                          placeholder="Explain the concept in your own words using what you observed in the cited files…"
                          onChange={(event) =>
                            setAnswers((current) => ({
                              ...current,
                              [tour.steps[activeStep].challenge!.id]: event.target.value,
                            }))
                          }
                        />
                      ) : (
                        <div className="challenge-options">
                          {tour.steps[activeStep].challenge?.options.map((option) => (
                          <label key={option.node_id}>
                            <input
                              type="radio"
                              name={tour.steps[activeStep].challenge?.id}
                              value={option.node_id}
                              checked={
                                answers[tour.steps[activeStep].challenge!.id] ===
                                option.node_id
                              }
                              onChange={() =>
                                setAnswers((current) => ({
                                  ...current,
                                  [tour.steps[activeStep].challenge!.id]:
                                    option.node_id,
                                }))
                              }
                            />
                            <span>{option.label}</span>
                          </label>
                          ))}
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() =>
                          void submitAnswer(
                            tour.steps[activeStep].challenge!.id,
                          )
                        }
                      >
                        Check answer
                      </button>
                      {results[tour.steps[activeStep].challenge!.id] && (
                        <div
                          className={`challenge-result ${
                            results[tour.steps[activeStep].challenge!.id].correct
                              ? "correct"
                              : "incorrect"
                          }`}
                        >
                          {results[tour.steps[activeStep].challenge!.id].correct ? (
                            <Check size={15} />
                          ) : (
                            <CircleAlert size={15} />
                          )}
                          {
                            results[tour.steps[activeStep].challenge!.id]
                              .explanation
                          }
                          {results[tour.steps[activeStep].challenge!.id].remediation && (
                            <p>{results[tour.steps[activeStep].challenge!.id].remediation}</p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              )}
            </div>
          </>
        )}
      </section>

      <aside className="mission-panel">
        <div className="onboarding-kicker">First contribution</div>
        {mission ? (
          <>
            <div className="mission-risk">{mission.risk} risk</div>
            <div className="mission-confidence">
              {mission.provider.replaceAll("-", " ")} · {Math.round(mission.confidence * 100)}% confidence · {mission.status}
            </div>
            <h2>{mission.title}</h2>
            <p>{mission.rationale}</p>
            <div className="mission-target">
              <Target size={17} />
              <div>
                <strong>{mission.target_node.qualified_name}</strong>
                <small>{mission.target_node.span?.path}</small>
              </div>
            </div>
            <h3>Mission checklist</h3>
            <ol>
              {mission.checklist.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ol>
            <h3>Definition of done</h3>
            <ul>
              {mission.definition_of_done.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>Validation</h3>
            <ul>
              {mission.validation_checks.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <button
              type="button"
              className="open-mission"
              onClick={() => onOpenNode(mission.target_node.id)}
            >
              Open mission target <ArrowRight size={15} />
            </button>
          </>
        ) : (
          <div className="mission-empty">
            <Target size={28} />
            <p>
              Generate a route to receive a low-risk, evidence-backed first
              contribution mission.
            </p>
          </div>
        )}
      </aside>
    </main>
  );
}
