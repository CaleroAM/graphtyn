"""Dependency-free local semantic index with optional Ollama embeddings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Any


DIMENSIONS = 384

_ALIASES = {
    "selección": ("selection", "select", "player"), "seleccion": ("selection", "select", "player"),
    "jugador": ("player",), "jugadores": ("player",), "impacto": ("impact", "consumer", "caller"),
    "consumidor": ("consumer", "caller"), "consumidores": ("consumer", "caller"),
    "sesión": ("session", "cookie"), "sesion": ("session", "cookie"),
    "firma": ("sign", "signature", "signer"), "ruta": ("route", "router"),
    "borrado": ("delete", "remove"), "eliminar": ("delete", "remove"),
    "persistencia": ("repository", "database", "save"),
    "autenticación": ("authentication", "auth", "identity", "token", "credential"),
    "autenticacion": ("authentication", "auth", "identity", "token", "credential"),
    "validación": ("validation", "validate", "verify", "check"),
    "validacion": ("validation", "validate", "verify", "check"),
    "credencial": ("credential", "auth", "identity"),
    "credenciales": ("credential", "auth", "identity"),
    "identidad": ("identity", "auth", "authentication"),
    "verifica": ("verify", "validate", "check"), "comprobar": ("verify", "validate", "check"),
    "comprueba": ("verify", "validate", "check"),
    "usuario": ("user", "identity", "account"), "usuarios": ("user", "identity", "account"),
    "paleta": ("palette", "theme", "appearance"),
    "configuración": ("configuration", "settings", "controls"),
    "configuracion": ("configuration", "settings", "controls"),
    "motor": ("engine", "pipeline"), "interfaz": ("interface", "ui", "dashboard"),
    "recuerdo": ("memory", "history", "decision"), "memoria": ("memory", "history", "decision"),
}


def _tokens(text: str) -> list[str]:
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]{1,}", split.lower())
    return words + [alias for word in words for alias in _ALIASES.get(word, ())]


def _text(node: dict[str, Any]) -> str:
    operations = " ".join(str(op.get("name") or op.get("text") or "") for op in node.get("operations", []))
    return " ".join(str(node.get(key) or "") for key in
                    ("name", "kind", "container", "namespace", "file", "signature", "details", "ai_description")) + " " + operations


def hashed_embedding(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    """Feature-hashed word/identifier n-grams; local, stable and zero-token."""
    vector = [0.0] * dimensions
    words = _tokens(text)
    features = words + [f"{a}:{b}" for a, b in zip(words, words[1:])]
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        vector[raw % dimensions] += 1.0 if raw & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def ollama_embedding(text: str) -> list[float] | None:
    model = os.environ.get("GRAPHTYN_EMBED_MODEL", "").strip()
    if not model:
        return None
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    payload = json.dumps({"model": model, "prompt": text[:12000]}).encode()
    try:
        request = urllib.request.Request(f"{host}/api/embeddings", data=payload,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            values = json.loads(response.read()).get("embedding")
        if not values:
            return None
        vector = [float(value) for value in values]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
    except Exception:
        return None


def build_semantic_index(graph: dict[str, Any], output: Path | None = None) -> dict[str, Any]:
    rows = []
    requested_provider = f"ollama:{os.environ.get('GRAPHTYN_EMBED_MODEL')}:cosine-v1" if os.environ.get("GRAPHTYN_EMBED_MODEL") else "feature-hash-v2"
    provider = requested_provider
    previous = {}
    if output and output.exists():
        try:
            loaded = json.loads(output.read_text(encoding="utf-8"))
            if loaded.get("provider") == requested_provider:
                previous = {row.get("id"): row for row in loaded.get("rows", [])}
        except (OSError, ValueError, TypeError):
            pass
    reused = 0
    embedded = 0
    for node in graph.get("nodes", []):
        if node.get("kind") in {"module", "community", "semantic_concept"}:
            continue
        text = _text(node).strip()
        if not text:
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        cached = previous.get(node.get("id"), {})
        if cached.get("sha256") == digest and cached.get("vector"):
            vector = cached["vector"]
            reused += 1
        else:
            vector = ollama_embedding(text)
            if vector is None:
                vector = hashed_embedding(text)
                if requested_provider.startswith("ollama:"):
                    provider = "feature-hash-v2"
            embedded += 1
        rows.append({"id": node.get("id"), "sha256": digest, "vector": vector})
    index = {"version": 2, "provider": provider, "dimensions": len(rows[0]["vector"]) if rows else 0,
             "incremental": {"reused": reused, "embedded": embedded, "removed": max(0, len(previous) - reused)}, "rows": rows}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    return index


def semantic_search(graph: dict[str, Any], query: str, limit: int = 8,
                    index: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    index = index or build_semantic_index(graph)
    ollama_provider = str(index.get("provider", "")).startswith("ollama:")
    query_vector = ollama_embedding(query) if ollama_provider else None
    expanded_query = " ".join(_tokens(query))
    query_vector = query_vector or hashed_embedding(expanded_query, int(index.get("dimensions") or DIMENSIONS))
    query_terms = set(_tokens(query))
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}
    scored = []
    for row in index.get("rows", []):
        vector = row.get("vector") or []
        score = sum(a * b for a, b in zip(query_vector, vector))
        if not ollama_provider:
            node_terms = set(_tokens(_text(nodes.get(row.get("id"), {}))))
            overlap = query_terms & node_terms
            if not overlap:
                continue
            score += len(overlap) / max(1, len(query_terms)) * 2
        if score > 0:
            scored.append((score, nodes.get(row.get("id"))))
    return [{"score": round(score, 4), "node": node} for score, node in
            sorted(scored, key=lambda item: (-item[0], str((item[1] or {}).get("id"))))[:limit] if node]
