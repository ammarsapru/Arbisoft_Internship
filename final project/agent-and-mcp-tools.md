# Internal agent and MCP tool inventory

## Current totals

| Surface | Callable tools | Additional capabilities |
|---|---:|---|
| Ask repository agent | 18 | Conversation memory and deterministic citation validation. |
| Onboarding route agent | 18 | Replaces final answer submission with tour submission. |
| Contribution mission agent | 18 | Replaces final answer submission with mission submission. |
| Issue investigation agent | 18 | Replaces final answer submission with findings submission. |
| Assessment model call | 1 | Dedicated `submit_assessment` schema, separate from the main loop. |
| MCP server | 17 | Two MCP resources and one MCP prompt in addition to tools. |

“18 tools” does not mean four unrelated sets of 18. The workflows share the same 17
investigation tools and each adds one workflow-specific final-submission tool.

## The 17 shared internal investigation tools

### Discovery and direct retrieval — 7

1. `list_repository_tree`
2. `search_repository`
3. `find_symbols`
4. `get_index_status`
5. `read_source`
6. `inspect_symbol`
7. `expand_graph`

### Semantic and architectural tools — 10

8. `get_repository_overview`
9. `get_feature_evidence`
10. `find_entry_points`
11. `get_backend_architecture`
12. `get_file_structure`
13. `get_symbol_relationships`
14. `find_related_tests`
15. `get_dependency_impact`
16. `get_project_configuration`
17. `get_analysis_diagnostics`

### Workflow-specific submission tool — 1

- Ask: `submit_answer`
- Onboarding: `submit_onboarding_tour`
- Mission: `submit_contribution_mission`
- Issues: `submit_issue_findings`

These tools are Python JSON-schema dictionaries, not a `SKILL.md`. They are defined in
`backend/app/agent/service.py:82-345`. `_execute_tool` at lines 395-479 dispatches the
selected action to the immutable index or semantic graph service. Onboarding and issue
modules derive their registries by replacing `submit_answer`.

With the Anthropic API, `tools=TOOLS` is sent directly to the Messages API. With Claude
Code, native Claude Code tools and skills are disabled; the same schemas are supplied as
the allowed Waypoint actions and the SDK output schema restricts action names.

## The 17 MCP server tools

### Repository acquisition and analysis — 2

1. `analyze_local_repository`
2. `clone_and_analyze_github_repository`

### Retrieval and graph exploration — 6

3. `list_repository_tree`
4. `search_repository`
5. `find_symbols`
6. `read_source`
7. `inspect_symbol`
8. `expand_graph`

### Semantic architecture — 6

9. `get_repository_overview`
10. `find_entry_points`
11. `get_backend_architecture`
12. `get_symbol_relationships`
13. `find_related_tests`
14. `get_dependency_impact`

### Index administration — 2

15. `get_index_status`
16. `rebuild_index`

### Optional full agent — 1

17. `ask_repository`

The MCP surface intentionally differs from the internal agent registry. MCP includes
repository acquisition and index rebuilding, but currently does not expose internal
`get_feature_evidence`, `get_file_structure`, `get_project_configuration`, or
`get_analysis_diagnostics` as standalone MCP tools.

## MCP capabilities that are not tools

- Resource: `waypoint://analyses/{analysis_id}/summary`
- Resource: `waypoint://analyses/{analysis_id}/index`
- Prompt: `explain_repository`

Resources are read-only addressable context and prompts are reusable prompt templates;
neither contributes to the 17-tool count.

## Related implementation

- `backend/app/agent/service.py:82-345` — internal tool schemas.
- `backend/app/agent/onboarding.py:58-213` — tour, mission, and assessment schemas.
- `backend/app/agent/issues.py:45-105` — issue findings schema and registry.
- `backend/app/mcp_server.py:74-280` — 17 tools, two resources, and one prompt.

