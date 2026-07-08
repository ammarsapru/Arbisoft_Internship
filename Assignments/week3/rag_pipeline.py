"""Structured-output RAG pipeline: retrieve -> LLM -> JSON -> validate -> save.

Flow for one question:
  1. similarity_search_with_score the vector store for the top-k chunks
     (score is surfaced to the model as a relevance signal, see
     format_context)
  2. prompt a local Ollama chat model with a SYSTEM message (persona,
     capabilities, hard behavioral constraints, output contract) and a
     separate USER message (retrieved context + question, each in its own
     clearly labeled section) requesting JSON that matches
     schemas.RAGAnswer (constrained decoding via Ollama's `format`
     parameter by default; pass constrained=False to see raw model behavior)
  3. parse_llm_output() validates the raw text against the schema
     (raises SchemaValidationError on any violation)
  4. hallucination.grounding_report() checks the validated answer against the
     retrieved context
  5. the full record (raw output, validated answer, grounding report,
     retrieved pages) is saved to results/answers/

Run:  uv run python rag_pipeline.py
The chat model defaults to qwen2.5:1.5b; override with the RAG_LLM_MODEL env var.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import ChatOllama

from chunking import get_chunks
from extract_pdf import load_pdf_pages
from get_embeddings import get_qwen_embed
from hallucination import grounding_report
from schemas import RAGAnswer, SchemaValidationError, parse_llm_output
from store_utils import build_vector_store

DEFAULT_LLM_MODEL = os.getenv("RAG_LLM_MODEL", "qwen2.5:1.5b")
RESULTS_DIR = Path(__file__).parent / "results" / "answers"

# Sent once per call as the system message: identity, capabilities, and hard
# behavioral constraints. This is deliberately separated from the per-question
# context/question (the human message, below) so that "the rules the model
# must follow" and "the data it was given" are never in the same turn -- a
# single-blob prompt makes it easy for a model to treat an instruction and a
# retrieved fact as equally negotiable content, which is what let the
# pre-restructure pipeline answer questions like "What is the capital of
# France?" instead of refusing (see hallucination_eval.json: 0% refusal rate
# across all 4 adversarial tiers before this change).
SYSTEM_PROMPT = """You are NikeFilingGPT, NIKE, Inc.'s dedicated expert report generator for its \
Fiscal Year 2023 Form 10-K filing. You are the PRIMARY and ONLY interface a user has to this \
document -- there is no human reviewing your answers before the user sees them, so you must \
enforce your own constraints.

WHAT YOU CAN DO:
- Answer questions using ONLY the information present in the "RETRIEVED CONTEXT" section of the
  user message for this turn.
- Cite the specific page and quote the specific text that supports each claim you make.
- Explicitly say when you cannot answer, instead of guessing or approximating.

WHAT YOU CANNOT DO (no exceptions, even if you are confident you know the answer from your own
training):
- You cannot use outside knowledge, general world knowledge, or anything about NIKE, its
  competitors, or any other topic that is not explicitly present in the retrieved context given
  to you this turn.
- You cannot discuss, compare against, or speculate about any company other than NIKE, Inc.
- You cannot discuss NIKE information from any fiscal year, filing, or time period other than
  what appears in the retrieved context (do not assume other years look similar).
- You cannot answer general-knowledge, current-events, personal, creative, or any other question
  that is not a factual question about NIKE's FY2023 10-K filing. This system has exactly one
  purpose; anything else is out of domain.
- You cannot pad, hedge, or partially answer when the context does not fully support an answer.

TWO SITUATIONS WHERE YOU MUST REFUSE (set "insufficient_context": true, "confidence" <= 0.2, and
"citations": []; the "answer" field must plainly state that the filing does not contain the
requested information -- do not answer the question, even partially, even if you happen to know
the answer):

  1. RETRIEVED CONTEXT LACKS SUBSTANCE: the retrieval step always returns the top-k nearest
     chunks by embedding similarity, even when none of them are actually relevant to the
     question -- similarity search never returns "nothing," it returns "the least-bad match."
     Each context block below is labeled with a cosine similarity score. Read the context
     blocks and judge for yourself whether they actually contain the specific fact needed to
     answer -- a high similarity score does NOT guarantee the content answers the question, and
     a low similarity score is a signal (not a guarantee) that it does not.
     Example: retrieved context is about NIKE's distribution centers, but the question asks
     about executive compensation -> the context has no substance relevant to the question ->
     refuse.

  2. QUESTION IS OUTSIDE THIS SYSTEM'S DOMAIN: if the user's question is not a factual question
     about NIKE's FY2023 10-K filing -- including questions about other companies, other fiscal
     years, current events, or general knowledge -- refuse immediately regardless of what the
     retrieved context contains, because retrieval will still return NIKE chunks (it always
     returns its k nearest matches) even though they cannot possibly answer an out-of-domain
     question.
     Example: "What was Adidas's revenue in fiscal 2023?" -> Adidas is not NIKE -> out of
     domain -> refuse, even if the retrieved context happens to contain NIKE revenue figures
     that look superficially similar.
     Example: "What is the capital of France?" -> not a NIKE 10-K question at all -> refuse.

OUTPUT CONTRACT: Respond with a single JSON object and NOTHING else -- no preamble, no markdown,
no explanation outside the JSON -- matching exactly this shape:
{
  "answer": "<answer in 1-3 sentences based only on the retrieved context, or a plain refusal
    statement per the rules above>",
  "citations": [{"page": <page number from a context block label>, "quote": "<short verbatim
    quote copied from that context block>"}],
  "confidence": <0.0 to 1.0>,
  "insufficient_context": <true if you are refusing per either rule above, else false>
}
"""

# Sent once per call as the human message: the retrieved context and the
# question, in clearly labeled, structurally distinct sections. The context
# is data to be evaluated, not an instruction -- keeping it out of the system
# message (and out of the same paragraph as the question) is what lets the
# model's own judgment ("does this context actually answer this question?")
# happen instead of pattern-matching "I was given context, so I should use it."
USER_PROMPT_TEMPLATE = """### RETRIEVED CONTEXT
Each block below is one of the top-{k} chunks retrieved from NIKE's FY2023 10-K by embedding \
similarity to the question. The cosine similarity score (higher = more similar, range -1 to 1) \
is shown for each block -- use it as a signal, not a rule, when judging relevance.

{context}

### USER QUESTION
{question}
"""


def format_context(docs_with_scores: list[tuple[Document, float]]) -> str:
    return "\n\n".join(
        f"[page {doc.metadata['page']}, relevance score {score:.4f}]\n{doc.page_content}"
        for doc, score in docs_with_scores
    )


# Second, independent LLM call: given the SAME context and question plus the
# first call's proposed answer, judge two things -- does the answer actually
# respond to the specific question (not a different, unrelated fact that
# happens to be real and grounded), and is it genuinely supported by its
# citations (or, if there are none, is that actually appropriate). This
# exists because prompt instructions alone are not reliably obeyed by a
# 1.5B model (measured: refusal_rate was still only 0.5 with a well-
# structured system prompt) -- a second, narrowly-scoped pass catches cases
# the first pass's own judgment missed, e.g. answering "How many
# distribution centers does Amazon operate?" with NIKE's own distribution
# center count, or answering with zero citations at all.
#
# On REJECT, answer_question retries generation ONCE with the rejection
# reason fed back to the model (see MAX_ATTEMPTS) before falling back to a
# deterministic, code-built refusal. An unconditional "zero citations ->
# discard" rule was tried first and measured to be too blunt: it overrode
# 100% of otherwise-correct in-scope answers, because this model frequently
# omits citations even when its answer content is right (see tracker.txt,
# Run D). Giving the model one concrete chance to correct itself, with the
# specific reason it failed, is what "a loop on itself to confirm" means in
# practice -- not a single silent discard.
VERIFY_SYSTEM_PROMPT = """You are a strict, independent verifier reviewing another AI's answer before it \
reaches the user. You did not write the proposed answer and have no stake in it being correct.

You will be given the retrieved context, the original question, and a proposed answer with its \
citations. Check exactly three things:

1. RESPONSIVE: does the proposed answer address the SPECIFIC question asked -- not a different \
company, different fact, or different time period, even if that other fact is real and appears \
in the context. An answer about NIKE when the question asked about a different company is NOT \
responsive, even if the NIKE fact is accurate and well-cited.
2. SUPPORTED: for each citation, does the quoted text genuinely appear in the context block for \
that page, and does it actually support the claim being made (not just share a topic or number)?
3. CITED: if the answer is not a refusal (it makes a substantive claim), does it provide at \
least one citation? A substantive claim with zero citations must be rejected -- it cannot be \
verified regardless of whether the claim happens to be true.

If any of the three checks fails, the answer must be rejected. Respond with EXACTLY one word,
nothing else:
VERIFIED  (all three checks pass)
REJECT    (any check fails)
"""

VERIFY_USER_TEMPLATE = """### RETRIEVED CONTEXT
{context}

### ORIGINAL QUESTION
{question}

### PROPOSED ANSWER TO VERIFY
{proposed_answer}

### CITATIONS IN THE PROPOSED ANSWER
{citations}
"""

# Appended to the user prompt on a retry attempt, after the first attempt's
# answer was rejected. Feeds the specific rejection reason back so the model
# has a real chance to fix it, rather than being silently discarded.
RETRY_SUFFIX_TEMPLATE = """

### YOUR PREVIOUS ATTEMPT WAS REJECTED
{previous_raw}

Reason: {reason}

Provide a corrected response. If you cannot find a specific passage in the RETRIEVED CONTEXT \
above that directly and specifically answers the QUESTION, you must set "insufficient_context": \
true, "confidence" no higher than 0.2, and "citations": []. Otherwise, answer again and cite the \
exact page and a verbatim quote that supports your answer. Respond with a single JSON object \
only, matching the same schema as before."""

# Deterministic fallback used only after MAX_ATTEMPTS is exhausted and the
# answer is still rejected. Built in code, not re-requested from the model,
# so a model that has already failed twice doesn't get a third chance to
# fail the same way while formatting its own override.
SELF_CHECK_OVERRIDE_ANSWER = (
    "The retrieved context does not contain information that directly answers this question."
)

MAX_ATTEMPTS = 2  # original generation + one feedback-guided retry


def format_citations(citations: list) -> str:
    if not citations:
        return "(none provided)"
    return "\n".join(f'- page {c.page}: "{c.quote}"' for c in citations)


def verify_answer(
    question: str,
    docs_with_scores: list[tuple[Document, float]],
    answer: RAGAnswer,
    model: str = DEFAULT_LLM_MODEL,
) -> str:
    """Self-check pass. Returns 'VERIFIED', 'REJECT', or 'ambiguous:<raw text>'."""
    llm = ChatOllama(model=model, temperature=0)
    user_prompt = VERIFY_USER_TEMPLATE.format(
        context=format_context(docs_with_scores),
        question=question,
        proposed_answer=answer.answer,
        citations=format_citations(answer.citations),
    )
    messages = [SystemMessage(content=VERIFY_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
    raw = llm.invoke(messages).content.strip()
    verdict = raw.upper()
    if "REJECT" in verdict:
        return "REJECT"
    if "VERIFIED" in verdict:
        return "VERIFIED"
    return f"ambiguous:{raw[:100]}"


def call_llm(
    question: str,
    docs_with_scores: list[tuple[Document, float]],
    model: str = DEFAULT_LLM_MODEL,
    constrained: bool = True,
    retry_context: dict | None = None,
) -> str:
    """Send the RAG prompt to the chat model and return its raw text output.

    The system message (persona/capabilities/constraints/output contract) and
    the human message (context/question) are sent as two distinct messages,
    not concatenated into one string -- see SYSTEM_PROMPT's docstring-comment
    above for why that separation matters. If retry_context is given (a dict
    with "previous_raw" and "reason"), the rejection feedback is appended to
    the same human message rather than opened as a new conversation turn.
    """
    llm = ChatOllama(
        model=model,
        temperature=0,
        format=RAGAnswer.model_json_schema() if constrained else None,
    )
    user_prompt = USER_PROMPT_TEMPLATE.format(
        k=len(docs_with_scores),
        context=format_context(docs_with_scores),
        question=question,
    )
    if retry_context:
        user_prompt += RETRY_SUFFIX_TEMPLATE.format(**retry_context)
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
    return llm.invoke(messages).content


def answer_question(
    question: str,
    store: InMemoryVectorStore,
    k: int = 4,
    model: str = DEFAULT_LLM_MODEL,
    constrained: bool = True,
    save: bool = True,
    self_check: bool = True,
) -> dict:
    """Run the full pipeline for one question and return the saved record.

    The record always contains the raw LLM output of the LAST attempt. If
    validation fails on the final attempt, the record has status
    'schema_error' instead of a validated answer, so failed generations are
    kept as evidence rather than silently dropped.

    If self_check=True (default) and the model produced a schema-valid
    answer that claims sufficient context (insufficient_context=False), it
    is checked by verify_answer for two things: is it actually responsive to
    the question (not a different, real, but off-topic fact), and is it
    genuinely supported by citations (an answer with zero citations always
    fails this). On REJECT, if attempts remain (MAX_ATTEMPTS), the model
    gets ONE retry with the specific rejection reason fed back to it. Only
    after retries are exhausted does the pipeline fall back to a
    deterministic, code-built refusal (SELF_CHECK_OVERRIDE_ANSWER) -- the
    model is never silently discarded on the first rejection.
    """
    docs_with_scores = store.similarity_search_with_score(question, k=k)
    docs = [doc for doc, _score in docs_with_scores]

    attempts = []
    retry_context = None
    answer = None
    schema_error = None

    for attempt_num in range(1, MAX_ATTEMPTS + 1):
        t0 = time.perf_counter()
        raw = call_llm(
            question, docs_with_scores, model=model, constrained=constrained,
            retry_context=retry_context,
        )
        llm_seconds = round(time.perf_counter() - t0, 2)
        attempt_record = {"attempt": attempt_num, "raw_output": raw, "llm_seconds": llm_seconds}

        try:
            answer = parse_llm_output(raw)
            schema_error = None
        except SchemaValidationError as exc:
            answer = None
            schema_error = str(exc)
            attempt_record["schema_error"] = schema_error
            attempts.append(attempt_record)
            if attempt_num < MAX_ATTEMPTS:
                retry_context = {
                    "previous_raw": raw,
                    "reason": f"output did not match the required JSON schema: {schema_error}",
                }
                continue
            break

        verdict, reason = None, None
        if self_check and not answer.insufficient_context:
            if not answer.citations:
                verdict = "REJECT"
                reason = (
                    'insufficient_context was false but citations was empty -- a substantive '
                    "claim must cite at least one specific page and quote, or set "
                    "insufficient_context to true."
                )
            else:
                t1 = time.perf_counter()
                verdict = verify_answer(question, docs_with_scores, answer, model=model)
                attempt_record["self_check_seconds"] = round(time.perf_counter() - t1, 2)
                if verdict == "REJECT":
                    reason = (
                        "an independent verifier judged this answer either not responsive to "
                        "the specific question asked, or not genuinely supported by its citations."
                    )
        attempt_record["verdict"] = verdict
        attempts.append(attempt_record)

        if verdict == "REJECT" and attempt_num < MAX_ATTEMPTS:
            retry_context = {"previous_raw": raw, "reason": reason}
            continue
        break  # success (verdict in {None, "VERIFIED"} or a rejected/ambiguous final attempt)

    final_attempt = attempts[-1]
    overridden = final_attempt.get("verdict") == "REJECT"
    if overridden:
        answer = RAGAnswer(
            answer=SELF_CHECK_OVERRIDE_ANSWER,
            citations=[],
            confidence=0.1,
            insufficient_context=True,
        )

    record = {
        "question": question,
        "model": model,
        "constrained": constrained,
        "retrieved_pages": [doc.metadata["page"] for doc in docs],
        "num_attempts": len(attempts),
        "attempts": attempts,
        "llm_seconds": round(sum(a["llm_seconds"] for a in attempts), 2),
        "raw_output": final_attempt["raw_output"],
        "self_check": {
            "ran": any(a.get("verdict") is not None for a in attempts),
            "verdict": final_attempt.get("verdict"),
            "overridden": overridden,
            "retried": len(attempts) > 1,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if answer is not None:
        record["status"] = "ok"
        record["validated"] = answer.model_dump()
        record["grounding"] = grounding_report(answer, docs)
    else:
        record["status"] = "schema_error"
        record["error"] = schema_error

    if save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = RESULTS_DIR / f"answer-{stamp}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        record["saved_to"] = str(out_path)
    return record


def main() -> None:
    load_dotenv()
    pdf_path = Path(__file__).parent / "data" / "nke-10k-2023.pdf"
    chunks = get_chunks(load_pdf_pages(str(pdf_path)))
    print(f"Indexing {len(chunks)} chunks with qwen3-embedding:0.6b...")
    store = build_vector_store(get_qwen_embed(), chunks)

    with open(Path(__file__).parent / "data" / "eval_dataset.json", encoding="utf-8") as f:
        questions = [q["question"] for q in json.load(f)["questions"][:3]]

    for question in questions:
        print("=========================")
        print(f"Q: {question}")
        record = answer_question(question, store)
        if record["status"] == "ok":
            print(f"A: {record['validated']['answer']}")
            print(f"   confidence={record['validated']['confidence']}")
            print(f"   grounded={record['grounding']['grounded']}")
            if not record["grounding"]["grounded"]:
                for issues in record["grounding"]["checks"].values():
                    for issue in issues:
                        print(f"   ISSUE: {issue}")
        else:
            print(f"SCHEMA ERROR: {record['error']}")
        print(f"   saved to {record.get('saved_to', '(not saved)')}")


if __name__ == "__main__":
    main()
