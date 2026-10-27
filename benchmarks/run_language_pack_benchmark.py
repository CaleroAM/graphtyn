#!/usr/bin/env python3
"""Local, model-free coverage and latency benchmark for the C/C++ packs."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import statistics
import tempfile
import time
from pathlib import Path

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.tree_sitter_backend import PARSER_VERSION, parse_file


FIXTURES = {
    "c": (
        "service.c",
        "#include <stdio.h>\n"
        "struct Service { int value; };\n"
        "int helper(int value) { return value + 1; }\n"
        "int run(struct Service *service) { return helper(service->value); }\n",
    ),
    "cpp": (
        "service.cpp",
        "#include <string>\n"
        "namespace demo {\n"
        "class Base { public: virtual int run() = 0; };\n"
        "int helper(int value) { return value + 1; }\n"
        "class Service : public Base { int value; public: int run() { return helper(value); } };\n"
        "}\n",
    ),
}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[position]


def _facts(language: str, result: dict) -> dict[str, bool]:
    symbols = {(item["name"], item["kind"]) for item in result["symbols"]}
    facts = {
        "clean_parse": result["has_error"] is False,
        "include": bool(result["imports"]),
        "type": ("Service", "struct" if language == "c" else "class") in symbols,
        "functions": {"helper", "run"} <= {item["name"] for item in result["symbols"]},
        "member": any(item["container"] == "Service" and item["name"] == "value"
                      for item in result["members"]),
        "call": any(item["caller"] == "run" and item["name"] == "helper"
                    for item in result["calls"]),
    }
    if language == "cpp":
        facts["inheritance"] = any(
            item["name"] == "Service" and item["bases"] == ["Base"]
            for item in result["symbols"]
        )
    return facts


def run(repetitions: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="graphtyn-language-pack-") as directory:
        root = Path(directory)
        paths = {}
        for language, (filename, source) in FIXTURES.items():
            paths[language] = root / filename
            paths[language].write_text(source, encoding="utf-8")

        measurements = {}
        for language, path in paths.items():
            parse_file(path, path.name)  # warm-up imports and native grammar loading
            elapsed = []
            result = None
            for _ in range(repetitions):
                started = time.perf_counter_ns()
                result = parse_file(path, path.name)
                elapsed.append((time.perf_counter_ns() - started) / 1_000_000)
            if result is None:
                raise RuntimeError(f"The {language} grammar is unavailable")
            facts = _facts(language, result)
            measurements[language] = {
                "facts": facts,
                "facts_passed": sum(facts.values()),
                "facts_total": len(facts),
                "median_ms": round(statistics.median(elapsed), 3),
                "p95_ms": round(_percentile(elapsed, 0.95), 3),
                "samples_ms": [round(value, 3) for value in elapsed],
            }

        graph = ASTParser().scan_directory(root, respect_git=False)
        nodes = {node["id"]: node for node in graph["nodes"]}
        inheritance = any(
            link.get("label") == "hereda"
            and nodes.get(link.get("source"), {}).get("name") == "Service"
            and nodes.get(link.get("target"), {}).get("name") == "Base"
            for link in graph["links"]
        )
        call_edges = sum(link.get("label") == "llama" for link in graph["links"])

    facts_passed = sum(item["facts_passed"] for item in measurements.values())
    facts_total = sum(item["facts_total"] for item in measurements.values())
    return {
        "protocol": {
            "name": "language-packs-c-cpp-v1",
            "scope": "local parser coverage and latency; no agent, model, network or token measurement",
            "repetitions": repetitions,
            "warmup_runs": 1,
            "fixtures": list(FIXTURES),
        },
        "environment": {
            "parser_version": PARSER_VERSION,
            "tree_sitter_c": importlib.metadata.version("tree-sitter-c"),
            "tree_sitter_cpp": importlib.metadata.version("tree-sitter-cpp"),
        },
        "measurements": measurements,
        "graph": {
            "tree_sitter_files": graph["metadata"]["tree_sitter_files"],
            "language_packs": graph["metadata"]["language_packs"],
            "inheritance_edge": inheritance,
            "call_edges": call_edges,
        },
        "summary": {
            "facts_passed": facts_passed,
            "facts_total": facts_total,
            "coverage": facts_passed / facts_total if facts_total else 0.0,
            "passed": facts_passed == facts_total and inheritance and call_edges >= 2,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repetitions < 2:
        parser.error("--repetitions must be at least 2")
    result = run(args.repetitions)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
