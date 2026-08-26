# Graphtyn agent policy

For a new checkout, run `graphtyn setup --path .` as a read-only preview and
only use `--apply` with user consent. Put runtime locations in configured memory
sources; never bake user names, IPs, containers or personas into instructions.

Use Graphtyn before broad repository exploration when a task asks for implementation, debugging, architectural tracing, persistence analysis, test selection, or change-impact assessment.

## Default workflow

1. Call `graph_query_intent` with the user's complete task and `evidence_mode=auto`. It uses the MCP server's configured workspace and does not accept `path`; the CLI equivalent `graphtyn query-intent` accepts `--path`.
2. Select `overview`, `flow`, `impact`, `persistence`, `bindings`, or `tests`; use `auto` only when no intent is evident. Use `overview` for repository purpose, technologies, entry points, subsystems, or architecture summaries.
3. Start with the MCP's compact default budget of 10 entities.
4. Verify the returned symbols and `file:line` locations in source. Source code remains authoritative.
5. Read only the selected files and ranges. Do not scan whole directories or load `index.json` unless the graph identifies a concrete evidence gap.
6. Preserve `context_id`. Expand with `extends_context_id` only for a named missing fact; stop when `do_not_expand` is true or `complete_for` covers the task.
7. For exact order, lifecycle, branch, concurrency or failure-semantics questions, use the returned `source_evidence` and cite its `file:start_line`; request `precision` explicitly only if `auto` reports a missing obligation.

Do not list the repository, grep broadly, or open files before this first query. If
`do_not_expand=true` and `source_evidence` covers the requested obligations, answer
from that bounded evidence without reading files again. If one named obligation is
missing, open only the exact returned line range or extend the existing `context_id`;
never load an entire file merely to reconfirm evidence Graphtyn already supplied.

Interpret confidence strictly: `EXTRACTED` is structural evidence, `INFERRED` requires source verification, and `AMBIGUOUS` must not be stated as fact. A nearby node or shared subsystem is not a consumer without a directed incoming relation.

For references such as “ese cambio” or “lo que me dijiste”, recover the concrete proposal from recent conversation and include it in the Graphtyn request. Ask for clarification only if it cannot be recovered unambiguously.

For web applications, trace `frontend → route → controller → validation → persistence → event/listener`, omitting stages that lack evidence. For an authorized code change, query before editing and perform a final `impact` check when consumers may be affected.

For `overview`, structure the answer from `project_profile`, `architecture`, `representative_flows`, and `risk_signals`; read only `read_first` plus necessary returned entry points. Verify purpose from documentation or code. If a persistent artifact is requested, generate `GRAPHTYN_REPORT.md` with `graphtyn report`.

Before publishing important architectural or impact claims, save the draft and run `graphtyn validate-answer --answer @draft.md --path .`. Before risky edits run `graphtyn impact --base HEAD --head HEAD --path .`; use its `GRAPHTYN_CHANGE_REPORT.md` verification plan after editing. Inspect unresolved candidates with `graphtyn review --ambiguities --path .`, and record an accept/reject/correct decision only after checking source.

Report the resulting flow or impact, affected symbols, direct consumers, side effects, tests, evidence locations, and any unresolved ambiguity. Keep the response compact and do not paste the full graph.

## Shared conversation memory

When the Graphtyn MCP exposes `memory_ingest_turn` and the project/user has opted
in to shared memory, call it once near the end of every substantive turn. Use the
native client conversation/session id as `external_session_id`; if unavailable,
create one stable opaque id and reuse it for the conversation. Set `agent_id` to
the actual client (`codex`, `agy`, `opencode`, `openclaw`, etc.), include the user
message and a concise assistant outcome in `messages`, set `consent=true`, and
leave `compact=true`. Set `close=true` only when the session is actually ending.
Never send system prompts, credentials, hidden reasoning, or unrelated tool dumps.
Treat an `isError` result as a failed capture and report it; never claim a memory
was saved from intent alone. At the start of a related future task, use
`memory_context` to retrieve the compacted, attributed memories.

Always pass the actual client identity in `requester_agent`. Obey each returned
`claim_policy`: `verified_measured` may be reported as a measured result with its
file/commit citation; `verified_fact` as a sourced fact; `historical_only` only as
what a past session observed; `proposed_only` only as an unverified proposal;
`contested`, `stale`, and `unsupported` must never be stated as settled facts.
For benchmark/comparison questions, run `graphtyn memory ingest-evidence --path .`
or MCP `memory_ingest_evidence` first and preserve limitations/sample-size warnings.

For conversations created before Graphtyn was installed, never copy histories
silently. Run `graphtyn memory bootstrap --provider <client> --source <path>
--path <project>` first, present its project/session/ambiguity preview, and import
only after explicit consent with `--apply --consent`. Subsequent synchronization
uses `memory sync --consent`; fingerprints make it incremental and idempotent.
Historical memories have `capture_mode=historical_import`: distinguish what an old
conversation recorded from what current source or a verified artifact proves.

## Personal agent brains

Aparte de la memoria de proyecto, el usuario mantiene **cerebros** personales
(espacios sin repositorio: carrera, idiomas, orquestador con subagentes). Las
conversaciones por tema se capturan con `graphtyn memory ingest-turn` apuntando
`--path` al cerebro correspondiente, usando la identidad real del agente. Para
preguntas que cruzan varios cerebros o proyectos usa `POST /api/memory/search-all`
con `paths` explícitos y reporta el espacio de origen de cada hallazgo. Consulta
primero a nivel conversacional (cerebro) y baja a memoria de proyecto sólo si se
requiere evidencia de código. Las identidades de agente se resuelven por alias
almacenados (`memory alias-import`, autodescubiertos al vincular workspaces):
nunca inventes variantes del id de un agente.
