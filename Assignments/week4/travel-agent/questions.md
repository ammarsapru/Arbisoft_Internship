# CLI Demo Script — Questions to Ask the Agent

Run `python travel_cli.py`, then work through these in order. Each question
is labeled with the capability it demonstrates and what a correct answer
looks like.

## Mode 1 session (travel-plan file)

Choose mode `1`, accept the default `trip_plan.pdf`. The kickoff itself
demonstrates: **file ingestion → constraint extraction → memory writes →
parallel constrained searches → budget verdict**. Then ask:

| # | Ask this | Demonstrates | Correct behavior |
|---|---|---|---|
| 1 | `What constraints are you working with right now, and where did each one come from?` | Memory recall + provenance | Lists budget $3,500, start Lahore, both legs with dates/arrival times — citing the PDF, without re-reading it |
| 2 | `/memory` | Inspect the raw store | CLI prints the MEMORY dict — compare it against the agent's previous answer |
| 3 | `Which leg of the trip is the most expensive to fly, and what share of the total budget do flights take up?` | Multi-hop over remembered results | Compares the three flight legs it already found (no new searches), computes share of $3,500 |
| 4 | `The Istanbul hotel budget feels high. Find options under 80 USD per night instead and tell me how much that saves over the 4 nights.` | Constraint change → re-search with new tool parameter | Calls search_hotels with max_price_per_night_usd=80, computes 4-night saving vs earlier pick |
| 5 | `Does my desired arrival time in Paris still hold with the cheapest flight you found? If not, what's the cheapest flight that meets it?` | Constraint checking (arrival time from the PDF) | Checks arrival <15:00 constraint against stored results; re-searches only if needed |
| 6 | `If I cut the total budget to 2,800 USD, does the plan still work? What would you change first?` | Multi-hop synthesis + judgment | Recomputes totals from memory, proposes cheapest-first substitutions |
| 7 | `/log` | Hook verification | CLI prints the last timestamped tool-call lines — every search above should appear |
| 8 | `Summarize the final recommended itinerary with total cost, one flight and one hotel per leg, with links where you have them.` | Final synthesis | Coherent per-leg plan under budget, built entirely from session state |

## Mode 2 session (manual entry)

Restart the CLI, choose mode `2`, and deliberately **leave the budget blank
and give a date without a year** (e.g. `09-20`). Then:

| # | Ask this | Demonstrates | Correct behavior |
|---|---|---|---|
| 9 | *(nothing — just watch)* | Ambiguity handling | The agent must ask ONE clarifying message (budget? which year?) BEFORE searching |
| 10 | Answer its question, e.g. `Budget is 1500 USD, dates are 2026-09-20 to 2026-09-27` | Constraint intake mid-conversation | It stores the answers and only then runs constrained flight+hotel searches |
| 11 | `Book nothing, but remind me: what did I tell you my budget was?` | Session memory | Answers 1500 USD from memory without any tool call except possibly recall_facts |

## What each feature maps to

- **Web research skill** → every `search_flights` / `search_hotels` call (questions 4, 5, 10)
- **Memory** → questions 1, 2, 3, 6, 11
- **File plugin** → the mode-1 kickoff (PDF) — retry with a `.txt` copy to show both formats
- **Hook** → question 7 (`/log`), and `tool_calls.log` after the session
- **Multi-hop** → questions 3, 5, 6, 8 (each needs ≥2 dependent facts chained)
- **Ambiguity questions** → questions 9–10 (mode 2 with missing budget/year)
