"""Refuse to declare a package complete when its evidence is too thin for the request.

Graph retrieval cannot tell which part of a multi-part request a symbol
answers, and lexical part-by-part checks did not separate good from bad
packages. The amount of evidence does: packages that claimed completeness while
covering little of a request carried far less source per requested part. A
request with several parts therefore needs a minimum of evidence per part
before ``do_not_expand`` may hold.
"""

from __future__ import annotations

import re
from typing import Any

from .lean_package import lean_payload, serialized_tokens

MIN_PARTS = 4
# Calibrated on the dev split of benchmarks/task_bank_2026-10-28: every package
# below it covered under half of its rubric, every package above it at least 60 %.
MIN_TOKENS_PER_PART = 250
_CITATION_REQUEST = re.compile(r"\s*Cit(?:a|e)\b[^.]*(?:archivo|file):l[ií]ne(?:a|s?)\b.*$", re.I | re.S)
GUIDANCE = ("The evidence is thin for a request with several parts: answer the parts it shows from it, "
            "and look up only the parts it does not address (one targeted search or exact range each).")


def request_parts(request: str) -> list[str]:
    """Clauses of an enumerated request, without the closing citation instruction."""
    text = _CITATION_REQUEST.sub("", str(request or ""))
    return [part.strip() for part in re.split(r"[,;:?]", text) if len(part.strip()) >= 8]


def evidence_tokens(result: dict[str, Any]) -> int:
    lean = lean_payload(result)
    return serialized_tokens({key: lean.get(key) for key in ("entities", "relations", "source_evidence")})


def mark_thin_evidence(result: dict[str, Any], request: str, mirror: dict[str, Any] | None = None) -> bool:
    """Withdraw a completeness claim the evidence cannot support; return whether it did.

    `mirror` (the internal package `result` was rendered from) receives the same verdict.
    """
    if not result.get("do_not_expand"):
        return False
    parts = len(request_parts(request))
    if parts < MIN_PARTS:
        return False
    tokens = evidence_tokens(result)
    required = MIN_TOKENS_PER_PART * parts
    if tokens >= required:
        return False
    result["missing"] = [*(result.get("missing") or []), "request_parts"]
    result["complete_for"] = []
    result["do_not_expand"] = False
    result["evidence_sufficiency"] = {"request_parts": parts, "evidence_tokens": tokens,
                                      "required_tokens": required}
    stopping = result.get("stopping")
    if isinstance(stopping, dict):
        stopping["sufficient_evidence"] = False
        stopping["reason"] = "evidence too thin for the number of requested parts"
    result["guidance"] = f"{result.get('guidance') or ''} {GUIDANCE}".strip()
    if mirror is not None:
        mirror.update({key: result[key] for key in ("missing", "complete_for", "do_not_expand",
                                                    "evidence_sufficiency", "guidance", "stopping")
                       if key in result})
    return True
