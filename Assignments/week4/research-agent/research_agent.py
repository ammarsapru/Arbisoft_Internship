"""
Week 4 assignment - Research Agent.

Covers:
  1. Web-search skill (SerpApi)          -> web_search tool
  2. Session memory (recalls facts)      -> remember_fact / recall_facts tools
                                            (+ ClaudeSDKClient multi-turn context)
  3. Hook logging every tool call        -> log_tool_call (Pre/PostToolUse), tool_calls.log
  4. File-read plugin (.txt / .pdf)      -> read_file tool (pypdf for PDFs)

All tools are registered as an in-process MCP server via the Claude Agent SDK,
so no external MCP process is needed.
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
# Use the Claude Code CLI login for the agent itself (the .env API key would
# override it and switch billing); only SERP_API_KEY is needed from .env.
os.environ.pop("ANTHROPIC_API_KEY", None)

SERP_API_KEY = os.environ.get("SERP_API_KEY")


# --------------------------------------------------------------------------
# Skill 1: web search via SerpApi
# --------------------------------------------------------------------------
@tool(
    "web_search",
    "Search the web (Google via SerpApi). Use for current events, facts, or "
    "anything not in your training data. Returns titles, links and snippets.",
    {"query": str},
)
async def web_search(args):
    if not SERP_API_KEY:
        return {
            "content": [{"type": "text", "text": "Error: SERP_API_KEY is not set."}],
            "is_error": True,
        }
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": args["query"], "api_key": SERP_API_KEY, "num": 5},
        timeout=30,
    )
    if resp.status_code != 200:
        return {
            "content": [{"type": "text", "text": f"SerpApi error {resp.status_code}: {resp.text[:300]}"}],
            "is_error": True,
        }
    data = resp.json()
    results = data.get("organic_results", [])[:5]
    if not results:
        answer_box = data.get("answer_box", {})
        if answer_box:
            return {"content": [{"type": "text", "text": f"Answer box: {json.dumps(answer_box)[:800]}"}]}
        return {"content": [{"type": "text", "text": "No results found."}]}
    lines = []
    for r in results:
        lines.append(f"- {r.get('title', '?')}\n  {r.get('link', '')}\n  {r.get('snippet', '')}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# --------------------------------------------------------------------------
# Skill 2: file-read plugin (.txt / .md / .pdf)
# --------------------------------------------------------------------------
@tool(
    "read_file",
    "Read a local text (.txt/.md) or PDF (.pdf) file and return its contents. "
    "Relative paths are resolved against the research-agent directory.",
    {"path": str},
)
async def read_file(args):
    path = pathlib.Path(args["path"])
    if not path.is_absolute():
        path = HERE / path
    if not path.exists():
        return {
            "content": [{"type": "text", "text": f"Error: file not found: {path}"}],
            "is_error": True,
        }
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
    if not text.strip():
        text = "(file contained no extractable text)"
    return {"content": [{"type": "text", "text": text[:8000]}]}


# --------------------------------------------------------------------------
# Skill 3: key-value session memory
# --------------------------------------------------------------------------
MEMORY: dict[str, str] = {}


@tool(
    "remember_fact",
    "Store a fact in session memory under a short key so it can be recalled later.",
    {"key": str, "value": str},
)
async def remember_fact(args):
    MEMORY[args["key"]] = args["value"]
    return {"content": [{"type": "text", "text": f"Remembered '{args['key']}' = '{args['value']}'"}]}


@tool(
    "recall_facts",
    "Recall all facts previously stored in session memory.",
    {},
)
async def recall_facts(args):
    if not MEMORY:
        return {"content": [{"type": "text", "text": "Memory is empty."}]}
    lines = [f"- {k}: {v}" for k, v in MEMORY.items()]
    return {"content": [{"type": "text", "text": "Facts in memory:\n" + "\n".join(lines)}]}


# --------------------------------------------------------------------------
# Hook: log every tool call with a timestamp
# --------------------------------------------------------------------------
async def log_tool_call(input_data, tool_use_id, context):
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    event = input_data.get("hook_event_name", "?")
    tool_name = input_data.get("tool_name", "?")
    tool_input = json.dumps(input_data.get("tool_input", {}), default=str)[:300]
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {event:<12} | tool={tool_name} | input={tool_input}\n")
    return {}  # empty output = allow the call to proceed unchanged


# --------------------------------------------------------------------------
# Wiring: in-process MCP server + agent options
# --------------------------------------------------------------------------
research_server = create_sdk_mcp_server(
    name="research",
    version="1.0.0",
    tools=[web_search, read_file, remember_fact, recall_facts],
)

SYSTEM_PROMPT = (
    "You are a research agent. You have these skills:\n"
    "- web_search: search the web for current information (always cite links)\n"
    "- read_file: read local .txt/.md/.pdf files\n"
    "- remember_fact / recall_facts: session key-value memory\n"
    "When you learn an important fact (from a file or a search) that later steps "
    "might need, store it with remember_fact. When answering follow-up questions, "
    "check recall_facts before searching again. Answer concisely and cite sources."
)


def build_options(**overrides) -> ClaudeAgentOptions:
    """Agent configuration shared by the demo and any future scripts."""
    defaults = dict(
        system_prompt=SYSTEM_PROMPT,
        model="sonnet",  # cheaper than the default model, plenty for this task
        mcp_servers={"research": research_server},
        allowed_tools=[
            "mcp__research__web_search",
            "mcp__research__read_file",
            "mcp__research__remember_fact",
            "mcp__research__recall_facts",
        ],
        hooks={
            "PreToolUse": [HookMatcher(hooks=[log_tool_call])],
            "PostToolUse": [HookMatcher(hooks=[log_tool_call])],
        },
        max_turns=15,
    )
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)
