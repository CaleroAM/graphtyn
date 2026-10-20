"""Dependency-free local semantic index with optional Ollama embeddings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from functools import lru_cache
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any


DIMENSIONS = 384
_INDEX_CACHE: OrderedDict[int, tuple[dict[str, Any], tuple[int, int], dict[str, Any]]] = OrderedDict()
_TERM_CACHE: OrderedDict[int, tuple[dict[str, Any], tuple[int, int], dict[str, set[str]]]] = OrderedDict()
_INDEX_CACHE_LOCK = threading.Lock()

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
    "prueba": ("test", "tests", "verification"),
    "pruebas": ("test", "tests", "verification"),
    "credencial": ("credential", "auth", "identity"),
    "credenciales": ("credential", "auth", "identity"),
    "identidad": ("identity", "auth", "authentication"),
    "alcance": ("scope", "lexical", "local"),
    "local": ("local", "lexical", "scope"),
    "alias": ("alias", "import"),
    "aliases": ("alias", "import"),
    "importado": ("import", "imported"),
    "importada": ("import", "imported"),
    "procedencia": ("provenance", "evidence", "source"),
    "ejecución": ("execution", "run", "command"),
    "ejecucion": ("execution", "run", "command"),
    "ejecuciones": ("execution", "run", "command"),
    "registra": ("record", "store", "log"),
    "registrar": ("record", "store", "log"),
    "verifica": ("verify", "validate", "check"), "comprobar": ("verify", "validate", "check"),
    "comprueba": ("verify", "validate", "check"),
    "usuario": ("user", "identity", "account"), "usuarios": ("user", "identity", "account"),
    "paleta": ("palette", "theme", "appearance"),
    "configuración": ("configuration", "settings", "controls"),
    "configuracion": ("configuration", "settings", "controls"),
    "motor": ("engine", "pipeline"), "interfaz": ("interface", "ui", "dashboard"),
    "recuerdo": ("memory", "history", "decision"), "memoria": ("memory", "history", "decision"),
    # Tailscale renamed/publicized overlapping exposure workflows over time.
    # Treat the product terms as retrieval neighbors without claiming that
    # Funnel (public internet) and Serve (tailnet-only) are equivalent.
    "funnel": ("serve", "tailscale", "https", "proxy"),
    "serve": ("funnel", "tailscale", "https", "proxy"),
    "publicar": ("publish", "serve", "proxy"), "publicado": ("publish", "serve", "proxy"),
    "puerto": ("port", "gateway"), "enlace": ("url", "link", "https"),
    "comando": ("command", "sudo"),
}


def _tokens(text: str) -> list[str]:
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]{1,}", split.lower())
    return words + [alias for word in words for alias in _ALIASES.get(word, ())]


def alias_tokens(text: str) -> list[str]:
    """Return only explicit language/domain aliases, excluding generic split words."""
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]{1,}", split.lower())
    return list(dict.fromkeys(alias for word in words for alias in _ALIASES.get(word, ())))


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
    cached = _ollama_embedding_cached(model, host, text[:12000])
    return list(cached) if cached is not None else None


@lru_cache(maxsize=128)
def _ollama_embedding_cached(model: str, host: str, text: str) -> tuple[float, ...] | None:
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
        return tuple(value / norm for value in vector)
    except Exception:
        return None


def ollama_embeddings(texts: list[str], *, batch_size: int = 24) -> list[list[float] | None]:
    """Embed local text batches, falling back to the compatible single endpoint."""
    model = os.environ.get("GRAPHTYN_EMBED_MODEL", "").strip()
    if not model or not texts:
        return [None for _ in texts]
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    results: list[list[float] | None] = []
    size = max(1, min(64, int(batch_size)))
    for start in range(0, len(texts), size):
        batch = [str(text)[:12000] for text in texts[start:start + size]]
        payload = json.dumps({"model": model, "input": batch}).encode()
        vectors = None
        try:
            request = urllib.request.Request(f"{host}/api/embed", data=payload,
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                vectors = json.loads(response.read()).get("embeddings")
        except Exception:
            vectors = None
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            results.extend(ollama_embedding(text) for text in batch)
            continue
        for values in vectors:
            try:
                vector = [float(value) for value in values]
                norm = math.sqrt(sum(value * value for value in vector)) or 1.0
                results.append([value / norm for value in vector])
            except (TypeError, ValueError):
                results.append(None)
    return results


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


def _cached_semantic_index(graph: dict[str, Any]) -> dict[str, Any]:
    """Reuse vectors while an immutable in-memory graph remains active."""
    key = id(graph)
    signature = (len(graph.get("nodes", [])), len(graph.get("links", [])))
    with _INDEX_CACHE_LOCK:
        cached = _INDEX_CACHE.get(key)
        if cached and cached[0] is graph and cached[1] == signature:
            _INDEX_CACHE.move_to_end(key)
            return cached[2]
    index = build_semantic_index(graph)
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE[key] = (graph, signature, index)
        _INDEX_CACHE.move_to_end(key)
        while len(_INDEX_CACHE) > 8:
            _INDEX_CACHE.popitem(last=False)
    return index


def _cached_node_terms(graph: dict[str, Any]) -> dict[str, set[str]]:
    """Cache lexical terms used to filter local semantic results."""
    key = id(graph)
    signature = (len(graph.get("nodes", [])), len(graph.get("links", [])))
    with _INDEX_CACHE_LOCK:
        cached = _TERM_CACHE.get(key)
        if cached and cached[0] is graph and cached[1] == signature:
            _TERM_CACHE.move_to_end(key)
            return cached[2]
    terms = {
        str(node.get("id")): set(_tokens(_text(node)))
        for node in graph.get("nodes", []) if node.get("id")
    }
    with _INDEX_CACHE_LOCK:
        _TERM_CACHE[key] = (graph, signature, terms)
        _TERM_CACHE.move_to_end(key)
        while len(_TERM_CACHE) > 8:
            _TERM_CACHE.popitem(last=False)
    return terms


def semantic_search(graph: dict[str, Any], query: str, limit: int = 8,
                    index: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    index = index or _cached_semantic_index(graph)
    ollama_provider = str(index.get("provider", "")).startswith("ollama:")
    query_vector = ollama_embedding(query) if ollama_provider else None
    # Vectors from different embedding spaces are not comparable. If an
    # Ollama-backed index cannot embed this query, callers can still use their
    # lexical path; hashing only the query would produce plausible but invalid
    # cosine scores against the stored Ollama vectors.
    if ollama_provider and query_vector is None:
        return []
    expanded_query = " ".join(_tokens(query))
    query_vector = query_vector or hashed_embedding(expanded_query, int(index.get("dimensions") or DIMENSIONS))
    query_terms = set(_tokens(query))
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}
    node_terms_by_id = _cached_node_terms(graph) if not ollama_provider else {}
    scored = []
    for row in index.get("rows", []):
        vector = row.get("vector") or []
        score = sum(a * b for a, b in zip(query_vector, vector))
        if not ollama_provider:
            node_terms = node_terms_by_id.get(str(row.get("id")), set())
            overlap = query_terms & node_terms
            if not overlap:
                continue
            score += len(overlap) / max(1, len(query_terms)) * 2
        if score > 0:
            scored.append((score, nodes.get(row.get("id"))))
    return [{"score": round(score, 4), "node": node} for score, node in
            sorted(scored, key=lambda item: (-item[0], str((item[1] or {}).get("id"))))[:limit] if node]
