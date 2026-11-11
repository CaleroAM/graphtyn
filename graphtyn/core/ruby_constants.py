"""Ruby constants: `X.new` builds through `initialize`, and `A::B` resolves through the caller's nesting."""
from __future__ import annotations

import re
from typing import Any

from .ruby_mro import qualified_name

_CONSTANT = r"(?:::)?[A-Z][A-Za-z0-9_]*(?:::[A-Z][A-Za-z0-9_]*)*"
_CONSTANT_PATH = re.compile(rf"^({_CONSTANT})$")
_NEW_RECEIVER = re.compile(rf"^({_CONSTANT})\.new(?:\(.*\))?$", re.S)


def ruby_constant_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark receivers written as constants, and add a call to `X#initialize` for each `X.new`.

    `Builder.new.build` was typed as `Builder.new`, and `Reflection.new` reached no method,
    so object creation in a Ruby project had no edge. The `new` call itself stays: a class
    may define its own `self.new`.
    """
    created = []
    for call in calls:
        receiver = str(call.get("receiver") or "").strip()
        match = _NEW_RECEIVER.match(receiver) or _CONSTANT_PATH.match(receiver)
        if not match:
            continue
        constant = match.group(1).lstrip(":")
        call.update({"receiver_type": constant, "ruby_constant": constant})
        if match.re is _CONSTANT_PATH and call.get("name") == "new":
            created.append({**call, "name": "initialize", "call_kind": "new_expression"})
    return calls + created


def ruby_receiver_type(constant: str, targets: set[str], node_by_id: dict[str, dict[str, Any]]) -> str:
    """The longest tail of `ActiveStorage::Blob` that names a candidate's owner.

    A compact `class ActiveStorage::Blob` owns its methods as `ActiveStorage::Blob`, a nested
    one as `Blob`; the leaf is kept when neither matches, so the call can still miss.
    """
    containers = {node_by_id.get(target, {}).get("container") for target in targets}
    parts = constant.split("::")
    for start in range(len(parts)):
        if "::".join(parts[start:]) in containers:
            return "::".join(parts[start:])
    return parts[-1]


def ruby_lexical_pick(best: list[str], call: dict[str, Any], source: dict[str, Any],
                      node_by_id: dict[str, dict[str, Any]]) -> list[str]:
    """Among equally ranked methods, the one whose owner Ruby's constant lookup reaches.

    Scopes are tried from the caller's innermost (`ActionMailer::Base`) outwards: `Builder`
    there is `ActionMailer::Builder` before any other `Builder`. Without a match the ranking
    stays as it was.
    """
    constant = call.get("ruby_constant")
    if len(best) < 2 or not constant:
        return best
    owners = {target: qualified_name(node_by_id.get(target, {})).rsplit("::", 1)[0] for target in best}
    scope = qualified_name(source).split("::") if source else []
    for depth in range(len(scope), -1, -1):
        full = "::".join([*scope[:depth], constant])
        reached = [target for target in best if owners[target] == full]
        if reached:
            return reached
    return best
