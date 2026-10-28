"""Refuse to declare a package complete when its evidence cannot support the request.

Graph retrieval cannot tell which part of a multi-part request a symbol
answers, and lexical part-by-part checks did not separate good from bad
packages. Two checks did, on the dev split of
``benchmarks/task_bank_2026-10-28``:

* **Thin evidence.** Packages that claimed completeness while covering little
  of a request carried far less source per requested part.
* **Unmatched identifiers.** A request that names ``BLPOP`` or ``TRYAGAIN`` is
  not answered by evidence that never mentions them, however large it is.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .lean_package import lean_payload, serialized_tokens

MIN_PARTS = 4
# Calibrated on the dev split: every package below it covered under half of
# its rubric, every package above it at least 60 %.
MIN_TOKENS_PER_PART = 250
_CITATION_REQUEST = re.compile(r"\s*Cit(?:a|e)\b[^.]*(?:archivo|file):l[ií]ne(?:a|s?)\b.*$", re.I | re.S)
# Code-shaped words: COMMANDS and CONSTANTS, snake_case, camelCase and PascalCase compounds.
_IDENTIFIER = re.compile(r"\b(?:[A-Z][A-Z0-9_]{2,}|[A-Za-z]+_[A-Za-z0-9_]+|[a-z]+[A-Z][A-Za-z0-9]*"
                         r"|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b")
GUIDANCE = ("The evidence does not cover the whole request: answer the parts it shows from it, and look up "
            "only what it does not address (one targeted search or exact range each).")


def request_parts(request: str) -> list[str]:
    """Clauses of an enumerated request, without the closing citation instruction."""
    text = _CITATION_REQUEST.sub("", str(request or ""))
    return [part.strip() for part in re.split(r"[,;:?]", text) if len(part.strip()) >= 8]


def named_identifiers(request: str) -> list[str]:
    """Identifiers the request spells out, without the closing citation instruction."""
    return list(dict.fromkeys(_IDENTIFIER.findall(_CITATION_REQUEST.sub("", str(request or "")))))


def evidence_tokens(lean: dict[str, Any]) -> int:
    return serialized_tokens({key: lean.get(key) for key in ("entities", "relations", "source_evidence")})


def _verdict(result: dict[str, Any], request: str) -> dict[str, Any]:
    lean = lean_payload(result)
    verdict: dict[str, Any] = {}
    parts = len(request_parts(request))
    tokens = evidence_tokens(lean)
    if parts >= MIN_PARTS and tokens < MIN_TOKENS_PER_PART * parts:
        verdict.update(request_parts=parts, evidence_tokens=tokens, required_tokens=MIN_TOKENS_PER_PART * parts)
    text = json.dumps(lean, ensure_ascii=False).lower()
    unmatched = [name for name in named_identifiers(request) if name.lower() not in text]
    if unmatched:
        verdict["unmatched_identifiers"] = unmatched
    return verdict


def mark_insufficient_evidence(result: dict[str, Any], request: str,
                               mirror: dict[str, Any] | None = None) -> bool:
    """Withdraw a completeness claim the evidence cannot support; return whether it did.

    `mirror` (the internal package `result` was rendered from) receives the same verdict.
    """
    if not result.get("do_not_expand"):
        return False
    verdict = _verdict(result, request)
    if not verdict:
        return False
    missing = (["request_parts"] if "request_parts" in verdict else []) + (
        ["named_identifiers"] if "unmatched_identifiers" in verdict else [])
    result["missing"] = [*(result.get("missing") or []), *missing]
    result["complete_for"] = []
    result["do_not_expand"] = False
    result["evidence_sufficiency"] = verdict
    stopping = result.get("stopping")
    if isinstance(stopping, dict):
        stopping["sufficient_evidence"] = False
        stopping["reason"] = "evidence does not cover the whole request"
    result["guidance"] = f"{result.get('guidance') or ''} {GUIDANCE}".strip()
    if mirror is not None:
        mirror.update({key: result[key] for key in ("missing", "complete_for", "do_not_expand",
                                                    "evidence_sufficiency", "guidance", "stopping")
                       if key in result})
    return True
