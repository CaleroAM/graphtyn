"""Deterministic regression tests for reliability issues identified on 2026-10-08.

Cases:
- E01: Fictitious execution records promoting metrics to verified_measured in benchmark evidence.
- V01: Citation to missing.py resolving against a graph node without a file attribute.
- V02: Citation with nonexistent path prefix resolving against real file via suffix match.
- V03: Numeric quantities in claim text promoted by citation line numbers.
- V04: Compound statements receiving supported status based on one partial edge.
- B01: Agent benchmark overwriting multiple repetitions per task when pairing.
Plus corresponding positive controls and edge conditions specified in RF01-RF05.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from graphtyn.core.agent_benchmark import compare_agent_runs
from graphtyn.core.answer_validation import validate_answer
from graphtyn.core.shared_memory import SharedMemoryStore


def make_reproduction_graph() -> dict[str, Any]:
    """Create the exact reproduction graph specified in PLAN_CORRECCIONES_FIABILIDAD_GRAPHTYN_2026-10-08.md.

    Contains:
    - handler in src/handler.py (lines 1-15)
    - Service in src/service.py (lines 1-30)
    - a project node without a file attribute
    - a relation handler -> Service, label 'llama', confidence 'EXTRACTED', located in src/handler.py:5.
    """
    return {
        "nodes": [
            {
                "id": "symbol:src/handler.py:handler",
                "name": "handler",
                "kind": "function",
                "file": "src/handler.py",
                "line": 1,
                "end_line": 15,
                "details": "Handles requests and coordinates services",
            },
            {
                "id": "symbol:src/service.py:Service",
                "name": "Service",
                "kind": "class",
                "file": "src/service.py",
                "line": 1,
                "end_line": 30,
                "details": "Core service provider coordinates tasks",
            },
            {
                "id": "project:root",
                "name": "myproject",
                "kind": "project",
                # Explicitly lacks a 'file' attribute or file is None
                "details": "Root project metadata node without a source file",
            },
        ],
        "links": [
            {
                "source": "symbol:src/handler.py:handler",
                "target": "symbol:src/service.py:Service",
                "label": "llama",
                "confidence": "EXTRACTED",
                "file": "src/handler.py",
                "line": 5,
            }
        ],
    }


def make_compound_confidence_graph(second_confidence: str) -> dict[str, Any]:
    graph = make_reproduction_graph()
    graph["nodes"].append({
        "id": "symbol:src/db.py:Database", "name": "Database", "kind": "class",
        "file": "src/db.py", "line": 1, "end_line": 20, "details": "Stores records",
    })
    graph["links"].append({
        "source": "symbol:src/service.py:Service", "target": "symbol:src/db.py:Database",
        "label": "llama", "confidence": second_confidence, "file": "src/service.py", "line": 10,
    })
    return graph


_COMPOUND_CONFIDENCE_CASES = [
    ("EXTRACTED", "supported", "extracted_relations_confirmed", False),
    ("AMBIGUOUS", "ambiguous", "claim_contains_ambiguous_relations", True),
    ("INFERRED", "partially_supported", "inferred_relations_require_verification", False),
]


# ============================================================================
# V01–V04: Answer Validation Regressions & Edge Cases (RF04)
# ============================================================================

class TestAnswerValidationRegressions20261008:
    """Regressions for V01, V02, V03, V04 and positive controls."""

    def test_v01_citation_missing_py_against_node_without_file_must_not_be_supported(self):
        """V01: 'handler calls Service (missing.py).' must not resolve against a node without a file."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service (missing.py)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        claim_verdict = result["claims"][0]

        assert claim_verdict["verdict"] != "supported", (
            f"V01 failed: missing.py was erroneously supported: {claim_verdict}"
        )
        assert claim_verdict["verdict"] in ("unsupported", "partially_supported", "abstained")
        assert "missing.py" in str(claim_verdict.get("unresolved_citations") or [])
        assert result["evidence_resolution"]["unresolved_citations"] != []

    def test_v02_citation_nonexistent_prefix_path_must_not_resolve(self):
        """V02: 'handler calls Service (nonexistent/src/handler.py:5).' must not resolve via suffix match."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service (nonexistent/src/handler.py:5)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        claim_verdict = result["claims"][0]

        assert claim_verdict["verdict"] != "supported", (
            f"V02 failed: nonexistent/src/handler.py was erroneously supported: {claim_verdict}"
        )
        assert claim_verdict["verdict"] in ("unsupported", "partially_supported", "abstained")
        assert any("nonexistent" in c for c in claim_verdict.get("unresolved_citations", []))

    def test_v03_citation_line_number_does_not_support_call_frequency(self):
        """V03: 'handler calls Service exactly 5 times (src/handler.py:5).' must not be supported."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service exactly 5 times (src/handler.py:5)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        claim_verdict = result["claims"][0]

        assert claim_verdict["verdict"] != "supported", (
            f"V03 failed: frequency '5 times' was erroneously promoted to supported by citation line 5: {claim_verdict}"
        )
        assert "numeric_values_not_in_evidence" in claim_verdict.get("verdict_reason", "") or claim_verdict["verdict"] != "supported"

    def test_v04_compound_statement_with_unsupported_clause_must_not_be_supported(self):
        """V04: 'handler calls Service and sends passwords to public logs.' must not receive supported."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service and sends passwords to public logs."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        claim_verdict = result["claims"][0]

        assert claim_verdict["verdict"] != "supported", (
            f"V04 failed: compound statement was fully supported despite unsupported secondary clause: {claim_verdict}"
        )
        assert claim_verdict["verdict"] in ("partially_supported", "unsupported", "abstained")

    def test_v_positive_control_valid_citation_and_relation(self):
        """Positive control: 'handler calls Service (src/handler.py:5).' must be supported."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service (src/handler.py:5)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        claim_verdict = result["claims"][0]

        assert claim_verdict["verdict"] == "supported", f"Positive control should be supported: {claim_verdict}"
        assert claim_verdict["unresolved_citations"] == []
        assert len(claim_verdict["relations"]) > 0

    def test_v_positive_control_valid_atomic_claim_without_citation(self):
        """Positive control: 'handler calls Service.' matches extracted edge and is supported."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        claim_verdict = result["claims"][0]

        assert claim_verdict["verdict"] == "supported"

    def test_v_line_out_of_range_rejected(self):
        """Line number outside symbol range fails citation resolution."""
        graph = make_reproduction_graph()
        claim_text = "handler calls Service (src/handler.py:9999)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        assert result["claims"][0]["verdict"] != "supported"
        assert "src/handler.py:9999" in str(result["claims"][0]["unresolved_citations"])

    def test_v_documentation_section_line_range_resolves(self):
        graph = {
            "nodes": [{
                "id": "documentation:docs/report.md:0001", "name": "Results",
                "kind": "documentation_section", "file": "docs/report.md",
                "line_start": 8, "line_end": 14, "details": "Measured latency is 20 ms.",
            }],
            "links": [],
        }

        result = validate_answer(graph, "Measured latency is 20 ms (docs/report.md:12).")

        assert result["claims"][0]["resolved_citations"] == ["docs/report.md:12"]
        assert result["claims"][0]["unresolved_citations"] == []

    def test_v_versions_and_localized_numbers_are_not_citations(self):
        graph = make_reproduction_graph()

        result = validate_answer(graph, "Graphtyn 0.10.4 indexed 2.533 nodes and 6.154 links.")

        assert result["evidence_resolution"]["total_citations"] == 0
        assert result["evidence_resolution"]["unresolved_citations"] == []

    def test_v_technical_dotted_names_are_not_file_citations(self):
        graph = make_reproduction_graph()

        result = validate_answer(graph, "El permiso api.puede_aprobar y manifest.input_schema.features son obligatorios.")

        assert result["evidence_resolution"]["total_citations"] == 0
        assert result["evidence_resolution"]["unresolved_citations"] == []

    def test_v_sha_algorithm_identifier_is_not_a_numeric_claim(self):
        graph = make_reproduction_graph()
        graph["nodes"][0]["details"] = "El manifiesto conserva un hash SHA-256 del artefacto."

        result = validate_answer(graph, "El manifiesto conserva SHA-256 (src/handler.py:5).")

        assert "numeric_values_not_in_evidence" not in result["claims"][0]["verdict_reason"]

    def test_v_existing_unindexed_file_is_distinguished(self, tmp_path):
        graph = make_reproduction_graph()
        (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

        result = validate_answer(
            graph, "La configuración está en docker-compose.yml:1.", project_root=tmp_path,
        )

        assert result["claims"][0]["citation_errors"][0]["reason"] == "file_exists_but_not_indexed"
        assert result["claims"][0]["verdict"] == "abstained"
        assert result["summary"]["abstained"] == 1
        assert result["summary"]["unsupported"] == 0

    def test_v_homonyms_multiple_files_ambiguity(self):
        """Abbreviated citation matching multiple files in different folders is flagged ambiguous."""
        graph = {
            "nodes": [
                {"id": "n1", "name": "A", "file": "src/pkg_a/service.py", "line": 1, "end_line": 10},
                {"id": "n2", "name": "B", "file": "src/pkg_b/service.py", "line": 1, "end_line": 10},
            ],
            "links": [],
        }
        claim_text = "service handles processing (service.py:5)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        assert result["claims"][0]["verdict"] != "supported"
        assert "service.py:5" in str(result["claims"][0]["unresolved_citations"])

    def test_v_windows_separators_normalized(self):
        """Windows backslashes in citations resolve cleanly against slash-separated graph."""
        graph = make_reproduction_graph()
        claim_text = r"handler calls Service (src\handler.py:5)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        assert result["claims"][0]["verdict"] == "supported"

    def test_v_explicit_supported_number(self):
        """When number is in evidence text, it is validated as supported."""
        graph = make_reproduction_graph()
        graph["nodes"][0]["details"] = "handler executes exactly 5 retry attempts."
        claim_text = "handler executes 5 retry attempts (src/handler.py:5)."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        assert result["claims"][0]["verdict"] in ("supported", "partially_supported")
        assert "numeric_values_not_in_evidence" not in result["claims"][0].get("verdict_reason", "")

    def test_v_negated_relation_rejected(self):
        """Negated relation (handler does not call Service) must not be supported by positive link."""
        graph = make_reproduction_graph()
        claim_text = "handler does not call Service."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        assert result["claims"][0]["verdict"] == "unsupported"
        assert result["claims"][0]["verdict_reason"] == "negated_relation"

    def test_v_reversed_direction_rejected(self):
        """Reversed relation (Service calls handler) must not be supported by handler -> Service link."""
        graph = make_reproduction_graph()
        claim_text = "Service calls handler."
        result = validate_answer(graph, claim_text, [{"text": claim_text}])
        assert result["claims"][0]["verdict"] == "unsupported"
        assert result["claims"][0]["verdict_reason"] == "relation_direction_reversed"

    def test_v_absolute_path_requires_exact_project_identity(self, tmp_path):
        graph = make_reproduction_graph()
        project = tmp_path / "project"
        project.mkdir()
        valid = project / "src" / "handler.py"
        claim = f"handler calls Service ({valid}:5)."

        accepted = validate_answer(graph, claim, [{"text": claim}], project_root=project)
        rejected_claim = "handler calls Service (/nonexistent/src/handler.py:5)."
        rejected = validate_answer(
            graph, rejected_claim, [{"text": rejected_claim}], project_root=project
        )

        assert accepted["claims"][0]["verdict"] == "supported"
        assert rejected["claims"][0]["verdict"] == "unsupported"
        assert rejected["claims"][0]["citation_errors"][0]["reason"] == "file_not_in_graph"

    def test_v_same_number_with_unrelated_meaning_does_not_support_quantity(self):
        graph = make_reproduction_graph()
        graph["links"][0]["evidence"] = "The retry delay is 5 seconds."
        graph["nodes"][1]["details"] = "The retry delay is 5 seconds."
        claim = "handler calls Service exactly 5 times (src/handler.py:5)."

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "numeric_values_not_in_evidence" in result["claims"][0]["verdict_reason"]

    def test_v_service_capacity_does_not_prove_call_frequency(self):
        graph = make_reproduction_graph()
        graph["nodes"][1]["details"] = "Service admite 5 usuarios."
        claim = "handler llama a Service 5 veces (src/handler.py:5)."

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "numeric_values_not_in_evidence" in result["claims"][0]["verdict_reason"]

    def test_v_numeric_context_cannot_cross_evidence_sentences(self):
        graph = make_reproduction_graph()
        graph["nodes"][0]["details"] = "handler calls Service"
        graph["nodes"][1]["details"] = "Service admits 5 users"
        claim = "handler calls Service 5 times"

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "numeric_values_not_in_evidence" in result["claims"][0]["verdict_reason"]

    def test_v_same_unit_and_shared_words_do_not_prove_another_relation_quantity(self):
        graph = make_reproduction_graph()
        graph["nodes"][0]["details"] = "handler calls Service"
        graph["nodes"][1]["details"] = "Service calls Database 5 times"
        claim = "handler calls Service 5 times"

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "numeric_values_not_in_evidence" in result["claims"][0]["verdict_reason"]

    def test_v_compound_clause_sharing_only_endpoint_remains_partial(self):
        graph = make_reproduction_graph()
        claim = "handler calls Service and Service sends passwords to public logs."

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "compound_claim_unsupported_clause" in result["claims"][0]["verdict_reason"]

    def test_v_compound_clause_is_not_proved_by_scattered_vocabulary(self):
        graph = make_reproduction_graph()
        graph["nodes"][1]["details"] = "Service admite 5 usuarios."
        claim = "handler llama a Service y handler admite 5 usuarios."

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "compound_claim_unsupported_clause" in result["claims"][0]["verdict_reason"]

    @pytest.mark.parametrize("connector", ["then", "which"])
    def test_v_residual_clause_after_non_enumerated_connector_remains_partial(self, connector):
        graph = make_reproduction_graph()
        claim = f"handler calls Service, {connector} deletes all user accounts"

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "compound_claim_unsupported_clause" in result["claims"][0]["verdict_reason"]

    def test_v_residual_predicate_without_connector_remains_partial(self):
        graph = make_reproduction_graph()
        claim = "handler calls Service, deletes all user accounts"

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert "compound_claim_unsupported_clause" in result["claims"][0]["verdict_reason"]

    @pytest.mark.parametrize(
        ("second_confidence", "expected_verdict", "expected_reason", "ambiguity_present"),
        _COMPOUND_CONFIDENCE_CASES,
    )
    def test_v_compound_relation_uses_weakest_required_confidence(
        self, second_confidence, expected_verdict, expected_reason, ambiguity_present,
    ):
        graph = make_compound_confidence_graph(second_confidence)
        claim = "handler calls Service, then Service calls Database"

        result = validate_answer(graph, claim, [{"text": claim}])

        verdict = result["claims"][0]
        assert verdict["verdict"] == expected_verdict
        assert verdict["verdict_reason"] == expected_reason
        assert verdict["ambiguity_present"] is ambiguity_present
        assert [relation["confidence"] for relation in verdict["relations"]] == [
            "EXTRACTED", second_confidence,
        ]
        assert result["summary"]["partial"] == (expected_verdict != "supported")

    @pytest.mark.parametrize(
        ("second_confidence", "expected_verdict", "expected_reason", "ambiguity_present"),
        _COMPOUND_CONFIDENCE_CASES,
    )
    def test_v_cli_preserves_weakest_required_confidence(
        self, second_confidence, expected_verdict, expected_reason, ambiguity_present,
        tmp_path, monkeypatch, capsys,
    ):
        from graphtyn import cli as graphtyn_cli

        graph = make_compound_confidence_graph(second_confidence)
        claim = "handler calls Service, then Service calls Database"
        monkeypatch.setattr(
            graphtyn_cli.ASTParser, "scan_directory", lambda *_args, **_kwargs: graph,
        )
        monkeypatch.setattr(sys, "argv", [
            "graphtyn", "validate-answer", "--answer", claim, "--path", str(tmp_path),
        ])

        graphtyn_cli.main()

        result = json.loads(capsys.readouterr().out)
        verdict = result["claims"][0]
        assert verdict["verdict"] == expected_verdict
        assert verdict["verdict_reason"] == expected_reason
        assert verdict["ambiguity_present"] is ambiguity_present

    @pytest.mark.parametrize(
        ("second_confidence", "expected_verdict", "expected_reason", "ambiguity_present"),
        _COMPOUND_CONFIDENCE_CASES,
    )
    def test_v_api_preserves_weakest_required_confidence(
        self, second_confidence, expected_verdict, expected_reason, ambiguity_present,
        tmp_path, monkeypatch,
    ):
        from graphtyn.api import main as api_main

        graph = make_compound_confidence_graph(second_confidence)
        claim = "handler calls Service, then Service calls Database"
        monkeypatch.setattr(api_main, "_load_index_for_api", lambda _path: (tmp_path, graph))

        response = api_main.validate_agent_answer({
            "path": str(tmp_path), "answer": claim, "claims": [{"text": claim}],
        })
        result = json.loads(response.body)
        verdict = result["claims"][0]
        assert verdict["verdict"] == expected_verdict
        assert verdict["verdict_reason"] == expected_reason
        assert verdict["ambiguity_present"] is ambiguity_present

    def test_v_modal_relation_is_not_promoted_to_confirmed_support(self):
        graph = make_reproduction_graph()
        claim = "handler may call Service."

        result = validate_answer(graph, claim, [{"text": claim}])

        assert result["claims"][0]["verdict"] == "partially_supported"
        assert result["claims"][0]["verdict_reason"] == "modal_relation_requires_verification"


# ============================================================================
# B01: Agent Benchmark Pairing Regressions (RF05)
# ============================================================================

class TestAgentBenchmarkRegressions20261008:
    """Regressions for B01 and pairing positive controls."""

    def test_b01_multiple_repetitions_per_task_paired_correctly(self):
        """B01: Baseline [100, 300], candidate [80, 280] for same task: deltas must be [-20, -20], mean -20."""
        baseline_runs = [
            {"task_id": "task_alpha", "repetition": 0, "usage": {"total_tokens": 100}, "quality_score": 1.0},
            {"task_id": "task_alpha", "repetition": 1, "usage": {"total_tokens": 300}, "quality_score": 1.0},
        ]
        treatment_runs = [
            {"task_id": "task_alpha", "repetition": 0, "usage": {"total_tokens": 80}, "quality_score": 1.0},
            {"task_id": "task_alpha", "repetition": 1, "usage": {"total_tokens": 280}, "quality_score": 1.0},
        ]

        result = compare_agent_runs(treatment_runs, baseline_runs)
        mean_token_delta = result["paired"]["mean_token_delta"]

        assert mean_token_delta == -20, (
            f"B01 failed: expected mean_token_delta -20, got {mean_token_delta}"
        )
        assert result["paired"]["pairs"] == 2

    def test_b01_permutation_order_invariance(self):
        """B01: Treatment runs passed in reverse repetition order must still pair correctly."""
        baseline_runs = [
            {"task_id": "task_alpha", "repetition": 0, "usage": {"total_tokens": 100}, "quality_score": 1.0},
            {"task_id": "task_alpha", "repetition": 1, "usage": {"total_tokens": 300}, "quality_score": 1.0},
        ]
        treatment_runs = [
            {"task_id": "task_alpha", "repetition": 1, "usage": {"total_tokens": 280}, "quality_score": 1.0},
            {"task_id": "task_alpha", "repetition": 0, "usage": {"total_tokens": 80}, "quality_score": 1.0},
        ]

        result = compare_agent_runs(treatment_runs, baseline_runs)
        assert result["paired"]["mean_token_delta"] == -20
        assert result["paired"]["pairs"] == 2

    def test_b_positive_control_single_repetition_per_task(self):
        """Positive control: Single run per task behaves identically."""
        baseline_runs = [
            {"task_id": "task_1", "usage": {"total_tokens": 100}, "quality_score": 1.0},
            {"task_id": "task_2", "usage": {"total_tokens": 200}, "quality_score": 1.0},
        ]
        treatment_runs = [
            {"task_id": "task_1", "usage": {"total_tokens": 80}, "quality_score": 1.0},
            {"task_id": "task_2", "usage": {"total_tokens": 170}, "quality_score": 1.0},
        ]

        result = compare_agent_runs(treatment_runs, baseline_runs)
        assert result["paired"]["pairs"] == 2
        assert result["paired"]["mean_token_delta"] == -25

    def test_b_missing_quality_scores_not_substituted_with_zero(self):
        """Missing quality score is recorded as unrated, not false tie or zero."""
        baseline_runs = [
            {"task_id": "task_1", "usage": {"total_tokens": 100}},
        ]
        treatment_runs = [
            {"task_id": "task_1", "usage": {"total_tokens": 80}},
        ]
        result = compare_agent_runs(treatment_runs, baseline_runs)
        assert result["paired"]["mean_quality_delta"] is None
        assert result["paired"]["unrated_pairs"] == 1
        assert result["paired"]["quality_ties"] == 0

    def test_b_duplicate_pair_keys_are_excluded_from_statistics(self):
        baseline = [
            {"task_id": "task_1", "repetition": 0, "usage": {"total_tokens": 100}},
            {"task_id": "task_1", "repetition": 0, "usage": {"total_tokens": 999}},
        ]
        treatment = [{"task_id": "task_1", "repetition": 0, "usage": {"total_tokens": 80}}]

        result = compare_agent_runs(treatment, baseline)

        assert result["paired"]["pairs"] == 0
        assert result["paired"]["mean_token_delta"] is None
        assert result["comparability"]["baseline_duplicates"]

    def test_b_ambiguous_repetitions_without_ids_are_excluded(self):
        baseline = [
            {"task_id": "task_1", "usage": {"total_tokens": 100}},
            {"task_id": "task_1", "usage": {"total_tokens": 300}},
        ]
        treatment = [
            {"task_id": "task_1", "usage": {"total_tokens": 280}},
            {"task_id": "task_1", "usage": {"total_tokens": 80}},
        ]

        result = compare_agent_runs(treatment, baseline)

        assert result["paired"]["pairs"] == 0
        assert {item["reason"] for item in result["comparability"]["baseline_exclusions"]} == {
            "ambiguous_missing_repetition"
        }

    def test_b_explicitly_incompatible_conditions_are_not_aggregated(self):
        baseline = [{
            "task_id": "task_1", "usage": {"total_tokens": 100}, "model": "model-a",
            "repository": "repo", "revision": "1", "instructions_digest": "same",
        }]
        treatment = [{
            "task_id": "task_1", "usage": {"total_tokens": 80}, "model": "model-b",
            "repository": "repo", "revision": "1", "instructions_digest": "same",
        }]

        result = compare_agent_runs(treatment, baseline)

        assert result["paired"]["candidate_pairs"] == 1
        assert result["paired"]["pairs"] == 0
        assert result["comparability"]["same_model"] is False
        assert result["paired"]["excluded_incompatible_pairs"][0]["mismatched_conditions"] == ["model"]

    def test_b_missing_token_metric_is_not_replaced_with_zero(self):
        baseline = [{"task_id": "task_1", "usage": {"total_tokens": 100}}]
        treatment = [{"task_id": "task_1", "quality_score": 1.0}]

        result = compare_agent_runs(treatment, baseline)

        assert result["paired"]["pairs"] == 1
        assert result["paired"]["pairs_list"][0]["token_delta"] is None
        assert result["paired"]["mean_token_delta"] is None
        assert result["paired"]["missing_token_pairs"] == 1

    def test_b_large_sample_uses_monte_carlo_permutation_without_hanging(self):
        """Large sample (> 15 pairs) completes swiftly via monte carlo approximation."""
        baseline_runs = [
            {"task_id": f"task_{i}", "usage": {"total_tokens": 100 + i}} for i in range(25)
        ]
        treatment_runs = [
            {"task_id": f"task_{i}", "usage": {"total_tokens": 80 + i}} for i in range(25)
        ]
        result = compare_agent_runs(treatment_runs, baseline_runs)
        assert result["paired"]["pairs"] == 25
        assert result["paired"]["token_permutation_method"] == "monte_carlo_10k"
        assert result["paired"]["token_permutation_p"] is not None


# ============================================================================
# E01: Evidence Provenance Regressions (RF03)
# ============================================================================

class TestEvidenceProvenanceRegressions20261008:
    """Regressions for E01 and evidence provenance."""

    def test_e01_fictitious_execution_record_not_promoted_to_verified_measured(self, tmp_path, monkeypatch):
        """E01: A JSON with tests_passed=123456, fictitious commit, unexecuted command, and filler hashes
        must remain imported_report / imported_only; no metric is verified_measured.
        """
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()

        (project / "benchmarks" / "probe").mkdir(parents=True)
        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "description": "Fictitious execution; command never executed.",
            "tests_passed": 123456,
            "execution_record": {
                "command": ["pytest", "nonexistent_test.py"],
                "exit_code": 0,
                "outcome": "success",
                "started_at": 1000.0,
                "finished_at": 1005.0,
                "executor": "fictitious_runner",
                "log_digest_sha256": "0" * 64,
                "project": {"id": "project"},
                "git_context": {"commit": "fictional_commit_hash", "dirty": False},
                "test_files": ["nonexistent_test.py"],
                "data_files": [],
                "environment_digest_sha256": "1" * 64,
                "declared_dependencies": [],
            },
        }), encoding="utf-8")

        store = SharedMemoryStore(project)
        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        assert imported["imported"]

        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        claim_policy = store._claim_policy(item, store._revision_status(item, store._git_state()))

        assert claim_policy != "verified_measured"
        assert item.get("status") != "verified"
        assert item["metadata"].get("verification_level") in ("imported_report", "integrity_verified", "execution_declared")
        assert claim_policy in ("imported_only", "execution_declared", "unverified", "evidence_missing")
        graph = store.attribution_graph("graphtyn-evidence")
        assert any(link["label"] == "declara" for link in graph["links"])
        assert not any(link["label"] == "produce" for link in graph["links"])

    def test_e_positive_control_verified_local_execution_promotes_measurement(self, tmp_path, monkeypatch):
        """Positive control: An authentic local execution recorded by the executor promotes its measured metric."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-real"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project-real"
        project.mkdir()
        (project / "benchmarks" / "probe").mkdir(parents=True)
        (project / "subject.py").write_text("def run(): return 42\n", encoding="utf-8")
        (project / "test_probe.py").write_text("def test_probe(): assert 6 * 7 == 42\n", encoding="utf-8")

        store = SharedMemoryStore(project)
        record = store.run_local_execution(
            command=[sys.executable, "-m", "pytest", "-q", "test_probe.py"],
            test_files=["test_probe.py"],
            declared_dependencies=["subject.py"],
        )
        assert record.get("execution_id")

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "subject.py",
            "tests_passed": 1,
            "execution_id": record["execution_id"],
            "execution_record": record,
        }), encoding="utf-8")

        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        assert imported["imported"]
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        claim_policy = store._claim_policy(item, store._revision_status(item, store._git_state()))

        assert claim_policy == "verified_measured"
        assert item["status"] == "verified"
        assert item["metadata"]["execution_observed"] is True
        assert item["metadata"]["verified_metrics"] == {"tests_passed": 1}

    def test_e_missing_or_altered_log_fails_verification(self, tmp_path, monkeypatch):
        """If log file is altered or missing on disk, execution is not verified."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()
        (project / "benchmarks" / "probe").mkdir(parents=True)
        (project / "subject.py").write_text("VALUE = 1\n", encoding="utf-8")

        store = SharedMemoryStore(project)
        record = store.record_local_execution(
            command=["python3", "test.py"],
            exit_code=0,
            outcome="success",
            stdout="1 passed\n",
            declared_dependencies=["subject.py"],
            measured_metrics={"tests_passed": 1},
        )
        # Tamper with the log file
        log_file = Path(record["log_path"])
        log_file.write_text("CORRUPTED LOG\n", encoding="utf-8")

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "subject.py",
            "tests_passed": 1,
            "execution_id": record["execution_id"],
            "execution_record": record,
        }), encoding="utf-8")

        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        claim_policy = store._claim_policy(item, store._revision_status(item, store._git_state()))

        assert claim_policy != "verified_measured"
        assert item["metadata"]["execution_observed"] is False
        assert "log_digest_mismatch" in item["metadata"]["execution_errors"]

    def test_e_execution_from_another_project_rejected(self, tmp_path, monkeypatch):
        """Execution recorded for project A cannot substantiate evidence in project B."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        proj_a = tmp_path / "proj_a"
        proj_b = tmp_path / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()
        (proj_b / "benchmarks" / "probe").mkdir(parents=True)
        (proj_b / "subject.py").write_text("VALUE = 1\n", encoding="utf-8")

        store_a = SharedMemoryStore(proj_a)
        store_b = SharedMemoryStore(proj_b)

        record_a = store_a.record_local_execution(
            command=["python3", "test.py"],
            exit_code=0,
            outcome="success",
            stdout="1 passed\n",
            measured_metrics={"tests_passed": 1},
        )

        artifact_b = proj_b / "benchmarks" / "probe" / "summary.json"
        artifact_b.write_text(json.dumps({
            "subject": "subject.py",
            "tests_passed": 1,
            "execution_id": record_a["execution_id"],
            "execution_record": record_a,
        }), encoding="utf-8")

        imported_b = store_b.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item_b = store_b.get(imported_b["imported"][0], requester_agent="graphtyn-evidence")
        claim_policy = store_b._claim_policy(item_b, store_b._revision_status(item_b, store_b._git_state()))

        assert claim_policy != "verified_measured"
        assert item_b["metadata"]["execution_observed"] is False

    def test_e_adulterated_metric_with_authentic_execution_is_distinguished(self, tmp_path, monkeypatch):
        """Authentic execution verifying tests_passed=1 does NOT verify an exaggerated report tests_passed=9999."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()
        (project / "benchmarks" / "probe").mkdir(parents=True)
        (project / "subject.py").write_text("VALUE = 1\n", encoding="utf-8")
        (project / "test_probe.py").write_text("def test_probe(): assert True\n", encoding="utf-8")

        store = SharedMemoryStore(project)
        record = store.run_local_execution(
            command=[sys.executable, "-m", "pytest", "-q", "test_probe.py"],
            test_files=["test_probe.py"],
            declared_dependencies=["subject.py"],
        )

        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "subject.py",
            "tests_passed": 9999,  # Adulterated metric!
            "execution_id": record["execution_id"],
            "execution_record": record,
        }), encoding="utf-8")

        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")
        claim_policy = store._claim_policy(item, store._revision_status(item, store._git_state()))

        # The exaggerated metric is NOT verified
        assert claim_policy != "verified_measured"
        assert item["metadata"]["verified_metrics"] == {}
        assert item["metadata"]["declared_metrics"]["tests_passed"] == 9999

    def test_e_migration_downgrades_historical_unbacked_evidence_with_backup(self, tmp_path, monkeypatch):
        """RF06: Historical items promoted without real local provenance are safely downgraded with backup."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()

        store = SharedMemoryStore(project)
        session = store.start_session("admin", "Test session")
        # Artificially insert a historical memory with status='verified' and unproven execution_observed
        mem = store.checkpoint(
            session["id"], "outcome", "Historical legacy benchmark", "Content",
            status="verified",
            metadata={
                "evidence_type": "benchmark",
                "verification_level": "execution_observed",
                "execution_observed": True,
                "execution_record": {"command": ["legacy"]},
                "reported_metrics": {"score": 95},
            }
        )

        # 1. Preview migration
        preview = store.migrate_evidence_provenance(preview=True)
        assert preview["downgraded_count"] == 1
        assert preview["records"][0]["memory_id"] == mem["id"]
        assert preview["records"][0]["new_status"] == "observed"

        # Check DB was NOT modified during preview
        item_pre = store.get(mem["id"], requester_agent="admin")
        assert item_pre["status"] == "verified"

        # 2. Apply migration
        applied = store.migrate_evidence_provenance(preview=False)
        assert applied["downgraded_count"] == 1

        item_post = store.get(mem["id"], requester_agent="admin")
        assert item_post["status"] == "observed"
        assert item_post["metadata"]["verification_level"] == "execution_declared"
        assert item_post["metadata"]["execution_observed"] is False
        assert item_post["metadata"]["downgraded_from_verified"] is True
        assert item_post["metadata"]["historical_backup"]["status"] == "verified"

    def test_e_real_roundtrip_execute_record_import_stale(self, tmp_path, monkeypatch):
        """RF06: Full roundtrip: execute -> record -> import -> query -> mutate dependency -> observe staleness."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "")
        project = tmp_path / "project"
        project.mkdir()
        (project / "benchmarks" / "suite").mkdir(parents=True)
        dep_file = project / "model.py"
        dep_file.write_text("PARAM = 100\n", encoding="utf-8")
        (project / "test_probe.py").write_text("def test_probe(): assert True\n", encoding="utf-8")

        store = SharedMemoryStore(project)
        # 1. Execute locally via runner
        exec_record = store.run_local_execution(
            command=[sys.executable, "-m", "pytest", "-q", "test_probe.py"],
            test_files=["test_probe.py"],
            data_files=[],
            declared_dependencies=["model.py"],
        )
        assert exec_record["exit_code"] == 0
        assert exec_record["measured_metrics"]["tests_passed"] == 1

        # 2. Generate artifact linked to local execution
        artifact = project / "benchmarks" / "suite" / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "model.py",
            "tests_passed": 1,
            "execution_id": exec_record["execution_id"],
            "execution_record": exec_record,
        }), encoding="utf-8")

        # 3. Import
        imported = store.ingest_benchmark_evidence(["benchmarks/suite/summary.json"])
        mem_id = imported["imported"][0]

        # 4. Query evidence status
        status = store.evidence_status(mem_id, requester_agent="admin")
        assert status["records"][0]["claim_policy"] == "verified_measured"
        assert status["records"][0]["execution_state"] == "success"

        # 5. Mutate dependency -> verify staleness
        dep_file.write_text("PARAM = 200\n", encoding="utf-8")
        status_after = store.evidence_status(mem_id, requester_agent="admin")
        assert status_after["records"][0]["claim_policy"] == "stale"
        assert "model.py" in status_after["records"][0]["stale_files"]

    def test_e_free_form_passed_text_is_not_a_verified_test_metric(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-free-form"))
        project = tmp_path / "project-free-form"
        project.mkdir()
        store = SharedMemoryStore(project)

        record = store.run_local_execution([sys.executable, "-c", "print('999 passed')"])

        assert record["outcome"] == "success"
        assert record["measured_metrics"] == {}

    def test_e_pytest_stderr_cannot_spoof_structured_test_count(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-stderr-spoof"))
        project = tmp_path / "project-stderr-spoof"
        project.mkdir()
        (project / "test_spoof.py").write_text(
            "import sys\n"
            "def test_real():\n"
            "    print('999 passed', file=sys.stderr)\n"
            "    assert True\n",
            encoding="utf-8",
        )
        store = SharedMemoryStore(project)

        record = store.run_local_execution(
            [sys.executable, "-m", "pytest", "-q", "-s", "test_spoof.py"],
            test_files=["test_spoof.py"],
        )

        assert record["outcome"] == "success"
        assert record["measured_metrics"]["tests_passed"] == 1
        assert record["metric_sources"]["tests_passed"]["format"] == "pytest_junit_xml"
        assert Path(record["metric_sources"]["tests_passed"]["path"]).is_file()

    def test_e_omitted_import_fingerprints_use_local_registry_for_staleness(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-registry-fingerprints"))
        project = tmp_path / "project-registry-fingerprints"
        (project / "benchmarks" / "probe").mkdir(parents=True)
        dependency = project / "dependency.py"
        dependency.write_text("VALUE = 1\n", encoding="utf-8")
        (project / "test_probe.py").write_text("def test_probe(): assert True\n", encoding="utf-8")
        store = SharedMemoryStore(project)
        record = store.run_local_execution(
            [sys.executable, "-m", "pytest", "-q", "test_probe.py"],
            test_files=["test_probe.py"],
            declared_dependencies=["dependency.py"],
        )
        dependency.write_text("VALUE = 2\n", encoding="utf-8")
        imported_record = dict(record)
        imported_record.pop("input_fingerprints", None)
        imported_record.pop("post_input_fingerprints", None)
        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "dependency.py",
            "tests": ["test_probe.py"],
            "tests_passed": 1,
            "execution_id": record["execution_id"],
            "execution_record": imported_record,
        }), encoding="utf-8")

        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        status = store.evidence_status(
            imported["imported"][0], requester_agent="admin"
        )["records"][0]

        assert status["claim_policy"] == "stale"
        assert "dependency.py" in status["stale_files"]

    def test_e_tampered_structured_result_cannot_verify_metrics(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-tampered-junit"))
        project = tmp_path / "project-tampered-junit"
        (project / "benchmarks" / "probe").mkdir(parents=True)
        (project / "test_probe.py").write_text("def test_probe(): assert True\n", encoding="utf-8")
        store = SharedMemoryStore(project)
        record = store.run_local_execution(
            [sys.executable, "-m", "pytest", "-q", "test_probe.py"],
            test_files=["test_probe.py"],
        )
        junit_path = Path(record["metric_sources"]["tests_passed"]["path"])
        junit_path.write_text("<testsuites/>", encoding="utf-8")
        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "tests_passed": 1,
            "execution_id": record["execution_id"],
            "execution_record": record,
        }), encoding="utf-8")

        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")

        assert item["metadata"]["execution_observed"] is False
        assert any(
            error.startswith("metric_source_digest_mismatch")
            for error in item["metadata"]["execution_errors"]
        )
        assert item["metadata"]["verified_metrics"] == {}

    def test_e_input_changed_during_test_execution_blocks_observation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-mutated"))
        project = tmp_path / "project-mutated"
        (project / "benchmarks" / "probe").mkdir(parents=True)
        dependency = project / "model.py"
        dependency.write_text("VALUE = 1\n", encoding="utf-8")
        (project / "test_mutates.py").write_text(
            "from pathlib import Path\n"
            "def test_mutates_dependency():\n"
            "    Path('model.py').write_text('VALUE = 2\\n')\n"
            "    assert True\n",
            encoding="utf-8",
        )
        store = SharedMemoryStore(project)
        record = store.run_local_execution(
            [sys.executable, "-m", "pytest", "-q", "test_mutates.py"],
            test_files=["test_mutates.py"], declared_dependencies=["model.py"],
        )
        assert record["inputs_changed"] is True
        artifact = project / "benchmarks" / "probe" / "summary.json"
        artifact.write_text(json.dumps({
            "subject": "model.py", "tests_passed": 1,
            "execution_id": record["execution_id"], "execution_record": record,
        }), encoding="utf-8")

        imported = store.ingest_benchmark_evidence(["benchmarks/probe/summary.json"])
        item = store.get(imported["imported"][0], requester_agent="graphtyn-evidence")

        assert item["metadata"]["execution_observed"] is False
        assert "execution_inputs_changed" in item["metadata"]["execution_errors"]
        assert item["status"] == "observed"

    def test_e_timeout_is_distinct_from_generic_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-timeout"))
        project = tmp_path / "project-timeout"
        project.mkdir()
        store = SharedMemoryStore(project)

        record = store.run_local_execution(
            [sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05
        )

        assert record["outcome"] == "timeout"
        assert record["exit_code"] == -1

    def test_e_execution_id_cannot_be_overwritten_with_different_result(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home-idempotent"))
        project = tmp_path / "project-idempotent"
        project.mkdir()
        store = SharedMemoryStore(project)
        kwargs = {
            "execution_id": "exec_stable",
            "command": ["pytest", "test_probe.py"],
            "exit_code": 0,
            "outcome": "success",
            "stdout": "1 passed\n",
            "test_files": ["test_probe.py"],
            "started_at": 1.0,
            "finished_at": 2.0,
        }
        first = store.record_local_execution(**kwargs)
        second = store.record_local_execution(**kwargs)
        assert first["log_digest_sha256"] == second["log_digest_sha256"]

        with pytest.raises(ValueError, match="execution_id_conflict"):
            store.record_local_execution(**{**kwargs, "stdout": "2 passed\n"})


# ============================================================================
# RF07: Retrieval Degradation, Dimension Incompatibility & Isolation
# ============================================================================

class TestRetrievalDegradationAndIsolationRF07:
    """Tests for embedding service unavailability, dimension incompatibility, and scope isolation."""

    def test_embedding_service_unavailable_degrades_gracefully_to_lexical(self, tmp_path, monkeypatch):
        """When an external embedding provider is configured but fails/times out, retrieval degrades to lexical search without comparing cross-space vectors."""
        import graphtyn.core.shared_memory as sm
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("GRAPHTYN_EMBED_MODEL", "mock-ollama")
        project = tmp_path / "project"
        project.mkdir()

        store = SharedMemoryStore(project)
        session = store.start_session("agy", "Session with Ollama embeddings")
        mem = store.checkpoint(
            session["id"], "fact", "Cache invalidation architecture",
            "CacheInvalidation evicts entries after reindexing",
            files=["cache.py"]
        )

        # Ensure the stored embedding has provider="ollama:mock-ollama:cosine-v1"
        provider = "ollama:mock-ollama:cosine-v1"
        with store._connect() as conn:
            conn.execute(
                "UPDATE memory_embeddings SET provider=?, dimensions=384 WHERE memory_id=?",
                (provider, mem["id"])
            )

        # Mock ollama_embedding to return None (service down or timeout)
        monkeypatch.setattr(sm, "ollama_embedding", lambda _text: None)

        results = store.search("CacheInvalidation evicts entries", requester_agent="agy")
        assert len(results) > 0
        assert results[0]["id"] == mem["id"]
        assert results[0]["retrieval"] == "lexical-degraded:embeddings_unavailable"

    def test_incompatible_vector_dimensions_are_not_compared(self, tmp_path, monkeypatch):
        """Vectors with mismatched dimensions must be skipped rather than truncated or compared across mismatched spaces."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        project = tmp_path / "project"
        project.mkdir()

        store = SharedMemoryStore(project)
        session = store.start_session("agy", "Vector test")
        mem1 = store.checkpoint(session["id"], "fact", "Memory 1", "Alpha content with unique token xyz123")
        mem2 = store.checkpoint(session["id"], "fact", "Memory 2", "Beta content with unique token xyz123")

        # Manually alter mem1 vector dimensions to 2, while mem2 has standard 384 dimensions
        with store._connect() as conn:
            conn.execute(
                "UPDATE memory_embeddings SET dimensions=2, vector_json='[0.5, 0.5]' WHERE memory_id=?",
                (mem1["id"],)
            )

        # Query using standard feature-hash (384 dimensions)
        results = store.search("xyz123", requester_agent="agy")
        # Both may match lexically, but mem1 should not have an invalid truncated dot product
        assert any(r["id"] == mem1["id"] for r in results)
        assert any(r["id"] == mem2["id"] for r in results)

    def test_agent_scope_isolation_prevents_unauthorized_recall(self, tmp_path, monkeypatch):
        """Memories scoped as private cannot be retrieved by unauthorized agents."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        project = tmp_path / "project"
        project.mkdir()

        store = SharedMemoryStore(project)
        session_a = store.start_session("agent_alpha", "Private research")
        private_mem = store.checkpoint(
            session_a["id"], "decision", "Secret key rotation",
            "TopSecretTokenXYZ strictly confidential",
            scope="private"
        )
        session_b = store.start_session("agent_beta", "General work")
        public_mem = store.checkpoint(
            session_b["id"], "fact", "Public token rotation",
            "PublicTokenABC shared configuration",
            scope="project"
        )

        # Agent beta queries for secret token
        res_beta = store.search("TopSecretTokenXYZ", requester_agent="agent_beta")
        assert not any(r["id"] == private_mem["id"] for r in res_beta), "Private memory leaked to unauthorized agent!"

        # Agent alpha queries for secret token
        res_alpha = store.search("TopSecretTokenXYZ", requester_agent="agent_alpha")
        assert any(r["id"] == private_mem["id"] for r in res_alpha), "Owner agent could not access private memory!"

    def test_negative_queries_yield_zero_results(self, tmp_path, monkeypatch):
        """Negative queries with non-existent terms return empty results without spurious hits."""
        monkeypatch.setenv("GRAPHTYN_HOME", str(tmp_path / "home"))
        project = tmp_path / "project"
        project.mkdir()

        store = SharedMemoryStore(project)
        session = store.start_session("agy", "Baseline")
        store.checkpoint(session["id"], "fact", "Normal service", "Standard database operations and logging")

        results = store.search("completelynonexistentpseudorandomterm999", requester_agent="agy")
        assert len(results) == 0
