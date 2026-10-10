"""RF07 scale benchmark for the shared-memory retrieval path."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from . import shared_memory as shared_memory_module
from .semantic_index import hashed_embedding
from .shared_memory import SharedMemoryStore
from .system_metrics import memory_info, peak_rss_bytes


QUALITY_THRESHOLDS = {
    "recall_at_5_min": 0.95,
    "mrr_min": 0.95,
    "ndcg_at_10_min": 0.95,
    "negative_accuracy_min": 0.99,
    "attribution_accuracy_min": 1.0,
    "errors_max": 0,
    "isolation_violations_max": 0,
    "retrieval_mode_explicit_min": 1.0,
    "peak_rss_fraction_max": 0.80,
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return round(ordered[index], 3)


def _database_bytes(path: Path) -> int:
    return sum(candidate.stat().st_size for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
               if candidate.exists())


def _bulk_load(store: SharedMemoryStore, dataset: dict[str, Any]) -> dict[str, Any]:
    """Load a controlled fixture in one transaction while preserving the production schema."""
    started = time.perf_counter()
    commit = store._git_state().get("commit")
    now = time.time()
    task = "RF07 deterministic scale benchmark"
    agents = sorted({str(item["agent_id"]) for item in dataset["memories"]})
    sessions = {agent: f"ses_rf07_{agent.rsplit('-', 1)[-1]}" for agent in agents}
    with store._connect() as conn:
        conn.executemany("INSERT INTO agents(id,client,display_name,created_at) VALUES(?,?,?,?)",
                         [(agent, agent, agent, now) for agent in agents])
        conn.executemany("""INSERT INTO sessions
            (id,agent_id,task,branch,base_commit,worktree,capture_enabled,started_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            [(sessions[agent], agent, task, "main", commit, str(store.workspace), 0, now)
             for agent in agents])
        for offset in range(0, len(dataset["memories"]), 1_000):
            chunk = dataset["memories"][offset:offset + 1_000]
            memory_rows, fts_rows, embedding_rows, provenance_rows, audit_rows = [], [], [], [], []
            for position, item in enumerate(chunk, start=offset):
                memory_id = f"mem_rf07_{position:07d}"
                agent = str(item["agent_id"])
                title, content = str(item["title"]), str(item["content"])
                created = now + position / 1_000_000
                content_digest = hashlib.sha256(_json([title, content, [], []]).encode()).hexdigest()
                embedding_text = f"fact {title} {content} {task}"
                vector = hashed_embedding(embedding_text)
                embedding_digest = hashlib.sha256(embedding_text.encode()).hexdigest()
                memory_rows.append((memory_id, sessions[agent], agent, "fact", "project", "verified",
                    title, content, task, "main", commit, commit, 1.0, "[]", "[]", "[]", "{}",
                    content_digest, created, created, None))
                fts_rows.append((memory_id, title, content, task, "", ""))
                embedding_rows.append((memory_id, "feature-hash-v2", len(vector), embedding_digest,
                                       _json(vector), created))
                provenance_rows.append((memory_id, sessions[agent], agent, "[]", created))
                audit_rows.append((created, "checkpoint", agent, sessions[agent], memory_id,
                                   '{"fixture":"rf07"}'))
            conn.executemany("""INSERT INTO memories
                (id,session_id,agent_id,kind,scope,status,title,content,task,branch,base_commit,
                 observed_commit,confidence,files_json,node_ids_json,tests_json,metadata_json,
                 content_sha256,created_at,updated_at,supersedes_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", memory_rows)
            conn.executemany("INSERT INTO memories_fts(memory_id,title,content,task,files,nodes) VALUES(?,?,?,?,?,?)",
                             fts_rows)
            conn.executemany("""INSERT INTO memory_embeddings
                (memory_id,provider,dimensions,content_sha256,vector_json,updated_at)
                VALUES(?,?,?,?,?,?)""", embedding_rows)
            conn.executemany("""INSERT INTO memory_provenance
                (memory_id,session_id,agent_id,source_message_ids_json,observed_at) VALUES(?,?,?,?,?)""",
                             provenance_rows)
            conn.executemany("""INSERT INTO audit_log
                (timestamp,action,agent_id,session_id,memory_id,details_json) VALUES(?,?,?,?,?,?)""",
                             audit_rows)
    with store._connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    elapsed = time.perf_counter() - started
    return {"seconds": round(elapsed, 3),
            "records_per_second": round(len(dataset["memories"]) / max(elapsed, 1e-9), 2)}


def _incremental_update(store: SharedMemoryStore, dataset: dict[str, Any]) -> dict[str, Any]:
    """Reindex a deterministic one-percent sample in a single incremental transaction."""
    count = max(10, min(500, len(dataset["memories"]) // 100))
    indexes = sorted({round(index * (len(dataset["memories"]) - 1) / max(1, count - 1))
                      for index in range(count)})
    started = time.perf_counter()
    memory_rows, fts_rows, embedding_rows, audit_rows, memory_ids = [], [], [], [], []
    task = "RF07 deterministic scale benchmark"
    for index in indexes:
        item = dataset["memories"][index]
        memory_id = f"mem_rf07_{index:07d}"
        agent = str(item["agent_id"])
        title = str(item["title"])
        content = f"{item['content']} Incremental revision rf07-{index:05d}."
        digest = hashlib.sha256(_json([title, content, [], []]).encode()).hexdigest()
        embedding_text = f"fact {title} {content} {task}"
        updated = time.time()
        memory_ids.append(memory_id)
        memory_rows.append((content, digest, updated, memory_id))
        fts_rows.append((memory_id, title, content, task, "", ""))
        embedding_rows.append((hashlib.sha256(embedding_text.encode()).hexdigest(),
                               _json(hashed_embedding(embedding_text)), updated, memory_id))
        audit_rows.append((updated, "incremental_reindex", agent,
                           f"ses_rf07_{agent.rsplit('-', 1)[-1]}", memory_id, '{"fixture":"rf07"}'))
    with store._connect() as conn:
        conn.executemany("UPDATE memories SET content=?,content_sha256=?,updated_at=? WHERE id=?", memory_rows)
        marks = ",".join("?" for _ in memory_ids)
        conn.execute(f"DELETE FROM memories_fts WHERE memory_id IN ({marks})", memory_ids)
        conn.executemany("INSERT INTO memories_fts(memory_id,title,content,task,files,nodes) VALUES(?,?,?,?,?,?)",
                         fts_rows)
        conn.executemany("""UPDATE memory_embeddings SET content_sha256=?,vector_json=?,updated_at=?
            WHERE memory_id=? AND provider='feature-hash-v2'""", embedding_rows)
        conn.executemany("""INSERT INTO audit_log
            (timestamp,action,agent_id,session_id,memory_id,details_json) VALUES(?,?,?,?,?,?)""", audit_rows)
    elapsed = time.perf_counter() - started
    return {"records": len(indexes), "seconds": round(elapsed, 3),
            "records_per_second": round(len(indexes) / max(elapsed, 1e-9), 2)}


def _query_metrics(store: SharedMemoryStore, dataset: dict[str, Any], mode: str) -> dict[str, Any]:
    latencies, rows, errors = [], [], []
    keys_by_id = {f"mem_rf07_{index:07d}": str(item["key"])
                  for index, item in enumerate(dataset["memories"])}
    started_all = time.perf_counter()
    for query in dataset["queries"]:
        started = time.perf_counter()
        try:
            context = store.context(str(query["query"]), requester_agent=str(query.get("agent_id") or "evaluator"),
                                    limit=10, token_budget=int(query.get("token_budget") or 500), include_graph=False)
            memories = context["memories"]
        except Exception as exc:  # the benchmark must retain every failed sample
            memories = []
            errors.append({"id": query.get("id"), "type": type(exc).__name__, "message": str(exc)[:500]})
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        returned = [keys_by_id.get(str(item.get("id")), "unknown") for item in memories]
        expected_key = query.get("expected_key")
        rank = returned.index(expected_key) + 1 if expected_key in returned else None
        negative = expected_key is None
        expected_agent = str(query.get("expected_agent") or "")
        attribution = bool(rank and memories[rank - 1].get("agent_id") == expected_agent) if expected_agent else bool(rank)
        rows.append({"id": query.get("id"), "query": str(query.get("query") or ""),
                     "query_kind": str(query.get("query_kind") or "unspecified"),
                     "negative": negative, "rank": rank,
                     "hit_at_5": bool(rank and rank <= 5), "hit_at_10": bool(rank and rank <= 10),
                     "reciprocal_rank": 1 / rank if rank else 0.0,
                     "ndcg_at_10": (1 / math.log2(rank + 1)) if rank and rank <= 10 else 0.0,
                     "attribution_correct": attribution, "returned": returned,
                     "retrieval": memories[0].get("retrieval") if memories else None,
                     "latency_ms": round(elapsed, 3)})
    elapsed_all = time.perf_counter() - started_all
    positives = [row for row in rows if not row["negative"]]
    negatives = [row for row in rows if row["negative"]]
    probe_query = next((str(item["query"]) for item in dataset["queries"] if item.get("expected_key")), "benchmark")
    probe = store.search(probe_query, requester_agent="scale-evaluator", limit=5)
    expected_retrieval = ("lexical-degraded:embeddings_unavailable"
                          if mode == "degraded_without_embeddings" else "hybrid-rrf:feature-hash-v2")
    retrieval_mode_explicit = float(bool(probe and probe[0].get("retrieval") == expected_retrieval))
    by_query_kind = {}
    for kind in sorted({row["query_kind"] for row in rows}):
        kind_rows = [row for row in rows if row["query_kind"] == kind]
        kind_positive = [row for row in kind_rows if not row["negative"]]
        kind_negative = [row for row in kind_rows if row["negative"]]
        by_query_kind[kind] = {
            "queries": len(kind_rows),
            "positive_queries": len(kind_positive),
            "negative_queries": len(kind_negative),
            "recall_at_5": (round(sum(row["hit_at_5"] for row in kind_positive) / len(kind_positive), 4)
                             if kind_positive else None),
            "mrr": (round(sum(row["reciprocal_rank"] for row in kind_positive) / len(kind_positive), 4)
                    if kind_positive else None),
            "negative_accuracy": (round(sum(not row["returned"] for row in kind_negative) / len(kind_negative), 4)
                                  if kind_negative else None),
        }
    return {"mode": mode, "queries": len(rows), "errors": errors,
            "recall_at_5": round(sum(row["hit_at_5"] for row in positives) / max(1, len(positives)), 4),
            "recall_at_10": round(sum(row["hit_at_10"] for row in positives) / max(1, len(positives)), 4),
            "mrr": round(sum(row["reciprocal_rank"] for row in positives) / max(1, len(positives)), 4),
            "ndcg_at_10": round(sum(row["ndcg_at_10"] for row in positives) / max(1, len(positives)), 4),
            "attribution_accuracy": round(sum(row["attribution_correct"] for row in positives) / max(1, len(positives)), 4),
            "negative_accuracy": round(sum(not row["returned"] for row in negatives) / max(1, len(negatives)), 4),
            "latency_ms_p50": _percentile(latencies, 0.50),
            "latency_ms_p95": _percentile(latencies, 0.95),
            "latency_ms_p99": _percentile(latencies, 0.99),
            "queries_per_second": round(len(rows) / max(elapsed_all, 1e-9), 2),
            "retrieval_mode_explicit": retrieval_mode_explicit,
            "by_query_kind": by_query_kind, "samples": rows}


def _check_isolation(primary: SharedMemoryStore, root: Path) -> int:
    other = root / "isolated-project"
    other.mkdir()
    secondary = SharedMemoryStore(other, db_path=root / "isolated-memory.db")
    session = secondary.start_session("isolated-agent", "RF07 isolation")
    secondary.checkpoint(session["id"], "fact", "Isolation sentinel",
                         "Exclusive sentinel rf07isolatedsecret", status="verified")
    leaked = primary.search("rf07isolatedsecret", requester_agent="scale-evaluator", limit=5)
    visible = secondary.search("rf07isolatedsecret", requester_agent="isolated-agent", limit=5)
    return int(bool(leaked)) + int(not visible)


def _guardrails(metrics: dict[str, Any], isolation_violations: int,
                peak_fraction: float | None) -> dict[str, Any]:
    actual = {**metrics, "errors": len(metrics["errors"]),
              "isolation_violations": isolation_violations, "peak_rss_fraction": peak_fraction}
    results = {}
    for name, threshold in QUALITY_THRESHOLDS.items():
        key, comparison = (name[:-4], "min") if name.endswith("_min") else (name[:-4], "max")
        value = actual.get(key)
        passed = value is not None and (value >= threshold if comparison == "min" else value <= threshold)
        results[name] = {"actual": value, "threshold": threshold, "passed": passed}
    return results


def _environment() -> dict[str, Any]:
    memory = memory_info()
    return {"hostname": platform.node(), "platform": platform.platform(),
            "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
            "cpu_count": os.cpu_count(), "memory": memory}


def run_scale_benchmark(dataset: dict[str, Any], *, repetitions: int = 5,
                        output: Path | None = None) -> dict[str, Any]:
    """Run paired normal/degraded retrieval measurements for one RF07 scale."""
    repetitions = max(1, min(20, int(repetitions)))
    runs, environment = [], _environment()
    total_memory = environment["memory"]["total_bytes"]
    for repetition in range(1, repetitions + 1):
        with tempfile.TemporaryDirectory(prefix="graphtyn-rf07-") as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            db_path = root / "memory.db"
            store = SharedMemoryStore(project, db_path=db_path)
            before_available = memory_info()["available_bytes"]
            indexing = _bulk_load(store, dataset)
            incremental = _incremental_update(store, dataset)
            normal = _query_metrics(store, dataset, "normal")
            with store._connect() as conn:
                conn.execute("UPDATE memory_embeddings SET provider='ollama:rf07-unavailable:cosine-v1'")
            original_ollama = shared_memory_module.ollama_embedding
            shared_memory_module.ollama_embedding = lambda _text: None
            try:
                degraded = _query_metrics(store, dataset, "degraded_without_embeddings")
            finally:
                shared_memory_module.ollama_embedding = original_ollama
            isolation_violations = _check_isolation(store, root)
            peak_bytes = peak_rss_bytes()
            peak_fraction = round(peak_bytes / total_memory, 6) if peak_bytes is not None and total_memory else None
            for metrics in (normal, degraded):
                metrics["guardrails"] = _guardrails(metrics, isolation_violations, peak_fraction)
            runs.append({"repetition": repetition, "indexing": indexing, "incremental": incremental,
                         "database_bytes": _database_bytes(db_path),
                         "peak_rss_bytes": peak_bytes, "peak_rss_fraction": peak_fraction,
                         "available_memory_delta_bytes": before_available - memory_info()["available_bytes"],
                         "isolation_violations": isolation_violations,
                         "normal": normal, "degraded_without_embeddings": degraded})
    summary = {}
    for mode in ("normal", "degraded_without_embeddings"):
        mode_runs = [run[mode] for run in runs]
        summary[mode] = {key: round(statistics.median(item[key] for item in mode_runs), 4)
                         for key in ("recall_at_5", "mrr", "ndcg_at_10", "negative_accuracy",
                                     "attribution_accuracy", "latency_ms_p50", "latency_ms_p95",
                                     "latency_ms_p99", "queries_per_second")}
        summary[mode]["errors"] = sum(len(item["errors"]) for item in mode_runs)
    passed = all(result["passed"] for run in runs for mode in ("normal", "degraded_without_embeddings")
                 for result in run[mode]["guardrails"].values())
    result = {"ok": passed, "protocol": "graphtyn-shared-memory-rf07-v1",
              "execution_id": f"rf07_{uuid.uuid4().hex}", "executed_at": time.time(),
              "dataset": {"suite": dataset.get("suite"), "records": len(dataset["memories"]),
                          "queries": len(dataset["queries"]),
                          "sha256": hashlib.sha256(_json(dataset).encode()).hexdigest()},
              "repetitions": repetitions, "thresholds_precommitted": QUALITY_THRESHOLDS,
              "environment": environment, "summary": summary, "runs": runs}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
