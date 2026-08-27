# GRAPHTYN REPORT — graphtyn

## Purpose
El motor de mapa topológico de código, registro de sesiones local y servidor MCP estándar para Agentes de IA (Google Antigravity, Claude Code, Codex, Cursor y Windsurf).

## Technology profile
- Languages: Python, JavaScript
- Frameworks/tools: FastAPI, Tree-sitter, Uvicorn, pytest
- Manifests: pyproject.toml

## Entry points
- `graphtyn/cli.py`
- `graphtyn/api/main.py`

## Architecture
```mermaid
flowchart TD
  ROOT[Project]
  ROOT --> S0[core]
  ROOT --> S1[js]
  ROOT --> S2[starlette]
  ROOT --> S3[tour]
  ROOT --> S4[graphtyn]
  ROOT --> S5[graphtyn]
  ROOT --> S6[starlette]
  ROOT --> S7[tour]
  S5 -->|10| S0
```

## Representative flows
- **scan_directory** —llama→ **_tree_facts** [EXTRACTED] · `graphtyn/core/ast_parser.py:388`
- **scan_directory** —llama→ **_add_tree_symbols** [EXTRACTED] · `graphtyn/core/ast_parser.py:390`
- **main** —llama→ **scan_directory** [EXTRACTED] · `graphtyn/cli.py:420`

## Risk and technical-debt signals
- **ambiguous_relations** (medium): 21 (usa: 11, llama: 10) Requieren verificación; no prueban un defecto.
- **high_connectivity_hotspots** (review): scan_directory, main, handle_request, visit, loadGraph Alta conectividad implica mayor radio potencial, no deuda confirmada.

## Key symbols
- `ProjectWatcher`
- `ASTParser`
- `HistoryTracker`
- `WatchManager`
- `loadGraph`
- `_enrich_with_ai`
- `apply3DStyle`
- `_text`

## Report metrics
- estimated_tokens: `359`
- selected_source_tokens: `17042`
- observable_coverage: `1.0`
- reduction_vs_selected_source: `0.9789`
- quality_note: `Coverage compares observable dimensions/headings, not ground-truth semantic correctness.`
