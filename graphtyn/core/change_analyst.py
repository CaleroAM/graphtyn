"""Deterministic, token-bounded evidence planning for code changes."""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any


_STOP = {
    "para", "como", "esta", "este", "esto", "that", "with", "from", "the",
    "una", "uno", "unos", "las", "los", "del", "por", "que", "and", "con",
    "change", "cambio", "modify", "modificar", "agregar", "add", "hacer",
}

_INTENT_MARKERS = {
    "overview": ("overview", "purpose", "architecture", "summary", "what is this", "de qué trata", "de que trata", "resumen", "arquitectura", "proyecto", "project", "repository"),
    "bindings": ("binding", "bindings", "addscoped", "addsingleton", "addtransient", "dependency", "dependencia", "registr", "inyección", "injection"),
    "persistence": ("persist", "repository", "repositorio", "database", "base de datos", "save", "deleteasync", "addasync", "query", "consulta"),
    "tests": ("test", "tests", "prueba", "pruebas", "coverage", "cobertura"),
    "impact": ("impact", "impacto", "consumer", "consumidor", "blast", "afecta"),
    "flow": ("flow", "flujo", "trace", "traza", "desde", "hasta", "event", "evento"),
}

_INTENT_OPERATIONS = {
    "overview": (),
    "bindings": ("addscoped", "addsingleton", "addtransient", "adddbcontext", "addinterceptors", "usesql", "getconnectionstring", "register"),
    "persistence": ("repository", "addasync", "deleteasync", "updateasync", "savechanges", "fromsql", "countasync", "skip", "take", "asnotracking"),
    "tests": ("assert", "should", "equal", "returns", "substitute", "mock", "verify"),
    "impact": (),
    "flow": ("send", "publish", "dispatch", "save", "update", "route", "post", "delete", "addasync", "sendemail", "registerdomainevent"),
}

_TECH_BY_SUFFIX = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "React/JavaScript",
    ".ts": "TypeScript", ".tsx": "React/TypeScript", ".php": "PHP",
    ".cs": "C#", ".java": "Java", ".kt": "Kotlin", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".swift": "Swift", ".vue": "Vue",
    ".svelte": "Svelte", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
}

_MANIFEST_NAMES = {
    "pyproject.toml", "setup.py", "requirements.txt", "package.json", "composer.json",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "gemfile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
}

_EDIT_EXECUTION_GUIDANCE = (
    "Follow implementation_context in order. When do_not_expand=true, open only read_first, "
    "skip broad search and dependency provisioning, and expand at most once for a named missing obligation."
)


def _intent_evidence_status(selected_intent: str, has_tests: bool) -> tuple[list[str], list[str]]:
    missing = [] if has_tests or selected_intent != "tests" else ["tests"]
    return ([] if missing else [selected_intent]), missing


def _intent_can_stop(result: dict[str, Any]) -> bool:
    return bool(result["stopping"]["sufficient_evidence"] and result["validation"]["ok"]
                and not result["missing"])


def _is_change_request(request: str) -> bool:
    """Identify requests where an agent is expected to edit the repository."""
    return bool(re.search(
        r"\b(?:implement(?:a|ar|e)|a(?:ñ|n)ad(?:e|ir)|agreg(?:a|ar)|modific(?:a|ar)|"
        r"corrig(?:e|ir)|cambi(?:a|ar)|refactor(?:iza|izar)?|fix|edit|update|remove|elimina)\b",
        str(request or ""),
        re.I,
    ))


_TEST_COMMAND_RE = re.compile(
    r"(?:^|\s)(?:"
    r"(?:python(?:\d+(?:\.\d+)*)?\s+-m\s+)?pytest\b|"
    r"npm\s+(?:run\s+)?test\b|pnpm\s+(?:run\s+)?test\b|yarn\s+test\b|"
    r"go\s+test\b|cargo\s+test\b|dotnet\s+test\b|"
    r"(?:mvn|gradle|\.\/gradlew)\s+[^\n]*\btest\b|"
    r"bundle\s+exec\s+rspec\b|(?:vendor/bin/)?phpunit\b"
    r")",
    re.I,
)


def _clean_indexed_command(line: str) -> str:
    """Return a bounded command from one indexed configuration/source line."""
    value = str(line or "").strip()
    value = re.sub(r"^(?:[-*]\s+)?(?:run|command)\s*:\s*", "", value, flags=re.I)
    value = re.sub(r"^[-*]\s+", "", value)
    value = value.strip(" `\t\"'")
    if not value or len(value) > 320 or not _TEST_COMMAND_RE.search(value):
        return ""
    # Preserve an explicit project runner (container/uv/poetry) because it
    # carries the environment choice that prevents dependency provisioning.
    match = _TEST_COMMAND_RE.search(value)
    wrapper = re.match(
        r"^(?:docker(?:\s+compose)?|uv\s+run|poetry\s+run|pipenv\s+run)\b",
        value,
        re.I,
    )
    prefix = value[:match.start()].strip()
    if prefix and not wrapper and not re.fullmatch(r"(?:commands?|script)\s*[:=]", prefix, re.I):
        return ""
    command = value if wrapper else value[match.start():].strip()
    command = re.split(r"\s+#\s+", command, maxsplit=1)[0].strip()
    return command[:240]


def _indexed_test_commands(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract explicit test commands with source locations from indexed project files."""
    candidates: list[tuple[int, str, int, str]] = []
    seen: set[str] = set()
    for node in graph.get("nodes", []):
        if node.get("kind") != "documentation_section":
            continue
        path = str(node.get("file") or "").replace("\\", "/")
        lower_path = path.lower()
        name = Path(lower_path).name
        trusted_source = (
            "/.github/workflows/" in f"/{lower_path}"
            or name in {"makefile", "gnumakefile", "justfile", "package.json", "composer.json"}
            or name.startswith("docker-compose")
            or lower_path.startswith(("docs/", "readme"))
            or name in {"pyproject.toml", "tox.ini", "pytest.ini"}
        )
        if not trusted_source:
            continue
        details = str(node.get("details") or "")
        start_line = int(node.get("line_start") or node.get("line") or 1)
        for offset, raw_line in enumerate(details.splitlines()[1:]):
            # package.json scripts are invoked through the package manager so
            # the agent does not have to reinterpret an embedded shell value.
            if name == "package.json" and re.search(r'"test"\s*:', raw_line):
                command = "npm test"
            else:
                command = _clean_indexed_command(raw_line)
            normalized = command.lower()
            if not command or normalized in seen:
                continue
            seen.add(normalized)
            priority = 0 if "/.github/workflows/" in f"/{lower_path}" else \
                1 if name in {"makefile", "gnumakefile", "justfile"} else \
                2 if name == "package.json" else \
                3 if name.startswith("docker-compose") else 4
            candidates.append((priority, path, start_line + offset, command))
    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [
        {"command": command, "source": f"{path}:{line}", "confidence": "EXTRACTED"}
        for _priority, path, line, command in candidates[:3]
    ]


def _requested_support_files(graph: dict[str, Any], request: str,
                             excluded: set[str]) -> list[dict[str, str]]:
    """Select bounded configuration/verifier files explicitly required by a change."""
    text = str(request or "").lower()
    rules: list[tuple[str, str, re.Pattern[str]]] = []
    if re.search(r"\bdocker\b|contenedor|container", text):
        rules.append(("configuration", "docker", re.compile(
            r"(?:^|/)(?:dockerfile|docker-compose(?:\.[^/]*)?\.ya?ml)$", re.I)))
    installation_requested = bool(re.search(r"comprob|instala|installer|doctor", text))
    backup_requested = bool(re.search(r"backup|respaldo|restore|restaura", text))
    if installation_requested:
        rules.append(("verifier", "installation", re.compile(
            r"comprob|install|doctor", re.I)))
    elif re.search(r"verific", text) and not backup_requested:
        rules.append(("verifier", "verifier", re.compile(r"verif", re.I)))
    if backup_requested:
        rules.append(("verifier", "backup", re.compile(
            r"backup|respaldo|restore|restaura", re.I)))
    if re.search(r"\bci\b|workflow|pipeline", text):
        rules.append(("configuration", "ci", re.compile(r"(?:^|/)\.github/workflows/", re.I)))
    if re.search(r"makefile|\bmake\b", text):
        rules.append(("configuration", "make", re.compile(
            r"(?:^|/)(?:makefile|gnumakefile|justfile)$", re.I)))
    if not rules:
        return []

    request_terms = {term for term in _terms(request) if len(term) >= 5}
    per_path: dict[str, str] = {}
    for node in graph.get("nodes", []):
        path = str(node.get("file") or "").replace("\\", "/")
        if not path or path in excluded or re.search(
                r"(?:^|/)(?:tests?|specs?)(?:/|$|[_.])", path, re.I):
            continue
        searchable = (
            " ".join(str(node.get(key) or "") for key in
                     ("name", "container", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                                 for op in node.get("operations") or [])
        ).lower()
        per_path[path] = f"{per_path.get(path, '')} {searchable}"

    selected: list[dict[str, str]] = []
    seen = set(excluded)
    for role, category, pattern in rules:
        if any(pattern.search(path) for path in seen):
            continue
        ranked: list[tuple[int, str]] = []
        for path, searchable in per_path.items():
            if path in seen or not pattern.search(path):
                continue
            name = Path(path).name.lower()
            score = sum(term in searchable for term in request_terms)
            score += sum(term in path.lower() for term in request_terms) * 2
            if category == "docker" and name in {"docker-compose.yml", "docker-compose.yaml"}:
                score += 8
            ranked.append((score, path))
        if not ranked:
            continue
        _score, path = sorted(ranked, key=lambda item: (-item[0], item[1]))[0]
        selected.append({"path": path, "role": role})
        seen.add(path)
    return selected[:4]


def _rank_test_commands(commands: list[dict[str, Any]], tests: list[str]) -> list[dict[str, Any]]:
    """Prefer project commands that actually cover the selected regression files."""
    if not tests:
        return []

    def score(item: dict[str, Any]) -> tuple[int, str]:
        command = str(item.get("command") or "").lower()
        value = 0
        for path in tests:
            normalized = path.lower()
            if normalized in command:
                value += 100
            parent = str(Path(normalized).parent).replace("\\", "/")
            if parent not in {"", "."} and parent in command:
                value += 30
        if re.search(r"(?:^|\s)(?:python\s+-m\s+)?pytest(?:\s+-q)?\s*$", command):
            value += 1
        return value, str(item.get("source") or "")

    ranked = sorted(commands, key=lambda item: (-score(item)[0], score(item)[1]))
    relevant = [item for item in ranked if score(item)[0] > 0]
    return (relevant or ranked[:1])[:2]


def _implementation_context(
    graph: dict[str, Any],
    request: str,
    matched: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the smallest useful implementation brief for an editing agent.

    The brief deliberately contains paths and line-level hints rather than
    copying more node bodies. It lets an agent open the target, its direct
    consumers and relevant tests without another broad repository search.
    """
    if not _is_change_request(request):
        return {}

    by_id = {str(node.get("id")): node for node in graph.get("nodes", []) if node.get("id")}
    ignored_request_terms = {
        "implementa", "implementar", "añade", "anade", "agrega", "actualiza",
        "prueba", "pruebas", "tests", "test", "cambio", "cambios", "telemetría",
        "telemetria",
    }
    request_names = {term for term in _terms(request) if term not in ignored_request_terms}
    candidate_pool: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    for node in [*matched, *selected]:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(node_id)
        candidate_pool.append(node)

    def target_score(node: dict[str, Any]) -> int:
        path = str(node.get("file") or "").replace("\\", "/")
        if re.search(r"(?:^|/)(?:tests?|specs?|benchmarks?)(?:/|$|[_.])", path, re.I):
            return -1
        searchable = (
            " ".join(str(node.get(key) or "") for key in
                     ("name", "container", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                                 for op in node.get("operations") or [])
        ).lower()
        exact = int(str(node.get("name") or "").lower() in request_names)
        return exact * 50 + sum(term in searchable for term in request_names) * 5 \
            + int(path.startswith(("src/", "graphtyn/", "backend/", "app/"))) * 3

    explicit_request_identifiers = {
        value.lower() for value in re.findall(
            r"\b(?:[A-Z][A-Z0-9_]{4,}|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b",
            str(request or ""),
        )
    }

    def identifier_hits(node: dict[str, Any]) -> int:
        path = str(node.get("file") or "").replace("\\", "/")
        if re.search(r"(?:^|/)(?:tests?|specs?|benchmarks?)(?:/|$|[_.])", path, re.I):
            return 0
        searchable = (
            " ".join(str(node.get(key) or "") for key in
                     ("name", "container", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                                 for op in node.get("operations") or [])
        ).lower()
        return sum(searchable.count(identifier) for identifier in explicit_request_identifiers)

    explicit_targets = sorted(
        (node for node in candidate_pool if identifier_hits(node)),
        key=lambda node: (-identifier_hits(node), -target_score(node), str(node.get("id") or "")),
    )
    ranked_targets = sorted(candidate_pool, key=lambda node: (-target_score(node), str(node.get("id") or "")))
    best_score = target_score(ranked_targets[0]) if ranked_targets else -1
    primary = explicit_targets[:3] or [
        node for node in ranked_targets[:3]
        if best_score > 0 and target_score(node) >= max(1, best_score - 5)
    ]
    if not primary:
        primary = matched[:1]
    seed_ids = {str(node.get("id")) for node in primary if node.get("id")}
    primary_files = {str(node.get("file") or "") for node in primary if node.get("file")}
    consumer_labels = {
        "llama", "usa", "referencia", "implementa", "hereda", "suscribe",
        "escucha", "despacha", "invoca ruta", "valida con", "crea",
    }
    direct_consumers: list[dict[str, Any]] = []
    seen_consumers: set[tuple[str, str, str]] = set()
    for link in graph.get("links", []):
        source = str(link.get("source") or "")
        target = str(link.get("target") or "")
        label = str(link.get("label") or "")
        if target not in seed_ids or source in seed_ids or label not in consumer_labels:
            continue
        node = by_id.get(source)
        if not node or not node.get("file"):
            continue
        identity = (source, target, label)
        if identity in seen_consumers:
            continue
        seen_consumers.add(identity)
        direct_consumers.append({
            "symbol": node.get("name"),
            "file": node.get("file"),
            "line": node.get("line"),
            "relation": label,
            "target": by_id.get(target, {}).get("name") or target,
            "confidence": link.get("confidence", "EXTRACTED"),
        })
    direct_consumers.sort(key=lambda item: (
        str(item.get("confidence")) == "AMBIGUOUS",
        str(item.get("file") or ""), int(item.get("line") or 0),
    ))
    direct_consumers = direct_consumers[:6]

    target_names = {
        str(node.get("name") or "").lower()
        for node in primary
        if len(str(node.get("name") or "")) >= 4
        and str(node.get("name") or "").lower() not in {
            "main", "handle", "run", "execute", "command", "documento", "services",
        }
    }
    request_terms = {term for term in _terms(request) if len(term) >= 5}
    direct_test_files = {
        str(item.get("file") or "").replace("\\", "/")
        for item in direct_consumers
        if re.search(r"(?:^|/)(?:tests?|specs?)(?:/|$|[_.])",
                     str(item.get("file") or "").replace("\\", "/"), re.I)
    }
    consumer_names = {
        str(item.get("symbol") or "").lower()
        for item in direct_consumers if len(str(item.get("symbol") or "")) >= 4
    }
    target_stems = {
        Path(path).stem.lower() for path in primary_files
        if path and Path(path).stem.lower() not in {"main", "app", "index", "service", "utils"}
    }
    target_stems.update(
        Path(str(item.get("file") or "")).stem.lower()
        for item in direct_consumers
        if item.get("file") and not re.search(
            r"(?:^|/)(?:tests?|specs?)(?:/|$|[_.])", str(item.get("file")), re.I)
    )
    test_scores: dict[str, int] = {}
    for node in graph.get("nodes", []):
        path = str(node.get("file") or "").replace("\\", "/")
        if not path or not re.search(r"(?:^|/)(?:tests?|specs?)(?:/|$|[_.])", path, re.I):
            continue
        if Path(path).name.lower() in {"conftest.py", "setup_tests.py", "fixtures.py"}:
            continue
        searchable = (
            " ".join(str(node.get(key) or "") for key in
                     ("name", "container", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                                 for op in node.get("operations") or [])
        ).lower()
        structural = int(path in direct_test_files) * 100
        structural += sum(stem in path.lower() for stem in target_stems) * 12
        structural += sum(term in searchable for term in target_names) * 8
        structural += sum(term in searchable for term in consumer_names) * 5
        structural += sum(identifier in searchable
                          for identifier in explicit_request_identifiers) * 20
        # Request words only break ties. They must never admit an unrelated
        # test merely because both happen to mention a generic term.
        score = structural * 10 + sum(term in searchable for term in request_terms)
        if structural:
            test_scores[path] = max(score, test_scores.get(path, 0))
    tests = [path for path, _score in sorted(
        test_scores.items(), key=lambda item: (-item[1], item[0])
    )[:2]]

    side_effects: list[dict[str, Any]] = []
    effect_pattern = re.compile(
        r"^(?:save|write|delete|remove|publish|dispatch|send|cache|commit|rollback|"
        r"setenv|persist|update|create|unlink|rename|clear|pop)",
        re.I,
    )
    relevant_effect_ids = seed_ids | {
        str(link.get("source") or "") for link in graph.get("links", [])
        if str(link.get("target") or "") in seed_ids
        and str(link.get("label") or "") in consumer_labels
    }
    for node in candidate_pool:
        if str(node.get("id") or "") not in relevant_effect_ids:
            continue
        for operation in node.get("operations") or []:
            operation_name = str(operation.get("name") or operation.get("kind") or "")
            if operation.get("kind") not in {"write", "delete", "publish", "dispatch"} \
                    and not effect_pattern.search(operation_name):
                continue
            side_effects.append({
                "symbol": node.get("name"), "file": node.get("file"),
                "line": operation.get("line") or node.get("line"),
                "operation": operation.get("name") or operation.get("kind"),
            })
            if len(side_effects) >= 6:
                break
        if len(side_effects) >= 6:
            break

    affected: list[dict[str, str]] = []
    seen_files: set[str] = set()
    consumer_files = {str(item.get("file") or "") for item in direct_consumers}
    affected_nodes = [*primary]
    affected_nodes.extend(
        by_id[source_id] for source_id in relevant_effect_ids - seed_ids if source_id in by_id
    )
    for node in affected_nodes:
        path = str(node.get("file") or "")
        if not path or path in seen_files:
            continue
        seen_files.add(path)
        role = "target" if path in primary_files \
            else "test" if re.search(r"(?:^|/)(?:tests?|specs?)(?:/|$|[_.])", path, re.I) \
            else "consumer" if path in consumer_files else "related"
        affected.append({"path": path, "role": role})
        if len(affected) >= 10:
            break
    for path in tests:
        if path not in seen_files and len(affected) < 10:
            affected.append({"path": path, "role": "test"})
            seen_files.add(path)

    support_files = _requested_support_files(graph, request, seen_files)
    for item in support_files:
        if len(affected) >= 10:
            break
        affected.append(item)
        seen_files.add(item["path"])

    suffixes = {path.rsplit(".", 1)[-1].lower() for path in tests if "." in path}
    indexed_commands = _rank_test_commands(_indexed_test_commands(graph), tests)
    commands = [item["command"] for item in indexed_commands]
    command_status = "extracted_from_project_source; execution_not_verified" \
        if commands else "suggested_from_test_files; execution_not_verified"
    if not commands and tests and "py" in suffixes:
        commands.append("python -m pytest " + " ".join(tests))
    if not commands and tests and suffixes.intersection({"js", "jsx", "ts", "tsx"}):
        commands.append("npm test -- " + " ".join(tests))
    if not commands and tests and "cs" in suffixes:
        commands.append("dotnet test")
    if not commands and tests and "go" in suffixes:
        commands.append("go test ./...")

    read_first = [item["path"] for item in affected if item["role"] == "target"][:4]
    read_first.extend(
        item["path"] for item in affected
        if item["role"] in {"configuration", "verifier"} and item["path"] not in read_first
    )
    read_first.extend(path for path in tests[:2] if path not in read_first)
    read_first = read_first[:8]
    return {
        "affected_files": affected,
        "direct_consumers": direct_consumers,
        "side_effects": side_effects,
        "test_files": tests,
        "suggested_test_commands": commands,
        "test_command_evidence": indexed_commands,
        "command_status": command_status,
        "read_first": read_first,
        "selection": "direct graph evidence plus lexical test matching",
        "execution_policy": {
            "order": ["read_first", "edit_targets", "run_first_test_command", "expand_on_named_gap"],
            "max_expansions": 1,
            "max_initial_files": len(read_first),
            "max_exact_search_results": 20,
            "broad_search": "skip_when_do_not_expand",
            "dependency_install": "outside_edit_session",
            "dependency_install_requires_explicit_request": True,
            "unavailable_runner": "report_gap_without_provisioning",
            "stop_when": "targeted_tests_pass_and_missing_is_empty",
        },
        "exploration_budget": {
            "initial_files": read_first,
            "max_initial_files": len(read_first),
            "max_expansions": 1,
            "search_mode": "exact_named_gap_only",
            "max_search_results": 20,
            "dependency_install_allowed": False,
        },
    }


def _compact_overview_node(node: dict[str, Any]) -> dict[str, Any]:
    compact = {key: node[key] for key in (
        "id", "name", "kind", "file", "path", "line", "end_line", "degree",
        "container", "namespace", "signature", "parser",
    ) if node.get(key) not in (None, "", [], {})}
    if node.get("details"):
        compact["details"] = str(node["details"])[:240]
    if node.get("imports"):
        compact["imports"] = list(node["imports"][:8])
    return compact


def _finalize_overview_projection(result: dict[str, Any], selected: list[dict[str, Any]],
                                  links: list[dict[str, Any]], token_budget: int = 4000) -> dict[str, Any]:
    """Emit each entity once and enforce a serialized response budget."""
    result["matched_ids"] = [str(node.get("id")) for node in selected[:5] if node.get("id")]
    result.pop("matched", None)
    result["nodes"] = [_compact_overview_node(node) for node in selected]
    result["links"] = [
        {key: link[key] for key in ("source", "target", "label", "confidence", "file", "line")
         if link.get(key) not in (None, "")}
        for link in links
    ]
    result["detail_refs"] = {
        str(node["id"]): {"tool": "graph_neighborhood", "symbol": str(node.get("name") or node["id"]),
                          "depth": 1}
        for node in result["nodes"] if node.get("id")
    }
    result["projection_version"] = "overview-compact-v2"
    result["payload_budget_tokens"] = int(token_budget)

    def size() -> int:
        return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    byte_budget = token_budget * 4
    while size() > byte_budget and len(result["nodes"]) > 4:
        removed = result["nodes"].pop()
        result["detail_refs"].pop(str(removed.get("id")), None)
        allowed = {node.get("id") for node in result["nodes"]}
        result["links"] = [link for link in result["links"]
                           if link.get("source") in allowed and link.get("target") in allowed]
    if size() > byte_budget:
        result["representative_flows"] = list(result.get("representative_flows") or [])[:3]
        result["risk_signals"] = list(result.get("risk_signals") or [])[:4]
    result["payload_bytes"] = size()
    result["estimated_tokens"] = result["payload_bytes"] // 4
    result["budget"].update({"selected_nodes": len(result["nodes"]),
                             "payload_tokens": result["estimated_tokens"],
                             "payload_token_budget": token_budget})
    return result


def _overview_package(graph: dict[str, Any], request: str, max_nodes: int) -> dict[str, Any]:
    """Select diverse architectural evidence instead of lexical neighbors."""
    all_nodes = graph.get("nodes", [])
    max_nodes = min(max(4, max_nodes), 12)

    def path_of(node: dict) -> str:
        path = str(node.get("file") or node.get("path") or node.get("details") or "").replace("\\", "/")
        return re.sub(r"^(?:Carpeta|Folder):\s*", "", path, flags=re.I)

    def basename(node: dict) -> str:
        path = path_of(node)
        return (path.rsplit("/", 1)[-1] or str(node.get("name") or "")).lower()

    def production(node: dict) -> bool:
        path = path_of(node).lower()
        generated_benchmark = re.search(r"_\d{4}-\d{2}-\d{2}(?:/|$)", path)
        excluded_tree = re.search(r"(?:^|/)(?:tests?|fixtures?|benchmarks?|vendor|node_modules|legacy|backup)(?:/|$)", path)
        return not (generated_benchmark or excluded_tree)

    files = [node for node in all_nodes if node.get("kind") in ("file", "doc") and production(node)]
    manifests = [node for node in files if basename(node) in _MANIFEST_NAMES]
    documents = [node for node in files if basename(node).startswith("readme") or basename(node) in ("architecture.md", "agents.md")]
    entry_re = re.compile(r"(?:^|/)(?:main|app|index|server|manage|program|startup|cli)\.(?:py|js|jsx|ts|tsx|php|cs|java|go|rs)$", re.I)
    entries = [node for node in files if entry_re.search(path_of(node))]
    modules = [node for node in all_nodes
               if node.get("kind") in ("module", "community") and production(node)
               and str(node.get("name") or "").lower() not in ("root", "dir:root", "general")]
    central = [node for node in all_nodes
               if node.get("kind") in ("class", "interface", "struct", "function", "method", "route")
               and production(node) and len(str(node.get("name") or "")) >= 3
               and str(node.get("name") or "").lower() not in ("index", "main", "get", "set")]

    by_degree = lambda node: (-int(node.get("degree") or 0), str(node.get("id") or ""))
    kind_weight = {"class": 35, "interface": 35, "struct": 30, "route": 20, "function": 10, "method": 5}
    central.sort(key=lambda node: (-(int(node.get("degree") or 0) + kind_weight.get(node.get("kind"), 0)), str(node.get("id") or "")))
    unique_central = []
    central_names = set()
    for node in central:
        name = str(node.get("name") or "").lower()
        if name not in central_names:
            unique_central.append(node)
            central_names.add(name)
    groups = [
        sorted(documents, key=by_degree), sorted(manifests, key=by_degree),
        sorted(entries, key=by_degree), sorted(modules, key=by_degree),
        unique_central,
    ]
    selected: list[dict] = []
    seen: set[str] = set()
    while len(selected) < max_nodes and any(groups):
        progressed = False
        for group in groups:
            while group and group[0].get("id") in seen:
                group.pop(0)
            if group and len(selected) < max_nodes:
                node = group.pop(0)
                selected.append(node)
                seen.add(node.get("id"))
                progressed = True
        if not progressed:
            break

    selected_ids = {node.get("id") for node in selected}
    links = [link for link in graph.get("links", []) if link.get("source") in selected_ids and link.get("target") in selected_ids]
    technology_counts: dict[str, int] = {}
    for node in files:
        name = basename(node)
        suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        technology = _TECH_BY_SUFFIX.get(suffix)
        if technology:
            technology_counts[technology] = technology_counts.get(technology, 0) + 1
    technologies = [name for name, _ in sorted(technology_counts.items(), key=lambda item: (-item[1], item[0]))]
    profile = {
        "technologies": technologies[:8],
        "manifests": [path_of(node) for node in manifests[:6]],
        "documentation": [path_of(node) for node in documents[:4]],
        "read_first": list(dict.fromkeys([path_of(node) for node in documents[:2] + manifests[:3]])),
        "entry_points": [path_of(node) for node in entries[:6]],
        "subsystems": [str(node.get("name") or node.get("id")) for node in sorted(modules, key=by_degree)[:8]],
        "key_symbols": [str(node.get("name") or node.get("id")) for node in unique_central[:8]],
    }
    result = {
        "request": str(request or "").strip(), "intent": "overview", "intent_terms": _terms(request),
        "project_profile": profile, "nodes": selected, "links": links, "complete_for": ["overview"],
        "missing": [] if selected else ["project evidence"], "do_not_expand": bool(selected),
        "guidance": "Explain purpose, technologies, entry points and subsystems from this evidence. Cite aliases; distinguish observed facts from inference.",
        "planner": "overview-v1", "budget": {"max_nodes": max_nodes, "selected_nodes": len(selected)},
        "operation_limit": 3,
    }
    from .overview_report import enrich_overview
    return _finalize_overview_projection(enrich_overview(graph, result), selected, links)

_QUERY_EXPANSIONS = {
    "eliminar": ("delete", "deleted"), "eliminación": ("delete", "deleted"),
    "borrado": ("delete", "deleted", "deleteservice"),
    "evento": ("event", "publish", "handler"), "eventos": ("event", "publish", "handler"),
    "correo": ("email", "sendemail"), "persistencia": ("repository", "save", "database"),
    "repositorio": ("repository",), "consulta": ("query",), "prueba": ("test", "assert"),
    "inyección": ("addscoped", "dependency", "service"),
    "propuesta": ("proposal", "salesproposal"), "propuestas": ("proposal", "salesproposal"),
    "factura": ("invoice", "salesinvoice"), "facturas": ("invoice", "salesinvoice"),
    "devolución": ("return", "purchasereturn"), "devoluciones": ("return", "purchasereturn"),
    "compra": ("purchase",), "compras": ("purchase",),
    "almacén": ("almacen", "warehouse", "store"),
    "manifiesto": ("manifest",), "integridad": ("hash", "checksum", "validar", "verify"),
    "parcela": ("parcel", "parcela_id", "id_poligono"),
    "producto": ("product",), "productos": ("product",),
    "arranque": ("bootstrap", "app.tsx", "app.blade.php", "inertia"),
    "creación": ("create", "store"), "crear": ("create", "store"),
    "conversión": ("convert", "converttoinvoice"), "convertir": ("convert", "converttoinvoice"),
    "aprobar": ("approve",), "aprobación": ("approve",),
    "completar": ("complete",), "completado": ("complete",),
    "autorización": ("authorize", "request"), "validación": ("request", "rules"),
    "lectura": ("cookie", "cookies", "decode", "loads"),
    "verificación": ("verify", "unsign", "signature", "signer", "badsignature"),
    "firma": ("sign", "unsign", "signer", "signature", "badsignature", "timestampsigner"),
    "inválida": ("invalid", "badsignature", "except", "session"),
    "acceso": ("accessed", "mark_accessed"), "modificación": ("modified", "mark_modified"),
    "escritura": ("encode", "b64encode", "set-cookie", "append"),
    "borrado": ("expires", "1970", "delete", "set-cookie"),
    "cookie": ("cookie", "set-cookie", "httponly", "samesite", "secure", "max-age"),
    "seguridad": ("httponly", "samesite", "secure", "https_only", "security_flags"),
    "estado": ("state", "active", "isauctionactive"),
    "interfaz": ("interface", "implements"), "interfaces": ("interface", "implements"),
    "consumidor": ("consumer", "caller", "calls"), "consumidores": ("consumer", "caller", "calls"),
    "captured": ("urlparams", "routeparams", "findroute", "keys", "values"),
    "capture": ("urlparams", "routeparams", "findroute", "keys", "values"),
    "entry": ("__call__", "servehttp", "main", "application"),
}


def _terms(request: str) -> list[str]:
    return list(dict.fromkeys(
        normalized for token in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_][\w.]+", request)
        if len(normalized := token.lower().strip(".")) >= 3 and normalized not in _STOP
    ))[:20]


def classify_intent(request: str, requested: str = "auto") -> str:
    text = str(request or "").lower()
    enumerated = len(set(re.findall(r"\bq\d+\s*[):]", text))) >= 2
    operational = bool(re.search(
        r"\b(?:c[oó]mo|cu[aá]les?|qu[eé] ocurre|si falta|comprueba|valida|genera|"
        r"docker|worker|api|archivo|manifiesto|integridad|esquema|script)\b",
        text,
    ))
    # Models sometimes choose ``overview`` merely because the prompt names a
    # repository. An enumerated operational question needs symbol/operation
    # evidence, even when the caller supplied that overly broad intent.
    if requested == "overview" and ((enumerated and operational) or _is_change_request(text)):
        return "flow"
    if requested in _INTENT_MARKERS:
        return requested
    if _is_change_request(text):
        return "flow"
    def marker_matches(marker: str) -> bool:
        if marker == "registr":
            return marker in text
        return bool(re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text))

    scores = {intent: sum(marker_matches(marker) for marker in markers)
              for intent, markers in _INTENT_MARKERS.items()}
    best = max(scores, key=lambda intent: scores[intent])
    return best if scores[best] else "flow"


def _requested_concerns(request: str) -> dict[str, re.Pattern[str]]:
    """Map explicit task obligations to evidence patterns.

    These are deliberately concrete. They let a multi-part request stop only
    when the selected evidence covers each named concern, without requiring a
    second graph call simply because the prompt used q1/q2 notation.
    """
    text = str(request or "").lower()
    concerns: dict[str, re.Pattern[str]] = {}
    if re.search(r"(?:dos|2) archivos|archivos? de datos|tabla.*manifiesto|manifiesto.*tabla", text):
        concerns["artifacts"] = re.compile(r"parquet|manifest|manifiesto|feature_store", re.I)
    if "docker" in text:
        concerns["docker_configuration"] = re.compile(r"docker-compose|dockerfile|feature_store_path", re.I)
    if re.search(r"si falta|cuando falta|ausencia|no existe", text):
        concerns["missing_artifact_behavior"] = re.compile(
            r"is_file|exists|no_disponibles|modelartifacterror|falta", re.I)
    if re.search(r"integridad|esquema|hash|sha-?256|checksum", text):
        concerns["integrity_schema"] = re.compile(
            r"sha|hash|schema|esquema|crs|duplic|id_poligono", re.I)
    if re.search(r"parcela|campa(?:ña|na)|geometr[ií]a|superficie", text):
        concerns["record_identity"] = re.compile(
            r"parcela|campana|campaña|geometr|superficie|id_poligono|vectorizar", re.I)
    if re.search(r"scripts?.*genera|genera.*(?:tabla|manifiesto)|produc.*(?:tabla|manifiesto)", text):
        if "tabla" in text:
            concerns["table_generation"] = re.compile(
                r"generar_variables|guardar_tabla|procesamiento/variables/__main__", re.I)
        if "manifiesto" in text or "manifest" in text:
            concerns["runtime_manifest_generation"] = re.compile(
                r"preparar_almacen(?:_inferencia)?|prepare[^/\s]*manifest", re.I)
    return concerns


def query_intent(graph: dict[str, Any], request: str, intent: str = "auto", max_nodes: int = 12) -> dict[str, Any]:
    """Return a one-shot, intent-specific evidence package."""
    selected_intent = classify_intent(request, intent)
    if selected_intent == "overview":
        return _overview_package(graph, request, max_nodes)
    requested_ceiling = max(4, max_nodes)
    complexity = min(3, len(re.findall(r"\b(?:and|y|then|después|también|además)\b", str(request), re.I)))
    intent_node_cap = {"bindings": 7, "persistence": 7, "tests": 8, "impact": 10, "flow": 9}[selected_intent]
    max_nodes = min(requested_ceiling, intent_node_cap + complexity)
    markers = _INTENT_OPERATIONS[selected_intent]
    request_lower = str(request or "").lower()
    tests_requested = bool(re.search(r"\b(?:tests?|pruebas?|coverage|cobertura)\b", request_lower))
    docker_requested = "docker" in request_lower
    verifier_requested = bool(re.search(
        r"\b(?:verifiers?|verificadores?|verificar|comprobar|instalaci[oó]n|backup|respaldo)\b",
        request_lower,
    ))
    requested_concerns = _requested_concerns(request_lower)
    expansions = list(dict.fromkeys(
        expansion for word, values in _QUERY_EXPANSIONS.items() if word in request_lower for expansion in values
    ))
    direct_terms = _terms(request)
    # Qualified symbols (Mux.ServeHTTP, Controller::store) preserve the full token;
    # also resolve each
    # identifier so exact symbol anchoring wins over broad semantic matches.
    non_symbol_suffixes = {
        "json", "yaml", "yml", "toml", "xml", "csv", "parquet", "md", "txt",
        "py", "js", "jsx", "ts", "tsx", "php", "cs", "java", "go", "rs",
    }
    qualified_parts = [
        part.lower()
        for token in direct_terms
        if "::" in token or "#" in token or token.rsplit(".", 1)[-1].lower() not in non_symbol_suffixes
        for part in re.split(r"\.|::|#", token)
        if len(part) >= 3 and part.lower() not in _STOP
    ]
    direct_terms = list(dict.fromkeys([*direct_terms, *qualified_parts]))[:24]
    request_terms = direct_terms + expansions
    generic_symbol_terms = {
        "app", "application", "context", "handler", "middleware", "request", "response", "route", "router",
        "api", "worker", "data", "datos", "file", "files", "archivo", "archivos", "variable", "variables",
        "script", "scripts", "function", "functions", "función", "funciones", "project", "proyecto",
    }
    symbol_terms = [term for term in direct_terms if term not in generic_symbol_terms]
    explicit_identifiers = {
        identifier.lower()
        for identifier in re.findall(r"\b[A-Z][A-Z0-9_]{4,}\b", str(request or ""))
    } | {
        identifier.lower()
        for identifier in re.findall(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", str(request or ""))
    }
    all_nodes = graph.get("nodes", [])
    qualified_symbols = [
        (owner.lower(), member.lower())
        for owner, member in re.findall(r"([A-Za-z_][\w]*)\s*(?:::|\.|#)\s*([A-Za-z_][\w]*)", str(request or ""))
        if member.lower() not in non_symbol_suffixes
    ]
    def qualified_match(node: dict) -> bool:
        name = str(node.get("name") or "").lower()
        owner_text = " ".join(str(node.get(key) or "") for key in ("container", "signature", "owner_signature")).lower()
        return any(name == member and re.search(rf"\b{re.escape(owner)}\b", owner_text)
                   for owner, member in qualified_symbols)

    qualified_nodes = [node for node in all_nodes if qualified_match(node)]
    explicit_names = {
        str(node.get("name") or "").lower()
        for node in all_nodes
        if str(node.get("name") or "").lower() in symbol_terms
        and node.get("kind") not in {"file", "module", "documentation_section", "doc", "image", "media"}
    }
    anchor_files = ({str(node.get("file") or "") for node in qualified_nodes if node.get("file")}
                    if qualified_nodes else
                    {str(node.get("file") or "") for node in all_nodes
                     if str(node.get("name") or "").lower() in explicit_names and node.get("file")})
    if selected_intent == "impact" and explicit_names:
        anchors = [node for node in all_nodes if str(node.get("name") or "").lower() in explicit_names]
        by_id = {node.get("id"): node for node in all_nodes}
        consumer_labels = {"llama", "usa", "referencia", "implementa", "hereda", "suscribe", "escucha",
                           "despacha", "invoca ruta", "valida con", "crea", "despacha evento"}
        adjacency: dict[str, list[tuple[str, dict]]] = {}
        for link in graph.get("links", []):
            source, target, label = link.get("source"), link.get("target"), str(link.get("label") or "")
            if label in consumer_labels:
                adjacency.setdefault(target, []).append((source, link))
                if label in {"implementa", "hereda"}:
                    adjacency.setdefault(source, []).append((target, link))
            elif label == "contiene":
                # Include the declaring file/container but never fan out from
                # that file into every sibling symbol.
                adjacency.setdefault(target, []).append((source, link))
        selected_ids = {node.get("id") for node in anchors}
        frontier = [(node.get("id"), 0) for node in anchors]
        traversed = []
        while frontier and len(selected_ids) < max_nodes:
            current, hop = frontier.pop(0)
            if hop >= 2 or str(current).startswith("file:"):
                continue
            neighbors = sorted(adjacency.get(current, []), key=lambda item: (
                str(item[1].get("confidence") or "") == "AMBIGUOUS", str(item[0])))
            for neighbor, edge in neighbors:
                if neighbor in selected_ids or neighbor not in by_id:
                    continue
                selected_ids.add(neighbor)
                traversed.append(edge)
                frontier.append((neighbor, hop + 1))
                if len(selected_ids) >= max_nodes:
                    break
        nodes = anchors + sorted((by_id[node_id] for node_id in selected_ids
                                  if node_id not in {node.get("id") for node in anchors}),
                                 key=lambda node: (not re.search(r"test", str(node.get("file") or ""), re.I),
                                                   -int(node.get("degree") or 0), str(node.get("id"))))
        node_ids = {node.get("id") for node in nodes}
        links = [link for link in graph.get("links", [])
                 if link.get("source") in node_ids and link.get("target") in node_ids]
        result = {
            "request": str(request or "").strip(), "intent": "impact", "intent_terms": request_terms,
            "matched": anchors[:5], "nodes": nodes[:max_nodes], "links": links,
            "complete_for": ["impact"], "missing": [] if len(nodes) > len(anchors) else ["consumers"],
            "negative_evidence": ({"consumers": 0, "meaning": "no incoming indexed consumer relation"}
                                  if not any(node.get("kind") != "file" and node not in anchors for node in nodes) else {}),
            "guidance": "Report only directional consumers/contracts in links; cite file and line; verify AMBIGUOUS.",
            "planner": "adaptive-impact-v2",
            "budget": {"requested_ceiling": requested_ceiling, "max_nodes": max_nodes, "selected_nodes": len(nodes[:max_nodes])},
            "stopping": {"sufficient_evidence": bool(anchors), "reason": "exact target and directional traversal completed"},
            "operation_limit": 4,
        }
        implementation = _implementation_context(graph, request, anchors[:5], nodes[:max_nodes])
        if implementation:
            result["implementation_context"] = implementation
            result["guidance"] += " " + _EDIT_EXECUTION_GUIDANCE
        from .answer_validation import validate_context_package
        result["validation"] = validate_context_package(graph, result)
        result["do_not_expand"] = _intent_can_stop(result)
        return result
    ranked = []
    strong_semantic_ids: set[str] = set()
    for node in all_nodes:
        operations = node.get("operations") or []
        filtered_ops = []
        operation_request_hits = 0
        for op in operations:
            searchable = f"{op.get('name', '')} {op.get('text', '')}".lower()
            operation_filters = list(markers)
            operation_name = str(op.get("name") or "").lower()
            if (not operation_filters or any(marker in searchable for marker in operation_filters)
                    or operation_name in request_terms
                    or any(term in searchable for term in request_terms)):
                filtered_ops.append(op)
            operation_request_hits += sum(
                1 for term in symbol_terms
                if len(term) >= 5 and term in searchable
            )
        copy = dict(node)
        if node.get("container") and node.get("kind") in ("method", "function"):
            owner = next((candidate for candidate in all_nodes
                          if candidate.get("file") == node.get("file")
                          and candidate.get("name") == node.get("container")
                          and candidate.get("kind") in ("class", "interface", "struct")), None)
            if owner and owner.get("signature"):
                copy["owner_signature"] = owner["signature"]
        if filtered_ops:
            copy["operations"] = filtered_ops
        elif "operations" in copy:
            copy.pop("operations")
        kind_relevant = selected_intent == "tests" and re.search(
            r"test", str(node.get("file") or ""), re.I
        )
        fields = " ".join(str(node.get(key) or "") for key in ("name", "container", "file", "signature", "kind")).lower()
        lexical_hits = sum(term in fields for term in request_terms)
        concept_hits = sum(term in fields for term in list(markers) + expansions)
        identity = {
            str(node.get("name") or "").lower(),
            str(node.get("container") or "").lower(),
        }
        # Expansions improve semantic recall but must not masquerade as a
        # user-named symbol (e.g. Spanish "borrado" expanding to `delete`).
        exact_hits = (sum(term in identity for term in symbol_terms)
                      if node.get("kind") not in {"file", "module", "documentation_section", "doc", "image", "media"}
                      else 0)
        if exact_hits and operations:
            # For an explicitly named component, its state transitions and
            # control flow are relevant even when operation names are generic
            # (encode, append, assign, return, etc.).
            filtered_ops = operations
            copy["operations"] = operations
        path = str(node.get("file") or "").replace("\\", "/")
        primary_bonus = 50 if path.startswith(("src/", "backend/", "app/")) else 0
        test_penalty = -250 if selected_intent != "tests" and not tests_requested and re.search(
            r"(?:^|/)(?:tests?|fixtures?)(?:/|$|[_.])", path, re.I
        ) else 0
        benchmark_penalty = -400 if "benchmark" not in request_lower and re.search(
            r"(?:^|/)benchmarks?(?:/|$)", path, re.I
        ) else 0
        anchor_bonus = 90 if path in anchor_files else 0
        container_bonus = 160 if str(node.get("container") or "").lower() in explicit_names else 0
        qualified_bonus = 900 if qualified_match(node) else 0
        entry_request = any(term in direct_terms for term in ("entry", "entrypoint", "entry-point"))
        entry_name = str(node.get("name") or "").lower() in {"__call__", "servehttp", "main", "run"}
        entry_file = bool(re.search(r"(?:^|/)(?:applications?|app|main|server)\.[^.]+$", path, re.I))
        entry_bonus = 1_200 if entry_request and entry_name and entry_file else 0
        capture_bonus = 700 if any(term in direct_terms for term in ("capture", "captured")) and str(node.get("name") or "").lower() == "findroute" else 0
        docker_bonus = 1_200 if docker_requested and re.search(r"(?:^|/)(?:dockerfile|docker-compose[^/]*)$", path, re.I) else 0
        verifier_bonus = 700 if verifier_requested and re.search(
            r"verif|comprob|instala|backup|respaldo", f"{path} {node.get('name', '')}", re.I
        ) else 0
        generation_bonus = 900 if any(
            pattern.search(f"{path} {node.get('name', '')}")
            for label, pattern in requested_concerns.items() if label.endswith("_generation")
        ) else 0
        score = (min(6, len(filtered_ops)) * 25 + min(4, operation_request_hits) * 300
                 + lexical_hits * 10 + concept_hits * 45 + exact_hits * 400 + qualified_bonus
                 + int(bool(kind_relevant)) * 100 + primary_bonus + test_penalty + benchmark_penalty
                 + anchor_bonus + container_bonus
                 + entry_bonus + capture_bonus
                 + docker_bonus + verifier_bonus + generation_bonus
                 + int(node.get("kind") == "route" and lexical_hits > 0) * 180
                 + int(node.get("kind") in ("method", "class", "interface")) * 10
                 + min(10, int(node.get("degree") or 0)))
        concept_allowed = selected_intent in ("flow", "tests", "impact")
        # Flow requests often name the exact framework component (for example
        # ``SessionMiddleware``) without using one of our domain operation
        # markers. Exact lexical evidence must remain eligible; otherwise
        # generic high-degree call sites crowd the requested component out.
        if (filtered_ops or kind_relevant or docker_bonus or verifier_bonus or generation_bonus
                or (concept_allowed and (concept_hits or lexical_hits))
                or (selected_intent in ("tests", "impact") and lexical_hits)):
            ranked.append((score, copy))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    if not anchor_files and any(term in direct_terms for term in ("entry", "entrypoint", "entry-point")):
        entry_anchor = next((node for _, node in ranked
                             if str(node.get("name") or "").lower() in {"__call__", "servehttp", "main", "run"}
                             and node.get("file")), None)
        if entry_anchor:
            anchor_files = {str(entry_anchor["file"])}
    if any(term in direct_terms for term in ("capture", "captured")):
        capture_ids = {
            node.get("id") for node in all_nodes
            if str(node.get("name") or "").lower() in {"findroute", "find_route"}
        }
        ranked = ([(900_000, dict(node)) for node in all_nodes if node.get("id") in capture_ids]
                  + [item for item in ranked if item[1].get("id") not in capture_ids])
    if qualified_nodes:
        # Qualified references are declarations, not search hints. Guarantee
        # their place before homonyms even when another symbol has more
        # operations or a higher graph degree.
        qualified_ids = {node.get("id") for node in qualified_nodes}
        qualified_ranked = [(1_000_000, dict(node)) for node in qualified_nodes]
        ranked = qualified_ranked + [item for item in ranked if item[1].get("id") not in qualified_ids]
    # Semantic retrieval is a recall fallback, never a replacement for exact
    # symbol/operation evidence. It remains local and deterministic unless an
    # explicit GRAPHTYN_EMBED_MODEL is configured.
    if not explicit_names or len(ranked) < max(3, max_nodes // 2):
        from .semantic_index import semantic_search
        ranked_ids = {item[1].get("id") for item in ranked}
        for hit in semantic_search(graph, request, limit=max_nodes):
            node = hit["node"]
            semantic_path = str(node.get("file") or "").replace("\\", "/")
            if "benchmark" not in request_lower and re.search(r"(?:^|/)benchmarks?(?:/|$)", semantic_path, re.I):
                continue
            if selected_intent != "tests" and re.search(
                r"(?:^|/)(?:tests?|fixtures?)(?:/|$|[_.])", semantic_path, re.I
            ):
                continue
            if hit["score"] >= 0.20:
                strong_semantic_ids.add(str(node.get("id") or ""))
            if node.get("id") not in ranked_ids and hit["score"] >= 0.08:
                ranked.append((int(40 + hit["score"] * 100), dict(node)))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    # Multi-obligation tasks need one strong representative per requested
    # concern. A single prolific verifier or test file must not consume the
    # complete node budget before configuration and runtime code are shown.
    def searchable_node(node: dict[str, Any]) -> str:
        return (
            " ".join(str(node.get(key) or "") for key in
                     ("name", "container", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                               for op in node.get("operations", []))
        ).lower()

    def concern_matches(label: str, pattern: re.Pattern[str], node: dict[str, Any]) -> bool:
        if label.endswith("_generation"):
            identity = " ".join(str(node.get(key) or "") for key in
                                ("name", "file", "signature")).lower()
            return bool(pattern.search(identity))
        return bool(pattern.search(searchable_node(node)))

    generation_patterns = {label: pattern for label, pattern in requested_concerns.items()
                           if label.endswith("_generation")}
    if generation_patterns:
        ranked_ids = {item[1].get("id") for item in ranked}
        ranked.extend(
            (2_000, dict(node)) for node in all_nodes
            if node.get("id") not in ranked_ids
            and any(concern_matches(label, pattern, node)
                    for label, pattern in generation_patterns.items())
        )
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))

    mandatory: list[tuple[int, dict[str, Any]]] = []
    predicates = []
    if explicit_identifiers:
        explicit_candidates = [
            item for item in ranked
            if any(identifier in searchable_node(item[1]) for identifier in explicit_identifiers)
        ]
        if explicit_candidates:
            ordered_explicit = sorted(
                explicit_candidates,
                key=lambda item: (
                    not bool(re.search(
                        r"(?:^|/)(?:tests?|fixtures?|benchmarks?)(?:/|$|[_.])",
                        str(item[1].get("file") or ""), re.I,
                    )),
                    sum(searchable_node(item[1]).count(identifier)
                        for identifier in explicit_identifiers),
                ),
                reverse=True,
            )
            explicit_files: set[str] = set()
            for candidate in ordered_explicit:
                path = str(candidate[1].get("file") or "")
                if path in explicit_files:
                    continue
                mandatory.append(candidate)
                explicit_files.add(path)
                if len(explicit_files) >= 2:
                    break
    if docker_requested:
        predicates.append(lambda node: bool(re.search(
            r"(?:^|/)(?:dockerfile|docker-compose[^/]*)$",
            str(node.get("file") or node.get("name") or "").replace("\\", "/"), re.I)))
    if tests_requested:
        predicates.append(lambda node: bool(re.search(
            r"(?:^|/)(?:tests?|fixtures?)(?:/|$|[_.])",
            str(node.get("file") or ""), re.I))
            and any(term in searchable_node(node) for term in symbol_terms if len(term) >= 5))
    if verifier_requested:
        predicates.append(lambda node: bool(re.search(
            r"verif|comprob|instala|backup|respaldo", searchable_node(node), re.I)))
    for predicate in predicates:
        candidates = [item for item in ranked
                      if predicate(item[1]) and item[1].get("id") not in
                      {selected[1].get("id") for selected in mandatory}]
        representative = max(
            candidates,
            key=lambda item: sum(searchable_node(item[1]).count(term)
                                 for term in symbol_terms if len(term) >= 5),
            default=None,
        )
        if representative:
            mandatory.append(representative)
    # Prefer a small set of entities that jointly covers the remaining named
    # concerns. This avoids spending one node per question when a loader body
    # proves absence, integrity and identity checks together.
    covered = {
        label for label, pattern in requested_concerns.items()
        if any(concern_matches(label, pattern, item[1]) for item in mandatory)
    }
    remaining = set(requested_concerns) - covered
    while remaining:
        used = {item[1].get("id") for item in mandatory}
        candidates = []
        for item in ranked:
            if item[1].get("id") in used:
                continue
            hits = {label for label in remaining
                    if concern_matches(label, requested_concerns[label], item[1])}
            if hits:
                candidates.append((len(hits), item[0], item, hits))
        if not candidates:
            break
        _count, _score, representative, hits = max(
            candidates, key=lambda candidate: (candidate[0], candidate[1])
        )
        mandatory.append(representative)
        remaining -= hits
    if mandatory:
        mandatory_ids = {item[1].get("id") for item in mandatory}
        ranked = mandatory + [item for item in ranked if item[1].get("id") not in mandatory_ids]
    selection_cap = max_nodes
    if requested_concerns and not remaining:
        # Once every explicit obligation has a representative, a few nearby
        # symbols are enough for context. Filling the full node ceiling adds
        # unrelated lexical matches and makes agents re-read the repository.
        selection_cap = min(max_nodes, max(6, len(mandatory) + 3))
    if anchor_files:
        # A named component is stronger evidence than a translated lexical
        # coincidence elsewhere. Reserve most of the small budget for its
        # implementation while leaving two slots for real cross-file flow.
        anchored = [item for item in ranked if str(item[1].get("file") or "") in anchor_files]
        external = [item for item in ranked if str(item[1].get("file") or "") not in anchor_files]
        reserve = max(1, max_nodes - 2)
        anchor_ids = {item[1].get("id") for item in anchored}
        connected_ids = {
            endpoint
            for link in graph.get("links", [])
            if (link.get("source") in anchor_ids or link.get("target") in anchor_ids)
            and str(link.get("confidence") or "EXTRACTED") != "AMBIGUOUS"
            for endpoint in (link.get("source"), link.get("target"))
        }
        connected = [item for item in external if item[1].get("id") in connected_ids]
        # When the named implementation already fills the evidence reserve,
        # omit unrelated lexical matches; they cost tokens and can mislead the
        # model into joining two independent flows.
        fallback_candidates = [item for item in external if item not in connected]
        # A flow may begin in a named API and be populated in another file
        # without a directly resolved call edge (route-tree parameter capture is
        # a common example). Preserve two high-ranked external stages.
        cross_file_flow = any(marker in request_lower for marker in ("capture", "captured", "through", "across", "handoff"))
        fallback = (fallback_candidates[:2] if selected_intent == "flow" and cross_file_flow
                    else [] if len(anchored) >= reserve else fallback_candidates)
        ranked = (anchored[:reserve] + fallback + connected + anchored[reserve:]
                  if cross_file_flow else anchored[:reserve] + connected + fallback + anchored[reserve:])
    nodes = []
    seen_roles = set()
    laravel_labels = {"despacha", "invoca ruta", "valida con", "crea", "despacha evento"}
    has_laravel = any(link.get("label") in laravel_labels for link in graph.get("links", []))
    laravel_request = has_laravel and selected_intent == "flow" and any(
        str(node.get("file") or "").lower().endswith((".php", ".tsx", ".jsx")) or node.get("kind") == "route"
        for _, node in ranked[:4]
    )
    lexical_cap = max(4, selection_cap - 4) if laravel_request else selection_cap
    for _, node in ranked:
        role_name = str(node.get("name") or "").lower()
        role = (role_name, str(node.get("container") or "").lower(), node.get("kind"),
                str(node.get("file") or "") if role_name in {"main", "run"} else "")
        if role in seen_roles:
            continue
        seen_roles.add(role)
        nodes.append(node)
        if len(nodes) >= max(1, lexical_cap):
            break
    if laravel_request:
        by_id = {node.get("id"): node for node in all_nodes}
        selected_ids = {node.get("id") for node in nodes}
        projected_links: list[dict[str, Any]] = []
        # Two hops connect controller↔route↔TSX while one hop brings in
        # FormRequests, models and dispatched events.
        # Preserve cross-layer recall first. Routes and controllers are often
        # already lexical anchors; the scarce expansion slots should bring in
        # their React/Inertia callers before fanning out through backend peers.
        relation_priority = {"invoca ruta": 0, "despacha": 1, "valida con": 2, "crea": 3, "despacha evento": 4}
        relevant_links = sorted(
            (link for link in graph.get("links", []) if link.get("label") in laravel_labels),
            key=lambda link: (relation_priority.get(str(link.get("label")), 9), str(link.get("source"))),
        )
        for hop in range(2):
            hop_cap = max_nodes - 1 if hop == 0 else max_nodes
            for link in relevant_links:
                if link.get("label") not in laravel_labels:
                    continue
                source, target = link.get("source"), link.get("target")
                candidate_id = target if source in selected_ids else source if target in selected_ids else None
                candidate = by_id.get(candidate_id)
                if candidate and candidate.get("kind") == "file":
                    file_endpoint = candidate_id
                    rel_file = str(candidate.get("details") or candidate.get("name") or "")
                    file_symbols = [item for item in all_nodes if item.get("file") == rel_file and item.get("operations")]
                    if file_symbols:
                        edge_line = int(link.get("line") or 0)
                        edge_evidence = f"{link.get('evidence', '')} {by_id.get(target, {}).get('name', '')}".lower()
                        evidence_terms = [term for term in re.findall(r"[a-z][\w.-]{3,}", edge_evidence)
                                          if term not in {"route", "invoca", "ruta"}]

                        def frontend_score(item: dict[str, Any]) -> tuple[int, int]:
                            operations = item.get("operations") or []
                            operation_text = " ".join(str(op.get("text") or op.get("name") or "") for op in operations).lower()
                            start, end = int(item.get("line") or 0), int(item.get("end_line") or 0)
                            covers_edge = bool(edge_line and start <= edge_line <= max(start, end))
                            evidence_hits = sum(term in operation_text for term in evidence_terms)
                            return (int(covers_edge) * 10_000 + evidence_hits * 500 + len(operations), -start)

                        candidate = max(file_symbols, key=frontend_score)
                        candidate_id = candidate.get("id")
                        candidate = dict(candidate)
                        focus_terms = set(request_terms + evidence_terms + ["permission", "permissions", "status", "route", "router"])
                        focused_ops = [
                            op for op in candidate.get("operations") or []
                            if (abs(int(op.get("line") or 0) - edge_line) <= 5
                                or any(term in f"{op.get('name', '')} {op.get('text', '')}".lower()
                                       for term in focus_terms))
                        ]
                        if focused_ops:
                            candidate["operations"] = focused_ops
                        projected = dict(link)
                        projected["source" if file_endpoint == source else "target"] = candidate_id
                        projected["projected_from"] = f"file:{rel_file}"
                        projected_links.append(projected)
                if not candidate:
                    continue
                if candidate_id in selected_ids:
                    for index, selected in enumerate(nodes):
                        if selected.get("id") != candidate_id:
                            continue
                        merged = dict(selected)
                        existing_ops = merged.get("operations") or []
                        seen_ops = {(op.get("kind"), op.get("name"), op.get("line"), op.get("text")) for op in existing_ops}
                        merged["operations"] = existing_ops + [
                            op for op in candidate.get("operations") or []
                            if (op.get("kind"), op.get("name"), op.get("line"), op.get("text")) not in seen_ops
                        ]
                        nodes[index] = merged
                        break
                    continue
                role_name = str(candidate.get("name") or "").lower()
                role = (role_name, str(candidate.get("container") or "").lower(), candidate.get("kind"),
                        str(candidate.get("file") or "") if role_name in {"main", "run"} else "")
                if role in seen_roles:
                    continue
                nodes.append(candidate)
                selected_ids.add(candidate_id)
                seen_roles.add(role)
                if len(nodes) >= hop_cap:
                    break
            if len(nodes) >= max_nodes:
                break
    else:
        projected_links = []
    node_ids = {node.get("id") for node in nodes}
    links = [link for link in graph.get("links", [])
             if link.get("source") in node_ids and link.get("target") in node_ids]
    links.extend(link for link in projected_links
                 if link.get("source") in node_ids and link.get("target") in node_ids
                 and link not in links)
    files = sorted({node.get("file") for node in nodes if node.get("file")})
    has_tests = any(re.search(r"test", str(path), re.I) for path in files)
    exact_matched = sorted(
        (node for node in nodes
         if str(node.get("name") or "").lower() in symbol_terms
         and node.get("kind") not in {"file", "module", "documentation_section", "doc", "image", "media"}),
        key=lambda node: (not qualified_match(node), -int(node.get("degree") or 0), str(node.get("id") or "")),
    )
    remaining_matches = [node for node in nodes if node not in exact_matched]
    if any(term in direct_terms for term in ("capture", "captured")):
        remaining_matches.sort(key=lambda node: (
            str(node.get("name") or "").lower() not in {"findroute", "find_route"},
            str(node.get("id") or ""),
        ))
    matched = exact_matched + remaining_matches
    complete_for, missing = _intent_evidence_status(selected_intent, has_tests)
    selected_paths = [str(node.get("file") or node.get("name") or "").replace("\\", "/").lower()
                      for node in nodes]
    selected_names = [str(node.get("name") or "").lower() for node in nodes]
    if tests_requested and not any(re.search(r"(?:^|/)(?:tests?|fixtures?)(?:/|$|[_.])", path)
                                   for path in selected_paths):
        missing.append("tests")
    if docker_requested and not any(re.search(r"(?:^|/)(?:dockerfile|docker-compose[^/]*)$", path)
                                    for path in selected_paths):
        missing.append("docker_configuration")
    if verifier_requested and not any(re.search(r"verif|comprob|instala|backup|respaldo", f"{path} {name}")
                                      for path, name in zip(selected_paths, selected_names)):
        missing.append("verifiers")
    missing = list(dict.fromkeys(missing))
    if missing:
        complete_for = []
    lexical_anchor_ids = {
        str(node.get("id") or "")
        for node in nodes
        if node.get("kind") not in {"file", "module", "documentation_section", "doc", "image", "media"}
        and any(len(term) >= 5 and term in
                f"{node.get('name', '')} {node.get('container', '')}".lower()
                for term in symbol_terms)
    }
    operation_anchor_ids = {
        str(node.get("id") or "")
        for node in nodes
        if any(any(len(term) >= 5 and term in f"{op.get('name', '')} {op.get('text', '')}".lower()
                   for term in [*symbol_terms, *expansions])
               for op in node.get("operations", []))
    }
    corroborated_semantic_ids = {
        str(node.get("id") or "")
        for node in nodes
        if str(node.get("id") or "") in strong_semantic_ids
        and node.get("kind") not in {"file", "module", "documentation_section", "doc", "image", "media"}
        and any(len(term) >= 5 and term in
                " ".join(str(node.get(key) or "") for key in
                         ("name", "container", "file", "signature", "details")).lower()
                for term in symbol_terms)
    }
    relevant_ids = ({str(node.get("id") or "") for node in exact_matched}
                    | lexical_anchor_ids | operation_anchor_ids | corroborated_semantic_ids)
    evidence_relevant = bool(relevant_ids.intersection(str(node.get("id") or "") for node in nodes))
    if explicit_identifiers:
        selected_text = " ".join(
            " ".join(str(node.get(key) or "") for key in
                     ("name", "container", "file", "signature", "details"))
            + " " + " ".join(f"{op.get('name', '')} {op.get('text', '')}"
                               for op in node.get("operations", []))
            for node in nodes
        ).lower()
        evidence_relevant = evidence_relevant and any(identifier in selected_text
                                                       for identifier in explicit_identifiers)
    if not evidence_relevant:
        missing = [*missing, "relevant_anchor"]
        complete_for = []
    missing_concerns = [label for label, pattern in requested_concerns.items()
                        if not any(concern_matches(label, pattern, node) for node in nodes)]
    obligation_evidence = {
        label: [str(node.get("id")) for node in nodes
                if node.get("id") and concern_matches(label, pattern, node)]
        for label, pattern in requested_concerns.items()
    }
    if missing_concerns:
        missing = list(dict.fromkeys([*missing, *missing_concerns]))
        complete_for = []
    result = {
        "request": str(request or "").strip(),
        "intent": selected_intent,
        "requested_obligations": list(requested_concerns),
        "obligation_evidence": obligation_evidence,
        "intent_terms": request_terms + list(markers),
        "matched": matched[:min(5, len(matched))],
        "nodes": nodes,
        "links": links,
        "complete_for": complete_for,
        "missing": missing,
        "do_not_expand": bool(nodes) and not missing,
        "guidance": "Answer now from ops and relations. Cite aliases. Do not call another graph tool when do_not_expand=true.",
        "planner": "adaptive-intent-v2",
        "budget": {"requested_ceiling": requested_ceiling, "max_nodes": max_nodes,
                   "selected_nodes": len(nodes), "complexity": complexity},
        "stopping": {"sufficient_evidence": bool(nodes) and evidence_relevant and not missing,
                     "reason": ("relevant exact or semantic anchor selected" if evidence_relevant
                                else "no relevant anchor selected")},
        "operation_limit": {"bindings": 10, "persistence": 6, "tests": 5, "impact": 5, "flow": 5}[selected_intent],
    }
    if "relevant_anchor" in missing:
        exact_queries = list(dict.fromkeys([
            *explicit_identifiers,
            *(term for term in symbol_terms if len(term) >= 5),
        ]))[:3]
        result["anchor_fallback"] = {
            "reason": "relevant_anchor_missing",
            "strategy": "one_exact_search_then_extend",
            "exact_queries": exact_queries,
            "max_results": 5,
            "max_expansions": 1,
            "broad_search_allowed": False,
        }
    implementation = _implementation_context(graph, request, result["matched"], nodes)
    if implementation:
        result["implementation_context"] = implementation
        result["guidance"] += " " + _EDIT_EXECUTION_GUIDANCE
        if tests_requested and implementation.get("test_files") and "tests" in result["missing"]:
            result["missing"] = [item for item in result["missing"] if item != "tests"]
            if not result["missing"]:
                result["complete_for"] = [selected_intent]
            result["stopping"]["sufficient_evidence"] = bool(nodes) and evidence_relevant \
                and not result["missing"]
    from .answer_validation import validate_context_package
    result["validation"] = validate_context_package(graph, result)
    result["do_not_expand"] = _intent_can_stop(result)
    return result


def analyze_change(graph: dict[str, Any], request: str, max_nodes: int = 18) -> dict[str, Any]:
    """Build an auditable implementation brief without invoking an LLM.

    The result is intentionally suitable as direct agent context or as the
    grounded input to a local/cloud model. Every target remains backed by an
    indexed node and every dependency by an indexed edge.
    """
    request = str(request or "").strip()
    terms = _terms(request)
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    ranked: list[tuple[int, dict]] = []
    for node in nodes:
        fields = " ".join(str(node.get(key) or "") for key in
                          ("name", "container", "file", "signature", "details", "kind")).lower()
        operation_text = " ".join(
            f"{op.get('kind', '')} {op.get('name', '')} {op.get('text', '')}"
            for op in node.get("operations", [])
        ).lower()
        fields = f"{fields} {operation_text}"
        hits = sum(term in fields for term in terms)
        if not hits:
            continue
        exact = sum(term == str(node.get("name") or "").lower() for term in terms)
        kind_bonus = 15 if node.get("kind") not in ("file", "module") else 0
        operation_hits = sum(term in operation_text for term in terms)
        path = str(node.get("file") or "").replace("\\", "/")
        primary_source_bonus = 35 if path.startswith("src/") else 0
        ranked.append((hits * 20 + operation_hits * 25 + exact * 80 + kind_bonus + primary_source_bonus + min(15, int(node.get("degree") or 0)), node))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    seeds = [node for _, node in ranked[:5]]
    seed_ids = {node.get("id") for node in seeds}

    adjacent_ids = set(seed_ids)
    relevant_links = []
    for link in links:
        if link.get("source") in seed_ids or link.get("target") in seed_ids:
            relevant_links.append(link)
            adjacent_ids.update((link.get("source"), link.get("target")))
    nodes_by_id = {node.get("id"): node for node in nodes}
    selected = [nodes_by_id[node_id] for node_id in adjacent_ids if node_id in nodes_by_id]
    selected.sort(key=lambda node: (node.get("id") not in seed_ids, -int(node.get("degree") or 0), str(node.get("id"))))
    selected = selected[:max(1, max_nodes)]
    selected_ids = {node.get("id") for node in selected}
    relevant_links = [link for link in relevant_links
                      if link.get("source") in selected_ids and link.get("target") in selected_ids]

    files = sorted({str(node.get("file")) for node in selected if node.get("file")})
    tests = sorted({path for path in files if re.search(r"(?:^|[/_.])tests?(?:[/_.]|$)", path, re.I)})
    contracts = [node for node in selected if node.get("kind") in ("interface", "property", "event")]
    state = [node for node in selected if node.get("kind") in ("field", "property")]
    operation_kinds = sorted({op.get("kind") for node in selected for op in node.get("operations", []) if op.get("kind")})
    ambiguous = sum(str(link.get("confidence")) == "AMBIGUOUS" for link in relevant_links)
    confidence = "high" if seeds and not ambiguous else "medium" if seeds else "low"

    actions = []
    if seeds:
        actions.append("Modificar primero los targets y preservar sus firmas públicas salvo requisito explícito.")
        if contracts:
            actions.append("Revisar contratos, propiedades y eventos antes de ajustar consumidores.")
        if state:
            actions.append("Comprobar inicialización, mutación y ciclo de vida del estado identificado.")
        actions.append("Actualizar o crear pruebas para cada comportamiento y consumidor afectado.")
    else:
        actions.append("Aclarar nombres de símbolos o dominio: el índice no encontró evidencia suficiente.")

    risks = []
    if ambiguous:
        risks.append(f"{ambiguous} relaciones ambiguas requieren confirmación antes de editar.")
    if seeds and not tests:
        risks.append("No aparecen pruebas adyacentes en el subgrafo; buscar o crear cobertura dirigida.")
    if not seeds:
        risks.append("La solicitud no coincide con símbolos indexados.")

    return {
        "request": request,
        "intent_terms": terms,
        "matched": seeds,
        "nodes": selected,
        "links": relevant_links,
        "plan": {
            "confidence": confidence,
            "target_ids": [node.get("id") for node in seeds],
            "files": files,
            "contracts": [node.get("id") for node in contracts],
            "state": [node.get("id") for node in state],
            "operation_kinds": operation_kinds,
            "tests": tests,
            "actions": actions,
            "risks": risks,
            "answer_guidance": "ops are line-level method-body evidence; when complete=true answer from them without reconfirming source text",
        },
        "grounding": "deterministic-index; AI suggestions must cite entity aliases and must not invent edges",
    }
