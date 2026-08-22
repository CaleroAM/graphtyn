"""Deterministic Laravel/Inertia relationships built from source declarations."""

from __future__ import annotations

import re
from typing import Any


_ROUTE = re.compile(
    r"Route::(?P<verb>get|post|put|patch|delete|resource)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]"
    r"(?P<body>.*?)(?:\)\s*->name\(\s*['\"](?P<name>[^'\"]+)['\"]|\)\s*;)",
    re.DOTALL,
)
_CONTROLLER = re.compile(r"\[\s*(?P<controller>[A-Za-z_][\w]*)::class\s*,\s*['\"](?P<method>[A-Za-z_][\w]*)['\"]\s*\]")
_INERTIA_ROUTE = re.compile(r"\broute\(\s*['\"](?P<name>[^'\"]+)['\"]")
_RESOURCE = re.compile(r"Route::resource\(\s*['\"](?P<path>[^'\"]+)['\"]\s*,\s*(?P<controller>[A-Za-z_][\w]*)::class\s*\)")


def add_laravel_relations(nodes: list[dict[str, Any]], links: list[dict[str, Any]], file_contents: dict[str, str]) -> dict[str, int]:
    """Add route dispatch, validation, persistence/event and Inertia edges."""
    node_ids = {node.get("id") for node in nodes}
    symbols = [node for node in nodes if str(node.get("id", "")).startswith("symbol:")]

    def symbol(name: str, *, container: str = "") -> dict[str, Any] | None:
        candidates = [node for node in symbols if node.get("name") == name]
        if container:
            exact = [node for node in candidates if node.get("container") == container]
            if exact:
                candidates = exact
            else:
                file_exact = [node for node in candidates if f"/{container}.php:" in str(node.get("id"))]
                if file_exact:
                    candidates = file_exact
        return sorted(candidates, key=lambda node: str(node.get("id")))[0] if candidates else None

    added: list[dict[str, Any]] = []
    routes: dict[str, str] = {}
    for rel_file, content in file_contents.items():
        if not rel_file.startswith("routes/") or not rel_file.endswith(".php"):
            continue
        for match in _ROUTE.finditer(content):
            body = match.group("body") or ""
            controller_match = _CONTROLLER.search(body)
            route_name = match.group("name") or f"{match.group('verb')}:{match.group('path')}"
            route_id = f"route:{rel_file}:{route_name}"
            line = content.count("\n", 0, match.start()) + 1
            if route_id not in node_ids:
                nodes.append({
                    "id": route_id, "name": route_name, "kind": "route", "file": rel_file,
                    "line": line, "end_line": line, "http_method": match.group("verb").upper(),
                    "path": match.group("path"), "parser": "laravel-resolver",
                    "details": f"{match.group('verb').upper()} {match.group('path')}",
                    "val": 4, "color": "#22c55e",
                })
                node_ids.add(route_id)
                added.append({"source": f"file:{rel_file}", "target": route_id, "label": "declara ruta", "confidence": "EXTRACTED", "file": rel_file, "line": line})
            routes[route_name] = route_id
            if controller_match:
                controller = controller_match.group("controller")
                method = controller_match.group("method")
                target = symbol(method, container=controller)
                if target:
                    added.append({"source": route_id, "target": target["id"], "label": "despacha", "confidence": "EXTRACTED", "file": rel_file, "line": line, "evidence": f"{controller}::{method}"})
        for match in _RESOURCE.finditer(content):
            base = match.group("path").strip("/").replace("/", ".")
            controller = match.group("controller")
            line = content.count("\n", 0, match.start()) + 1
            for suffix, method, verb in (("index", "index", "GET"), ("create", "create", "GET"), ("store", "store", "POST"), ("show", "show", "GET"), ("edit", "edit", "GET"), ("update", "update", "PUT"), ("destroy", "destroy", "DELETE")):
                route_name = f"{base}.{suffix}"
                route_id = f"route:{rel_file}:{route_name}"
                if route_id not in node_ids:
                    nodes.append({"id": route_id, "name": route_name, "kind": "route", "file": rel_file, "line": line, "end_line": line, "http_method": verb, "path": match.group("path"), "parser": "laravel-resolver", "details": f"{verb} resource {match.group('path')}", "val": 4, "color": "#22c55e"})
                    node_ids.add(route_id)
                    added.append({"source": f"file:{rel_file}", "target": route_id, "label": "declara ruta", "confidence": "EXTRACTED", "file": rel_file, "line": line})
                routes[route_name] = route_id
                target = symbol(method, container=controller)
                if target:
                    added.append({"source": route_id, "target": target["id"], "label": "despacha", "confidence": "EXTRACTED", "file": rel_file, "line": line, "evidence": f"{controller}::{method}"})

    for node in symbols:
        if node.get("kind") not in ("method", "function"):
            continue
        signature = str(node.get("signature") or "")
        for request_name in re.findall(r"\b([A-Z][A-Za-z0-9_]*(?:Request|FormRequest))\b", signature):
            target = symbol(request_name)
            if target and target["id"] != node["id"]:
                added.append({"source": node["id"], "target": target["id"], "label": "valida con", "confidence": "EXTRACTED", "file": node.get("file"), "line": node.get("line")})
        for op in node.get("operations") or []:
            text = str(op.get("text") or "")
            for model_name in re.findall(r"\bnew\s+([A-Z][A-Za-z0-9_]*)", text):
                target = symbol(model_name)
                if target and target["id"] != node["id"]:
                    added.append({"source": node["id"], "target": target["id"], "label": "crea", "confidence": "EXTRACTED", "file": node.get("file"), "line": op.get("line"), "evidence": text[:240]})
            event = re.search(r"\b([A-Z][A-Za-z0-9_]*)::dispatch\s*\(", text)
            if event:
                target = symbol(event.group(1))
                if target and target["id"] != node["id"]:
                    added.append({"source": node["id"], "target": target["id"], "label": "despacha evento", "confidence": "EXTRACTED", "file": node.get("file"), "line": op.get("line"), "evidence": text[:240]})

    for rel_file, content in file_contents.items():
        if not rel_file.endswith((".ts", ".tsx", ".js", ".jsx")):
            continue
        for match in _INERTIA_ROUTE.finditer(content):
            route_id = routes.get(match.group("name"))
            if route_id:
                line = content.count("\n", 0, match.start()) + 1
                added.append({"source": f"file:{rel_file}", "target": route_id, "label": "invoca ruta", "confidence": "EXTRACTED", "file": rel_file, "line": line, "evidence": match.group(0)})

    existing = {(link.get("source"), link.get("target"), link.get("label"), link.get("line")) for link in links}
    for link in added:
        key = (link.get("source"), link.get("target"), link.get("label"), link.get("line"))
        if link.get("source") in node_ids and link.get("target") in node_ids and key not in existing:
            links.append(link)
            existing.add(key)
    return {"routes": len(routes), "relations": len(existing) - (len(links) - len(added))}
