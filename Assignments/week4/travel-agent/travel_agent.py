"""
Flight Research Agent - core definition.

Skills (in-process MCP server "travel"):
  - search_flights : SerpApi Google Flights engine (structured results,
                     supports budget / one-way / round-trip constraints)
  - search_hotels  : SerpApi Google Hotels engine (per-night budget constraint)
  - read_file      : ingest .txt/.md/.pdf travel plans
  - remember_fact / recall_facts : session key-value memory

Hook:
  - log_tool_call  : logs every tool call (Pre + Post) with timestamps
                     to tool_calls.log

The user's inputs (budget, start/end locations and dates, trip type) are
CONSTRAINTS: the system prompt instructs the agent to pass them into the
tool parameters (max_price, trip_type, dates) rather than filtering by eye,
and to ask the user about anything ambiguous before searching.
"""

import datetime
import json
import os
import pathlib

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    create_sdk_mcp_server,
    tool,
)

HERE = pathlib.Path(__file__).parent
LOG_FILE = HERE / "tool_calls.log"

# SERP_API_KEY lives in first-agent/.env
load_dotenv(HERE.parent / "first-agent" / ".env")
# Agent auth comes from the Claude Code CLI login; the .env Anthropic key
# would override it and switch billing, so drop it.
os.environ.pop("ANTHROPIC_API_KEY", None)

SERP_API_KEY = os.environ.get("SERP_API_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"


def _serpapi(params: dict) -> dict | None:
    """Call SerpApi; return parsed JSON or None on failure."""
    if not SERP_API_KEY:
        return None
    resp = requests.get(
        SERPAPI_URL, params={**params, "api_key": SERP_API_KEY}, timeout=45
    )
    if resp.status_code != 200:
        return {"__error__": f"SerpApi HTTP {resp.status_code}: {resp.text[:300]}"}
    return resp.json()


# --------------------------------------------------------------------------
# Skill 1: flight search (Google Flights engine) - constraint-aware
# --------------------------------------------------------------------------
@tool(
    "search_flights",
    "Search real flights via Google Flights. Use IATA airport codes "
    "(e.g. LHE, DXB, CDG). Pass the user's budget as max_price_usd so results "
    "are pre-filtered. trip_type 'one_way' needs no return_date; 'round_trip' "
    "requires return_date.",
    {
        "type": "object",
        "properties": {
            "departure_id": {"type": "string", "description": "IATA code of departure airport, e.g. LHE"},
            "arrival_id": {"type": "string", "description": "IATA code of arrival airport, e.g. IST"},
            "outbound_date": {"type": "string", "description": "Departure date YYYY-MM-DD"},
            "trip_type": {"type": "string", "enum": ["round_trip", "one_way"], "description": "Trip type"},
            "return_date": {"type": "string", "description": "Return date YYYY-MM-DD (required for round_trip)"},
            "max_price_usd": {"type": "number", "description": "Optional budget cap in USD for this flight"},
        },
        "required": ["departure_id", "arrival_id", "outbound_date", "trip_type"],
    },
)
async def search_flights(args):
    trip_type = args["trip_type"]
    params = {
        "engine": "google_flights",
        "departure_id": args["departure_id"].upper(),
        "arrival_id": args["arrival_id"].upper(),
        "outbound_date": args["outbound_date"],
        "type": 1 if trip_type == "round_trip" else 2,
        "currency": "USD",
        "hl": "en",
    }
    if trip_type == "round_trip":
        if not args.get("return_date"):
            return {
                "content": [{"type": "text", "text": "Error: round_trip requires return_date."}],
                "is_error": True,
            }
        params["return_date"] = args["return_date"]
    if args.get("max_price_usd"):
        params["max_price"] = int(args["max_price_usd"])

    data = _serpapi(params)
    if data is None:
        return {"content": [{"type": "text", "text": "Error: SERP_API_KEY not set."}], "is_error": True}
    if "__error__" in data:
        return {"content": [{"type": "text", "text": data["__error__"]}], "is_error": True}
    if data.get("error"):
        return {"content": [{"type": "text", "text": f"Google Flights error: {data['error']}"}], "is_error": True}

    options = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    if not options:
        return {"content": [{"type": "text", "text": "No flights found for these parameters (try nearby dates or airports)."}]}

    lines = []
    for opt in options[:5]:
        legs = opt.get("flights", [])
        if not legs:
            continue
        first, last = legs[0], legs[-1]
        airlines = " + ".join(sorted({leg.get("airline", "?") for leg in legs}))
        stops = len(legs) - 1
        total_min = opt.get("total_duration", 0)
        lines.append(
            f"- ${opt.get('price', '?')} | {airlines} | "
            f"{'nonstop' if stops == 0 else f'{stops} stop(s)'} | "
            f"{total_min // 60}h{total_min % 60:02d}m | "
            f"dep {first.get('departure_airport', {}).get('time', '?')} "
            f"({first.get('departure_airport', {}).get('id', '?')}) -> "
            f"arr {last.get('arrival_airport', {}).get('time', '?')} "
            f"({last.get('arrival_airport', {}).get('id', '?')})"
        )
    insights = data.get("price_insights", {})
    if insights.get("lowest_price"):
        lines.append(f"(price insight: lowest seen ${insights['lowest_price']}, level: {insights.get('price_level', '?')})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# --------------------------------------------------------------------------
# Skill 2: hotel search (Google Hotels engine) - constraint-aware
# --------------------------------------------------------------------------
@tool(
    "search_hotels",
    "Search real hotels via Google Hotels for a city and date range. Pass the "
    "per-night budget as max_price_per_night_usd so results are pre-filtered.",
    {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City (and country), e.g. 'Istanbul, Turkey'"},
            "check_in_date": {"type": "string", "description": "Check-in YYYY-MM-DD"},
            "check_out_date": {"type": "string", "description": "Check-out YYYY-MM-DD"},
            "max_price_per_night_usd": {"type": "number", "description": "Optional per-night budget cap in USD"},
            "adults": {"type": "integer", "description": "Number of adults (default 1)"},
        },
        "required": ["city", "check_in_date", "check_out_date"],
    },
)
async def search_hotels(args):
    params = {
        "engine": "google_hotels",
        "q": args["city"],
        "check_in_date": args["check_in_date"],
        "check_out_date": args["check_out_date"],
        "adults": args.get("adults", 1),
        "currency": "USD",
        "hl": "en",
    }
    if args.get("max_price_per_night_usd"):
        params["max_price"] = int(args["max_price_per_night_usd"])

    data = _serpapi(params)
    if data is None:
        return {"content": [{"type": "text", "text": "Error: SERP_API_KEY not set."}], "is_error": True}
    if "__error__" in data:
        return {"content": [{"type": "text", "text": data["__error__"]}], "is_error": True}
    if data.get("error"):
        return {"content": [{"type": "text", "text": f"Google Hotels error: {data['error']}"}], "is_error": True}

    props = data.get("properties", [])[:5]
    if not props:
        return {"content": [{"type": "text", "text": "No hotels found for these parameters."}]}
    lines = []
    for p in props:
        rate = (p.get("rate_per_night") or {}).get("lowest", "?")
        lines.append(
            f"- {p.get('name', '?')} | {rate}/night | "
            f"rating {p.get('overall_rating', '?')} ({p.get('reviews', '?')} reviews) | "
            f"{p.get('hotel_class', 'class ?')} | {p.get('link', '')}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# --------------------------------------------------------------------------
# Skill 3: file-read plugin (.txt / .md / .pdf travel plans)
# --------------------------------------------------------------------------
@tool(
    "read_file",
    "Read a local travel-plan file (.txt, .md or .pdf) and return its text. "
    "Relative paths resolve against the travel-agent directory.",
    {"path": str},
)
async def read_file(args):
    path = pathlib.Path(args["path"])
    if not path.is_absolute():
        path = HERE / path
    if not path.exists():
        return {"content": [{"type": "text", "text": f"Error: file not found: {path}"}], "is_error": True}
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix in (".txt", ".md"):
        text = path.read_text(encoding="utf-8")
    else:
        return {
            "content": [{"type": "text", "text": f"Error: unsupported file type '{suffix}' (only .txt, .md, .pdf)"}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": (text.strip() or "(no extractable text)")[:8000]}]}


# --------------------------------------------------------------------------
# Skill 4: session memory
# --------------------------------------------------------------------------
MEMORY: dict[str, str] = {}


@tool("remember_fact", "Store a fact (e.g. a trip constraint or search finding) under a short key.", {"key": str, "value": str})
async def remember_fact(args):
    MEMORY[args["key"]] = args["value"]
    return {"content": [{"type": "text", "text": f"Remembered '{args['key']}' = '{args['value']}'"}]}


@tool("recall_facts", "Recall all facts stored in session memory.", {})
async def recall_facts(args):
    if not MEMORY:
        return {"content": [{"type": "text", "text": "Memory is empty."}]}
    return {"content": [{"type": "text", "text": "Facts in memory:\n" + "\n".join(f"- {k}: {v}" for k, v in MEMORY.items())}]}


# --------------------------------------------------------------------------
# Hook: timestamped log of every tool call
# --------------------------------------------------------------------------
async def log_tool_call(input_data, tool_use_id, context):
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    event = input_data.get("hook_event_name", "?")
    tool_name = input_data.get("tool_name", "?")
    tool_input = json.dumps(input_data.get("tool_input", {}), default=str)[:300]
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {event:<12} | tool={tool_name} | input={tool_input}\n")
    return {}


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------
travel_server = create_sdk_mcp_server(
    name="travel",
    version="1.0.0",
    tools=[search_flights, search_hotels, read_file, remember_fact, recall_facts],
)

SYSTEM_PROMPT = f"""You are a flight & travel research agent. Today's date is {datetime.date.today().isoformat()}.

Required constraints for any research task: total budget (USD), start location,
start date, end location, end date, and trip type (round_trip or one_way).

Workflow:
1. Get constraints - either from a travel-plan file (via read_file) or from the
   user's message. Store each constraint with remember_fact as soon as you
   learn it. Check recall_facts before asking the user to repeat anything.
2. If any REQUIRED constraint is missing, contradictory, or ambiguous (e.g. no
   year on a date, a city with several airports where the choice matters, no
   trip type), ask the user a short clarifying question BEFORE searching.
   Ask everything you need in ONE message.
3. Apply constraints INSIDE the tools: pass max_price_usd / trip_type /
   max_price_per_night_usd / dates as tool parameters - do not fetch
   unconstrained results and filter by eye. Infer IATA codes yourself.
4. Be fast: issue independent searches (flights + hotels, or multiple legs) in
   PARALLEL in a single turn. Do not re-search what memory already answers.
5. For multi-city plans: research every leg (flights between consecutive
   cities, hotel for each stay), respect desired arrival times from the plan,
   and check the combined cost against the total budget.
6. Report concisely: per leg - top flight options with price/airline/times,
   top hotel options with per-night rate; then a total-vs-budget verdict.
   Always state which constraints you applied.
7. Use ONLY the mcp__travel__* tools for searches, file reading and memory.
   Do not call external connector tools (Expedia, etc.) - they are not
   permitted in this harness."""


def build_options(**overrides) -> ClaudeAgentOptions:
    defaults = dict(
        system_prompt=SYSTEM_PROMPT,
        model="sonnet",
        mcp_servers={"travel": travel_server},
        allowed_tools=[
            "mcp__travel__search_flights",
            "mcp__travel__search_hotels",
            "mcp__travel__read_file",
            "mcp__travel__remember_fact",
            "mcp__travel__recall_facts",
        ],
        hooks={
            "PreToolUse": [HookMatcher(hooks=[log_tool_call])],
            "PostToolUse": [HookMatcher(hooks=[log_tool_call])],
        },
        # Block external claude.ai connector tools (Expedia etc.) so the agent
        # doesn't waste turns on them instead of our travel tools.
        disallowed_tools=[
            "mcp__claude_ai_Expedia",
            "mcp__claude_ai_Indeed",
            "mcp__claude_ai_Canva",
        ],
        max_turns=40,
    )
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)
