#!/usr/bin/env python3
"""Blind conceptual adjudication (rubric v2) of benchmark answers.

`prepare` shuffles every complete answer of the run, labels it with a random
id and writes one packet per corpus with the task, the conceptual criteria and
the anonymous answers. The id → (client, arm, repetition) key goes to a separate
file that the adjudicator must not open before `score`.

`score` joins the adjudicator's judgments with the key. The frozen literal
rubric remains the primary quality metric; this file only reports where a
correct paraphrase fails the literal match, or a literal match is wrong.
"""

from __future__ import annotations

import argparse
import json
import random
import secrets
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Rubric v2: the concept each frozen fact stands for, independent of wording.
CRITERIA = {
    "redis": {
        "entry": "Identifies processCommand in src/server.c as the entry point.",
        "lookup": "Explains command reuse (lastcmd/isCommandReusable) or lookup (lookupCommand).",
        "shape_checks": "Explains at least one of: unknown command rejection, arity check, protected command check.",
        "auth": "Explains the authentication gate (auth required / commands allowed without auth).",
        "acl": "Explains the ACL permission check and its rejection (NOPERM or ACL log).",
        "operational_rejections": "Names at least one concrete operational rejection branch with its source: "
                                  "OOM/eviction, disk write error, insufficient good replicas, master down, "
                                  "loading, read-only replica.",
        "multi": "Explains that inside MULTI the command is queued instead of executed (QUEUED).",
        "execute": "Identifies where the command is finally executed (call(c, ...)).",
    },
    "fmt": {
        "compile_string": "Explains that format_string/fstring checks literals at compile time (consteval constructor / checker).",
        "compile_parse": "Explains that the compile-time check parses the string (parse_format_string or compile checks).",
        "runtime": "Explains what fmt::runtime changes (runtime_format_string skips compile-time checking).",
        "public_format": "Locates the public fmt::format entry point (format.h).",
        "arguments": "Explains how arguments are packed (vargs / format_args / make_format_args).",
        "vformat_buffer": "Explains vformat writing into a memory_buffer and converting it to a string.",
        "runtime_parse": "Explains detail::vformat_to parsing the string and the fast path for a single {}.",
        "output_iterator": "Explains how format_to adapts an output iterator (buffer/get_iterator).",
    },
    "rails": {
        "transaction_wrapper": "Explains that save runs inside a transaction wrapper (with_transaction_returning_status).",
        "validation_layer": "Explains where validations run (perform_validations / validate: false).",
        "save_entry": "Locates Persistence#save calling create_or_update (and save! raising RecordInvalid/NotSaved).",
        "callbacks": "Explains save/create callbacks wrapping create_or_update/_create_record.",
        "create_branch": "Explains that a new record takes the _create_record (insert) branch rather than update.",
        "create_record": "Explains _create_record building the insert attributes and calling _insert_record.",
        "adapter_insert": "Identifies the final adapter insert (connection insert / InsertManager).",
        "failure_semantics": "Explains what happens on failure: save returns false and/or the transaction rolls back, "
                             "callbacks can abort (:abort).",
    },
}


def _answers(run_root: Path) -> list[dict]:
    rows = []
    for summary_path in sorted(run_root.glob("*/*/runs/*/summary.json")):
        summary = json.loads(summary_path.read_text())
        if summary["session_status"] != "complete":
            continue
        corpus = summary_path.parents[3].name
        rows.append({"corpus": corpus, "client": summary["client"], "arm": summary["arm"],
                     "repetition": summary.get("repetition", 1), "run_id": summary_path.parent.name,
                     "answer": (summary_path.parent / "answer.txt").read_text(encoding="utf-8")})
    return rows


def prepare(run_root: Path, out: Path, key_path: Path, sample_per_corpus: int = 3) -> None:
    """Every answer with a literal-rubric miss plus a random sample of full scores.

    The packet does not say which answers missed; the sample checks that full
    literal scores are not false positives.
    """
    grades = {row["run_id"]: row for row in json.loads((HERE / "grades_by_run.json").read_text())}
    rows = [row for row in _answers(run_root) if row["run_id"] in grades
            and row["corpus"] == grades[row["run_id"]]["repository"]]
    rng = random.Random(secrets.randbits(64))
    selected = []
    for corpus in CRITERIA:
        group = [row for row in rows if row["corpus"] == corpus]
        missed = [row for row in group if grades[row["run_id"]]["quality"]["passed"]
                  < grades[row["run_id"]]["quality"]["total"]]
        full = [row for row in group if row not in missed]
        selected += missed + rng.sample(full, min(sample_per_corpus, len(full)))
    rows = selected
    rng.shuffle(rows)
    key = {}
    out.mkdir(parents=True, exist_ok=True)
    for corpus in CRITERIA:
        task = json.loads((HERE / f"{corpus}_tasks.json").read_text())["tasks"][0]
        lines = [f"# {corpus}", "", task["request"], "", "## Criterios", ""]
        lines += [f"- `{fact}`: {text}" for fact, text in CRITERIA[corpus].items()]
        for row in (row for row in rows if row["corpus"] == corpus):
            label = f"{corpus[:2].upper()}{secrets.token_hex(3)}"
            key[label] = {name: row[name] for name in ("corpus", "client", "arm", "repetition", "run_id")}
            lines += ["", f"## {label}", "", row["answer"].strip()]
        (out / f"{corpus}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")


def score(judgments_path: Path, key_path: Path, output: Path) -> None:
    judgments = json.loads(judgments_path.read_text())
    key = json.loads(key_path.read_text())
    missing = sorted(set(key) - set(judgments))
    if missing:
        raise SystemExit(f"unjudged answers: {missing}")
    rows = []
    for label, facts in judgments.items():
        rows.append({**key[label], "label": label, "facts": facts["facts"], "passed": sum(facts["facts"].values()),
                     "notes": facts.get("notes", "")})
    output.write_text(json.dumps({
        "method": "Adjudicación conceptual ciega (rúbrica v2): respuestas barajadas con etiqueta aleatoria; "
                  "cliente, brazo y repetición se revelaron sólo tras puntuar. Adjudicador: el mismo agente "
                  "que implementó los cambios (no independiente).",
        "criteria": CRITERIA, "rows": sorted(rows, key=lambda r: (r["corpus"], r["client"], r["arm"], r["repetition"])),
    }, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--run-root", type=Path, required=True)
    prep.add_argument("--out", type=Path, required=True)
    prep.add_argument("--key", type=Path, required=True)
    sc = sub.add_parser("score")
    sc.add_argument("--judgments", type=Path, required=True)
    sc.add_argument("--key", type=Path, required=True)
    sc.add_argument("--output", type=Path, default=HERE / "manual_adjudication.json")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.run_root, args.out, args.key)
    else:
        score(args.judgments, args.key, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
