import json
import requests
import asyncio
from typing import Any
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions, AssistantMessage, ResultMessage

@tool(
    name="search_flights",
    description = "Search for flights using SerpApi. Input should be a json string with 'origin', 'destination' and 'date' fields.",
    input_scheme = {
        "type": "object",
        "properties": {
            "departue_id": {"type": "string", "description": "IATA code of the departue"},
            "arrival_id": {"type": "string", "description": "IATA code of the arrival airport"},
            "type": {"type": "number", "description": "Type of fight search: 1 for round trip (default), 2 for one way"},
            "outbound_date": {"type": "string", "description": "departue date in YYYY-MM=DD format"},
            "return_date": {"type": "string", "description": "Departure date in YYYY-MM-DD format (required if type is 1)"}
        },
        "required": ["departue_id", "arrival_id", "type", "outbound_date"],
    },
)
async def search_flights(arg: dict[str,Any]) -> dict[str,Any]:
    try:
        departure_id = args["departure_id "]