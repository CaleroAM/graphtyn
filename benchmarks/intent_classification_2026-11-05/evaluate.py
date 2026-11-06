#!/usr/bin/env python3
"""Agreement of `classify_intent` with labels another model wrote, per batch, intent and language.

The batches were generated and labelled by Gemini through the Antigravity CLI, without
tools or access to Graphtyn's code. See report.md for which batch tuned and which tested.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from graphtyn.core.intent_classifier import classify_intent  # noqa: E402


def agreement(path: Path) -> dict:
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    hits, totals, misses = Counter(), Counter(), []
    for item in items:
        got = classify_intent(item["question"], "auto")
        totals[item["intent"]] += 1
        if got == item["intent"]:
            hits[item["intent"]] += 1
        else:
            misses.append({"expected": item["intent"], "got": got, "language": item["language"], "question": item["question"]})
    return {"agree": sum(hits.values()), "total": len(items),
            "by_intent": {intent: f"{hits[intent]}/{totals[intent]}" for intent in totals}, "misses": misses}


def main() -> int:
    for path in sorted(HERE.glob("batch*.json")):
        result = agreement(path)
        print(f"{path.stem}: {result['agree']}/{result['total']} {result['by_intent']}")
        for miss in result["misses"] if "--misses" in sys.argv else []:
            print(f"  {miss['expected']} -> {miss['got']} [{miss['language']}] {miss['question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
