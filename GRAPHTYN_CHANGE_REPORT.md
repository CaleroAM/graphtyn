# GRAPHTYN CHANGE REPORT — graphtyn

- Base: `HEAD`
- Risk: **HIGH** (100/100)
- Changed files: 23
- Changed symbols: 16
- Impacted nodes: 283

## Changed symbols

- `register_project` — `graphtyn/api/main.py:913` (signature)
- `memory_status` — `graphtyn/api/main.py:1841` (signature)
- `memory_integrations_verify` — `graphtyn/api/main.py:1861` (signature)
- `main` — `graphtyn/cli.py:185` (logic)
- `install_agent` — `graphtyn/core/agent_installer.py:67` (logic)
- `initialize_project` — `graphtyn/core/deployment.py:18` (logic)
- `apply_setup` — `graphtyn/core/deployment.py:79` (logic)
- `register` — `graphtyn/core/history_import.py:1216` (signature)
- `stateLabel` — `graphtyn/web/js/memory.js:193` (logic)
- `verifyProjectMcp` — `graphtyn/web/js/memory.js:224` (logic)
- `test_dashboard_project_registration_creates_stable_memory_identity` — `tests/test_api.py:434` (signature)
- `test_agent_install_antigravity_uses_project_gemini_policy` — `tests/test_cli.py:264` (signature)
- `test_setup_memory_opt_in_does_not_import_historical_sessions` — `tests/test_cli.py:305` (signature)
- `test_setup_history_import_requires_explicit_consent` — `tests/test_cli.py:320` (signature)
- `test_agent_install_upgrades_existing_graphtyn_policy` — `tests/test_cli.py:420` (signature)
- `test_agent_policies_enforce_context_stop_contract` — `tests/test_cli.py:434` (signature)

## Blast radius

- hop 1 · `contexto-comparativo.md` · usa · AMBIGUOUS · `docs/contexto-comparativo.md`
- hop 1 · `CHANGELOG.md` · usa · INFERRED · `docs/CHANGELOG.md`
- hop 1 · `ARCHITECTURE.md` · referencia · EXTRACTED · `docs/ARCHITECTURE.md`
- hop 1 · `openclaw-native.md` · usa · INFERRED · `docs/openclaw-native.md`
- hop 1 · `loadMemoryOverview` · llama · INFERRED · `graphtyn/web/js/memory.js`
- hop 1 · `cli.py` · llama · EXTRACTED · `graphtyn/cli.py`
- hop 1 · `MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md` · usa · INFERRED · `docs/MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md`
- hop 1 · `ProjectIdentityRegistry` · declara · EXTRACTED · `graphtyn/core/history_import.py`
- hop 1 · `boot` · contiene · EXTRACTED · `graphtyn/web/dashboard.js`
- hop 1 · `openFromChanges` · contiene · EXTRACTED · `graphtyn/web/dashboard.js`
- hop 1 · `closeDropdownMenus` · contiene · EXTRACTED · `graphtyn/web/dashboard.js`
- hop 1 · `project_identity_register` · llama · EXTRACTED · `graphtyn/api/main.py`
- hop 1 · `test_agent_installer_is_idempotent` · llama · INFERRED · `tests/test_enterprise_features.py`
- hop 1 · `test_agent_installer_updates_managed_memory_policy_without_losing_project_rules` · llama · INFERRED · `tests/test_enterprise_features.py`
- hop 1 · `test_setup_is_previewable_and_applies_without_source_edits` · llama · INFERRED · `tests/test_deployment_admin.py`
- hop 1 · `showWelcomeOnce` · contiene · EXTRACTED · `graphtyn/web/dashboard.js`
- hop 1 · `test_federated_v1_context_lists_preintegration_projects` · llama · EXTRACTED · `tests/test_history_import.py`
- hop 1 · `closeWelcome` · contiene · EXTRACTED · `graphtyn/web/dashboard.js`
- hop 1 · `Act and report` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Alcance de la versión` · contiene · EXTRACTED · `README.md`
- hop 1 · `Arquitectura en un minuto` · contiene · EXTRACTED · `README.md`
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
- hop 1 · `Calidad y benchmarks` · contiene · EXTRACTED · `README.md`
- hop 1 · `Changed symbols` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Choose memory or code context` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Configurar el proyecto y preguntar si se activa memoria` · contiene · EXTRACTED · `README.md`
- hop 1 · `Conversational references` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Crear o actualizar el índice` · contiene · EXTRACTED · `README.md`
- hop 1 · `Dashboard` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Dashboard y API` · contiene · EXTRACTED · `README.md`
- hop 1 · `Default workflow` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Default workflow` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Diseño y operación` · contiene · EXTRACTED · `docs/index.md`
- hop 1 · `Documentación` · contiene · EXTRACTED · `README.md`
- hop 1 · `Documentación de Graphtyn` · contiene · EXTRACTED · `docs/index.md`
- hop 1 · `Documento` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Empezar` · contiene · EXTRACTED · `docs/index.md`
- hop 1 · `Entender el repositorio y obtener contexto acotado` · contiene · EXTRACTED · `README.md`
- hop 1 · `Espacios de código y agentes` · contiene · EXTRACTED · `README.md`
- hop 1 · `Evidence policy` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Evidencia` · contiene · EXTRACTED · `docs/index.md`
- hop 1 · `Flujo habitual` · contiene · EXTRACTED · `README.md`
- hop 1 · `GRAPHTYN CHANGE REPORT — graphtyn` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Generar artefactos persistentes` · contiene · EXTRACTED · `README.md`
- hop 1 · `Graphtyn` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Graphtyn agent policy` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Importar o sincronizar historiales autorizados` · contiene · EXTRACTED · `README.md`
- hop 1 · `Importar o sincronizar historiales autorizados` · contiene · EXTRACTED · `README.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Incorporar un legado al cerebro activo` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Instalación rápida` · contiene · EXTRACTED · `README.md`
- hop 1 · `Instalar MCP con memoria del proyecto para Codex` · contiene · EXTRACTED · `README.md`
- hop 1 · `Instalar MCP del proyecto sólo en los clientes elegidos` · contiene · EXTRACTED · `README.md`
- hop 1 · `Integración con agentes` · contiene · EXTRACTED · `README.md`
- hop 1 · `Interpret evidence` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `La captura continua se activa por separado` · contiene · EXTRACTED · `README.md`
- hop 1 · `Licencia` · contiene · EXTRACTED · `README.md`
- hop 1 · `Memoria compartida` · contiene · EXTRACTED · `README.md`
- hop 1 · `Memoria compartida del proyecto` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática` · contiene · EXTRACTED · `README.md`
- hop 1 · `Memoria temática` · contiene · EXTRACTED · `README.md`
- hop 1 · `Memoria temática` · contiene · EXTRACTED · `README.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Memoria temática y captura incremental` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `OpenClaw project memory` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Operación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Operación portable` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Personal agent brains` · contiene · EXTRACTED · `AGENTS.md`
- hop 1 · `Personal agent brains` · contiene · EXTRACTED · `skills/graphtyn/SKILL.md`
- hop 1 · `Planificar y verificar cambios` · contiene · EXTRACTED · `README.md`
- hop 1 · `Potential conflicts` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Pregunta en una terminal (predeterminado)` · contiene · EXTRACTED · `README.md`
- hop 1 · `Qué guarda` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Qué ofrece` · contiene · EXTRACTED · `README.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recommended verification` · contiene · EXTRACTED · `GRAPHTYN_CHANGE_REPORT.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`
- hop 1 · `Recuperación` · contiene · EXTRACTED · `docs/shared-memory.md`

## Recommended verification

1. `register_project` — changed (graphtyn/api/main.py)
2. `memory_status` — changed (graphtyn/api/main.py)
3. `memory_integrations_verify` — changed (graphtyn/api/main.py)
4. `main` — changed (graphtyn/cli.py)
5. `install_agent` — changed (graphtyn/core/agent_installer.py)
6. `initialize_project` — changed (graphtyn/core/deployment.py)
7. `apply_setup` — changed (graphtyn/core/deployment.py)
8. `register` — changed (graphtyn/core/history_import.py)
9. `stateLabel` — changed (graphtyn/web/js/memory.js)
10. `verifyProjectMcp` — changed (graphtyn/web/js/memory.js)
11. `test_dashboard_project_registration_creates_stable_memory_identity` — changed (tests/test_api.py)
12. `test_agent_install_antigravity_uses_project_gemini_policy` — changed (tests/test_cli.py)
13. `test_setup_memory_opt_in_does_not_import_historical_sessions` — changed (tests/test_cli.py)
14. `test_setup_history_import_requires_explicit_consent` — changed (tests/test_cli.py)
15. `test_agent_install_upgrades_existing_graphtyn_policy` — changed (tests/test_cli.py)
16. `test_agent_policies_enforce_context_stop_contract` — changed (tests/test_cli.py)
17. `contexto-comparativo.md` — consumer_hop_1 (location unavailable)
18. `CHANGELOG.md` — consumer_hop_1 (location unavailable)
19. `ARCHITECTURE.md` — consumer_hop_1 (location unavailable)
20. `openclaw-native.md` — consumer_hop_1 (location unavailable)
21. `loadMemoryOverview` — consumer_hop_1 (graphtyn/web/js/memory.js)
22. `cli.py` — consumer_hop_1 (location unavailable)
23. `MEMORY_RETRIEVAL_VALIDATION_2026-09-13.md` — consumer_hop_1 (location unavailable)
24. `ProjectIdentityRegistry` — consumer_hop_1 (graphtyn/core/history_import.py)
25. `boot` — consumer_hop_1 (graphtyn/web/dashboard.js)
26. `openFromChanges` — consumer_hop_1 (graphtyn/web/dashboard.js)
27. `closeDropdownMenus` — consumer_hop_1 (graphtyn/web/dashboard.js)
28. `project_identity_register` — consumer_hop_1 (graphtyn/api/main.py)
29. `test_agent_installer_is_idempotent` — consumer_hop_1 (tests/test_enterprise_features.py)
30. `test_agent_installer_updates_managed_memory_policy_without_losing_project_rules` — consumer_hop_1 (tests/test_enterprise_features.py)
31. `test_setup_is_previewable_and_applies_without_source_edits` — consumer_hop_1 (tests/test_deployment_admin.py)
32. `showWelcomeOnce` — consumer_hop_1 (graphtyn/web/dashboard.js)
33. `test_federated_v1_context_lists_preintegration_projects` — consumer_hop_1 (tests/test_history_import.py)
34. `closeWelcome` — consumer_hop_1 (graphtyn/web/dashboard.js)
35. `Act and report` — consumer_hop_1 (skills/graphtyn/SKILL.md)
36. `Alcance de la versión` — consumer_hop_1 (README.md)
37. `Arquitectura en un minuto` — consumer_hop_1 (README.md)
38. `Blast radius` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
39. `Bootstrap histórico y API v1` — consumer_hop_1 (docs/shared-memory.md)
40. `Calidad y benchmarks` — consumer_hop_1 (README.md)
41. `Changed symbols` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
42. `Choose memory or code context` — consumer_hop_1 (skills/graphtyn/SKILL.md)
43. `Configurar el proyecto y preguntar si se activa memoria` — consumer_hop_1 (README.md)
44. `Conversational references` — consumer_hop_1 (skills/graphtyn/SKILL.md)
45. `Crear o actualizar el índice` — consumer_hop_1 (README.md)
46. `Dashboard` — consumer_hop_1 (docs/shared-memory.md)
47. `Dashboard y API` — consumer_hop_1 (README.md)
48. `Default workflow` — consumer_hop_1 (AGENTS.md)
49. `Diseño y operación` — consumer_hop_1 (docs/index.md)
50. `Documentación` — consumer_hop_1 (README.md)
51. `Documentación de Graphtyn` — consumer_hop_1 (docs/index.md)
52. `Documento` — consumer_hop_1 (skills/graphtyn/SKILL.md)
53. `Empezar` — consumer_hop_1 (docs/index.md)
54. `Entender el repositorio y obtener contexto acotado` — consumer_hop_1 (README.md)
55. `Espacios de código y agentes` — consumer_hop_1 (README.md)
56. `Evidence policy` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
57. `Evidencia` — consumer_hop_1 (docs/index.md)
58. `Flujo habitual` — consumer_hop_1 (README.md)
59. `GRAPHTYN CHANGE REPORT — graphtyn` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
60. `Generar artefactos persistentes` — consumer_hop_1 (README.md)
61. `Graphtyn` — consumer_hop_1 (skills/graphtyn/SKILL.md)
62. `Graphtyn agent policy` — consumer_hop_1 (AGENTS.md)
63. `Importar o sincronizar historiales autorizados` — consumer_hop_1 (README.md)
64. `Incorporar un legado al cerebro activo` — consumer_hop_1 (docs/shared-memory.md)
65. `Instalación rápida` — consumer_hop_1 (README.md)
66. `Instalar MCP con memoria del proyecto para Codex` — consumer_hop_1 (README.md)
67. `Instalar MCP del proyecto sólo en los clientes elegidos` — consumer_hop_1 (README.md)
68. `Integración con agentes` — consumer_hop_1 (README.md)
69. `Interpret evidence` — consumer_hop_1 (skills/graphtyn/SKILL.md)
70. `La captura continua se activa por separado` — consumer_hop_1 (README.md)
71. `Licencia` — consumer_hop_1 (README.md)
72. `Memoria compartida` — consumer_hop_1 (README.md)
73. `Memoria compartida del proyecto` — consumer_hop_1 (docs/shared-memory.md)
74. `Memoria temática` — consumer_hop_1 (README.md)
75. `Memoria temática y captura incremental` — consumer_hop_1 (docs/shared-memory.md)
76. `OpenClaw project memory` — consumer_hop_1 (AGENTS.md)
77. `Operación` — consumer_hop_1 (docs/shared-memory.md)
78. `Operación portable` — consumer_hop_1 (docs/shared-memory.md)
79. `Personal agent brains` — consumer_hop_1 (AGENTS.md)
80. `Planificar y verificar cambios` — consumer_hop_1 (README.md)
81. `Potential conflicts` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
82. `Pregunta en una terminal (predeterminado)` — consumer_hop_1 (README.md)
83. `Qué guarda` — consumer_hop_1 (docs/shared-memory.md)
84. `Qué ofrece` — consumer_hop_1 (README.md)
85. `Recommended verification` — consumer_hop_1 (GRAPHTYN_CHANGE_REPORT.md)
86. `Recuperación` — consumer_hop_1 (docs/shared-memory.md)
87. `Registros históricos` — consumer_hop_1 (docs/index.md)
88. `Repository code query` — consumer_hop_1 (skills/graphtyn/SKILL.md)
89. `Shared project memory` — consumer_hop_1 (graphtyn/agent_memory_policy.md)
90. `🌌 Graphtyn` — consumer_hop_1 (README.md)
91. `list` — consumer_hop_2 (graphtyn/core/history_import.py)
92. `_sync_cycle_space_summary` — consumer_hop_2 (graphtyn/cli.py)
93. `sync_once` — consumer_hop_2 (graphtyn/cli.py)
94. `discover_all_space_targets` — consumer_hop_2 (graphtyn/cli.py)
95. `runMemorySync` — consumer_hop_2 (graphtyn/web/js/memory.js)
96. `sync_targets` — consumer_hop_2 (graphtyn/cli.py)
97. `sync_path` — consumer_hop_2 (graphtyn/cli.py)
98. `_install_openclaw_capture_service` — consumer_hop_2 (graphtyn/cli.py)
99. `applyHistoricalMemory` — consumer_hop_2 (graphtyn/web/js/memory.js)
100. `correctSharedMemory` — consumer_hop_2 (graphtyn/web/js/memory.js)

## Potential conflicts

- None reported. Conflictos potenciales obtenidos mediante simulación no destructiva de git merge-tree.

## Evidence policy

EXTRACTED is parser evidence; INFERRED requires source verification; AMBIGUOUS must not be asserted as fact.
