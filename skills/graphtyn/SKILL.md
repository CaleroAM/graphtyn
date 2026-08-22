---
name: graphtyn
description: Use Graphtyn to select compact, evidence-backed repository context for project overviews, impact analysis, execution flows, bindings, persistence, and tests before broad code exploration. Apply when the user names Graphtyn or asks about repository purpose, architecture, dependencies, or change impact; do not use it for requests unrelated to a code repository.
---

# Graphtyn

Use Graphtyn as a context selector. Treat source code as the final authority.

## Query

Call `graph_query_intent` before reading directories or many files. It queries the workspace configured when the MCP server started, so do not invent a `path` argument. Use the user's complete request, including the concrete change recovered from recent conversation context. When using the CLI instead, pass `--path` if the target is not the current directory.

Choose the narrowest intent:

- `overview`: explain repository purpose, technologies, entry points, subsystems, and architecture.
- `flow`: trace runtime or user behavior end to end.
- `impact`: assess consequences of a proposed change.
- `persistence`: find writes, models, transactions, and events.
- `bindings`: resolve routes, contracts, interfaces, and implementations.
- `tests`: find coverage and regression targets.
- `auto`: only when the request does not make the intent clear.

Start with `limit: 10`, the MCP's compact default. Prefer a single call. Preserve `context_id`; if evidence is genuinely missing, expand with `extends_context_id` so only new context is returned. Do not expand when `do_not_expand` is true or `complete_for` covers the task.

## Interpret evidence

- Treat `EXTRACTED` as structural evidence.
- Treat `INFERRED` as a lead to verify in source.
- Never present `AMBIGUOUS` as confirmed; verify it or report the ambiguity.
- Use directed edges to identify callers and consumers. Proximity or membership in the same subsystem does not prove consumption.
- Read only the returned files and relevant line ranges unless a specific gap requires more.

For web flows, prefer the directed chain `frontend → route → controller → validation → persistence → event/listener`. Do not invent a missing stage.

For `overview`, use `project_profile`, `architecture`, `representative_flows`, and `risk_signals` as the outline. Inspect only `read_first` documents plus returned entry points needed to verify purpose. Explain purpose, technologies/frameworks, entry points, subsystems, representative flows, risks, and uncertainty; do not infer product behavior from directory names alone. When the user requests a persistent artifact, run `graphtyn report --path <project> --output GRAPHTYN_REPORT.md`.

## Conversational references

Resolve phrases such as “ese cambio”, “lo anterior” or “el cambio que propusiste” from the recent conversation. Include the resolved change explicitly in `request`. Ask one concise clarification only when multiple plausible changes remain or the referenced change is absent; never invent it.

## Act and report

For analysis or diagnosis, report evidence before proposing action. For authorized implementation, use the graph to scope the edit, verify the returned source, implement, run relevant tests, and use `impact` again when the change could affect consumers.

For a Git-aware implementation, run `graphtyn impact --base HEAD --head HEAD --path <project>` and follow `GRAPHTYN_CHANGE_REPORT.md`. Use `graphtyn review --staged` for the exact staged set. If the graph reports ambiguous relations, list them with `graphtyn review --ambiguities`; record accept/reject/correct only after source verification. For high-impact answers, run `graphtyn validate-answer --answer @draft.md` and fix unsupported claims before publishing.

Summarize:

- the selected flow or impact;
- affected symbols and `file:line` evidence;
- direct consumers and side effects;
- tests to run or add;
- unresolved inferred or ambiguous relationships.

Do not dump the full graph, `index.json`, or entire source files into context.
