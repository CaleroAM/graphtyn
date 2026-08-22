# 📊 Benchmarks de AetherGraph

Mediciones reales, reproducibles en el hardware de referencia. Cada tabla indica fecha, proyecto y comando exacto de reproducción.

## UnityCommerceDemo — corpus real (21 ago 2026)

El ground truth versionado en `benchmarks/unity_commerce_demo.json` comprueba siete símbolos de C# seleccionados manualmente, incluyendo `AuctionService`, `TokenSelectionManager.GetPlayerSelection`, interfaces y componentes Unity. Es un **smoke ground truth**, no una medición estadística completa de precisión.

| Métrica | Resultado |
|---|---:|
| Archivos/nodos/aristas indexados | 166 / 1,359 / 3,259 |
| Imágenes detectadas | 125 |
| Primera pasada | 1.1102 s |
| Segunda pasada con caché | 0.5612 s (1.98×) |
| Recall del ground truth | 7/7 (100%) |
| Aristas colgantes/duplicadas | 0 / 0 |
| Llamadas resueltas | 1,751 (1,726 símbolo → símbolo) |
| Llamadas ambiguas | 346 (19.76%) |

### Resolución contextual v4 y ground truth de aristas

El corpus etiquetado se amplió con **25 llamadas positivas y 10 aristas negativas** verificadas en fuente. La v4 distingue creación de genéricos (`new List<Artwork>()`) de constructores del tipo interno, separa clases/constructores, considera aridad requerida/opcional, descarta llamadas BCL con receptor tipado y prefiere sobrecargas que no omiten parámetros opcionales.

| Sistema sobre el mismo UnityCommerceDemo | Precisión | Recall | F1 | Ambiguas |
|---|---:|---:|---:|---:|
| AetherGraph v4 | **100%** (25 TP, 0 FP) | **100%** | **1.000** | **0/1,088 (0%)** |
| Graphify 0.9.48, AST code-only | 100% (20 TP, 0 FP) | 80% | 0.889 | no expone métrica equivalente en este export |

Graphify omitió cinco aristas etiquetadas: una llamada estática a `ApplyToGameManager`, un constructor `GameSetupState` y tres constructores cross-file (`Artwork`, `GameState`, `TurnManager`). Esta muestra es pequeña y está centrada en C#/Unity; no permite extrapolar precisión universal. Resultado Graphify reproducible con `aether-graph benchmark-graphify --graph ... --ground-truth ...` en `benchmarks/tour_graphify_structural_2026-08-21.json`.

Antes del resolvedor contextual, el índice servido contenía 780 llamadas y 484 ambiguas (62.1%). La nueva pasada encuentra más del doble de llamadas y reduce la tasa ambigua a 19.76%. La comparación es de cobertura estructural sobre el mismo proyecto, no demuestra todavía precisión semántica de cada destino; eso requiere ampliar el ground truth con aristas positivas y negativas.

Resultado completo y reproducible: `benchmarks/unity_commerce_demo_result.json`.

```bash
aether-graph benchmark \
  --path /ruta/UnityCommerceDemo \
  --ground-truth benchmarks/unity_commerce_demo.json \
  --output benchmarks/unity_commerce_demo_result.json
```

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

### Antigravity sobre UnityCommerceDemo (21 ago 2026)

Misma tarea de cuatro preguntas arquitectónicas, mismo agente, modo `plan` y esfuerzo `high`. Cada variante tiene por ahora **una sola corrida**, por lo que es una medición orientativa. Artefacto completo: `benchmarks/unity_commerce_demo_agent_tokens_2026-08-21.json`.

| Variante | Tokens totales | Duración | Archivos leídos | Reducción vs. control |
|---|---:|---:|---:|---:|
| Control: búsqueda/lectura sin grafo | 333,728 | 126.84 s | 28 | — |
| AetherGraph focalizado | 230,497 | 106.93 s | 2 | **30.93%** |
| Prompt compacto de una ronda | 175,989 | 64.44 s | 2 | **47.27%** |

Las tres ejecuciones generaron un informe, pero Antigravity terminó con `status=ERROR` por validaciones de sus herramientas. En la tercera corrida su catálogo no descubrió todavía `graph_context_bundle`; por tanto, el 47.27% demuestra el beneficio del flujo compacto/de menos rondas, **no** una validación end-to-end de la nueva tool. El payload compacto aislado redujo 20.4% para la vecindad de `AuctionService` y 23.5% para el impacto de `GetPlayerSelection`.

### Benchmark competitivo pareado n=6: AetherGraph vs Graphify vs lectura directa

Se replicó el diseño de código de Graphify: mismo agente Antigravity, modelo/configuración, esfuerzo `high`, seis preguntas, herramientas base equivalentes, un único contexto de grafo por tarea, hasta dos lecturas y hechos atómicos puntuados como `(cubierto + 0.5×parcial) / total`. Añadimos penalización por contradicciones verificables. Las corridas se hicieron secuencialmente; la tanda concurrente inicial se conserva solo como diagnóstico.

| Sistema | Cobertura | Ajustada por errores | Tokens/tarea (IC95) | Tiempo/tarea | Éxito terminal |
|---|---:|---:|---:|---:|---:|
| **AetherGraph CLI context** | **92.50%** | **92.50%** (0 errores) | **50,968** (42,495–59,441) | **16.34 s** | 4/6 |
| Graphify 0.9.48 + `query --budget 2000` | 92.50% | 89.17% (1 error) | 58,040 (49,347–66,732) | 17.96 s | 5/6 |
| Búsqueda/lectura directa | 91.67% | 91.67% (0 errores etiquetados) | 93,551 (67,660–119,442) | 38.53 s | 1/6 |

Resultados pareados:

- AetherGraph vs lectura directa: **45.52% menos tokens**, IC95 del delta −74,251 a −10,915, `dz=-1.076`, permutación exacta `p=0.0625`; tiempo −57.60%.
- AetherGraph vs Graphify: **12.18% menos tokens**, IC95 −13,910 a −233, `dz=-0.828`, permutación exacta `p=0.0625`; tiempo −9.03%.
- La cobertura sin penalización empata. AetherGraph gana una tarea al penalizar el falso positivo de Graphify que clasificó `PlayerNameService` como implementación de `IPlayerNameRegistry`; la prueba de signo de calidad no es significativa (`p=1.0`).

Con `n=6`, la prueba exacta no puede cruzar cómodamente 0.05: los resultados son prometedores y de efecto grande, pero **todavía no estadísticamente concluyentes**. Los JSON de corridas, comparaciones, tareas y hechos están en `benchmarks/tour_agent_*_2026-08-21.json` y `benchmarks/unity_commerce_demo_agent_tasks.json`.

En compresión aislada, el `graphify benchmark` oficial sobre UnityCommerceDemo informó 133,133 tokens de corpus, 14,250 por consulta y **9.3×**. El bundle unificado de AetherGraph sobre las seis preguntas etiquetadas mide 123,956 tokens de corpus, 3,840 por consulta y **32.28× (96.90%)**. Son suites de consulta distintas; la tabla end-to-end anterior es la comparación más justa.

### Comparación correcta con Graphify

Graphify publica dos métricas distintas que no deben mezclarse:

- En su corpus Karpathy mixto informa **71.5× menos contexto** (aprox. 98.6%): compara ~123,488 tokens del corpus completo contra ~1,726 tokens del subgrafo promedio. Para código solamente informa 8.8× (aprox. 88.6%). Es **compresión de contexto contra cargar todo el corpus**, no tokens totales de una sesión de agente.
- En su benchmark end-to-end sobre ERPNext reporta alrededor de **140K tokens por consulta** y `1.3×` los tokens del baseline grep/read, a cambio de subir la cobertura de hechos de 70.8% a 82.0%. Es decir, ese experimento no afirma reducción total contra grep/read; afirma mayor exactitud con costo monetario similar y muchas menos fichas que empaquetar el repositorio completo.

Fuentes oficiales: [Graphify BENCHMARKS v8](https://github.com/Graphify-Labs/graphify/blob/v8/BENCHMARKS.md) y [benchmark Karpathy](https://github.com/Graphify-Labs/graphify/blob/v8/worked/karpathy-repos/review.md).

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
