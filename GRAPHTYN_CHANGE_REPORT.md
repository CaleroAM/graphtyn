# GRAPHTYN CHANGE REPORT — graphtyn

- Base: `HEAD`
- Risk: **HIGH** (100/100)
- Changed files: 21
- Changed symbols: 54
- Impacted nodes: 579

## Changed symbols

- `_http_mcp_tools` — `graphtyn/api/main.py:2678` (logic)
- `mcp_http` — `graphtyn/api/main.py:2688` (logic)
- `_antigravity_workspace_map` — `graphtyn/core/history_import.py:99` (signature)
- `decode_workspace` — `graphtyn/core/history_import.py:128` (signature)
- `associate` — `graphtyn/core/history_import.py:158` (signature)
- `parse_history_database` — `graphtyn/core/history_import.py:395` (signature)
- `discover_histories` — `graphtyn/core/history_import.py:835` (signature)
- `sync_memory_workspace` — `graphtyn/core/history_import.py:986` (signature)
- `_sync_openclaw_project_memories` — `graphtyn/core/history_import.py:1064` (signature)
- `import_histories` — `graphtyn/core/history_import.py:1207` (signature)
- `_init_topics` — `graphtyn/core/memory_topics.py:61` (signature)
- `_file_references` — `graphtyn/core/memory_topics.py:342` (signature)
- `_entity_ids` — `graphtyn/core/memory_topics.py:385` (signature)
- `_link_topic_entities` — `graphtyn/core/memory_topics.py:437` (signature)
- `topic_graph` — `graphtyn/core/memory_topics.py:494` (signature)
- `relation_candidates` — `graphtyn/core/memory_topics.py:745` (signature)
- `_propose_relation_candidates` — `graphtyn/core/memory_topics.py:847` (signature)
- `_topic_relation_term_stats` — `graphtyn/core/memory_topics.py:904` (signature)
- `_specific_shared_terms` — `graphtyn/core/memory_topics.py:931` (signature)
- `process_topics` — `graphtyn/core/memory_topics.py:987` (signature)
- `enrich_topics` — `graphtyn/core/memory_topics.py:1168` (signature)
- `topic` — `graphtyn/core/memory_topics.py:1321` (signature)
- `_message_search_text` — `graphtyn/core/shared_memory.py:71` (signature)
- `_init_db_locked` — `graphtyn/core/shared_memory.py:320` (signature)
- `search_messages` — `graphtyn/core/shared_memory.py:1276` (signature)
- `context` — `graphtyn/core/shared_memory.py:1371` (signature)
- `status` — `graphtyn/core/shared_memory.py:1821` (signature)
- `record_project_routing` — `graphtyn/core/shared_memory.py:2099` (signature)
- `project_routing_status` — `graphtyn/core/shared_memory.py:2136` (signature)
- `run_mcp_server` — `graphtyn/mcp_server.py:521` (signature)
- `handle_request` — `graphtyn/mcp_server.py:532` (signature)
- `updateLinkStyles` — `graphtyn/web/js/controls.js:163` (logic)
- `neuralLinkPainter` — `graphtyn/web/js/painters.js:210` (logic)
- `holoLinkPainter` — `graphtyn/web/js/painters.js:366` (logic)
- `test_http_mcp_reads_only_explicit_registered_project_memory` — `tests/test_api.py:316` (signature)
- `call` — `tests/test_api.py:338` (signature)
- `test_http_mcp_project_context_rejects_ambiguous_name_and_out_of_scope_token` — `tests/test_api.py:363` (signature)
- `test_antigravity_workspace_metadata_routes_only_matching_project_sessions` — `tests/test_history_import.py:325` (signature)
- `test_antigravity_last_conversation_cache_scopes_new_cli_session` — `tests/test_history_import.py:372` (signature)
- `test_mcp_initialize_and_tools_list` — `tests/test_mcp_server.py:35` (signature)
- `test_mcp_stdio_ignores_notifications_without_shifting_responses` — `tests/test_mcp_server.py:59` (signature)
- `test_mcp_intent_profile_exposes_context_and_topic_expansion` — `tests/test_mcp_server.py:70` (signature)
- `test_mcp_memory_project_context_resolves_registered_project` — `tests/test_mcp_server.py:91` (signature)
- `test_context_budget_keeps_theme_when_topic_has_many_file_entities` — `tests/test_memory_topics.py:95` (signature)
- `test_topic_graph_marks_possible_relations_ambiguous` — `tests/test_memory_topics.py:149` (signature)
- `test_file_references_from_tool_output_connect_agents_with_attribution` — `tests/test_memory_topics.py:287` (signature)
- `test_file_reference_extraction_rejects_external_and_parent_paths` — `tests/test_memory_topics.py:321` (signature)
- `test_related_topics_remain_separate_across_all_agent_names` — `tests/test_memory_topics.py:333` (signature)
- `test_common_project_words_do_not_create_ambiguous_edges` — `tests/test_memory_topics.py:352` (signature)
- `test_stream_restart_partial_tail_and_exclusions` — `tests/test_memory_topics.py:364` (signature)
- `test_agent_brain_does_not_create_cross_owner_file_relations` — `tests/test_memory_topics.py:437` (signature)
- `test_continuity_context_finds_older_query_matched_message_across_agents` — `tests/test_shared_memory.py:80` (signature)
- `test_source_message_search_keeps_one_result_per_session` — `tests/test_shared_memory.py:131` (signature)
- `test_agent_brain_does_not_continue_another_agents_topic` — `tests/test_shared_memory.py:294` (signature)

## Blast radius

- hop 1 · `main.py` · llama · INFERRED · `graphtyn/api/main.py`
- hop 1 · `main` · llama · INFERRED · `graphtyn/cli.py`
- hop 1 · `SharedMemoryStore` · declara · EXTRACTED · `graphtyn/core/shared_memory.py`
- hop 1 · `contexto-comparativo.md` · usa · INFERRED · `docs/contexto-comparativo.md`
- hop 1 · `README.md` · referencia · EXTRACTED · `README.md`
- hop 1 · `BENCHMARKS.md` · usa · AMBIGUOUS · `docs/BENCHMARKS.md`
- hop 1 · `ARCHITECTURE.md` · referencia · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 1 · `index.md` · referencia · EXTRACTED · `docs/index.md`
- hop 1 · `TopicMemoryMixin` · declara · EXTRACTED · `graphtyn/core/memory_topics.py`
- hop 1 · `GRAPHTYN_REPORT.md` · usa · INFERRED · `docs/GRAPHTYN_REPORT.md`
- hop 1 · `agent_memory_policy.md` · usa · AMBIGUOUS · `graphtyn/agent_memory_policy.md`
- hop 1 · `test_memory_policy_is_per_installation_persists_and_removes_only_its_source` · llama · INFERRED · `tests/test_openclaw_integration.py`
- hop 1 · `competitive-validation-0.8.0.md` · usa · INFERRED · `docs/competitive-validation-0.8.0.md`
- hop 1 · `REPORT.md` · usa · AMBIGUOUS · `benchmarks/real_repos_current_2026-08-22/REPORT.md`
- hop 1 · `REPORT.md` · usa · AMBIGUOUS · `benchmarks/quality_v2_real_2026-08-22/REPORT.md`
- hop 1 · `test_agent_mcp_context_is_bound_to_token_identity_and_store` · llama · AMBIGUOUS · `tests/test_api.py`
- hop 1 · `import_history_archive` · llama · EXTRACTED · `graphtyn/core/history_import.py`
- hop 1 · `test_opencode_json_sqlite_histories_keep_only_conversation_text_and_exact_project` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `import_start` · llama · INFERRED · `graphtyn/api/main.py`
- hop 1 · `sync_path` · llama · INFERRED · `graphtyn/cli.py`
- hop 1 · `test_historical_import_is_idempotent_and_searchable` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_history_source_is_scoped_to_one_memory_space` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `_hydrate_history_previews` · llama · INFERRED · `graphtyn/api/main.py`
- hop 1 · `test_capture_baseline_excludes_old_sessions_and_keeps_new_sessions` · llama · INFERRED · `tests/test_openclaw_integration.py`
- hop 1 · `test_history_source_owner_filters_a_shared_agent_directory` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_openclaw_history_discovery_preserves_attribution` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_project_sync_discovers_local_coding_histories_but_keeps_ambiguous_sessions_pending` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_source` · llama · EXTRACTED · `graphtyn/core/history_import.py`
- hop 1 · `test_codex_environment_context_is_not_imported_as_a_user_message` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_codex_nested_payload_and_sqlite_histories` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_openclaw_trajectory_pointer_only_imports_canonical_transcript` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `_memory_watch_loop` · llama · INFERRED · `graphtyn/api/main.py`
- hop 1 · `test_discovery_ignores_skill_templates_that_look_like_conversations` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_historical_import_does_not_invent_source_time_when_missing` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_historical_import_enforces_configured_agent_owner` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_import_does_not_mix_unknown_project_workspace` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_invalid_ssh_history_source_is_rejected_without_execution` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_openclaw_pointer_cannot_escape_selected_source` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `test_openclaw_sqlite_transcript_events_are_imported_with_roles` · llama · INFERRED · `tests/test_history_import.py`
- hop 1 · `Act and report` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Archivos `LEGADO`: histórico y mixto` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Archivos `LEGADO`: histórico y mixto` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Carga GRAPHTYN_MCP_TOKEN desde el gestor de secretos del host.` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Cerebros, subagentes y memoria familiar` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Conexión nativa con OpenClaw` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Conversaciones de OpenClaw dentro de la memoria de un proyecto` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Conversaciones de OpenClaw dentro de la memoria de un proyecto` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Conversaciones de OpenClaw dentro de la memoria de un proyecto` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Conversational references` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Dashboard` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Dashboard` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Default workflow` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Default workflow` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Descubrir y conectar` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Documento` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Estabilidad de memoria compartida` · contiene · EXTRACTED · `docs/shared_memory_stability.md`
- hop 1 · `Graphtyn` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Graphtyn agent policy` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Guardrails` · contiene · EXTRACTED · `docs/shared_memory_stability.md`
- hop 1 · `Host, VM, VPS y Docker` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Interpret evidence` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Matriz viva de clientes` · contiene · EXTRACTED · `docs/shared_memory_stability.md`
- hop 1 · `Memoria compartida del proyecto` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Operación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Personal agent brains` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Personal agent brains` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Query` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Query` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Qué guarda` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Qué se modifica en OpenClaw` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Reejecución · 13 de septiembre de 2026` · contiene · EXTRACTED · `docs/shared_memory_stability.md`
- hop 1 · `Resultado observado · 22 de agosto de 2026` · contiene · EXTRACTED · `docs/shared_memory_stability.md`
- hop 1 · `SSH explícito para VM o VPS` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `SSH explícito para VM o VPS` · contiene · EXTRACTED · `docs/openclaw-native.md`
- hop 1 · `Shared project memory` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Shared project memory` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Shared project memory` · contiene · EXTRACTED · `AGENTS.md`

## Recommended verification

1. `_http_mcp_tools` — changed (graphtyn/api/main.py)
2. `mcp_http` — changed (graphtyn/api/main.py)
3. `_antigravity_workspace_map` — changed (graphtyn/core/history_import.py)
4. `decode_workspace` — changed (graphtyn/core/history_import.py)
5. `associate` — changed (graphtyn/core/history_import.py)
6. `parse_history_database` — changed (graphtyn/core/history_import.py)
7. `discover_histories` — changed (graphtyn/core/history_import.py)
8. `sync_memory_workspace` — changed (graphtyn/core/history_import.py)
9. `_sync_openclaw_project_memories` — changed (graphtyn/core/history_import.py)
10. `import_histories` — changed (graphtyn/core/history_import.py)
11. `_init_topics` — changed (graphtyn/core/memory_topics.py)
12. `_file_references` — changed (graphtyn/core/memory_topics.py)
13. `_entity_ids` — changed (graphtyn/core/memory_topics.py)
14. `_link_topic_entities` — changed (graphtyn/core/memory_topics.py)
15. `topic_graph` — changed (graphtyn/core/memory_topics.py)
16. `relation_candidates` — changed (graphtyn/core/memory_topics.py)
17. `_propose_relation_candidates` — changed (graphtyn/core/memory_topics.py)
18. `_topic_relation_term_stats` — changed (graphtyn/core/memory_topics.py)
19. `_specific_shared_terms` — changed (graphtyn/core/memory_topics.py)
20. `process_topics` — changed (graphtyn/core/memory_topics.py)
21. `enrich_topics` — changed (graphtyn/core/memory_topics.py)
22. `topic` — changed (graphtyn/core/memory_topics.py)
23. `_message_search_text` — changed (graphtyn/core/shared_memory.py)
24. `_init_db_locked` — changed (graphtyn/core/shared_memory.py)
25. `search_messages` — changed (graphtyn/core/shared_memory.py)
26. `context` — changed (graphtyn/core/shared_memory.py)
27. `status` — changed (graphtyn/core/shared_memory.py)
28. `record_project_routing` — changed (graphtyn/core/shared_memory.py)
29. `project_routing_status` — changed (graphtyn/core/shared_memory.py)
30. `run_mcp_server` — changed (graphtyn/mcp_server.py)
31. `handle_request` — changed (graphtyn/mcp_server.py)
32. `updateLinkStyles` — changed (graphtyn/web/js/controls.js)
33. `neuralLinkPainter` — changed (graphtyn/web/js/painters.js)
34. `holoLinkPainter` — changed (graphtyn/web/js/painters.js)
35. `test_http_mcp_reads_only_explicit_registered_project_memory` — changed (tests/test_api.py)
36. `call` — changed (tests/test_api.py)
37. `test_http_mcp_project_context_rejects_ambiguous_name_and_out_of_scope_token` — changed (tests/test_api.py)
38. `test_antigravity_workspace_metadata_routes_only_matching_project_sessions` — changed (tests/test_history_import.py)
39. `test_antigravity_last_conversation_cache_scopes_new_cli_session` — changed (tests/test_history_import.py)
40. `test_mcp_initialize_and_tools_list` — changed (tests/test_mcp_server.py)
41. `test_mcp_stdio_ignores_notifications_without_shifting_responses` — changed (tests/test_mcp_server.py)
42. `test_mcp_intent_profile_exposes_context_and_topic_expansion` — changed (tests/test_mcp_server.py)
43. `test_mcp_memory_project_context_resolves_registered_project` — changed (tests/test_mcp_server.py)
44. `test_context_budget_keeps_theme_when_topic_has_many_file_entities` — changed (tests/test_memory_topics.py)
45. `test_topic_graph_marks_possible_relations_ambiguous` — changed (tests/test_memory_topics.py)
46. `test_file_references_from_tool_output_connect_agents_with_attribution` — changed (tests/test_memory_topics.py)
47. `test_file_reference_extraction_rejects_external_and_parent_paths` — changed (tests/test_memory_topics.py)
48. `test_related_topics_remain_separate_across_all_agent_names` — changed (tests/test_memory_topics.py)
49. `test_common_project_words_do_not_create_ambiguous_edges` — changed (tests/test_memory_topics.py)
50. `test_stream_restart_partial_tail_and_exclusions` — changed (tests/test_memory_topics.py)
51. `test_agent_brain_does_not_create_cross_owner_file_relations` — changed (tests/test_memory_topics.py)
52. `test_continuity_context_finds_older_query_matched_message_across_agents` — changed (tests/test_shared_memory.py)
53. `test_source_message_search_keeps_one_result_per_session` — changed (tests/test_shared_memory.py)
54. `test_agent_brain_does_not_continue_another_agents_topic` — changed (tests/test_shared_memory.py)
55. `main.py` — consumer_hop_1 (location unavailable)
56. `main` — consumer_hop_1 (graphtyn/cli.py)
57. `SharedMemoryStore` — consumer_hop_1 (graphtyn/core/shared_memory.py)
58. `contexto-comparativo.md` — consumer_hop_1 (location unavailable)
59. `README.md` — consumer_hop_1 (location unavailable)
60. `BENCHMARKS.md` — consumer_hop_1 (location unavailable)
61. `ARCHITECTURE.md` — consumer_hop_1 (location unavailable)
62. `index.md` — consumer_hop_1 (location unavailable)
63. `TopicMemoryMixin` — consumer_hop_1 (graphtyn/core/memory_topics.py)
64. `GRAPHTYN_REPORT.md` — consumer_hop_1 (location unavailable)
65. `agent_memory_policy.md` — consumer_hop_1 (location unavailable)
66. `test_memory_policy_is_per_installation_persists_and_removes_only_its_source` — consumer_hop_1 (tests/test_openclaw_integration.py)
67. `competitive-validation-0.8.0.md` — consumer_hop_1 (location unavailable)
68. `REPORT.md` — consumer_hop_1 (location unavailable)
69. `test_agent_mcp_context_is_bound_to_token_identity_and_store` — consumer_hop_1 (tests/test_api.py)
70. `import_history_archive` — consumer_hop_1 (graphtyn/core/history_import.py)
71. `test_opencode_json_sqlite_histories_keep_only_conversation_text_and_exact_project` — consumer_hop_1 (tests/test_history_import.py)
72. `import_start` — consumer_hop_1 (graphtyn/api/main.py)
73. `sync_path` — consumer_hop_1 (graphtyn/cli.py)
74. `test_historical_import_is_idempotent_and_searchable` — consumer_hop_1 (tests/test_history_import.py)
75. `test_history_source_is_scoped_to_one_memory_space` — consumer_hop_1 (tests/test_history_import.py)
76. `_hydrate_history_previews` — consumer_hop_1 (graphtyn/api/main.py)
77. `test_capture_baseline_excludes_old_sessions_and_keeps_new_sessions` — consumer_hop_1 (tests/test_openclaw_integration.py)
78. `test_history_source_owner_filters_a_shared_agent_directory` — consumer_hop_1 (tests/test_history_import.py)
79. `test_openclaw_history_discovery_preserves_attribution` — consumer_hop_1 (tests/test_history_import.py)
80. `test_project_sync_discovers_local_coding_histories_but_keeps_ambiguous_sessions_pending` — consumer_hop_1 (tests/test_history_import.py)
81. `test_source` — consumer_hop_1 (graphtyn/core/history_import.py)
82. `test_codex_environment_context_is_not_imported_as_a_user_message` — consumer_hop_1 (tests/test_history_import.py)
83. `test_codex_nested_payload_and_sqlite_histories` — consumer_hop_1 (tests/test_history_import.py)
84. `test_openclaw_trajectory_pointer_only_imports_canonical_transcript` — consumer_hop_1 (tests/test_history_import.py)
85. `_memory_watch_loop` — consumer_hop_1 (graphtyn/api/main.py)
86. `test_discovery_ignores_skill_templates_that_look_like_conversations` — consumer_hop_1 (tests/test_history_import.py)
87. `test_historical_import_does_not_invent_source_time_when_missing` — consumer_hop_1 (tests/test_history_import.py)
88. `test_historical_import_enforces_configured_agent_owner` — consumer_hop_1 (tests/test_history_import.py)
89. `test_import_does_not_mix_unknown_project_workspace` — consumer_hop_1 (tests/test_history_import.py)
90. `test_invalid_ssh_history_source_is_rejected_without_execution` — consumer_hop_1 (tests/test_history_import.py)
91. `test_openclaw_pointer_cannot_escape_selected_source` — consumer_hop_1 (tests/test_history_import.py)
92. `test_openclaw_sqlite_transcript_events_are_imported_with_roles` — consumer_hop_1 (tests/test_history_import.py)
93. `Act and report` — consumer_hop_1 (skills/graphtyn/SKILL.md)
94. `Archivos `LEGADO`: histórico y mixto` — consumer_hop_1 (docs/openclaw-native.md)
95. `Bootstrap histórico y API v1` — consumer_hop_1 (docs/shared-memory.md)
96. `Carga GRAPHTYN_MCP_TOKEN desde el gestor de secretos del host.` — consumer_hop_1 (docs/openclaw-native.md)
97. `Cerebros, subagentes y memoria familiar` — consumer_hop_1 (docs/openclaw-native.md)
98. `Conexión nativa con OpenClaw` — consumer_hop_1 (docs/openclaw-native.md)
99. `Conversaciones de OpenClaw dentro de la memoria de un proyecto` — consumer_hop_1 (docs/openclaw-native.md)
100. `Conversational references` — consumer_hop_1 (skills/graphtyn/SKILL.md)

## Potential conflicts

- None reported. Conflictos potenciales obtenidos mediante simulación no destructiva de git merge-tree.

## Evidence policy

EXTRACTED is parser evidence; INFERRED requires source verification; AMBIGUOUS must not be asserted as fact.
