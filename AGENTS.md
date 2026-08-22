# Graphtyn agent policy

Use Graphtyn before broad repository exploration when a task asks for implementation, debugging, architectural tracing, persistence analysis, test selection, or change-impact assessment.

## Default workflow

1. Call `graph_query_intent` with the user's complete task. It uses the MCP server's configured workspace and does not accept `path`; the CLI equivalent `graphtyn query-intent` accepts `--path`.
2. Select `overview`, `flow`, `impact`, `persistence`, `bindings`, or `tests`; use `auto` only when no intent is evident. Use `overview` for repository purpose, technologies, entry points, subsystems, or architecture summaries.
3. Start with the MCP's compact default budget of 10 entities.
4. Verify the returned symbols and `file:line` locations in source. Source code remains authoritative.
5. Read only the selected files and ranges. Do not scan whole directories or load `index.json` unless the graph identifies a concrete evidence gap.
6. Preserve `context_id`. Expand with `extends_context_id` only for a named missing fact; stop when `do_not_expand` is true or `complete_for` covers the task.

Interpret confidence strictly: `EXTRACTED` is structural evidence, `INFERRED` requires source verification, and `AMBIGUOUS` must not be stated as fact. A nearby node or shared subsystem is not a consumer without a directed incoming relation.

For references such as “ese cambio” or “lo que me dijiste”, recover the concrete proposal from recent conversation and include it in the Graphtyn request. Ask for clarification only if it cannot be recovered unambiguously.

For web applications, trace `frontend → route → controller → validation → persistence → event/listener`, omitting stages that lack evidence. For an authorized code change, query before editing and perform a final `impact` check when consumers may be affected.

For `overview`, structure the answer from `project_profile`, `architecture`, `representative_flows`, and `risk_signals`; read only `read_first` plus necessary returned entry points. Verify purpose from documentation or code. If a persistent artifact is requested, generate `GRAPHTYN_REPORT.md` with `graphtyn report`.

Before publishing important architectural or impact claims, save the draft and run `graphtyn validate-answer --answer @draft.md --path .`. Before risky edits run `graphtyn impact --base HEAD --head HEAD --path .`; use its `GRAPHTYN_CHANGE_REPORT.md` verification plan after editing. Inspect unresolved candidates with `graphtyn review --ambiguities --path .`, and record an accept/reject/correct decision only after checking source.

Report the resulting flow or impact, affected symbols, direct consumers, side effects, tests, evidence locations, and any unresolved ambiguity. Keep the response compact and do not paste the full graph.
