"""Deterministic, isolated benchmark for source-message retrieval."""

from __future__ import annotations

import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from .shared_memory import SharedMemoryStore


CASES = (
    {
        "id": "tailscale-command-rationale",
        "query": ("¿Qué comando se usó para Tailscale, cuál era el enlace, el puerto, "
                  "el backend, si fue Serve o Funnel y por qué se decidió así?"),
        "source_id": "ground-truth:tailscale",
        "answer": ("Se ejecutó `sudo tailscale serve --bg --https=443 --set-path / "
                   "http://192.0.2.79:18789`. El enlace fue "
                   "https://node.example.test. Se eligió Serve en el host porque "
                   "la VM ya no estaba en el tailnet; el host termina HTTPS en 443 y "
                   "hace proxy al backend HTTP del puerto 18789."),
    },
    {
        "id": "memory-product-purpose",
        "query": "¿Cómo explicarías Graphtyn en diez palabras y para qué sirve su memoria de proyecto?",
        "source_id": "ground-truth:purpose",
        "answer": ("Graphtyn recupera contexto verificable y memoria compartida para agentes de un proyecto."),
    },
)


def run_source_message_benchmark(*, repetitions: int = 5) -> dict[str, Any]:
    """Measure retrieval quality/latency without models, services, or live stores."""
    repetitions = max(1, min(50, int(repetitions)))
    old_home = os.environ.get("GRAPHTYN_HOME")
    old_model = os.environ.pop("GRAPHTYN_EMBED_MODEL", None)
    try:
        with tempfile.TemporaryDirectory(prefix="graphtyn-memory-eval-") as temporary:
            root = Path(temporary)
            os.environ["GRAPHTYN_HOME"] = str(root / "home")
            project = root / "project"
            project.mkdir()
            store = SharedMemoryStore(project)
            session = store.ensure_external_session(
                "benchmark/source", "ground-truth", "Deterministic retrieval evidence", consent=True)
            for case in CASES:
                store.append_message(session["id"], "assistant", case["answer"], metadata={
                    "provider": "benchmark", "source_message_id": case["source_id"],
                    "origin": "conversation", "evaluation": False})
            noise = store.ensure_external_session(
                "benchmark/evaluator", "evaluation-noise", "Evaluation transcript", consent=True)
            store.append_message(noise["id"], "assistant",
                "La evaluación repite Tailscale, Graphtyn, el comando y el enlace sin ser evidencia.",
                metadata={"provider": "benchmark", "source_message_id": "evaluation:echo",
                          "origin": "evaluation", "evaluation": True,
                          "derived_from": [case["source_id"] for case in CASES]})

            observations = []
            latencies = []
            for _iteration in range(repetitions):
                for case in CASES:
                    started = time.perf_counter()
                    result = store.search_messages(case["query"], limit=6)
                    latencies.append((time.perf_counter() - started) * 1000)
                    ids = [item.get("source_message_id") for item in result["messages"]]
                    observations.append({
                        "case": case["id"], "hit": case["source_id"] in ids,
                        "evaluation_leak": "evaluation:echo" in ids,
                        "sufficient_evidence": result["obligations"]["sufficient_evidence"],
                        "missing": result["obligations"]["missing"],
                        "returned_characters": sum(len(item["content"]) for item in result["messages"]),
                        "candidate_messages": result["scanned_messages"],
                        "retrieval": result["retrieval"],
                    })
            ordered = sorted(latencies)
            p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * .95) - 1))
            return {
                "ok": all(row["hit"] and not row["evaluation_leak"] for row in observations),
                "schema_version": 1, "isolated": True, "external_models": False,
                "live_store_modified": False, "cases": len(CASES), "repetitions": repetitions,
                "queries": len(observations),
                "recall_at_6": sum(row["hit"] for row in observations) / len(observations),
                "obligation_sufficiency_rate": sum(row["sufficient_evidence"] for row in observations) / len(observations),
                "evaluation_leak_rate": sum(row["evaluation_leak"] for row in observations) / len(observations),
                "latency_ms": {"median": round(statistics.median(latencies), 3),
                               "p95": round(ordered[p95_index], 3)},
                "consumption_guardrail": {
                    "metric": "returned_characters", "limit_per_query": 3840,
                    "maximum_observed": max(row["returned_characters"] for row in observations),
                    "passed": max(row["returned_characters"] for row in observations) <= 3840,
                    "note": "Context size guardrail; not provider-billed tokens.",
                },
                "observations": observations,
            }
    finally:
        if old_home is None:
            os.environ.pop("GRAPHTYN_HOME", None)
        else:
            os.environ["GRAPHTYN_HOME"] = old_home
        if old_model is not None:
            os.environ["GRAPHTYN_EMBED_MODEL"] = old_model
