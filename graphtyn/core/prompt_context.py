"""Prefetch Graphtyn context into the first model turn (Claude Code, Codex and OpenCode).

With the MCP path, the agent spends one model call to request
`graph_query_intent` and a second one to answer, so the client's fixed prompt is
processed twice. A `UserPromptSubmit` hook can run the same retrieval before
the first call and add the package as context, which lets the agent answer in
one turn. The hook is opt-in, never builds an index, injects nothing for
prompts that are not about code, and gives up silently after a time budget.
"""
from __future__ import annotations

import json
import re
import shlex
import threading
from pathlib import Path
from typing import Any

HOOK_COMMAND = "graphtyn claude-context hook"
DEFAULT_BUDGET_SECONDS = 12.0
# Claude Code kills the hook after this many seconds; leave room for startup.
HOOK_TIMEOUT_SECONDS = 20
# Claude Code persists each hook's context above 10,000 characters to a file and
# shows the model only its path, which would cost an extra Read turn. The cap is
# per hook, so the package is split across PARTS hooks of the same event; they
# run in parallel and each one recomputes the same deterministic package.
MAX_CONTEXT_CHARACTERS = 9_800
PARTS = 2
# Codex previews hook context above ~2,500 tokens unless the handler raises
# `additionalContextLimit`, so one hook carries the whole block there.
CODEX_HOOK_COMMAND = "graphtyn codex-context hook"
CODEX_MAX_CONTEXT_CHARACTERS = MAX_CONTEXT_CHARACTERS * PARTS
CODEX_CONTEXT_TOKEN_LIMIT = 8_000

# A code identifier (camelCase, snake_case, `a::b`, a source file...) is the
# same in every language, so it anchors a code request on its own. Without one,
# the prompt needs a code verb and a code noun; these word lists cover Spanish,
# English, Portuguese, French, German and Italian.
_CODE_REQUEST = re.compile(
    r"\b(?:traza\w*|trace\w*|flujo|flow|funciona|works?|dónde|donde|where|impact\w*|romp\w*|break\w*|"
    r"persist\w*|guard\w*|sav\w*|llam\w*|calls?|callers?|consum\w*|depend\w*|expl[ií]ca\w*|explain\w*|"
    r"arquitectura|architecture|qué hace|what does|tests?|prueba\w*|valid\w*|refactor\w*|implement\w*|"
    r"bug|error\w*|fall\w*|fails?|crash\w*|lifecycle|ciclo de vida|ruta|route\w*|endpoint\w*|"
    r"controlador\w*|controller\w*|modelo|model|esquema|schema|migraci\w*|transacci\w*|transaction\w*|"
    # Portuguese / French / Italian
    r"rastre\w*|fluxo|explique\w*|onde|chama\w*|quebra\w*|arquitetura|trac\w*|flux|expliqu\w*|"
    r"où|appel\w*|cass\w*|fonctionne\w*|spiega\w*|dove|chiama\w*|flusso|architettura|"
    # German
    r"erkl[äa]r\w*|ablauf|wo|aufruf\w*|funktioniert|architektur|fehler)\b",
    re.IGNORECASE)
# Identifier shapes are case-sensitive (camelCase, PascalCase with an inner capital).
_IDENTIFIER = re.compile(
    r"`[^`]+`|\b[a-z]+[A-Z]\w*|\b[A-Z][a-z0-9]+[A-Z]\w*|\b\w+_\w+\b|\w::\w|\w#\w|\w\.\w+\(|"
    r"\b[\w./-]+\.(?:py|rb|js|jsx|ts|tsx|go|rs|java|kt|swift|scala|cs|php|c|h|cc|cpp|hpp)\b")
_CODE_NOUN = re.compile(
    r"\b(?:repositori\w*|repo|proyecto|project|projeto|projet|progetto|projekt\w*|codebase|código|code|codice|"
    r"clase|class|classe|klasse\w*|función|function|função|fonction|funzione|funktion\w*|método|method|méthode|"
    r"metodo|methode\w*|módulo|module|modulo|modul\w*)\b", re.IGNORECASE)
# Questions about past conversations belong to memory_context, not the code graph.
_HISTORY_REQUEST = re.compile(
    r"\b(?:qué hiciste|que hiciste|what did you|sesión anterior|previous session|recuerdas|remember|"
    r"lo que me dijiste|what you told|historial|history|o que você fez|sessão anterior|lembra\w*|"
    r"qu'as-tu fait|session précédente|souviens|cosa hai fatto|sessione precedente|ricordi|"
    r"was hast du|letzte sitzung|erinnerst)\b", re.IGNORECASE)


def should_prefetch(prompt: str) -> tuple[bool, str]:
    text = (prompt or "").strip()
    if len(text) < 20:
        return False, "too_short"
    if text.startswith(("/", "!", "#")):
        return False, "client_command"
    if _HISTORY_REQUEST.search(text):
        return False, "history_question"
    if _IDENTIFIER.search(text):
        return True, "code_anchor"
    if not _CODE_REQUEST.search(text):
        return False, "not_a_code_request"
    if not _CODE_NOUN.search(text):
        return False, "no_code_anchor"
    return True, "code_request"


def _index_path(root: Path) -> Path:
    from .storage import data_home, project_store_dir
    return project_store_dir(data_home(), root) / "index.json"


def _indexed_root(cwd: str | None) -> Path | None:
    """Nearest directory, from cwd upwards, that already has a Graphtyn index."""
    if not cwd:
        return None
    current = Path(cwd).expanduser().resolve()
    for candidate in (current, *current.parents):
        if _index_path(candidate).is_file():
            return candidate
    return None


def prefetch_package(root: Path, prompt: str, client: str | None = None) -> dict[str, Any] | None:
    """The lean `graph_query_intent` package for `prompt`, or None without an index.

    With `client`, the query is recorded for the dashboard as coming from that client's hook.
    """
    from ..mcp_server import _tag_graph_result, build_intent_package, lean_payload
    index = _index_path(root)
    if not index.is_file():
        return None
    graph = json.loads(index.read_text(encoding="utf-8"))
    raw, result, context_id = build_intent_package(root, graph, prompt)
    result["context_id"] = context_id
    _tag_graph_result(result, root)
    package = lean_payload(result)
    if client:
        from .query_log import record_query
        record_query(root, raw, source="hook", agent=client, request=prompt, result=package, context_id=context_id)
    return package


# Rendered as plain text: JSON would escape every newline and quote of the excerpts.
_RENDERED_KEYS = {"context_id", "entities", "relations", "files", "source_evidence", "citations", "legend",
                  "guidance", "payload_tokens"}
_STATUS_KEYS = ("intent", "complete_for", "missing", "do_not_expand", "requested_obligations",
                "not_applicable_obligations", "obligation_evidence", "omitted_unrelated_entities",
                "payload_truncated")


def _entity_lines(package: dict[str, Any]) -> list[str]:
    files = package.get("files") or {}
    lines = []
    for alias, item in (package.get("entities") or {}).items():
        file_alias, _, line = str(item.get("at") or "").partition(":")
        location = f"{files.get(file_alias, file_alias)}:{line}" if line else str(files.get(file_alias, ""))
        parts = [f"{alias} {item.get('name')} ({item.get('kind')}) {location}".rstrip()]
        if item.get("signature"):
            parts.append(f"sig: {item['signature']}")
        for op in item.get("ops") or []:
            parts.append(f"L{op[2]} {op[0]} {op[1]}: {op[3]}")
        for why in item.get("why") or []:
            parts.append(f"why L{why[0]} {why[1]}: {why[2]}")
        lines.append(" | ".join(parts))
    return lines


def _excerpt_priority(package: dict[str, Any], excerpt: dict[str, Any]) -> int:
    required = {name.casefold() for name in (package.get("source_coverage") or {}).get("required_symbols") or {}}
    return 0 if excerpt.get("covers") or str(excerpt.get("symbol") or "").casefold() in required else 1


def render_context(package: dict[str, Any], limit: int | None = None) -> str | None:
    """Compact text rendering that fits the client's context cap, or None.

    Secondary excerpts are shortened (keeping their head and tail) or dropped
    before the excerpts of required symbols are touched.
    """
    from ..mcp_server import _drop_excerpt_middle
    limit = limit or MAX_CONTEXT_CHARACTERS * PARTS
    if package.get("do_not_expand") and not package.get("missing"):
        # The same stop rule an agent applies to the MCP result it requested itself.
        instruction = ("No further graph query is needed (do_not_expand=true, missing=[]). Answer from this "
                       "block, citing the real file:line shown here, and do not re-read or re-verify what it "
                       "shows. Graph retrieval can miss part of a multi-part request: for a part this block "
                       "does not address, look up only that part (one targeted search or its exact range), "
                       "then answer.")
    elif {"request_parts", "named_identifiers"} & set(package.get("missing") or []):
        instruction = ("This evidence does not cover the whole request (see evidence_sufficiency): answer the "
                       "parts it shows from this block without re-reading them, and look up only what it does "
                       "not address, such as the unmatched identifiers (one targeted search or exact range "
                       "each), then answer.")
    else:
        instruction = ("This evidence is partial: query or read only the facts listed in missing, then answer.")
    header = [
        f"<graphtyn-context context_id=\"{package.get('context_id', '')}\">",
        "Graphtyn already ran graph_query_intent with this exact user message; this block is that result. "
        "Do not call graph_query_intent again for the same request. " + instruction
        + " Source code remains authoritative.",
        "status: " + json.dumps({key: package[key] for key in _STATUS_KEYS if key in package},
                                ensure_ascii=False, separators=(",", ":")),
    ]
    if package.get("guidance"):
        # Paths are already expanded here, so alias and citation advice does not apply.
        sentences = re.split(r"(?<=[.;])\s+", str(package["guidance"]))
        guidance = " ".join(sentence for sentence in sentences if "alias" not in sentence)
        if guidance:
            header.append(f"guidance: {guidance}")
    extra = {key: value for key, value in package.items()
             if key not in _RENDERED_KEYS and key not in _STATUS_KEYS}
    files = package.get("files") or {}
    if extra.get("call_outline"):
        # The files map is not rendered, so the outline carries real paths instead of F aliases.
        def located(at: Any) -> str:
            alias, _, line = str(at).partition(":")
            return f"{files.get(alias, alias)}:{line}" if line else str(files.get(alias, alias))
        extra["call_outline"] = [[*row[:2], located(row[2]), *row[3:]] for row in extra["call_outline"]]
        if isinstance(extra.get("call_outline_legend"), str):
            extra["call_outline_legend"] = extra["call_outline_legend"].replace("F:line", "file:line")
    header += [f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
               for key, value in extra.items()]
    tail = []
    entity_lines = _entity_lines(package)
    if entity_lines:
        tail += ["entities:", *entity_lines]
    if package.get("relations"):
        tail.append("relations [source,label,target,E|I|A,line]: "
                    + json.dumps(package["relations"], ensure_ascii=False, separators=(",", ":")))
    if package.get("do_not_expand") and not package.get("missing"):
        # Repeated last, next to the user message: injected context weighs less
        # than a tool result the model requested, and a closing reminder holds.
        tail.append("End of evidence: answer from it without re-reading what it shows; look up only a part "
                    "of the request it does not address.")
    tail.append("</graphtyn-context>")
    excerpts =[dict(item) for item in package.get("source_evidence") or []]

    def assemble() -> str:
        blocks = [f"== {item.get('file')}:{item.get('start_line')}-{item.get('end_line')} {item.get('symbol')}\n"
                  f"{item.get('text')}" for item in excerpts]
        return "\n".join([*header, *blocks, *tail])

    text = assemble()
    for priority in (1, 0):
        for index in reversed(range(len(excerpts))):
            if len(text) <= limit:
                return text
            excerpt = excerpts[index]
            if _excerpt_priority(package, excerpt) != priority:
                continue
            surplus = len(text) - limit
            body = str(excerpt.get("text") or "")
            if priority == 1 and len(body) - surplus < 400:
                excerpts.pop(index)  # too little would remain to be useful
            else:
                excerpt["text"] = _drop_excerpt_middle(body, surplus + 60)
            text = assemble()
    return text if len(text) <= limit else None


def split_context(text: str, parts: int, limit: int = MAX_CONTEXT_CHARACTERS) -> list[str]:
    """Split a rendered block on line boundaries into at most `parts` labelled chunks."""
    if len(text) <= limit:
        return [text]
    context_id = re.search(r'context_id="([^"]*)"', text)
    label = context_id.group(1) if context_id else ""
    chunks, current = [], ""
    for line in text.split("\n"):
        # Room for the continuation marker added below.
        if current and len(current) + len(line) + 1 > limit - 120:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    chunks.append(current)
    if len(chunks) > parts:
        raise ValueError("context does not fit in the available hook parts")
    total = len(chunks)
    return [chunk if index == 0 else
            f"[graphtyn-context {label} part {index + 1}/{total}: continues part {index}]\n{chunk}"
            for index, chunk in enumerate(chunks)]


def handle_prompt_hook(payload: dict[str, Any], root: Path | None = None,
                       budget_seconds: float = DEFAULT_BUDGET_SECONDS,
                       part: int = 1, parts: int = 1,
                       part_limit: int = MAX_CONTEXT_CHARACTERS, client: str | None = None) -> dict[str, Any]:
    """Decide, retrieve within the budget and return this hook part's outcome.

    `context` is set only when there is something worth injecting. With several
    parts, each process returns its own slice of the same rendered block, and only the
    first one records the query for `client`.
    """
    prompt = str(payload.get("prompt") or "")
    wanted, reason = should_prefetch(prompt)
    if not wanted:
        return {"injected": False, "reason": reason}
    root = root.expanduser().resolve() if root else _indexed_root(payload.get("cwd"))
    if root is None or not _index_path(root).is_file():
        return {"injected": False, "reason": "no_index"}
    outcome: dict[str, Any] = {}

    def work() -> None:
        try:
            outcome["package"] = prefetch_package(root, prompt, client if part == 1 else None)
        except Exception as exc:  # noqa: BLE001 - reported, never raised into the client
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    # A daemon thread lets the hook return on time; the process exits right after.
    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(budget_seconds)
    if worker.is_alive():
        return {"injected": False, "reason": "time_budget_exceeded", "path": str(root)}
    if "error" in outcome:
        return {"injected": False, "reason": "error", "error": outcome["error"], "path": str(root)}
    package = outcome.get("package")
    if not package:
        return {"injected": False, "reason": "no_index", "path": str(root)}
    if not package.get("source_evidence") and not package.get("do_not_expand"):
        # A weak package would cost tokens without replacing the MCP call.
        return {"injected": False, "reason": "insufficient_evidence", "path": str(root)}
    context = render_context(package, part_limit * parts - 200 * (parts - 1))
    if context is None:
        return {"injected": False, "reason": "context_too_large", "path": str(root)}
    chunks = split_context(context, parts, part_limit)
    if part > len(chunks):
        return {"injected": False, "reason": "part_not_needed", "path": str(root)}
    return {"injected": True, "reason": reason, "path": str(root), "context_id": package.get("context_id"),
            "payload_tokens": package.get("payload_tokens"), "part": f"{part}/{len(chunks)}",
            "context": chunks[part - 1]}


def hook_output(outcome: dict[str, Any]) -> str:
    """UserPromptSubmit response (same shape in Claude Code and Codex); empty when nothing is injected."""
    if not outcome.get("injected"):
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                              "additionalContext": outcome["context"]}},
                      ensure_ascii=False)


def install_prompt_hook(root: str | Path) -> dict[str, Any]:
    from .claude_capture import install_claude_hook
    return install_claude_hook(root, "UserPromptSubmit", HOOK_COMMAND, HOOK_TIMEOUT_SECONDS,
                               invocations=part_invocations("graphtyn"))


def uninstall_prompt_hook(root: str | Path) -> dict[str, Any]:
    from .claude_capture import uninstall_claude_hook
    return uninstall_claude_hook(root, "UserPromptSubmit", HOOK_COMMAND)


def prompt_hook_installed(root: str | Path) -> bool:
    from .claude_capture import _is_managed, _settings
    _path, data = _settings(Path(root).expanduser().resolve())
    groups = (data.get("hooks") or {}).get("UserPromptSubmit") or []
    return any(_is_managed(group, HOOK_COMMAND) for group in groups)


def hook_invocation(executable: str, root: Path | None = None) -> str:
    """Command line for a hook that pins the project root (used by benchmarks)."""
    command = f"{shlex.quote(executable)} claude-context hook"
    return command + (f" --path {shlex.quote(str(root))}" if root else "")


def part_invocations(executable: str, root: Path | None = None) -> list[str]:
    """One command per hook part; all belong to the same UserPromptSubmit group."""
    return [f"{hook_invocation(executable, root)} --part {part} --parts {PARTS}" for part in range(1, PARTS + 1)]


def _codex_hooks_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / ".codex" / "hooks.json"


def _codex_managed(group: dict[str, Any]) -> bool:
    return any("codex-context hook" in str(hook.get("command") or "")
               for hook in group.get("hooks") or [] if isinstance(hook, dict))


def _read_codex_hooks(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} no contiene un objeto JSON")
    return data


def install_codex_prompt_hook(root: str | Path, command: str = CODEX_HOOK_COMMAND) -> dict[str, Any]:
    """Add (or refresh) the managed group in `<root>/.codex/hooks.json`, keeping user hooks.

    Codex runs project hooks only when the project's `.codex/` layer is trusted
    and the hook itself has been reviewed with `/hooks`.
    """
    path = _codex_hooks_path(root)
    data = _read_codex_hooks(path)
    hooks = data.setdefault("hooks", {})
    groups = [group for group in hooks.get("UserPromptSubmit") or [] if not _codex_managed(group)]
    groups.append({"hooks": [{"type": "command", "command": command, "timeout": HOOK_TIMEOUT_SECONDS,
                              "additionalContextLimit": CODEX_CONTEXT_TOKEN_LIMIT,
                              "statusMessage": "Graphtyn: preparando contexto"}]})
    hooks["UserPromptSubmit"] = groups
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "installed": True, "hooks_file": str(path), "event": "UserPromptSubmit",
            "requires": "Proyecto .codex/ de confianza y hook revisado con /hooks en Codex"}


def uninstall_codex_prompt_hook(root: str | Path) -> dict[str, Any]:
    path = _codex_hooks_path(root)
    data = _read_codex_hooks(path)
    hooks = data.get("hooks") or {}
    groups = hooks.get("UserPromptSubmit") or []
    kept = [group for group in groups if not _codex_managed(group)]
    removed = len(kept) != len(groups)
    if removed:
        if kept:
            hooks["UserPromptSubmit"] = kept
        else:
            hooks.pop("UserPromptSubmit", None)
        if not hooks:
            data.pop("hooks", None)
        if data:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            path.unlink()
    return {"ok": True, "removed": removed, "hooks_file": str(path)}


def codex_prompt_hook_installed(root: str | Path) -> bool:
    try:
        data = _read_codex_hooks(_codex_hooks_path(root))
    except (OSError, ValueError):
        return False
    return any(_codex_managed(group) for group in (data.get("hooks") or {}).get("UserPromptSubmit") or [])


def codex_hook_invocation(executable: str, root: Path | None = None) -> str:
    command = f"{shlex.quote(executable)} codex-context hook"
    return command + (f" --path {shlex.quote(str(root))}" if root else "")


OPENCODE_PLUGIN = Path(".opencode") / "plugins" / "graphtyn-context.js"
_OPENCODE_MARKER = "// Managed by `graphtyn opencode-context install`"
# OpenCode drops `synthetic` parts before calling the model, so the block is a
# regular text part placed right after the user's own text.
_OPENCODE_TEMPLATE = _OPENCODE_MARKER + """; remove with `graphtyn opencode-context uninstall`.
const COMMAND = __COMMAND__
const TIMEOUT_MS = __TIMEOUT_MS__

export const GraphtynContext = async ({ directory }) => ({
  "chat.message": async (_input, output) => {
    const prompt = output.parts.filter((part) => part.type === "text" && !part.synthetic)
      .map((part) => part.text).join("\\n")
    if (!prompt.trim()) return
    try {
      const proc = Bun.spawn(COMMAND, { cwd: directory, stdin: "pipe", stdout: "pipe", stderr: "ignore" })
      proc.stdin.write(JSON.stringify({ prompt, cwd: directory, hook_event_name: "UserPromptSubmit" }))
      proc.stdin.end()
      const timer = setTimeout(() => proc.kill(), TIMEOUT_MS)
      const text = await new Response(proc.stdout).text()
      clearTimeout(timer)
      const context = text.trim() && JSON.parse(text)?.hookSpecificOutput?.additionalContext
      if (!context) return
      output.parts.push({
        id: output.parts[output.parts.length - 1].id.slice(0, -6) + "zzzzzz",
        sessionID: output.message.sessionID, messageID: output.message.id, type: "text", text: context,
      })
    } catch {
      // Never break the user's turn.
    }
  },
})
"""


def opencode_plugin_source(command: list[str]) -> str:
    return (_OPENCODE_TEMPLATE.replace("__COMMAND__", json.dumps(command))
            .replace("__TIMEOUT_MS__", str(HOOK_TIMEOUT_SECONDS * 1000)))


def install_opencode_prompt_plugin(root: str | Path, executable: str = "graphtyn") -> dict[str, Any]:
    """Write the project plugin that calls `graphtyn opencode-context hook` on each message."""
    path = Path(root).expanduser().resolve() / OPENCODE_PLUGIN
    if path.is_file() and _OPENCODE_MARKER not in path.read_text(encoding="utf-8"):
        raise ValueError(f"{path} existe y no lo gestiona Graphtyn")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(opencode_plugin_source([executable, "opencode-context", "hook"]), encoding="utf-8")
    return {"ok": True, "installed": True, "plugin": str(path), "event": "chat.message"}


def uninstall_opencode_prompt_plugin(root: str | Path) -> dict[str, Any]:
    path = Path(root).expanduser().resolve() / OPENCODE_PLUGIN
    removed = opencode_prompt_plugin_installed(root)
    if removed:
        path.unlink()
    return {"ok": True, "removed": removed, "plugin": str(path)}


def opencode_prompt_plugin_installed(root: str | Path) -> bool:
    path = Path(root).expanduser().resolve() / OPENCODE_PLUGIN
    try:
        return _OPENCODE_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False
