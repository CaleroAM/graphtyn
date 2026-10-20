#!/usr/bin/env python3
"""Run the isolated deterministic source-message retrieval benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphtyn.core.memory_retrieval_benchmark import run_source_message_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_source_message_benchmark(repetitions=args.repetitions)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    raise SystemExit(0 if result["ok"] and result["consumption_guardrail"]["passed"] else 1)


if __name__ == "__main__":
    main()
