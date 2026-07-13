# Recap (Web-Track Focus): Structured Outputs and Output Validation as Agent Guardrails

## The core idea

An agent that produces free-text output and hopes downstream code (or another agent) can parse it correctly is fragile by construction — the model can phrase the same information a dozen different ways, and "parse the model's prose" is itself an unbounded, error-prone task. **Structured output** means constraining what the model can return to a defined schema (a Pydantic model, a JSON Schema) at generation time, so the output is guaranteed parseable, and **output validation** means checking that structured output against additional constraints (value ranges, cross-field invariants, business rules) that the schema alone can't express, before it's trusted by the rest of the system.

Together these function as a **guardrail**: a boundary the system enforces regardless of what the model actually does, rather than a hope about what the model will do.

## Structured output, mechanically

Modern LLM SDKs support this natively — the model is given a schema and constrained (via tool-use/function-calling under the hood) to only emit output matching it. In LangChain, `.with_structured_output(PydanticModel)` on a chat model does this: the call either returns a validated instance of `PydanticModel` or raises, there is no "hope the model formatted the JSON right" step.

This eliminates an entire class of bugs: no `json.loads` on malformed model output, no regex-extracting a number from a sentence, no silent misinterpretation of "the model said 'about 5%'" as a precise value.

## Validation as a second, independent layer

A schema only enforces *shape* (this field is a string, this field is one of these enum values). It does not enforce *correctness* (is this actually the right company's data, is this ticker really valid, does this number make business sense). That's what explicit validators add:

- **Field-level constraints** (`Field(ge=1, le=5)`, `Literal[...]`, regex patterns) catch out-of-range or malformed individual values.
- **Cross-field validators** (`@model_validator`) catch internally inconsistent objects (a "Down" price movement with a positive value).
- **Semantic/relevance checks** — sometimes a schema-valid object is still wrong in a way no field constraint can express (the news articles are schema-valid `NewsArticle` objects but are actually about a *different* company with a similar name). This class of check often needs its own small, focused LLM call with its own structured output (e.g. `{"is_relevant": bool, "reason": str}`) — guardrails can themselves be implemented as agents.

## Guardrails as first-class outcomes, not exceptions

The most robust pattern (used throughout this project) is to make **validation failure a typed result**, not a thrown exception that unwinds the stack. A `ValidationFailure(stage, reason, raw_payload)` object that gets added to shared state lets the orchestrating agent (the supervisor) *decide* what to do — retry with adjusted instructions, ask the user for disambiguation, or terminate cleanly with an honest explanation — rather than the system crashing opaquely or, worse, silently continuing with bad data.

Discriminated unions extend this idea to *expected* alternate outcomes, not just failures: if "the company isn't publicly listed" is a legitimate, anticipated result (not an error), it deserves its own named variant in the return type (`NotPubliclyListed`) rather than being conflated with a genuine lookup error (`LookupFailed`) or a validation exception. The type system communicates every real branch the caller needs to handle.

## Why this matters most at agent-to-agent boundaries

A single well-behaved agent talking to a human can often get away with looser output — a human reader tolerates minor formatting inconsistency. An agent whose output is consumed by *another agent* (or by deterministic code, like the Excel builder) has no such tolerance: the receiving code needs a guaranteed shape to operate on. This is why every hand-off in this project's supervisor/worker graph is a typed Pydantic object, not a string, and why every worker's return is validated before the supervisor is allowed to route forward.

---

## Our Implementation *(built, tested, and caught a real bug the guardrails were designed to catch)*

The full mechanism (raw/domain schema layering, `Annotated` constrained types, discriminated unions for tool outcomes, `@field_validator`/`@model_validator`, and `.with_structured_output()` at every LLM call producing data) is in `plan.md`'s "Pydantic & LangChain usage strategy" section. Points confirmed by live testing (`reports/TEST_RUN_REPORT.md`):

- **Every worker→supervisor hand-off passes through a validation gate**: schema validation (automatic, via the Pydantic-typed `PipelineState`) plus a semantic relevance check (`agents/supervisor.py`'s `_llm_validate`) before the supervisor routes onward. The post-formatting gate is a deliberate exception — a deterministic file-exists check rather than another LLM call, since by that point there's no further worker to route to and "did a file get written" doesn't need judgment (see `docs/07`).
- **The guardrail architecture caught a real, live case it was designed for**: querying "SpaceX" resolved to a technically-valid, verifiable ticker (`SPCX:NASDAQ` — the deterministic verification step in `resolve_ticker` passed it), but the supervisor's *semantic* validation gate correctly judged that this didn't plausibly correspond to SpaceX and aborted the pipeline rather than generating a report against likely-wrong data. Neither guardrail alone would have caught this: the deterministic check only knows "does this ticker exist," and the semantic check never runs on data that never resolved at all (e.g. a nonexistent company, which aborts even earlier with zero LLM cost).
- **Failure is always a typed value the supervisor/CLI can branch on**: `ValidationFailure` in `PipelineState.validation_failures`, or a discriminated-union outcome like `ResolveTickerResult`'s `NotPubliclyListed`/`LookupFailed` — never a bare exception crossing an agent boundary.
- **The guardrail mechanism itself needed a guardrail**: a live run hit a case where the model's own structured output violated a `max_length` field constraint, raising a raw pydantic `ValidationError` out of `.with_structured_output()` with no built-in recovery. `agents/structured_call.py` now wraps every such call with one retry plus a safe fallback value, so a formatting slip in a self-critique field can't crash the whole pipeline — applying this doc's own philosophy recursively to the validation layer's own reliability.
