#!/usr/bin/env python3
"""Local, model-free coverage and latency benchmark for the Ruby pack."""

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


ORDER_SOURCE = '''require_relative "application_record"
require_relative "trackable"

module Billing
  module Trackable
    def audit(event)
      Logger.info(event)
    end
  end

  class Order < ApplicationRecord
    include Trackable

    def total(multiplier = 1)
      audit(:total)
      line_items.sum(&:price) * multiplier
    end

    def self.find_paid(id)
      find(id)
    end
  end
end
'''


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[position]


def _parser_facts(result: dict) -> dict[str, bool]:
    symbols = {(item["name"], item["kind"]): item for item in result["symbols"]}
    order = symbols.get(("Order", "class"), {})
    return {
        "clean_parse": result["has_error"] is False,
        "requires": len(result["imports"]) == 2,
        "module": ("Trackable", "module") in symbols,
        "class": ("Order", "class") in symbols,
        "inheritance": order.get("bases") == ["ApplicationRecord"],
        "mixin": any(item.get("name") == "Trackable" for item in order.get("mixins", [])),
        "instance_method": ("total", "method") in symbols,
        "singleton_method": ("find_paid", "method") in symbols,
        "call": any(item["caller"] == "total" and item["name"] == "audit"
                    for item in result["calls"]),
    }


def run(repetitions: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="graphtyn-ruby-pack-") as directory:
        root = Path(directory)
        (root / "application_record.rb").write_text(
            "class ApplicationRecord\nend\n", encoding="utf-8",
        )
        (root / "trackable.rb").write_text(
            "module Trackable\n  def audit(event)\n  end\nend\n", encoding="utf-8",
        )
        order_path = root / "order.rb"
        order_path.write_text(ORDER_SOURCE, encoding="utf-8")

        parse_file(order_path, "order.rb")
        elapsed = []
        result = None
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            result = parse_file(order_path, "order.rb")
            elapsed.append((time.perf_counter_ns() - started) / 1_000_000)
        if result is None:
            raise RuntimeError("The Ruby grammar is unavailable")

        parser_facts = _parser_facts(result)
        graph = ASTParser().scan_directory(root, respect_git=False)
        nodes = {node["id"]: node for node in graph["nodes"]}
        relations = {
            (nodes.get(link.get("source"), {}).get("name"), link.get("label"),
             nodes.get(link.get("target"), {}).get("name"), link.get("mixin_kind"))
            for link in graph["links"]
        }
        graph_facts = {
            "inheritance_edge": ("Order", "hereda", "ApplicationRecord", None) in relations,
            "mixin_edge": ("Order", "incluye", "Trackable", "include") in relations,
            "call_edge": ("total", "llama", "audit", None) in relations,
        }

    facts = {**parser_facts, **graph_facts}
    return {
        "protocol": {
            "name": "language-pack-ruby-v1",
            "scope": "local parser and graph coverage; no agent, model, network or token measurement",
            "repetitions": repetitions,
            "warmup_runs": 1,
        },
        "environment": {
            "parser_version": PARSER_VERSION,
            "tree_sitter_ruby": importlib.metadata.version("tree-sitter-ruby"),
        },
        "measurement": {
            "facts": facts,
            "facts_passed": sum(facts.values()),
            "facts_total": len(facts),
            "median_ms": round(statistics.median(elapsed), 3),
            "p95_ms": round(_percentile(elapsed, 0.95), 3),
            "samples_ms": [round(value, 3) for value in elapsed],
        },
        "graph": {
            "tree_sitter_files": graph["metadata"]["tree_sitter_files"],
            "language_packs": graph["metadata"]["language_packs"],
        },
        "summary": {
            "coverage": sum(facts.values()) / len(facts),
            "passed": all(facts.values()),
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
