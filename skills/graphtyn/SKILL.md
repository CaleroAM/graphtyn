---
name: graphtyn
description: Use Graphtyn to select compact, evidence-backed repository context for project overviews, impact analysis, execution flows, bindings, persistence, and tests before broad code exploration, and to read or capture shared agent memory: per-project stores and personal topic brains (career, languages, orchestrator with subagents). Apply when the user names Graphtyn or asks about repository purpose, architecture, dependencies, change impact, prior conversations, or cross-session knowledge; do not use it for requests unrelated to a code repository or recorded agent memory.
---

# Graphtyn

For first-time configuration, prefer `graphtyn setup --path .` and inspect its
dry-run. Apply only with authorization. Use manifest adapters and configured
history sources for unknown agents; never hardcode deployment identities.

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

Start with `limit: 10` and `evidence_mode: auto`. Prefer a single call. `auto` remains compact for ordinary graph questions and includes only selected symbol bodies when exact order, branches, lifecycle, concurrency, or failure semantics require source-level proof. Use `compact` to prohibit source excerpts, `balanced` for one bounded excerpt, and `precision` only when a named obligation remains missing. Preserve `context_id`; if evidence is genuinely missing, expand with `extends_context_id` so only new context is returned. Do not expand when `do_not_expand` is true or `complete_for` covers the task.

The first repository-inspection action must be this Graphtyn query: do not list the
tree, grep broadly, or read source beforehand. When `do_not_expand=true` and
`source_evidence` satisfies the obligations, answer directly from those excerpts
without reopening their files. For a named gap, read only the returned line range
or extend the same `context_id`; never open an entire file as redundant validation.

## Interpret evidence

- Treat `EXTRACTED` as structural evidence.
- Treat `INFERRED` as a lead to verify in source.
- Never present `AMBIGUOUS` as confirmed; verify it or report the ambiguity.
- Use directed edges to identify callers and consumers. Proximity or membership in the same subsystem does not prove consumption.
- Read only the returned files and relevant line ranges unless a specific gap requires more.
- When `source_evidence` is present, cite its numbered `file:start_line` ranges and use `requested_obligations` as a completion checklist.

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

## Capture an opted-in conversation

When shared memory is enabled, finish each substantive turn with one
`memory_ingest_turn` call. Reuse the client session id as `external_session_id`,
identify the real client in `agent_id`, and send only the user message plus a
concise assistant outcome. Set `consent=true` and `compact=true`; use `close=true`
only at real session termination. The operation is idempotent, sanitizes content,
compacts durable facts/decisions/results, and embeds those memories. Do not send
system prompts, hidden reasoning, secrets, or bulk tool output. Retrieve relevant
knowledge in later sessions with `memory_context` and preserve its attribution.

Pass the real client identity as `requester_agent`. Follow `claim_policy` exactly:
only `verified_measured`/`verified_fact` support factual language and citations;
qualify `historical_only`/`proposed_only`; do not settle `contested`, `stale`, or
`unsupported`. For comparisons, call `memory_ingest_evidence` first and preserve
the artifact's model, revision, sample size, protocol, and limitations.

For pre-existing Codex, AGY, OpenCode, OpenClaw, Hermes or Claude histories, use
`graphtyn memory bootstrap` without `--apply` to preview first. Show discovered
projects and ambiguous associations; require explicit user consent before
`--apply --consent`. Use `memory sync --consent` afterward. Never mix a session
whose workspace points to another project, and label imported claims as historical
unless current Git/source evidence verifies them.

## Personal agent brains

Besides project memory, the user may keep **brain** workspaces without a repository
(career, language practice, an orchestrator plus its subagents). Write each
substantive conversation outcome there:

```bash
graphtyn memory ingest-turn --agent <your-id> --external-session <chat-id> \
  --task "<topic>" --role assistant --consent \
  --path ~/memoria-personal/cerebro-<agent> --content "<concise outcome>"
```

Use one brain per autonomous agent; an orchestrator's brain also receives its
subagents' turns, each attributed with the subagent's real id. Retrieve
conversational knowledge first from the relevant brain (`memory_search`/
`memory_context` semantics against that path); consult project memory only when
code-level evidence is required. To query several brains and projects at once,
call `POST /api/memory/search-all` with an explicit `paths` list and report which
store each finding came from.

Agent identities are resolved through stored aliases — never invent variant
spellings. Register new agents by linking their workspace via
`POST /api/memory/agent-profile`, or discover many at once with
`graphtyn memory brain-init --agents-dir <dir> --register`.
