"""Project-local review decisions for ambiguous graph relations."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def relation_key(link: dict) -> str:
    raw = "\0".join(str(link.get(k) or "") for k in ("source", "target", "label", "file", "line"))
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def review_path(root: Path) -> Path:
    return root / ".graphtyn" / "ambiguity-decisions.json"


def load_decisions(root: Path) -> dict[str, dict]:
    try:
        return json.loads(review_path(root).read_text(encoding="utf-8")).get("decisions", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def ambiguity_queue(graph: dict, root: Path) -> dict[str, Any]:
    decisions = load_decisions(root)
    items = []
    for link in graph.get("links", []):
        if str(link.get("confidence") or "").upper() not in {"AMBIGUOUS", "REVIEWED"}:
            continue
        key = relation_key(link)
        items.append({"key": key, "relation": link, "decision": decisions.get(key)})
    return {"ok": True, "pending": sum(not item["decision"] for item in items),
            "reviewed": sum(bool(item["decision"]) for item in items), "items": items}


def save_decision(root: Path, key: str, decision: str, note: str = "") -> dict:
    if decision not in {"accept", "reject", "correct"}:
        raise ValueError("decision must be accept, reject or correct")
    target = review_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    decisions = load_decisions(root)
    decisions[key] = {"decision": decision, "note": note[:1000], "timestamp": int(time.time())}
    target.write_text(json.dumps({"version": 1, "decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf-8")
    return decisions[key]


def apply_decisions(graph: dict, root: Path) -> dict:
    decisions = load_decisions(root)
    links = []
    applied = 0
    for link in graph.get("links", []):
        item = decisions.get(relation_key(link))
        if not item:
            links.append(link)
        elif item["decision"] == "reject":
            applied += 1
        else:
            updated = dict(link)
            updated["confidence"] = "REVIEWED"
            updated["review"] = item
            links.append(updated)
            applied += 1
    graph["links"] = links
    graph.setdefault("metadata", {})["ambiguity_reviews_applied"] = applied
    return graph
