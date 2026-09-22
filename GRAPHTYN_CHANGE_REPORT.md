# GRAPHTYN CHANGE REPORT — graphtyn

- Base: `HEAD`
- Risk: **HIGH** (100/100)
- Changed files: 8
- Changed symbols: 12
- Impacted nodes: 197

## Changed symbols

- `_project_sync_watcher` — `graphtyn/cli.py:185` (signature)
- `_start_project_memory_watch` — `graphtyn/cli.py:197` (signature)
- `main` — `graphtyn/cli.py:240` (signature)
- `resolve_tool_profile` — `graphtyn/core/agent_installer.py:68` (signature)
- `update_agent_manifest` — `graphtyn/core/agent_installer.py:85` (signature)
- `install_agent` — `graphtyn/core/agent_installer.py:99` (signature)
- `apply_setup` — `graphtyn/core/deployment.py:80` (logic)
- `ensure_project_memory_scope` — `graphtyn/core/memory_scope.py:9` (signature)
- `project_integration_status` — `graphtyn/core/project_integrations.py:312` (logic)
- `test_setup_memory_configures_full_profile_and_project_scope` — `tests/test_cli.py:321` (signature)
- `test_setup_preserves_existing_full_profile_when_profile_is_omitted` — `tests/test_cli.py:337` (signature)
- `test_setup_memory_watch_starts_and_reuses_one_watcher` — `tests/test_cli.py:351` (signature)

## Blast radius

- hop 1 · `README.md` · referencia · EXTRACTED · `README.md`
- hop 1 · `index.md` · referencia · EXTRACTED · `docs/index.md`
- hop 1 · `ARCHITECTURE.md` · referencia · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 1 · `cli.py` · llama · EXTRACTED · `graphtyn/cli.py`
- hop 1 · `configure_project_integrations` · llama · EXTRACTED · `graphtyn/core/project_integrations.py`
- hop 1 · `memory_status` · llama · INFERRED · `graphtyn/api/main.py`
- hop 1 · `verify_project_mcp` · llama · EXTRACTED · `graphtyn/core/project_integrations.py`
- hop 1 · `test_agent_install_status_and_remove_only_touch_managed_mcp` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 1 · `test_project_mcp_stdio_handshake_verifies_memory_tools` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 1 · `test_agent_installer_is_idempotent` · llama · INFERRED · `tests/test_enterprise_features.py`
- hop 1 · `test_agent_installer_updates_managed_memory_policy_without_losing_project_rules` · llama · INFERRED · `tests/test_enterprise_features.py`
- hop 1 · `test_antigravity_migrates_only_its_previous_plugin_server` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 1 · `test_setup_is_previewable_and_applies_without_source_edits` · llama · INFERRED · `tests/test_deployment_admin.py`
- hop 1 · `test_status_recognizes_matching_codex_user_config_without_rewriting_it` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 1 · `Blast radius` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Blast radius` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Blast radius` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Blast radius` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Blast radius` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Bootstrap histórico y API v1` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Changed symbols` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Dashboard` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Evidence policy` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `GRAPHTYN CHANGE REPORT — graphtyn` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria compartida del proyecto` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Potential conflicts` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Qué guarda` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 2 · `SKILL.md` · usa · INFERRED · `skills/graphtyn/SKILL.md`
- hop 2 · `AGENTS.md` · usa · INFERRED · `AGENTS.md`
- hop 2 · `CHANGELOG.md` · usa · INFERRED · `docs/CHANGELOG.md`
- hop 2 · `openclaw-native.md` · usa · INFERRED · `docs/openclaw-native.md`
- hop 2 · `agent_memory_policy.md` · usa · INFERRED · `graphtyn/agent_memory_policy.md`
- hop 2 · `MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md` · usa · INFERRED · `docs/MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md`
- hop 2 · `_sync_cycle_space_summary` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `sync_once` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `discover_all_space_targets` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `sync_targets` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `sync_path` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `_install_openclaw_capture_service` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `record_cycle` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `update_watchers` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `_sync_cycle_log_summary` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `bfs_path` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `memory_integrations_verify` · llama · INFERRED · `graphtyn/api/main.py`
- hop 2 · `parse_pairs` · contiene · EXTRACTED · `graphtyn/cli.py`
- hop 2 · `test_project_mcp_configs_are_scoped_idempotent_and_preserve_other_servers` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 2 · `test_verify_uses_existing_codex_user_entry_and_preserves_global_config` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 2 · `test_invalid_client_json_is_preserved_and_reported` · llama · INFERRED · `tests/test_project_integrations.py`
- hop 2 · `1. Extracción estructural` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `2. Ensamblado, consulta y cambio` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `3. Memoria compartida` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `4. Interfaces` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `5. Persistencia y actualización` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Alcance de la versión` · contiene · EXTRACTED · `README.md`
- hop 2 · `Arquitectura de Graphtyn` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Arquitectura en un minuto` · contiene · EXTRACTED · `README.md`
- hop 2 · `Calidad y benchmarks` · contiene · EXTRACTED · `README.md`
- hop 2 · `Capas y responsabilidades` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Captura y recuperación de memoria` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Configurar el proyecto y preguntar si se activa memoria` · contiene · EXTRACTED · `README.md`
- hop 2 · `Crear o actualizar el índice` · contiene · EXTRACTED · `README.md`
- hop 2 · `Dashboard y API` · contiene · EXTRACTED · `README.md`
- hop 2 · `Dependencias opcionales y externas` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Diseño y operación` · contiene · EXTRACTED · `docs/index.md`
- hop 2 · `Documentación` · contiene · EXTRACTED · `README.md`
- hop 2 · `Documentación de Graphtyn` · contiene · EXTRACTED · `docs/index.md`
- hop 2 · `Documentación relacionada` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Empaquetado, despliegue y entrega` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Empezar` · contiene · EXTRACTED · `docs/index.md`
- hop 2 · `Entender el repositorio y obtener contexto acotado` · contiene · EXTRACTED · `README.md`
- hop 2 · `Espacios de código y agentes` · contiene · EXTRACTED · `README.md`
- hop 2 · `Evidencia` · contiene · EXTRACTED · `docs/index.md`
- hop 2 · `Flujo habitual` · contiene · EXTRACTED · `README.md`
- hop 2 · `Flujos principales` · contiene · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 2 · `Generar artefactos persistentes` · contiene · EXTRACTED · `README.md`

## Recommended verification

1. `_project_sync_watcher` — changed (graphtyn/cli.py)
2. `_start_project_memory_watch` — changed (graphtyn/cli.py)
3. `main` — changed (graphtyn/cli.py)
4. `resolve_tool_profile` — changed (graphtyn/core/agent_installer.py)
5. `update_agent_manifest` — changed (graphtyn/core/agent_installer.py)
6. `install_agent` — changed (graphtyn/core/agent_installer.py)
7. `apply_setup` — changed (graphtyn/core/deployment.py)
8. `ensure_project_memory_scope` — changed (graphtyn/core/memory_scope.py)
9. `project_integration_status` — changed (graphtyn/core/project_integrations.py)
10. `test_setup_memory_configures_full_profile_and_project_scope` — changed (tests/test_cli.py)
11. `test_setup_preserves_existing_full_profile_when_profile_is_omitted` — changed (tests/test_cli.py)
12. `test_setup_memory_watch_starts_and_reuses_one_watcher` — changed (tests/test_cli.py)
13. `README.md` — consumer_hop_1 (location unavailable)
14. `index.md` — consumer_hop_1 (location unavailable)
15. `ARCHITECTURE.md` — consumer_hop_1 (location unavailable)
16. `cli.py` — consumer_hop_1 (location unavailable)
17. `configure_project_integrations` — consumer_hop_1 (graphtyn/core/project_integrations.py)
18. `memory_status` — consumer_hop_1 (graphtyn/api/main.py)
19. `verify_project_mcp` — consumer_hop_1 (graphtyn/core/project_integrations.py)
20. `test_agent_install_status_and_remove_only_touch_managed_mcp` — consumer_hop_1 (tests/test_project_integrations.py)
21. `test_project_mcp_stdio_handshake_verifies_memory_tools` — consumer_hop_1 (tests/test_project_integrations.py)
22. `test_agent_installer_is_idempotent` — consumer_hop_1 (tests/test_enterprise_features.py)
23. `test_agent_installer_updates_managed_memory_policy_without_losing_project_rules` — consumer_hop_1 (tests/test_enterprise_features.py)
24. `test_antigravity_migrates_only_its_previous_plugin_server` — consumer_hop_1 (tests/test_project_integrations.py)
25. `test_setup_is_previewable_and_applies_without_source_edits` — consumer_hop_1 (tests/test_deployment_admin.py)
26. `test_status_recognizes_matching_codex_user_config_without_rewriting_it` — consumer_hop_1 (tests/test_project_integrations.py)
27. `Blast radius` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
28. `Bootstrap histórico y API v1` — consumer_hop_1 (docs/shared-memory.md)
29. `Changed symbols` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
30. `Dashboard` — consumer_hop_1 (docs/shared-memory.md)
31. `Evidence policy` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
32. `GRAPHTYN CHANGE REPORT — graphtyn` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
33. `Incorporar un legado al cerebro activo` — consumer_hop_1 (docs/shared-memory.md)
34. `Memoria compartida del proyecto` — consumer_hop_1 (docs/shared-memory.md)
35. `Memoria temática y captura incremental` — consumer_hop_1 (docs/shared-memory.md)
36. `Operación` — consumer_hop_1 (docs/shared-memory.md)
37. `Operación portable` — consumer_hop_1 (docs/shared-memory.md)
38. `Potential conflicts` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
39. `Qué guarda` — consumer_hop_1 (docs/shared-memory.md)
40. `Recommended verification` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
41. `Recuperación` — consumer_hop_1 (docs/shared-memory.md)
42. `SKILL.md` — consumer_hop_2 (location unavailable)
43. `AGENTS.md` — consumer_hop_2 (location unavailable)
44. `CHANGELOG.md` — consumer_hop_2 (location unavailable)
45. `openclaw-native.md` — consumer_hop_2 (location unavailable)
46. `agent_memory_policy.md` — consumer_hop_2 (location unavailable)
47. `MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md` — consumer_hop_2 (location unavailable)
48. `_sync_cycle_space_summary` — consumer_hop_2 (graphtyn/cli.py)
49. `sync_once` — consumer_hop_2 (graphtyn/cli.py)
50. `discover_all_space_targets` — consumer_hop_2 (graphtyn/cli.py)
51. `sync_targets` — consumer_hop_2 (graphtyn/cli.py)
52. `sync_path` — consumer_hop_2 (graphtyn/cli.py)
53. `_install_openclaw_capture_service` — consumer_hop_2 (graphtyn/cli.py)
54. `record_cycle` — consumer_hop_2 (graphtyn/cli.py)
55. `update_watchers` — consumer_hop_2 (graphtyn/cli.py)
56. `_sync_cycle_log_summary` — consumer_hop_2 (graphtyn/cli.py)
57. `bfs_path` — consumer_hop_2 (graphtyn/cli.py)
58. `memory_integrations_verify` — consumer_hop_2 (graphtyn/api/main.py)
59. `parse_pairs` — consumer_hop_2 (graphtyn/cli.py)
60. `test_project_mcp_configs_are_scoped_idempotent_and_preserve_other_servers` — consumer_hop_2 (tests/test_project_integrations.py)
61. `test_verify_uses_existing_codex_user_entry_and_preserves_global_config` — consumer_hop_2 (tests/test_project_integrations.py)
62. `test_invalid_client_json_is_preserved_and_reported` — consumer_hop_2 (tests/test_project_integrations.py)
63. `1. Extracción estructural` — consumer_hop_2 (docs/ARCHITECTURE.md)
64. `2. Ensamblado, consulta y cambio` — consumer_hop_2 (docs/ARCHITECTURE.md)
65. `3. Memoria compartida` — consumer_hop_2 (docs/ARCHITECTURE.md)
66. `4. Interfaces` — consumer_hop_2 (docs/ARCHITECTURE.md)
67. `5. Persistencia y actualización` — consumer_hop_2 (docs/ARCHITECTURE.md)
68. `Alcance de la versión` — consumer_hop_2 (README.md)
69. `Arquitectura de Graphtyn` — consumer_hop_2 (docs/ARCHITECTURE.md)
70. `Arquitectura en un minuto` — consumer_hop_2 (README.md)
71. `Calidad y benchmarks` — consumer_hop_2 (README.md)
72. `Capas y responsabilidades` — consumer_hop_2 (docs/ARCHITECTURE.md)
73. `Captura y recuperación de memoria` — consumer_hop_2 (docs/ARCHITECTURE.md)
74. `Configurar el proyecto y preguntar si se activa memoria` — consumer_hop_2 (README.md)
75. `Crear o actualizar el índice` — consumer_hop_2 (README.md)
76. `Dashboard y API` — consumer_hop_2 (README.md)
77. `Dependencias opcionales y externas` — consumer_hop_2 (docs/ARCHITECTURE.md)
78. `Diseño y operación` — consumer_hop_2 (docs/index.md)
79. `Documentación` — consumer_hop_2 (README.md)
80. `Documentación de Graphtyn` — consumer_hop_2 (docs/index.md)
81. `Documentación relacionada` — consumer_hop_2 (docs/ARCHITECTURE.md)
82. `Empaquetado, despliegue y entrega` — consumer_hop_2 (docs/ARCHITECTURE.md)
83. `Empezar` — consumer_hop_2 (docs/index.md)
84. `Entender el repositorio y obtener contexto acotado` — consumer_hop_2 (README.md)
85. `Espacios de código y agentes` — consumer_hop_2 (README.md)
86. `Evidencia` — consumer_hop_2 (docs/index.md)
87. `Flujo habitual` — consumer_hop_2 (README.md)
88. `Flujos principales` — consumer_hop_2 (docs/ARCHITECTURE.md)
89. `Generar artefactos persistentes` — consumer_hop_2 (README.md)
90. `Importar o sincronizar historiales autorizados` — consumer_hop_2 (README.md)
91. `Indexación y consulta` — consumer_hop_2 (docs/ARCHITECTURE.md)
92. `Instalación rápida` — consumer_hop_2 (README.md)
93. `Instalar MCP con memoria del proyecto para Codex` — consumer_hop_2 (README.md)
94. `Instalar MCP del proyecto sólo en los clientes elegidos` — consumer_hop_2 (README.md)
95. `Integración con agentes` — consumer_hop_2 (README.md)
96. `La captura continua se activa por separado` — consumer_hop_2 (README.md)
97. `Licencia` — consumer_hop_2 (README.md)
98. `Mapa del sistema` — consumer_hop_2 (docs/ARCHITECTURE.md)
99. `Memoria compartida` — consumer_hop_2 (README.md)
100. `Memoria temática` — consumer_hop_2 (README.md)

## Potential conflicts

- None reported. Conflictos potenciales obtenidos mediante simulación no destructiva de git merge-tree.

## Evidence policy

EXTRACTED is parser evidence; INFERRED requires source verification; AMBIGUOUS must not be asserted as fact.
