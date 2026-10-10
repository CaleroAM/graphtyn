"""Regression tests and baseline reproductions for findings H01 and H02 (Task G01).

Findings covered:
- H01: The support of a claim can be apparent (unrelated citations, missing evidence IDs,
       and AMBIGUOUS relations erroneously promote to 'supported'; completeness 'ok'
       confused with factual support).
- H02: Integrity of a report does not equal verified measurement (synthetic reports
       without observed execution promoted to 'verified' and 'verified_measured';
       dependencies of reported code not tracked for staleness).

Each finding includes:
1. Baseline reproduction test: Documents and verifies the currently observed flaw.
2. Target contract test (marked xfail): Specifies the exact contract expected after
   implementing tasks G02 and G03, ensuring regressions are caught and verified.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from graphtyn.core.answer_validation import validate_answer
from graphtyn.core.shared_memory import SharedMemoryStore


# ============================================================================
# Fixtures & Graph Helpers
# ============================================================================

def make_test_graph() -> dict[str, Any]:
    """Create a minimal deterministic code graph for answer validation testing."""
    return {
        "nodes": [
            {
                "id": "symbol:src/service.py:Service",
                "name": "Service",
                "kind": "class",
                "file": "src/service.py",
                "line": 1,
                "end_line": 30,
                "details": "Coordinates jobs and task execution",
            },
            {
                "id": "symbol:src/handler.py:handler",
                "name": "handler",
                "kind": "function",
                "file": "src/handler.py",
                "line": 1,
                "end_line": 15,
                "details": "Handles HTTP requests",
            },
        ],
        "links": [
            {
                "source": "symbol:src/handler.py:handler",
                "target": "symbol:src/service.py:Service",
                "label": "llama",
                "confidence": "AMBIGUOUS",
                "file": "src/handler.py",
                "line": 5,
            }
        ],
    }


# ============================================================================
# H01: Regression Verifications (G02 Fixes Validated)
# ============================================================================

class TestH01RegressionVerifications:
    """Verify that H01 flaws are resolved and deterministic negatives do NOT promote to supported."""

    def test_h01_unrelated_citation_must_not_promote_to_supported(self):
        """Verified fix: a non-existent file citation with lexical term match yields unsupported."""
        graph = make_test_graph()
        claim_text = "Service sends payments (missing.py:999999)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])

        # Verified fix: cannot be supported; citation is marked unresolved
        assert result["claims"][0]["verdict"] != "supported"
        assert result["claims"][0]["verdict"] == "unsupported"
        assert "missing.py:999999" in result["claims"][0]["unresolved_citations"]
        assert result["evidence_resolution"]["unresolved_citations"] == ["missing.py:999999"]

    def test_h01_missing_evidence_id_must_not_promote_to_supported(self):
        """Verified fix: requesting a non-existent evidence_id yields unsupported."""
        graph = make_test_graph()
        claim_text = "Service sends payments automatically every evening."
        result = validate_answer(graph, claim_text, [{"text": claim_text, "evidence_ids": ["missing-node"]}])

        # Verified fix: cannot be supported when requested ID is not in graph
        assert result["claims"][0]["verdict"] != "supported"
        assert result["claims"][0]["verdict"] == "unsupported"
        assert result["evidence_resolution"]["unresolved_evidence_ids"] == ["missing-node"]

    def test_h01_ambiguous_relation_must_not_promote_to_supported(self):
        """Verified fix: a link with confidence 'AMBIGUOUS' yields 'ambiguous', not confirmed 'supported'."""
        graph = make_test_graph()
        claim_text = "handler calls Service during request processing."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])

        # Verified fix: uncertainty preserved
        assert result["claims"][0]["verdict"] == "ambiguous"
        assert result["claims"][0]["ambiguity_present"] is True

    def test_h01_unsupported_claim_distinguishes_operation_ok_from_support(self):
        """Verified fix: operation_ok is True, but summary supported is 0 and verdict is unsupported."""
        graph = make_test_graph()
        claim_text = "Zebras transport galaxies safely across distant universes."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])

        # Operation succeeded, but claim is completely unsupported
        assert result["operation_ok"] is True
        assert result["claims"][0]["verdict"] == "unsupported"
        assert result["summary"]["supported"] == 0
        assert result["summary"]["unsupported"] == 1

    def test_h01_unasserted_nearby_relation_does_not_reject_valid_citation(self):
        """A graph edge is irrelevant when the claim does not assert its predicate."""
        graph = make_test_graph()
        claim_text = "The handler documentation is located in src/handler.py:9."

        result = validate_answer(graph, claim_text, [{"text": claim_text}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert result["claims"][0]["verdict_reason"] == "citation_resolved_but_claim_semantics_unverified"


# ============================================================================
# H01: Target Contracts (Fully Satisfied by Task G02)
# ============================================================================

class TestH01TargetContracts:
    """Target regression assertions for H01, fully satisfied by Task G02."""

    def test_h01_target_nonexistent_citation_must_not_promote_supported(self):
        """Non-existent citation (missing.py:999999) must be flagged unresolved and not supported."""
        graph = make_test_graph()
        claim_text = "Service sends payments (missing.py:999999)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        verdict = result["claims"][0]["verdict"]

        assert verdict != "supported", f"Unrelated non-existent citation must not yield supported; got {verdict}"
        assert verdict in ("unsupported", "abstained", "partially_supported")

    def test_h01_target_nonexistent_evidence_id_must_not_promote_supported(self):
        """Non-existent evidence_id ('missing-node') must be validated and rejected."""
        graph = make_test_graph()
        claim_text = "Service sends payments automatically every evening."
        result = validate_answer(graph, claim_text, [{"text": claim_text, "evidence_ids": ["missing-node"]}])
        verdict = result["claims"][0]["verdict"]

        assert verdict != "supported", f"Missing evidence_id must not promote claim to supported; got {verdict}"

    def test_h01_target_ambiguous_relation_must_preserve_uncertainty(self):
        """AMBIGUOUS relations must not be stated as confirmed supported facts."""
        graph = make_test_graph()
        claim_text = "handler calls Service during request processing."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        verdict = result["claims"][0]["verdict"]

        assert verdict != "supported", f"AMBIGUOUS relation must not produce supported verdict; got {verdict}"
        assert verdict in ("ambiguous", "partially_supported")

    def test_h01_target_contract_separates_operation_ok_from_support(self):
        """Structured contract must expose operation_ok and evidence_resolution explicitly."""
        graph = make_test_graph()
        claim_text = "Zebras transport galaxies safely across distant universes."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])

        assert "operation_ok" in result and "evidence_resolution" in result


# ============================================================================
# H02: Regression Verifications (G03 Fixes Validated)
# ============================================================================

class TestH02RegressionVerifications:
    """Verify that H02 flaws are resolved and synthetic reports do not become verified_measured."""

    def test_h02_synthetic_benchmark_is_not_promoted_to_verified_measured(self, tmp_path, monkeypatch):
        """Verified fix: an unexecuted synthetic benchmark is classified as imported_report / imported_only."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()

        source = project / "unreferenced_model.py"
        source.write_text("def model(): return 1\n", encoding="utf-8")

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({
            "description": "Synthetic claim; no command executed.",
            "subject": "unreferenced_model.py",
            "tests_passed": 123456,
        }), encoding="utf-8")

        store = SharedMemoryStore(project)
        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        assert imported["imported"]

        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        rev_status = store._revision_status(item, store._git_state())
        claim_policy = store._claim_policy(item, rev_status)

        # Verified fix:
        assert item["status"] != "verified"
        assert item["status"] == "observed"
        assert item["metadata"]["verification_level"] == "imported_report"
        assert claim_policy != "verified_measured"
        assert claim_policy == "imported_only"
        # Declared subject is fingerprinted along with the artifact
        assert "unreferenced_model.py" in item["metadata"]["source_fingerprints"]

    def test_h02_referenced_code_change_triggers_staleness(self, tmp_path, monkeypatch):
        """Verified fix: modifying code referenced in a benchmark properly triggers staleness."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()

        source = project / "unreferenced_model.py"
        source.write_text("def model(): return 1\n", encoding="utf-8")

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({
            "description": "Synthetic claim; no command executed.",
            "subject": "unreferenced_model.py",
            "tests_passed": 123456,
        }), encoding="utf-8")

        store = SharedMemoryStore(project)
        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")

        stale_before = store._stale_files(item)
        assert stale_before == []

        # Modify the source file named in the benchmark
        source.write_text("def model(): return 2\n", encoding="utf-8")

        stale_after = store._stale_files(item)
        # Verified fix: stale_files detects that the dependent source was altered
        assert "unreferenced_model.py" in stale_after

    @pytest.mark.parametrize(("outcome", "exit_code", "policy"), [
        ("failed", 2, "execution_failed"),
        ("cancelled", None, "execution_cancelled"),
    ])
    def test_h02_observed_non_successful_execution_is_preserved_without_metric_promotion(
            self, tmp_path, monkeypatch, outcome, exit_code, policy):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / f"home-{outcome}"))
        project = tmp_path / outcome
        (project / "benchmarks" / outcome).mkdir(parents=True)
        (project / "subject.py").write_text("VALUE = 1\n", encoding="utf-8")
        store = SharedMemoryStore(project)
        rec = store.record_local_execution(
            command=["pytest"],
            exit_code=exit_code if exit_code is not None else -1,
            outcome=outcome,
            executor="ci/test",
            declared_dependencies=["subject.py"],
            measured_metrics={"tests_passed": 999},
        )
        artifact = project / "benchmarks" / outcome / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "subject.py", "tests_passed": 999,
            "execution_id": rec["execution_id"],
            "execution_record": rec,
        }), encoding="utf-8")
        imported = store.ingest_benchmark_evidence([f"benchmarks/{outcome}/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        revision = store._revision_status(item, store._git_state())

        assert item["metadata"]["execution_observed"] is True
        assert item["metadata"]["execution_outcome"] == outcome
        assert item["status"] == "observed"
        assert store._claim_policy(item, revision) == policy
        assert store.evidence_status(item["id"], requester_agent="dashboard")["records"][0]["execution_state"] == outcome


# ============================================================================
# H02: Target Contracts (Fully Satisfied by Task G03)
# ============================================================================

class TestH02TargetContracts:
    """Target regression assertions for H02, fully satisfied by Task G03."""

    def test_h02_target_synthetic_report_must_not_be_verified_measured(self, tmp_path, monkeypatch):
        """Imported reports without observed execution must be classified as imported_report, not verified_measured."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({
            "description": "Synthetic claim; no command executed.",
            "tests_passed": 123456,
        }), encoding="utf-8")

        store = SharedMemoryStore(project)
        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        claim_policy = store._claim_policy(item, store._revision_status(item, store._git_state()))

        assert claim_policy != "verified_measured", (
            f"Synthetic report without execution must not yield verified_measured; got {claim_policy}"
        )
        assert item.get("verification_level") in ("imported_report", "integrity_verified") or claim_policy == "imported_only"

    def test_h02_target_declared_dependencies_tracked_for_staleness(self, tmp_path, monkeypatch):
        """When declared subject or dependency code changes, the benchmark evidence must become stale."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()

        source = project / "unreferenced_model.py"
        source.write_text("def model(): return 1\n", encoding="utf-8")

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({
            "description": "Benchmark with declared dependencies.",
            "subject": "unreferenced_model.py",
            "dependencies": ["unreferenced_model.py"],
            "tests_passed": 123456,
        }), encoding="utf-8")

        store = SharedMemoryStore(project)
        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")

        # Mutate the declared dependency
        source.write_text("def model(): return 2\n", encoding="utf-8")

        stale_files = store._stale_files(item)
        assert "unreferenced_model.py" in stale_files, (
            f"Expected unreferenced_model.py in stale_files; got {stale_files}"
        )
