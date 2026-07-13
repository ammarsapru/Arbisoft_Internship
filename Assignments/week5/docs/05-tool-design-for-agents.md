# Tool Design for Agents: Clear Names, Narrow Scopes, Good Error Messages

## Tools are documentation-driven, not code-driven

A human developer reads the function body to understand a function. A model calling a tool only ever sees the name, the parameter schema, and the docstring — never the implementation. This inverts normal engineering priorities: the docstring is not an afterthought, it *is* the interface. If the description is ambiguous, the model will misuse the tool no matter how correct the implementation is.

## Naming

Use verb-first, unambiguous names that describe the action and its object: `resolve_ticker`, not `ticker` or `lookup`. Avoid names that could plausibly mean two different things (`get_data` says nothing about *which* data). If two tools are easy to confuse, that's a sign they should either be merged or more sharply distinguished by name (`get_market_snapshot` vs. `get_stock_financials` — both "finance data," but one is market-wide index context and the other is a single company's own numbers; the names alone should make that distinction obvious without reading further).

## Narrow scope over Swiss-army tools

A tool that does one thing well is easier for a model to select correctly than a tool with a `mode` parameter that changes its entire behavior. The tell-tale sign of a too-broad tool is a docstring that starts listing "if X, does A; if Y, does B" — that's usually two tools wearing one name. This project's `resolve_ticker` is a partial exception worth justifying explicitly: it *internally* runs a two-stage lookup (direct Google Finance query, then a web-search fallback), but this stays a single tool because from the calling agent's point of view it is one coherent capability ("give me a company name, get back a ticker or a typed reason why not") — the two stages are an implementation detail of robustness, not two different things the agent is choosing between.

## Inputs: make invalid states unrepresentable

Where a parameter has a finite set of valid values, type it as an enum (`Literal[...]` in Python/Pydantic), not a free string. This project's `get_stock_financials(ticker, window)` takes `window: Literal["1D","5D","1M","6M","YTD","1Y","5Y","MAX"]` rather than an arbitrary string — the model literally cannot pass `"3 years"` because it isn't a legal value, and the JSON Schema surfaced to the model documents the exact allowed set. Compare this to accepting a free-text period and trying to parse it *inside* the tool — that pushes ambiguity into runtime failure instead of catching it at the schema level.

## Outputs: typed and outcome-aware, not just "data or error"

A good tool result tells the caller not just *what happened* but *which of the expected outcomes* happened, so the agent can branch programmatically:

- Bad: return `None` on failure and a dict on success — the caller has to guess why it failed.
- Good: return a discriminated union of named outcomes (`Resolved | Ambiguous | NotPubliclyListed | LookupFailed`), each carrying the specific information relevant to that outcome. `Ambiguous` carries candidates; `NotPubliclyListed` carries a human-readable reason; `LookupFailed` carries enough detail to decide whether a retry is worth it.

## Error messages are for the model, not (only) the human

When a tool call fails validation or hits an external API error, the message that comes back needs to be actionable *by the model on its next attempt* — "invalid window" is worse than "window must be one of 1D, 5D, 1M, 6M, YTD, 1Y, 5Y, MAX; got '3 years'". Every rejected/failed call is effectively a mini-prompt to the model about what to do differently.

---

## Our Implementation *(built and confirmed against live behavior)*

Two worked examples this project builds to demonstrate the above, both in `mcp_server/tools/finance_tools.py`:

1. **`resolve_ticker`** — narrow single-purpose name, internal multi-stage lookup kept invisible to the caller, discriminated-union return type (`ResolveTickerResult`) so the supervisor branches on `.outcome` rather than `None`-checking. Live testing changed the internal staging (web search first for a free-text name, direct verification only when the input is already `TICKER:EXCHANGE`-shaped) but the *external contract* — one tool, one outcome-typed result — never changed, which is exactly the point of hiding the fallback logic inside the tool rather than exposing it as separate steps the caller has to orchestrate.
2. **`get_stock_financials`'s `window` parameter** — closed `Literal["1D","5D","1M","6M","YTD","1Y","5Y","MAX"]` matching exactly what Google Finance supports, confirmed live. The natural-language-to-enum mapping (`agents/period.py`'s `parse_period()`) happens *before* the tool call, at the agent layer — confirmed working in test run 2, where "10 years" correctly mapped to `MAX` with a caveat that then appeared verbatim in the generated Excel report and executive summary, rather than being silently dropped.
3. **A third example that emerged from testing, not planning**: `agents/structured_call.py`'s retry-then-fallback wrapper is itself a tool/call-design lesson — the supervisor's own `reason` field violated its `max_length` constraint in a live run (a pydantic `ValidationError`, not an API error), which is the same "actionable failure, not a crash" principle applied to a *model's own structured-output call* rather than an external API call.

Every tool's docstring in `src/fin_analyst/mcp_server/tools/` states: what it does, what each parameter means (including the full enum where relevant), and what each possible outcome/failure mode means — written to be read by a model, not just a human maintainer.
