---
name: graphtyn
description: Selects compact, evidence-backed context from a local Graphtyn code graph before exploring a repository. Use when the user asks to trace an execution flow, assess the impact or blast radius of a change, find callers, consumers, bindings, persistence or the tests that cover some code, or explain a repository's architecture, and before editing code whose consumers may be affected. Requires the Graphtyn MCP server or CLI. Not for questions about previous conversations (use graphtyn-memory), general programming questions, or edits that need no repository context.
---

# Graphtyn: code context and impact

Graphtyn answers questions about a repository from a local, deterministic code
graph: it returns the relevant symbols, directed relations, `file:line`
locations and, when needed, exact source excerpts. Use it as a context selector;
source code remains the final authority.

Graphtyn is an independent product, not a Graphify backend or compatibility
alias. Never install `graphifyy`, run `graphify-mcp`, register either command
under the `graphtyn` MCP name, or treat `graphify-out/` as a Graphtyn index. If
the executable is missing, request the official Graphtyn package or repository;
do not substitute another product. Verify with `graphtyn --version` and the
client's MCP listing. For first-time configuration, run `graphtyn setup --path .`
as a dry run and apply it only with the user's authorization.

## Not a history tool

Questions about what an agent previously did, added or decided belong to shared
memory (the `graphtyn-memory` skill, `memory_context`, or the CLI fallback
`graphtyn memory context "<question>" --mode continuity --no-graph`). Do not call
`graph_query_intent` or `graphtyn query-intent` for them:
those commands inspect source code and do not retrieve session history. For
mixed questions, retrieve memory first, then verify current code here.

## First query

If the turn already contains a `<graphtyn-context>` block, it is the result of
this query for the current message (a first-turn hook ran it): do not query
again, and apply the stopping rule below to that block.

Otherwise, the first repository-inspection action is one call to
`graph_query_intent`, before listing the tree, grepping or reading source:

- `request`: the user's complete task. Resolve references such as “ese cambio”
  or “lo anterior” from the conversation and include the concrete change; ask
  one short question only if the reference cannot be recovered.
- `intent`: the narrowest of `overview` (purpose, technologies, entry points,
  architecture), `flow` (behavior end to end), `impact` (consequences of a
  change), `persistence` (writes, models, transactions, events), `bindings`
  (routes, contracts, implementations), `tests` (coverage and regression
  targets); `auto` only when none is evident.
- `limit: 10`, `evidence_mode: auto`.

The server queries the workspace it was started for; do not invent a `path`.
With the CLI, use `graphtyn query-intent "<request>" --intent <intent> --path <project>`.

## Stop or expand

- When `do_not_expand=true` and `missing` is empty, answer from the returned
  entities, relations and `source_evidence`. Do not reopen those files, grep, or
  read an entire file to re-verify evidence already supplied.
- Graph retrieval can miss part of a multi-part request. For a part the evidence
  does not address, look up only that part (one targeted search or its exact
  range); do not broaden the search or re-check the parts already covered.
- When `missing` names an obligation, read only the returned line range or call
  again with `extends_context_id` set to the preserved `context_id`. Expand at
  most once per named gap.
- When `missing` contains `relevant_anchor`, run only the exact queries in
  `anchor_fallback`, once; if nothing matches, report the gap.

## Read the evidence correctly

- `EXTRACTED`/`TYPED`: structural fact. `INFERRED`: a lead to verify in source.
  `AMBIGUOUS`: never state it as fact.
- Only a directed incoming relation makes something a caller or consumer;
  sharing a file or subsystem does not.
- Cite the numbered `file:start_line` of `source_evidence`, and use
  `requested_obligations` as the checklist of what the answer must cover.
- For web flows follow `frontend → route → controller → validation →
  persistence → event/listener`, omitting stages without evidence.

## Answer

Report the flow or impact, affected symbols with `file:line`, direct consumers
and side effects, tests to run or add, and any unresolved inferred or ambiguous
relation. Keep it compact; never paste the graph, `index.json` or whole files.

For an authorized code change, a repository overview, or an important claim
that must be validated before publishing, follow
[references/change-workflow.md](references/change-workflow.md).
