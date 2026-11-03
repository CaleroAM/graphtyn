import json
from pathlib import Path

import pytest

from graphtyn.core import prompt_context
from graphtyn.mcp_server import lean_payload


def _package(**overrides):
    package = {
        "intent": "flow", "request": "Traza processCommand", "planner": "adaptive-intent-v2",
        "budget": {"max_nodes": 10}, "timing_ms": {"total": 3.0}, "evidence_mode": "precision",
        "format": "evidence-v1", "estimated_tokens": 900, "complete": True,
        "validation": {"ok": True, "ambiguous_relations": 0, "nodes": 3},
        "stopping": {"sufficient_evidence": True}, "do_not_expand": True, "missing": [],
        "complete_for": ["flow"], "source_coverage": {"complete": True},
        "guidance": "Cite file:line. Cite file:line. Do not call another tool.",
        "files": {"F1": "src/server.c", "F2": "src/debug.c"},
        "entities": {
            "N1": {"name": "processCommand", "kind": "function", "at": "F1:10",
                   "signature": "int processCommand(client *c)",
                   "ops": [["call", "lookupCommand", 11, "lookupCommand(c)"],
                           ["call", "call", 40, "call(c)"]]},
            "N2": {"name": "lookupCommand", "kind": "function", "at": "F1:80"},
            "N3": {"name": "genInfoString", "kind": "function", "at": "F2:5"},
            "N4": {"name": "main", "kind": "function", "at": "F2:90"},
        },
        "relations": [["N4", "llama", "N3", "I", 91], ["N1", "llama", "N2", "E", 11]],
        "coverage": {"incoming_calls_or_uses": 0}, "negative_evidence": ["no incoming"],
        "citations": ["src/server.c:10-20 processCommand", "src/debug.c:5 genInfoString"],
        "source_evidence": [{"symbol": "processCommand", "file": "src/server.c", "start_line": 10,
                             "end_line": 20, "text": "10: int processCommand(client *c) {\n"
                                                     "11: cmd = lookupCommand(c);\n…: (5 lines omitted)"}],
        "project_context": {"workspace": "/w", "project_id": None, "project_name": "w",
                            "project_aliases": [], "scope": "project"},
    }
    package.update(overrides)
    return package


def test_lean_payload_drops_unrelated_entities_and_repeated_lines():
    lean = lean_payload(_package())

    assert set(lean["entities"]) == {"N1", "N2"}
    assert lean["omitted_unrelated_entities"] == 2
    assert lean["relations"] == [["N1", "llama", "N2", "E", 11]]
    assert lean["files"] == {"F1": "src/server.c"}
    # Signature and line 11 are printed in the excerpt; line 40 is not.
    assert "signature" not in lean["entities"]["N1"]
    assert lean["entities"]["N1"]["ops"] == [["call", "call", 40, "call(c)"]]
    assert lean["citations"] == ["src/server.c:10-20 processCommand"]
    assert lean["guidance"] == "Cite file:line. Do not call another tool."
    for key in ("request", "planner", "budget", "timing_ms", "validation", "stopping", "coverage",
                "negative_evidence", "estimated_tokens"):
        assert key not in lean
    assert lean["project_context"] == {"workspace": "/w", "project_name": "w"}
    assert lean["payload_tokens"] < lean_payload(_package(entities={}, relations=[]))["payload_tokens"] + 400


def test_lean_payload_keeps_relational_evidence_and_open_packages():
    impact = lean_payload(_package(intent="impact"))
    assert set(impact["entities"]) == {"N1", "N2", "N3", "N4"}
    assert impact["negative_evidence"] == ["no incoming"]

    unfinished = lean_payload(_package(do_not_expand=False, missing=["failure_semantics"]))
    assert "N4" in unfinished["entities"]
    assert unfinished["stopping"] == {"sufficient_evidence": True}

    ambiguous = lean_payload(_package(validation={"ok": True, "ambiguous_relations": 2, "policy": "p"}))
    assert ambiguous["validation"] == {"ok": True, "ambiguous_relations": 2, "policy": "p"}


@pytest.mark.parametrize("prompt, expected", [
    ("Traza cómo Redis procesa un comando desde processCommand", (True, "code_anchor")),
    ("Explain how ActiveRecord::Base#save persists a record", (True, "code_anchor")),
    ("Wie funktioniert der Ablauf in handle_request genau?", (True, "code_anchor")),
    ("Explique o fluxo de pagamento deste projeto, por favor", (True, "code_request")),
    ("Où est appelée la fonction de validation du panier ?", (True, "code_request")),
    ("Erkläre die Architektur dieses Projekts im Detail", (True, "code_request")),
    ("Cosa hai fatto nella sessione precedente con validate_cart?", (False, "history_question")),
    ("Bonjour, comment allez-vous aujourd'hui ?", (False, "not_a_code_request")),
    ("¿Qué hace el módulo de pagos y dónde valida la tarjeta?", (True, "code_request")),
    ("hola, ¿cómo estás hoy?", (False, "not_a_code_request")),
    ("/review este cambio por favor", (False, "client_command")),
    ("¿Qué hiciste en la sesión anterior con el flujo de pagos?", (False, "history_question")),
    ("Explícame la diferencia entre amor y cariño", (False, "no_code_anchor")),
])
def test_prefetch_gate(prompt, expected):
    assert prompt_context.should_prefetch(prompt) == expected


def _indexed_project(tmp_path, monkeypatch):
    from graphtyn.cli import main
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()
    (project / "flow.py").write_text(
        "def run_order(order):\n    if not validate_order(order):\n        return False\n"
        "    return persist_order(order)\n\n"
        "def validate_order(order):\n    return bool(order)\n\n"
        "def persist_order(order):\n    return order\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["graphtyn", "reindex", "--path", str(project)])
    main()
    return project


def test_prompt_hook_injects_the_mcp_package_only_for_code_prompts(tmp_path, monkeypatch, capsys):
    project = _indexed_project(tmp_path, monkeypatch)
    capsys.readouterr()
    request = "Explica el orden exacto y las condiciones de run_order"

    outcome = prompt_context.handle_prompt_hook({"prompt": request, "cwd": str(project)})

    assert outcome["injected"] is True and outcome["path"] == str(project.resolve())
    output = json.loads(prompt_context.hook_output(outcome))["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    context = output["additionalContext"]
    assert context.startswith(f'<graphtyn-context context_id="{outcome["context_id"]}">')
    status = json.loads(next(line for line in context.split("\n") if line.startswith("status: "))[8:])
    assert status["intent"] == "flow"
    assert "validate_order" in context and "flow.py:" in context
    assert "planner" not in context and len(context) <= prompt_context.MAX_CONTEXT_CHARACTERS
    skipped = prompt_context.handle_prompt_hook({"prompt": "hola, ¿qué tal el día?", "cwd": str(project)})
    assert skipped == {"injected": False, "reason": "not_a_code_request"}
    assert prompt_context.hook_output(skipped) == ""


def test_prompt_hook_never_builds_an_index_and_respects_the_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
    request = {"prompt": "Explica el orden exacto y las condiciones de run_order", "cwd": str(tmp_path)}
    assert prompt_context.handle_prompt_hook(request) == {"injected": False, "reason": "no_index"}

    project = _indexed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(prompt_context, "prefetch_package", lambda *_args: __import__("time").sleep(2))
    slow = prompt_context.handle_prompt_hook({**request, "cwd": str(project)}, budget_seconds=0.1)
    assert slow["reason"] == "time_budget_exceeded"


def test_prompt_hook_install_is_reversible_and_preserves_user_hooks(tmp_path):
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    user_hook = {"hooks": [{"type": "command", "command": "echo mine"}]}
    settings.write_text(json.dumps({"hooks": {"UserPromptSubmit": [user_hook]}}))

    prompt_context.install_prompt_hook(tmp_path)
    prompt_context.install_prompt_hook(tmp_path)
    groups = json.loads(settings.read_text())["hooks"]["UserPromptSubmit"]
    assert len(groups) == 2 and groups[0] == user_hook
    assert [hook["command"] for hook in groups[1]["hooks"]] == [
        f"{prompt_context.HOOK_COMMAND} --part 1 --parts 2", f"{prompt_context.HOOK_COMMAND} --part 2 --parts 2"]
    assert prompt_context.prompt_hook_installed(tmp_path)

    assert prompt_context.uninstall_prompt_hook(tmp_path)["removed"] is True
    assert json.loads(settings.read_text())["hooks"]["UserPromptSubmit"] == [user_hook]
    assert not prompt_context.prompt_hook_installed(tmp_path)


def test_cli_install_requires_consent(tmp_path, monkeypatch):
    from graphtyn.cli import main
    monkeypatch.setattr("sys.argv", ["graphtyn", "claude-context", "install", "--path", str(tmp_path)])
    with pytest.raises(SystemExit):
        main()
    assert not (tmp_path / ".claude" / "settings.local.json").exists()


def test_hook_invocation_pins_root_with_quoting():
    command = prompt_context.hook_invocation("/opt/g tyn/graphtyn", Path("/w/my project"))
    assert command == "'/opt/g tyn/graphtyn' claude-context hook --path '/w/my project'"


def test_rendered_context_fits_the_client_cap_and_trims_secondary_excerpts_first():
    long_body = "\n".join(f"{number}: line {number} " + "x" * 60 for number in range(1, 301))
    package = lean_payload(_package(source_evidence=[
        {"symbol": "processCommand", "file": "src/server.c", "start_line": 1, "end_line": 300,
         "covers": ["source_symbol:processcommand"], "text": long_body},
        {"symbol": "helper", "file": "src/util.c", "start_line": 1, "end_line": 300, "covers": [],
         "text": long_body},
    ], source_coverage={"complete": True, "required_symbols": {"processcommand": True}}))
    package["context_id"] = "abc"

    text = prompt_context.render_context(package)

    assert text is not None and len(text) <= prompt_context.MAX_CONTEXT_CHARACTERS * prompt_context.PARTS
    assert "== src/server.c:1-300 processCommand" in text
    assert "1: line 1 " in text and "300: line 300 " in text
    assert "alias" not in text.split("guidance:", 1)[-1].split("\n", 1)[0]
    assert prompt_context.render_context(package, limit=300) is None


def test_evidence_result_does_not_mutate_the_internal_package():
    from graphtyn.mcp_server import evidence_result
    excerpt = {"symbol": "f", "file": "a.py", "start_line": 1, "end_line": 400, "covers": [],
               "text": "\n".join(f"{n}: " + "y" * 80 for n in range(1, 401))}
    raw = {"intent": "flow", "matched": [], "nodes": [], "links": [], "source_evidence": [excerpt]}

    evidence_result(raw, max_nodes=4, token_budget=600)

    assert raw["source_evidence"][0] is excerpt and excerpt["text"].count("\n") == 399


def test_large_context_is_split_into_labelled_parts_under_the_per_hook_cap():
    text = '<graphtyn-context context_id="abc">\n' + "\n".join(f"{n}: " + "w" * 90 for n in range(150)) + "\n</graphtyn-context>"
    parts = prompt_context.split_context(text, 2)

    assert len(parts) == 2 and all(len(part) <= prompt_context.MAX_CONTEXT_CHARACTERS for part in parts)
    assert parts[1].startswith("[graphtyn-context abc part 2/2: continues part 1]")
    rejoined = parts[0] + "\n" + parts[1].split("\n", 1)[1]
    assert rejoined == text
    assert prompt_context.split_context("short", 2) == ["short"]
    with pytest.raises(ValueError):
        prompt_context.split_context(text, 1)


def test_header_states_the_stop_rule_only_for_complete_evidence():
    complete = prompt_context.render_context({**lean_payload(_package()), "context_id": "a"})
    partial = prompt_context.render_context({**lean_payload(_package(do_not_expand=False, missing=["x"])),
                                             "context_id": "b"})

    assert "do not re-read or re-verify what it shows" in complete
    # Retrieval can miss a part of the request: the agent may look up that part only.
    assert "look up only that part" in complete
    assert "re-verify" not in partial and "facts listed in missing" in partial


def test_codex_hook_install_is_reversible_and_preserves_user_hooks(tmp_path):
    hooks_file = tmp_path / ".codex" / "hooks.json"
    hooks_file.parent.mkdir()
    user_group = {"hooks": [{"type": "command", "command": "echo mine"}]}
    hooks_file.write_text(json.dumps({"hooks": {"UserPromptSubmit": [user_group]}}))

    prompt_context.install_codex_prompt_hook(tmp_path)
    prompt_context.install_codex_prompt_hook(tmp_path)
    groups = json.loads(hooks_file.read_text())["hooks"]["UserPromptSubmit"]
    assert len(groups) == 2 and groups[0] == user_group
    managed = groups[1]["hooks"][0]
    assert managed["command"] == prompt_context.CODEX_HOOK_COMMAND
    assert managed["additionalContextLimit"] == prompt_context.CODEX_CONTEXT_TOKEN_LIMIT
    assert prompt_context.codex_prompt_hook_installed(tmp_path)

    assert prompt_context.uninstall_codex_prompt_hook(tmp_path)["removed"] is True
    assert json.loads(hooks_file.read_text())["hooks"]["UserPromptSubmit"] == [user_group]
    assert not prompt_context.codex_prompt_hook_installed(tmp_path)


def test_codex_hook_returns_one_block_through_the_cli(tmp_path, monkeypatch, capsys):
    import io
    from graphtyn.cli import main
    project = _indexed_project(tmp_path, monkeypatch)
    capsys.readouterr()
    payload = {"prompt": "Explica el orden exacto y las condiciones de run_order", "cwd": str(project),
               "hook_event_name": "UserPromptSubmit", "turn_id": "t1"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.argv", ["graphtyn", "codex-context", "hook"])

    main()

    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    assert output["additionalContext"].startswith("<graphtyn-context")
    assert output["additionalContext"].rstrip().endswith("</graphtyn-context>")
