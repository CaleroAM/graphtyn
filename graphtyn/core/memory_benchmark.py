"""Reproducible shared-memory retrieval benchmark with honest aggregate metrics."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from .shared_memory import SharedMemoryStore


_STABILITY_TOPICS = [
    ("authgateway", "Authentication gateway", "AuthGateway validates credentials and rotates JWT signing keys"),
    ("postgresledger", "PostgreSQL ledger", "PostgresLedger replaced the earlier MySQL accounting proposal"),
    ("viewportpanel", "Viewport panels", "ViewportPanel keeps palette and engine controls inside the browser viewport"),
    ("dragphysics", "Node drag physics", "DragPhysics preserves pointer capture while graph nodes are moved"),
    ("cacheinvalidation", "Cache invalidation", "CacheInvalidation evicts project entries after incremental indexing"),
    ("paymentretry", "Payment retry", "PaymentRetry uses exponential backoff and an idempotency key"),
    ("queueworker", "Queue worker", "QueueWorker acknowledges jobs only after durable processing"),
    ("emailoutbox", "Email outbox", "EmailOutbox publishes messages after the database transaction commits"),
    ("searchranking", "Search ranking", "SearchRanking combines lexical evidence and semantic similarity"),
    ("uploadscanner", "Upload scanner", "UploadScanner quarantines files until malware inspection completes"),
    ("rolepolicy", "Role policy", "RolePolicy denies administrative actions without explicit permission"),
    ("audittrail", "Audit trail", "AuditTrail preserves actor session timestamp and correction provenance"),
    ("structuredlogs", "Structured logs", "StructuredLogs redact credentials and retain correlation identifiers"),
    ("latencymetrics", "Latency metrics", "LatencyMetrics reports mean and p95 without hiding failed samples"),
    ("bluedeploy", "Blue green deploy", "BlueDeploy shifts traffic only after health checks succeed"),
    ("containerhealth", "Container health", "ContainerHealth separates readiness from liveness probes"),
    ("configschema", "Configuration schema", "ConfigSchema rejects unknown engine settings before reindexing"),
    ("schemamigration", "Schema migration", "SchemaMigration uses versioned forward migrations and rollback notes"),
    ("rollbackguard", "Rollback guard", "RollbackGuard blocks rollback when irreversible writes are detected"),
    ("webhooksignature", "Webhook signature", "WebhookSignature verifies timestamps and rejects replayed payloads"),
    ("invoiceworkflow", "Invoice workflow", "InvoiceWorkflow emits approval events before final settlement"),
    ("inventoryreserve", "Inventory reserve", "InventoryReserve releases stock after checkout timeout"),
    ("customermerge", "Customer merge", "CustomerMerge retains aliases and records the surviving profile"),
    ("sessionrotation", "Session rotation", "SessionRotation replaces identifiers after privilege changes"),
    ("fieldencryption", "Field encryption", "FieldEncryption encrypts sensitive columns with rotated envelope keys"),
    ("backupverify", "Backup verification", "BackupVerify restores a sample before declaring a backup healthy"),
    ("retrybudget", "Retry budget", "RetryBudget caps repeated calls to protect downstream services"),
    ("timeoutpolicy", "Timeout policy", "TimeoutPolicy applies separate connect and response deadlines"),
    ("featuretoggle", "Feature toggle", "FeatureToggle records owner expiry date and rollout percentage"),
    ("localecatalog", "Locale catalog", "LocaleCatalog falls back by language without hiding missing translations")
]


def build_stability_dataset() -> dict[str, Any]:
    authors = ["agy", "opencode", "codex", "openclaw"]
    requesters = ["codex", "agy", "openclaw"]
    memories, queries = [], []
    for index, (anchor, title, content) in enumerate(_STABILITY_TOPICS):
        author = authors[index % len(authors)]
        key = f"scenario-{index + 1:02d}"
        memories.append({"key": key, "agent_id": author, "session": key, "kind": "decision",
                         "task": title, "title": f"{title} [{anchor}]", "content": f"Alias {anchor}. {content}",
                         "branch": "main" if index % 2 == 0 else f"feature/{anchor}"})
        formulations = [f"Explain the {anchor} decision", f"¿Qué se decidió sobre {anchor}?",
                        f"Recall implementation details for {anchor}"]
        for form_index, formulation in enumerate(formulations):
            for requester in requesters:
                queries.append({"id": f"{key}-f{form_index + 1}-{requester}", "query": formulation,
                                "expected_key": key, "expected_agent": author, "agent_id": requester,
                                "token_budget": 700})
    for index in range(15):
        queries.append({"id": f"negative-{index + 1:02d}", "query": f"nonexistenttopic{index:02d}",
                        "expected_key": None, "agent_id": requesters[index % 3], "token_budget": 300})
    return {"version": 1, "suite": "stable-30x3x3", "memories": memories, "queries": queries,
            "design": {"scenarios": 30, "formulations_per_scenario": 3, "requesters": requesters,
                       "positive_queries": 270, "negative_queries": 15}}


def run_memory_benchmark(dataset: dict[str, Any], output: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="graphtyn-memory-benchmark-") as temp:
        project = Path(temp) / "project"
        project.mkdir()
        store = SharedMemoryStore(project, db_path=Path(temp) / "memory-v2.db")
        ids: dict[str, str] = {}
        sessions: dict[str, str] = {}
        for item in dataset.get("memories", []):
            agent = str(item.get("agent_id") or "benchmark")
            session_key = str(item.get("session") or agent)
            if session_key not in sessions:
                sessions[session_key] = store.start_session(agent, str(item.get("task") or "benchmark"),
                    branch=item.get("branch"), session_id=f"ses_bench_{len(sessions)}")["id"]
            memory = store.checkpoint(sessions[session_key], str(item.get("kind") or "fact"),
                str(item.get("title") or item["key"]), str(item.get("content") or ""),
                files=item.get("files") or [], node_ids=item.get("node_ids") or [], status="verified")
            ids[str(item["key"])] = memory["id"]
        rows, latencies, total_tokens = [], [], 0
        keys_by_id = {memory_id: key for key, memory_id in ids.items()}
        for query in dataset.get("queries", []):
            started = time.perf_counter()
            context = store.context(str(query["query"]), requester_agent=str(query.get("agent_id") or "evaluator"),
                                    limit=int(query.get("limit") or 10), token_budget=int(query.get("token_budget") or 1200),
                                    include_graph=False)
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            total_tokens += context["estimated_tokens"]
            returned = [item["id"] for item in context["memories"]]
            expected = ids.get(str(query["expected_key"]))
            negative = query.get("expected_key") is None
            rank = returned.index(expected) + 1 if expected in returned else None
            expected_agent = str(query.get("expected_agent") or "")
            attributed = bool(rank and context["memories"][rank - 1]["agent_id"] == expected_agent) if expected_agent else bool(rank)
            rows.append({"id": query.get("id"), "query": query["query"], "expected_key": query["expected_key"],
                         "negative": negative, "requester_agent": str(query.get("agent_id") or "evaluator"),
                         "returned_keys": [keys_by_id.get(memory_id, "unknown") for memory_id in returned],
                         "rank": rank, "hit_at_5": bool(rank and rank <= 5), "hit_at_10": bool(rank and rank <= 10),
                         "reciprocal_rank": round(1 / rank, 6) if rank else 0.0,
                         "attribution_correct": attributed, "estimated_tokens": context["estimated_tokens"],
                         "latency_ms": round(elapsed, 3)})
        positives = [row for row in rows if not row["negative"]]
        negatives = [row for row in rows if row["negative"]]
        count = len(rows)
        percentile = sorted(latencies)[max(0, min(len(latencies) - 1, int(len(latencies) * .95) - 1))] if latencies else 0
        metrics = {"queries": count, "positive_queries": len(positives), "negative_queries": len(negatives),
                   "recall_at_5": round(sum(row["hit_at_5"] for row in positives) / max(1, len(positives)), 4),
                   "recall_at_10": round(sum(row["hit_at_10"] for row in positives) / max(1, len(positives)), 4),
                   "mrr": round(sum(row["reciprocal_rank"] for row in positives) / max(1, len(positives)), 4),
                   "attribution_accuracy": round(sum(row["attribution_correct"] for row in positives) / max(1, len(positives)), 4),
                   "negative_accuracy": round(sum(not row["returned_keys"] for row in negatives) / max(1, len(negatives)), 4),
                   "estimated_tokens_total": total_tokens,
                   "estimated_tokens_mean": round(total_tokens / max(1, count), 2),
                   "latency_ms_mean": round(statistics.mean(latencies), 3) if latencies else 0,
                   "latency_ms_p95": round(percentile, 3)}
        metrics["by_requester_agent"] = {}
        for agent in sorted({row["requester_agent"] for row in positives}):
            agent_rows = [row for row in positives if row["requester_agent"] == agent]
            metrics["by_requester_agent"][agent] = {
                "queries": len(agent_rows),
                "recall_at_5": round(sum(row["hit_at_5"] for row in agent_rows) / len(agent_rows), 4),
                "mrr": round(sum(row["reciprocal_rank"] for row in agent_rows) / len(agent_rows), 4),
                "attribution_accuracy": round(sum(row["attribution_correct"] for row in agent_rows) / len(agent_rows), 4),
            }
        result = {"ok": True, "protocol": "graphtyn-shared-memory-v1", "metrics": metrics,
                  "queries": rows, "failures": [row for row in rows if (not row["negative"] and not row["hit_at_10"]) or (row["negative"] and row["returned_keys"])],
                  "token_estimation": "caracteres UTF-8 / 4; no es facturación del proveedor"}
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
