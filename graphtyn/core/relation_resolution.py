"""Deterministic helpers for structural symbol and relation resolution."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


def unique_symbol_id(
    rel_file: str, qualified: str, kind: str, symbol: dict[str, Any], existing: set[str]
) -> str | None:
    """Build a stable ID and retain same-name/same-arity lexical definitions."""
    base = f"symbol:{rel_file}:{qualified}"
    if base not in existing:
        return base
    if kind not in {"method", "function"}:
        return None
    arity = symbol.get("parameter_count")
    overload = f"{base}/{arity if arity is not None else symbol['line']}"
    return overload if overload not in existing else f"{overload}@{symbol['line']}"


class CandidateRanker:
    """Rank possible relation targets from structural and import evidence."""

    def __init__(self, nodes: dict[str, dict[str, Any]], imports: dict[str, list[dict[str, Any]]]):
        self.nodes = nodes
        self.imports = imports
        self._contexts: dict[str, tuple[set[str], dict[str, str], dict[str, str]]] = {}

    @staticmethod
    def _python_module(rel_file: str, raw_module: str) -> str:
        leading_dots = len(raw_module) - len(raw_module.lstrip("."))
        if not leading_dots:
            return raw_module
        package = list(PurePosixPath(rel_file).with_suffix("").parts[:-1])
        parents = leading_dots - 1
        if parents > len(package):
            return ""
        base = package[:len(package) - parents] if parents else package
        suffix = [part for part in raw_module.lstrip(".").split(".") if part]
        return ".".join([*base, *suffix])

    def _import_context(self, rel_file: str) -> tuple[set[str], dict[str, str], dict[str, str]]:
        cached = self._contexts.get(rel_file)
        if cached is not None:
            return cached
        namespaces: set[str] = set()
        aliases: dict[str, str] = {}
        symbols: dict[str, str] = {}
        for item in self.imports.get(rel_file, []):
            text = str(item.get("text") or "")
            match = re.search(r"\busing\s+(?:(\w+)\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)", text)
            if match:
                if match.group(1):
                    aliases[match.group(1)] = match.group(2)
                else:
                    namespaces.add(match.group(2))
            python_from = re.match(r"\s*from\s+([.A-Za-z_][.A-Za-z0-9_]*)\s+import\s+(.+)", text)
            if python_from:
                module = self._python_module(rel_file, python_from.group(1))
                for part in python_from.group(2).strip().strip("()").split(","):
                    bits = re.split(r"\s+as\s+", part.strip())
                    if bits and re.fullmatch(r"[A-Za-z_]\w*", bits[0]):
                        symbols[bits[-1]] = f"{module}.{bits[0]}"
        self._contexts[rel_file] = namespaces, aliases, symbols
        return self._contexts[rel_file]

    def imported_target_name(self, rel_file: str, called_name: str) -> str:
        imported = self._import_context(rel_file)[2].get(called_name, "")
        return imported.rsplit(".", 1)[-1] if imported else called_name

    def is_imported(self, rel_file: str, called_name: str) -> bool:
        return called_name in self._import_context(rel_file)[2]

    def filter_imported_targets(self, rel_file: str, called_name: str,
                                targets: set[str]) -> set[str]:
        """Restrict imported calls to the module Python would actually load."""
        imported = self._import_context(rel_file)[2].get(called_name, "")
        if not imported:
            return targets
        module, symbol = imported.rsplit(".", 1)
        expected_file = module.replace(".", "/")
        return {
            target_id for target_id in targets
            if self.nodes.get(target_id, {}).get("name") == symbol
            and str(self.nodes.get(target_id, {}).get("file") or "")
            .removesuffix("/__init__.py").removesuffix(".py") == expected_file
        }

    def lexical_targets(self, rel_file: str, called_name: str,
                        caller: str, targets: set[str]) -> set[str]:
        """Return definitions that shadow an imported name in Python scope.

        Import filtering is only a fallback: a nested or module-level
        definition with the same spelling wins during Python name lookup.
        An alias is treated exactly like any other binding: a local definition
        named ``fetch`` shadows an imported ``collect as fetch``.
        """
        same_file = {
            target for target in targets
            if self.nodes.get(target, {}).get("file") == rel_file
            and self.nodes.get(target, {}).get("name") == called_name
            and self.nodes.get(target, {}).get("kind") in ("function", "method")
        }
        if not same_file:
            return set()
        scoped = {target for target in same_file
                  if caller and self.nodes.get(target, {}).get("scope") == caller}
        return scoped or {
            target for target in same_file
            if not self.nodes.get(target, {}).get("scope")
        }

    def __call__(
        self, target_id: str, rel_file: str, container: str = "", receiver: str = "",
        arity: Any = None, lexical_scope: str = "", called_name: str = "",
    ) -> int:
        target = self.nodes.get(target_id, {})
        score = 4 if target.get("file") == rel_file else 0
        if lexical_scope and target.get("scope") == lexical_scope:
            score += 16
        if container and target.get("container") == container:
            score += 5
        if receiver and receiver in {target.get("container"), target.get("name")}:
            score += 12
        required, maximum = target.get("required_parameter_count"), target.get("parameter_count")
        if arity is not None and maximum == arity:
            score += 5
        elif arity is not None and required is not None and maximum is not None and required <= arity <= maximum:
            score += 5 if required == arity else 3
        source_assembly = self.nodes.get(f"file:{rel_file}", {}).get("assembly")
        if source_assembly and source_assembly == target.get("assembly"):
            score += 2
        namespaces, aliases, imported_symbols = self._import_context(rel_file)
        namespace = str(target.get("namespace") or "")
        if namespace and (namespace in namespaces or any(namespace.startswith(item + ".") for item in namespaces)):
            score += 3
        if receiver and aliases.get(receiver, "").endswith("." + str(target.get("container") or "")):
            score += 12
        imported_symbol = imported_symbols.get(called_name, "")
        if imported_symbol:
            module = imported_symbol.rsplit(".", 1)[0].replace(".", "/")
            target_file = str(target.get("file") or "").removesuffix("/__init__.py").removesuffix(".py")
            if target.get("name") == imported_symbol.rsplit(".", 1)[-1] and target_file == module:
                score += 16
        return score
