# GRAPHTYN CHANGE REPORT — graphtyn

- Base: `HEAD`
- Risk: **HIGH** (100/100)
- Changed files: 83
- Changed symbols: 433
- Impacted nodes: 694

## Changed symbols

- `_median` — `benchmarks/summarize_shared_memory_rf07.py:30` (logic)
- `_load` — `benchmarks/summarize_shared_memory_rf07.py:34` (logic)
- `_source_revision` — `benchmarks/summarize_shared_memory_rf07.py:45` (logic)
- `summarize` — `benchmarks/summarize_shared_memory_rf07.py:62` (logic)
- `_report` — `benchmarks/summarize_shared_memory_rf07.py:115` (logic)
- `main` — `benchmarks/summarize_shared_memory_rf07.py:138` (logic)
- `_vision_ask` — `graphtyn/api/enrich.py:29` (signature)
- `_enrich_with_ai` — `graphtyn/api/enrich.py:261` (signature)
- `lifespan` — `graphtyn/api/main.py:64` (signature)
- `require_remote_memory_auth` — `graphtyn/api/main.py:445` (signature)
- `_registered_code_project` — `graphtyn/api/main.py:593` (signature)
- `_project_access_denied` — `graphtyn/api/main.py:609` (signature)
- `_ensure_reindex_jobs_ready` — `graphtyn/api/main.py:1036` (signature)
- `_public_reindex_job` — `graphtyn/api/main.py:1047` (signature)
- `_set_reindex_job` — `graphtyn/api/main.py:1054` (signature)
- `_reindex_cancelled` — `graphtyn/api/main.py:1058` (signature)
- `_execute_reindex` — `graphtyn/api/main.py:1062` (signature)
- `_run_reindex_job` — `graphtyn/api/main.py:1172` (signature)
- `update` — `graphtyn/api/main.py:1175` (signature)
- `reindex_project` — `graphtyn/api/main.py:1191` (signature)
- `get_reindex_job` — `graphtyn/api/main.py:1242` (signature)
- `get_reindex_status` — `graphtyn/api/main.py:1254` (signature)
- `cancel_reindex_job` — `graphtyn/api/main.py:1264` (signature)
- `generate_semantic_graph` — `graphtyn/api/main.py:1275` (signature)
- `validate_agent_answer` — `graphtyn/api/main.py:1355` (signature)
- `get_graph` — `graphtyn/api/main.py:1506` (signature)
- `memory_evidence_status` — `graphtyn/api/main.py:1847` (signature)
- `memory_project_doctor` — `graphtyn/api/main.py:1859` (signature)
- `_http_mcp_tools` — `graphtyn/api/main.py:2719` (signature)
- `_mcp_tool_response` — `graphtyn/api/main.py:2750` (signature)
- `_mcp_protocol_error` — `graphtyn/api/main.py:2757` (signature)
- `_authorize_http_mcp` — `graphtyn/api/main.py:2762` (signature)
- `_http_project_context_tool` — `graphtyn/api/main.py:2782` (signature)
- `_http_agent_tool` — `graphtyn/api/main.py:2837` (signature)
- `_authorize_http_memory_tool` — `graphtyn/api/main.py:2915` (signature)
- `_execute_http_memory_tool` — `graphtyn/api/main.py:2938` (signature)
- `_execute_http_memory_read_or_lifecycle` — `graphtyn/api/main.py:2986` (signature)
- `_execute_http_graph_tool` — `graphtyn/api/main.py:3071` (signature)
- `_dispatch_http_mcp_tool` — `graphtyn/api/main.py:3120` (signature)
- `mcp_http` — `graphtyn/api/main.py:3154` (signature)
- `_community_of` — `graphtyn/api/semantic_graph.py:26` (logic)
- `_node_community` — `graphtyn/api/semantic_graph.py:34` (logic)
- `_semantic_tokens` — `graphtyn/api/semantic_graph.py:46` (logic)
- `_load_embedding_vectors` — `graphtyn/api/semantic_graph.py:59` (logic)
- `_embedding_similarity` — `graphtyn/api/semantic_graph.py:72` (logic)
- `_build_communities` — `graphtyn/api/semantic_graph.py:83` (logic)
- `_semantic_candidates` — `graphtyn/api/semantic_graph.py:129` (logic)
- `_append_semantic_links` — `graphtyn/api/semantic_graph.py:158` (logic)
- `_append_structural_links` — `graphtyn/api/semantic_graph.py:191` (logic)
- `build_semantic_graph` — `graphtyn/api/semantic_graph.py:203` (logic)
- `_command_harness` — `graphtyn/cli.py:219` (signature)
- `parse_pairs` — `graphtyn/cli.py:224` (signature)
- `_command_setup` — `graphtyn/cli.py:300` (signature)
- `_command_onboard` — `graphtyn/cli.py:364` (signature)
- `_command_adapter` — `graphtyn/cli.py:438` (signature)
- `_command_service` — `graphtyn/cli.py:447` (signature)
- `_command_token` — `graphtyn/cli.py:469` (signature)
- `_command_restore` — `graphtyn/cli.py:477` (signature)
- `_command_init` — `graphtyn/cli.py:484` (signature)
- `_command_reindex` — `graphtyn/cli.py:491` (signature)
- `_command_query` — `graphtyn/cli.py:528` (signature)
- `_command_query_intent` — `graphtyn/cli.py:535` (signature)
- `_command_analyze_change` — `graphtyn/cli.py:543` (signature)
- `_command_context` — `graphtyn/cli.py:548` (signature)
- `_command_path` — `graphtyn/cli.py:553` (signature)
- `_command_explain` — `graphtyn/cli.py:562` (signature)
- `_command_diff` — `graphtyn/cli.py:574` (signature)
- `_command_ci_check` — `graphtyn/cli.py:600` (signature)
- `_command_verify_edit` — `graphtyn/cli.py:617` (signature)
- `_command_validate_answer` — `graphtyn/cli.py:621` (signature)
- `_command_impact` — `graphtyn/cli.py:626` (signature)
- `_command_review` — `graphtyn/cli.py:641` (signature)
- `_command_benchmark` — `graphtyn/cli.py:653` (signature)
- `_command_agent_benchmark` — `graphtyn/cli.py:661` (signature)
- `_command_benchmark_suite` — `graphtyn/cli.py:667` (signature)
- `_command_type_status` — `graphtyn/cli.py:679` (signature)
- `_command_agent_grade` — `graphtyn/cli.py:684` (signature)
- `_command_benchmark_graphify` — `graphtyn/cli.py:690` (signature)
- `_command_export_md` — `graphtyn/cli.py:696` (signature)
- `_command_report` — `graphtyn/cli.py:717` (signature)
- `_command_global` — `graphtyn/cli.py:730` (signature)
- `_command_memory` — `graphtyn/cli.py:746` (signature)
- `_command_agent_install` — `graphtyn/cli.py:749` (signature)
- `_command_integrations` — `graphtyn/cli.py:761` (signature)
- `_command_ci_install` — `graphtyn/cli.py:778` (signature)
- `_command_timeline` — `graphtyn/cli.py:782` (signature)
- `_command_mcp` — `graphtyn/cli.py:792` (signature)
- `_command_serve` — `graphtyn/cli.py:795` (signature)
- `_command_gitignore` — `graphtyn/cli.py:817` (signature)
- `_command_hook` — `graphtyn/cli.py:824` (signature)
- `main` — `graphtyn/cli.py:844` (signature)
- `_sync_cycle_space_summary` — `graphtyn/cli_memory.py:29` (logic)
- `_sync_cycle_log_summary` — `graphtyn/cli_memory.py:52` (logic)
- `_memory_brain_init` — `graphtyn/cli_memory.py:76` (logic)
- `_memory_consolidate` — `graphtyn/cli_memory.py:113` (logic)
- `_memory_scope` — `graphtyn/cli_memory.py:146` (logic)
- `_memory_alias_import` — `graphtyn/cli_memory.py:199` (logic)
- `_memory_stores` — `graphtyn/cli_memory.py:222` (logic)
- `_memory_bootstrap` — `graphtyn/cli_memory.py:251` (logic)
- `_memory_projects` — `graphtyn/cli_memory.py:276` (logic)

## Blast radius

- hop 1 · `SharedMemoryStore` · declara · EXTRACTED · `graphtyn/core/shared_memory.py`
- hop 1 · `contexto-comparativo.md` · usa · INFERRED · `docs/contexto-comparativo.md`
- hop 1 · `shared_semantic_memory_plan.md` · usa · INFERRED · `docs/shared_semantic_memory_plan.md`
- hop 1 · `README.md` · referencia · EXTRACTED · `README.md`
- hop 1 · `shared-memory.md` · usa · INFERRED · `docs/shared-memory.md`
- hop 1 · `cli.py` · llama · EXTRACTED · `graphtyn/cli.py`
- hop 1 · `SKILL.md` · usa · INFERRED · `skills/graphtyn/SKILL.md`
- hop 1 · `AGENTS.md` · usa · INFERRED · `AGENTS.md`
- hop 1 · `index.md` · referencia · EXTRACTED · `docs/index.md`
- hop 1 · `getMemoryColor` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `GRAPHTYN_REPORT.md` · usa · INFERRED · `docs/GRAPHTYN_REPORT.md`
- hop 1 · `install_agent` · llama · EXTRACTED · `graphtyn/core/agent_installer.py`
- hop 1 · `particleProfile` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `MemoryJobManager` · declara · EXTRACTED · `graphtyn/core/memory_jobs.py`
- hop 1 · `agent_memory_policy.md` · usa · INFERRED · `graphtyn/agent_memory_policy.md`
- hop 1 · `competitive-validation-0.8.0.md` · usa · INFERRED · `docs/competitive-validation-0.8.0.md`
- hop 1 · `ProjectWatcher` · declara · EXTRACTED · `graphtyn/core/watcher.py`
- hop 1 · `check_maintainability.py` · llama · EXTRACTED · `tools/check_maintainability.py`
- hop 1 · `hexRgb` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `testing.md` · usa · INFERRED · `docs/testing.md`
- hop 1 · `ASTParser` · declara · EXTRACTED · `graphtyn/core/ast_parser.py`
- hop 1 · `apply_setup` · llama · EXTRACTED · `graphtyn/core/deployment.py`
- hop 1 · `saveMemoryColors` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `setView` · llama · INFERRED · `graphtyn/web/js/controls.js`
- hop 1 · `applyMemoryPalette` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `getMemoryColors` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `_memory_scope_agents` · llama · EXTRACTED · `graphtyn/mcp_server.py`
- hop 1 · `loadProjects` · llama · INFERRED · `graphtyn/web/js/ui.js`
- hop 1 · `parse_file` · llama · EXTRACTED · `graphtyn/core/tree_sitter_backend.py`
- hop 1 · `REPORT.md` · usa · INFERRED · `benchmarks/real_repos_current_2026-08-22/REPORT.md`
- hop 1 · `render_report` · llama · EXTRACTED · `graphtyn/core/overview_report.py`
- hop 1 · `MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md` · usa · INFERRED · `docs/MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md`
- hop 1 · `market-study.md` · referencia · EXTRACTED · `docs/market-study.md`
- hop 1 · `closeBlastPanel` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `markMemoryCustom` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `summarize_shared_memory_rf07.py` · llama · EXTRACTED · `benchmarks/summarize_shared_memory_rf07.py`
- hop 1 · `test_agent_mcp_context_is_bound_to_token_identity_and_store` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `build_local_index` · llama · EXTRACTED · `graphtyn/core/deployment.py`
- hop 1 · `generate_change_report` · llama · EXTRACTED · `graphtyn/api/main.py`
- hop 1 · `safePaint` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `saveMemoryPalette` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `selectProject` · llama · INFERRED · `graphtyn/web/js/ui.js`
- hop 1 · `smoke_frontend.py` · llama · EXTRACTED · `tests/smoke_frontend.py`
- hop 1 · `writeJsonStorage` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `cloneMemoryColors` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `focusNode` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `getMemoryPalette` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `initWatchPolling` · llama · INFERRED · `graphtyn/web/js/ui.js`
- hop 1 · `resetMemoryColor` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `resetMemoryColors` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `updateMemoryColor` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `_refresh` · llama · EXTRACTED · `graphtyn/core/watcher.py`
- hop 1 · `changeGraphStyle` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `getCommKey` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `get_diff` · llama · EXTRACTED · `graphtyn/api/main.py`
- hop 1 · `handleGraphBackgroundClick` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `installReliableNodeDrag` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `markMemoryColorsCustom` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `particleSeed` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `readJsonStorage` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `saveVisualPreferences` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `setDim` · llama · INFERRED · `graphtyn/web/js/controls.js`
- hop 1 · `showStyleErr` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `test_http_mcp_project_context_rejects_ambiguous_name_and_out_of_scope_token` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_install_agent_updates_memory_scope_automatically` · llama · INFERRED · `tests/test_memory_scope.py`
- hop 1 · `test_overview_verifies_purpose_frameworks_architecture_and_risks` · llama · EXTRACTED · `tests/test_overview_report.py`
- hop 1 · `test_pr_impact_reports_risk_and_changed_file` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_report_is_compact_persistent_format_and_compares_graphify_tokens` · llama · EXTRACTED · `tests/test_overview_report.py`
- hop 1 · `test_structural_cache_reuses_unchanged_tree_sitter_result` · llama · EXTRACTED · `tests/test_ast_parser.py`
- hop 1 · `test_symbol_level_diff_impacts_callers_not_every_symbol` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `changeNodeShape` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `handleGraphNodeClick` · llama · EXTRACTED · `graphtyn/web/js/graph.js`
- hop 1 · `loadVisualPreferences` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `mixColor` · contiene · EXTRACTED · `graphtyn/web/js/state.js`
- hop 1 · `setMemoryGraphMode` · llama · INFERRED · `graphtyn/web/js/controls.js`
- hop 1 · `test_adaptive_planner_uses_semantic_fallback_and_validates_context` · llama · EXTRACTED · `tests/test_advanced_quality.py`
- hop 1 · `test_adaptive_source_evidence_reads_only_selected_symbol_body` · llama · EXTRACTED · `tests/test_advanced_quality.py`
- hop 1 · `test_change_analyst_returns_grounded_targets_state_and_contracts` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_csharp_members_are_typed_graph_entities` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_history_endpoint` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_http_mcp_reads_only_explicit_registered_project_memory` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_impact_planner_uses_directional_consumers_not_lexical_noise` · llama · EXTRACTED · `tests/test_advanced_quality.py`
- hop 1 · `test_markdown_sections_become_located_searchable_nodes_and_redact_credentials` · llama · EXTRACTED · `tests/test_ast_parser.py`
- hop 1 · `test_overview_intent_builds_diverse_repository_profile` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_qualified_selector_disambiguates_same_named_methods` · llama · EXTRACTED · `tests/test_mcp_server.py`
- hop 1 · `test_query_intent_filters_bindings_into_one_shot_package` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_query_intent_keeps_exact_python_component_without_flow_markers` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_type_sidecar_is_applied_and_parser_reports_incremental_cache` · llama · EXTRACTED · `tests/test_advanced_quality.py`
- hop 1 · `test_csharp_cross_file_resolution_prefers_container_and_interface` · llama · EXTRACTED · `tests/test_ast_parser.py`
- hop 1 · `test_csharp_method_operations_preserve_external_calls_and_returns` · llama · EXTRACTED · `tests/test_competitive_features.py`
- hop 1 · `test_csharp_nested_member_chain_resolves_receiver_type` · llama · EXTRACTED · `tests/test_ast_parser.py`
- hop 1 · `test_dashboard_assets_served` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_evidence_answer_checks_make_requested_zeros_explicit` · llama · EXTRACTED · `tests/test_mcp_server.py`
- hop 1 · `test_evidence_format_deduplicates_paths_and_reduces_payload` · llama · EXTRACTED · `tests/test_mcp_server.py`
- hop 1 · `test_evidence_prioritizes_query_relevant_operations` · llama · EXTRACTED · `tests/test_mcp_server.py`
- hop 1 · `test_health_endpoint` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_js_route_rejects_traversal` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_memory_search_all_enforces_token_project_scope` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_memory_search_all_federated` · llama · EXTRACTED · `tests/test_api.py`
- hop 1 · `test_ollama_models_unreachable_returns_empty` · llama · EXTRACTED · `tests/test_api.py`

## Recommended verification

1. `None` — impact_engine_action (location unavailable)
2. `_median` — changed (benchmarks/summarize_shared_memory_rf07.py)
3. `_load` — changed (benchmarks/summarize_shared_memory_rf07.py)
4. `_source_revision` — changed (benchmarks/summarize_shared_memory_rf07.py)
5. `summarize` — changed (benchmarks/summarize_shared_memory_rf07.py)
6. `_report` — changed (benchmarks/summarize_shared_memory_rf07.py)
7. `main` — changed (benchmarks/summarize_shared_memory_rf07.py)
8. `_vision_ask` — changed (graphtyn/api/enrich.py)
9. `_enrich_with_ai` — changed (graphtyn/api/enrich.py)
10. `lifespan` — changed (graphtyn/api/main.py)
11. `require_remote_memory_auth` — changed (graphtyn/api/main.py)
12. `_registered_code_project` — changed (graphtyn/api/main.py)
13. `_project_access_denied` — changed (graphtyn/api/main.py)
14. `_ensure_reindex_jobs_ready` — changed (graphtyn/api/main.py)
15. `_public_reindex_job` — changed (graphtyn/api/main.py)
16. `_set_reindex_job` — changed (graphtyn/api/main.py)
17. `_reindex_cancelled` — changed (graphtyn/api/main.py)
18. `_execute_reindex` — changed (graphtyn/api/main.py)
19. `_run_reindex_job` — changed (graphtyn/api/main.py)
20. `update` — changed (graphtyn/api/main.py)
21. `reindex_project` — changed (graphtyn/api/main.py)
22. `get_reindex_job` — changed (graphtyn/api/main.py)
23. `get_reindex_status` — changed (graphtyn/api/main.py)
24. `cancel_reindex_job` — changed (graphtyn/api/main.py)
25. `generate_semantic_graph` — changed (graphtyn/api/main.py)
26. `validate_agent_answer` — changed (graphtyn/api/main.py)
27. `get_graph` — changed (graphtyn/api/main.py)
28. `memory_evidence_status` — changed (graphtyn/api/main.py)
29. `memory_project_doctor` — changed (graphtyn/api/main.py)
30. `_http_mcp_tools` — changed (graphtyn/api/main.py)
31. `_mcp_tool_response` — changed (graphtyn/api/main.py)
32. `_mcp_protocol_error` — changed (graphtyn/api/main.py)
33. `_authorize_http_mcp` — changed (graphtyn/api/main.py)
34. `_http_project_context_tool` — changed (graphtyn/api/main.py)
35. `_http_agent_tool` — changed (graphtyn/api/main.py)
36. `_authorize_http_memory_tool` — changed (graphtyn/api/main.py)
37. `_execute_http_memory_tool` — changed (graphtyn/api/main.py)
38. `_execute_http_memory_read_or_lifecycle` — changed (graphtyn/api/main.py)
39. `_execute_http_graph_tool` — changed (graphtyn/api/main.py)
40. `_dispatch_http_mcp_tool` — changed (graphtyn/api/main.py)
41. `mcp_http` — changed (graphtyn/api/main.py)
42. `_community_of` — changed (graphtyn/api/semantic_graph.py)
43. `_node_community` — changed (graphtyn/api/semantic_graph.py)
44. `_semantic_tokens` — changed (graphtyn/api/semantic_graph.py)
45. `_load_embedding_vectors` — changed (graphtyn/api/semantic_graph.py)
46. `_embedding_similarity` — changed (graphtyn/api/semantic_graph.py)
47. `_build_communities` — changed (graphtyn/api/semantic_graph.py)
48. `_semantic_candidates` — changed (graphtyn/api/semantic_graph.py)
49. `_append_semantic_links` — changed (graphtyn/api/semantic_graph.py)
50. `SharedMemoryStore` — consumer_hop_1 (graphtyn/core/shared_memory.py)
51. `contexto-comparativo.md` — consumer_hop_1 (location unavailable)
52. `shared_semantic_memory_plan.md` — consumer_hop_1 (location unavailable)
53. `README.md` — consumer_hop_1 (location unavailable)
54. `shared-memory.md` — consumer_hop_1 (location unavailable)
55. `cli.py` — consumer_hop_1 (location unavailable)
56. `SKILL.md` — consumer_hop_1 (location unavailable)
57. `AGENTS.md` — consumer_hop_1 (location unavailable)
58. `index.md` — consumer_hop_1 (location unavailable)
59. `GRAPHTYN_REPORT.md` — consumer_hop_1 (location unavailable)
60. `install_agent` — consumer_hop_1 (graphtyn/core/agent_installer.py)
61. `MemoryJobManager` — consumer_hop_1 (graphtyn/core/memory_jobs.py)
62. `agent_memory_policy.md` — consumer_hop_1 (location unavailable)
63. `competitive-validation-0.8.0.md` — consumer_hop_1 (location unavailable)
64. `ProjectWatcher` — consumer_hop_1 (graphtyn/core/watcher.py)
65. `check_maintainability.py` — consumer_hop_1 (location unavailable)
66. `testing.md` — consumer_hop_1 (location unavailable)
67. `ASTParser` — consumer_hop_1 (graphtyn/core/ast_parser.py)
68. `apply_setup` — consumer_hop_1 (graphtyn/core/deployment.py)
69. `setView` — consumer_hop_1 (graphtyn/web/js/controls.js)
70. `_memory_scope_agents` — consumer_hop_1 (graphtyn/mcp_server.py)
71. `loadProjects` — consumer_hop_1 (graphtyn/web/js/ui.js)
72. `parse_file` — consumer_hop_1 (graphtyn/core/tree_sitter_backend.py)
73. `REPORT.md` — consumer_hop_1 (location unavailable)
74. `render_report` — consumer_hop_1 (graphtyn/core/overview_report.py)
75. `MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md` — consumer_hop_1 (location unavailable)
76. `market-study.md` — consumer_hop_1 (location unavailable)
77. `closeBlastPanel` — consumer_hop_1 (graphtyn/web/js/graph.js)
78. `summarize_shared_memory_rf07.py` — consumer_hop_1 (location unavailable)
79. `test_agent_mcp_context_is_bound_to_token_identity_and_store` — consumer_hop_1 (tests/test_api.py)
80. `build_local_index` — consumer_hop_1 (graphtyn/core/deployment.py)
81. `generate_change_report` — consumer_hop_1 (graphtyn/api/main.py)
82. `selectProject` — consumer_hop_1 (graphtyn/web/js/ui.js)
83. `smoke_frontend.py` — consumer_hop_1 (location unavailable)
84. `focusNode` — consumer_hop_1 (graphtyn/web/js/graph.js)
85. `initWatchPolling` — consumer_hop_1 (graphtyn/web/js/ui.js)
86. `_refresh` — consumer_hop_1 (graphtyn/core/watcher.py)
87. `changeGraphStyle` — consumer_hop_1 (graphtyn/web/js/graph.js)
88. `get_diff` — consumer_hop_1 (graphtyn/api/main.py)
89. `handleGraphBackgroundClick` — consumer_hop_1 (graphtyn/web/js/graph.js)
90. `installReliableNodeDrag` — consumer_hop_1 (graphtyn/web/js/graph.js)
91. `setDim` — consumer_hop_1 (graphtyn/web/js/controls.js)
92. `test_http_mcp_project_context_rejects_ambiguous_name_and_out_of_scope_token` — consumer_hop_1 (tests/test_api.py)
93. `test_install_agent_updates_memory_scope_automatically` — consumer_hop_1 (tests/test_memory_scope.py)
94. `test_overview_verifies_purpose_frameworks_architecture_and_risks` — consumer_hop_1 (tests/test_overview_report.py)
95. `test_pr_impact_reports_risk_and_changed_file` — consumer_hop_1 (tests/test_competitive_features.py)
96. `test_report_is_compact_persistent_format_and_compares_graphify_tokens` — consumer_hop_1 (tests/test_overview_report.py)
97. `test_structural_cache_reuses_unchanged_tree_sitter_result` — consumer_hop_1 (tests/test_ast_parser.py)
98. `test_symbol_level_diff_impacts_callers_not_every_symbol` — consumer_hop_1 (tests/test_competitive_features.py)
99. `changeNodeShape` — consumer_hop_1 (graphtyn/web/js/graph.js)
100. `handleGraphNodeClick` — consumer_hop_1 (graphtyn/web/js/graph.js)

## Potential conflicts

- None reported. Conflictos potenciales obtenidos mediante simulación no destructiva de git merge-tree.

## Evidence policy

EXTRACTED is parser evidence; INFERRED requires source verification; AMBIGUOUS must not be asserted as fact.
