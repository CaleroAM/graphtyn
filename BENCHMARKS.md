# 📊 Benchmarks de AetherGraph

Mediciones reales, reproducibles en el hardware de referencia. Cada tabla indica fecha, proyecto y comando exacto de reproducción.

## ⚙️ Hardware de Referencia

| Componente | Detalle |
|---|---|
| CPU | Intel Core i5-12500H (16 hilos) |
| RAM | 15 GB |
| GPU | NVIDIA GeForce RTX 3050 Mobile (4 GB VRAM, CUDA) |
| OS | NixOS 26.05 (Linux) |
| Ollama | 0.30.6 (CUDA 12.9) |
| Modelos locales | `llama3.2:latest`, `qwen2.5-coder:3b`, `qwen2.5-coder:7b`, `llama3.1:8b` |

## ⏱️ 1. Pasada Determinista (Solo AST) — 0 Tokens

**Comando:** `aether-graph reindex --path <proyecto> --engine ast_pure` (mide el roundtrip CLI→daemon; el scan directo del parser se mide aparte).

| Proyecto | Archivos | Nodos | Conectores | Tiempo | Tokens |
|---|---|---|---|---|---|
| aether-graph (propio) | 11 | 50 | 44 | 0.147 s | 0 |
| 366metrics-cdk (AWS CDK, Python) | 22 `.py` | 108 | 95+ | **0.406 s** (scan directo: 0.327 s) | 0 |

*Medido: 18 ago 2026. Escala ~lineal con el tamaño del proyecto (~2.2× más grande → ~2.8× el tiempo del README base).*

## 🧠 2. AST + Enriquecimiento Local (Ollama, GPU) — 0 Tokens (Local)

**Comando:** `OLLAMA_MODEL=qwen2.5-coder:3b aether-graph reindex --path <proyecto> --engine ast_local_llm`

| Proyecto | Modelo | Tiempo Full | Enriquecidos | Tokens |
|---|---|---|---|---|
| aether-graph (propio) | qwen2.5-coder:3b | ~50 s | ~40 símbolos | 0 (local) |
| 366metrics-cdk | qwen2.5-coder:3b | **96.3 s** (incluye carga en frío) | 26 archivos + 69 símbolos + `ai_summary` global | 0 (local) |

**Reindexado incremental** (solo archivos cambiados según `git status`, sin untracked):

| Escenario | Tiempo |
|---|---|
| 366metrics-cdk, 0 cambios reales (contexto reutilizado) | **2.57 s** |
| Referencia README: proyecto de 277 archivos, 0 cambios | 5-8 s (vs ~5 min full) |

*El incremental detecta cambios con `git status --porcelain` y solo re-enriquece los archivos realmente modificados; el resto conserva su contexto cacheado.*

## 🦙 3. Benchmark de Modelos Locales (vía Ollama)

Prompts reales de AetherGraph (resumen de arquitectura global + resumen de archivo), temperatura 0.2.

| Modelo | Tamaño | Resumen Arquitectura | Resumen Archivo | Distribución GPU/CPU |
|---|---|---|---|---|
| `llama3.2:latest` (3B) | ~2.0 GB | 0.98 s / 45 tok | 0.85 s / 36 tok | 100% GPU |
| `qwen2.5-coder:3b` | ~1.9 GB | 1.83 s* / 160 tok | 1.83 s / 97 tok | 100% GPU |
| `qwen2.5-coder:7b` | ~4.7 GB | 16.1 s / 24 tok | 10.3 s / 110 tok | 53% CPU / 47% GPU |
| `llama3.1:8b` | ~4.9 GB | 19.2 s / 66 tok | 4.1 s / 36 tok | 55% CPU / 45% GPU |

\* La primera llamada de `qwen2.5-coder:3b` (7.87 s) incluye la carga en frío del modelo.

**Conclusión:** en 4 GB de VRAM los modelos 3B cargan 100% en GPU y generan en ~1 s; los 7B/8B derraman a CPU y tardan 10-20 s sin mejora proporcional para resúmenes de una frase.

## 📦 4. Payloads del MCP (eficiencia de contexto para el agente)

Medido sobre el índice enriquecido de 366metrics-cdk (108 nodos). Los payloads del MCP no incluyen campos visuales del dashboard (`color`/`val`).

| Consulta | Nodos devueltos | Payload | Reducción |
|---|---|---|---|
| `graph_neighborhood` (completo) | 108 | ~66K chars ≈ 16.5K tokens | — |
| `graph_neighborhood {symbol:"KommoExtractor", depth:2}` | 24 | ~15.6K chars ≈ **3.9K tokens** | 76% |
| `graph_neighborhood {symbol:"fetch_tenants", depth:1}` | ~8 | ~1.5K tokens | ~90% |
| `graph_neighborhood {limit:15}` | 15 | ~4K tokens + `tokens_avoided` estimado: **33K** | ~88% |

Cada consulta MCP registra en el historial (`graph_history_*`) el campo `tokens_avoided` = tamaño estimado de leer los archivos crudos involucrados menos el tamaño del payload servido.

### Contexto real de un agente (medición de extremo a extremo)

Sesión real de un agente (OpenClaw + Gemini 3.1 Pro) conectado al MCP de AetherGraph sobre 366metrics-cdk: **4.15M tokens en 125 llamadas al modelo**. Desglose:

| Componente | Tokens |
|---|---|
| Entrada total (historial + system prompt reenviados por el agente) | 4.09M |
| Salida del modelo | 56.6K |
| Bucle de reintentos de una tool (20 llamadas a `graph_register_project`) | 928K |

**Lectura:** el costo dominante no es el análisis de AetherGraph (0 tokens), sino el mecanismo del agente de reenviar su contexto completo en cada llamada. AetherGraph reduce la fracción que toca el código: el mapa completo en 1 consulta (~16K tokens) reemplaza la lectura de 22 archivos (~150K+ tokens).

## 🔁 Reproducción

```bash
# 1. Pasada determinista
time aether-graph reindex --path /ruta/proyecto --engine ast_pure

# 2. Enriquecimiento local (requiere Ollama con qwen2.5-coder:3b)
OLLAMA_MODEL=qwen2.5-coder:3b time aether-graph reindex --path /ruta/proyecto --engine ast_local_llm

# 3. Incremental (segunda corrida, sin cambios)
OLLAMA_MODEL=qwen2.5-coder:3b time aether-graph reindex --path /ruta/proyecto --engine ast_local_llm

# 4. Payloads MCP
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"graph_neighborhood","arguments":{"symbol":"NombreSimbolo","depth":2}}}' | aether-graph mcp --path /ruta/proyecto
```

## 📄 5. Multi-Modal (Docs · PDF · Office · Imágenes · Audio)

Medido sobre un proyecto sintético real (README.md + manual.docx + tenants.xlsx + dummy.pdf + 3 imágenes reales + audio real), enriquecimiento local `qwen2.5-coder:3b` + `qwen3-vl:2b` + `whisper-small` (CPU), todo $0 tokens:

| Tarea | Tiempo | Resultado |
|---|---|---|
| Reindex completo multi-modal (8 nodos: docs + PDF + DOCX + XLSX + 3 imágenes) | 200.9 s | 7/8 enriquecidos; descripciones correctas (pipeline ETL del DOCX, tenants del XLSX, tiburón/vaca de las fotos) |
| Descripción de imagen (qwen3-vl:2b, caliente) | 14-40 s/imagen | Identifica sujeto + rol técnico |
| Descripción de imagen (minicpm-v4.6:1b, caliente) | 2-3 s/imagen (imágenes pequeñas) | Correcto en diagramas; flojo en especies de fotos |
| Transcripción de audio real (whisper-small, CPU 16 hilos) | 4.5 s por ~3 s de audio | "Puedo registrarme temprano." — exacto |
| Reindex media (audio → transcripción → resumen LLM) | 16.5 s total | Nodo con resumen semántico correcto |

### Comparativa de modelos de visión (RTX 3050 4GB)

| Modelo | VRAM | Tiempo/imagen | Notas |
|---|---|---|---|
| `qwen3-vl:2b` | 2.3 GB (40% GPU) | 14-40 s | Mejor comprensión real (vaca, tiburón, diagramas); emite thinking tokens |
| `minicpm-v4.6:1b` | 900 MB (95% GPU) | 2-3 s | Directo, sin thinking; flojo en especies de fotos |

**Nota NixOS:** el daemon requiere `LD_LIBRARY_PATH` con `zlib` y `gcc-lib` del nix store para cargar `av`/`faster-whisper`.
