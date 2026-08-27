# 📊 Benchmarks de Graphtyn

> **Lectura:** este archivo conserva resultados actuales e históricos. Use los
> estados de [`testing.md`](testing.md). La matriz de 36 tareas/108
> celdas continúa `PENDING`; los resultados parciales no prueban liderazgo general.

## Estado resumido

| Corpus | Estado |
|---|---|
| Starlette, Python/ASGI | FULL para ese corpus |
| go-chi, Go | PARTIAL; la regresión dirigida cambió el protocolo |
| CleanArchitecture, .NET | PARTIAL; v8 no completó las tres condiciones |
| ZERP, Laravel/React | PARTIAL; diagnóstico y una tarea dirigida |
| Memoria compartida | PARTIAL; falta más escala y repetición |
| 36 tareas multilenguaje | PENDING |

## Validación de regresión — 25 ago 2026

| Comprobación | Resultado | Estado |
|---|---:|---|
| Suite sin arnés HTTP `TestClient` | 180 passed, 3 skipped, 16.37 s | FULL |
| Protocolo multilenguaje | 36 tareas, 6 tecnologías, 108 celdas, 0 errores | FULL (estructura) |
| SQLite de memoria real | 56 memorias, 56 embeddings, 56 FTS, 0 huérfanos | FULL |
| Grafo HTTP de memoria | 82 nodos, 118 aristas, 5 autores, 4 consultores | FULL |
| Estabilidad de retrieval | 285 consultas; Recall@5 1.0; MRR 0.9889 | FULL para dataset sintético |
| Atribución / negativos | 1.0 / 1.0 | FULL para dataset sintético |
| Contexto recuperado | media estimada 315.85 tokens | estimación, no facturación |
| Latencia local | media 12.412 ms; p95 14.095 ms | entorno de referencia |
| Smoke visual Playwright | omitido: falta `libstdc++.so.6` en runtime | BLOCKED ambiental |
| Suite HTTP en proceso | `TestClient.get()` se bloquea en Python 3.13 | BLOCKED del arnés |

Los endpoints reales `/health`, `/`, `/api/projects` y `/api/memory/graph` sí
respondieron en `127.0.0.1:9210`. El benchmark de estabilidad crea un corpus
sintético controlado; no debe extrapolarse a conversaciones empresariales sin la
matriz viva adicional.

Los casos se describen por tecnología y propósito para que sean comprensibles sin conocer sus nombres internos. Cuando aparece `UnityCommerceDemo`, se refiere al **repositorio real Unity/C# de un juego empresarial por turnos**; `Starlette` identifica el **framework público Python/ASGI** usado como validación externa. En las tablas, el competidor directo se presenta como **Gra…ify**. Los nombres exactos se conservan únicamente en rutas, comandos y artefactos necesarios para reproducibilidad.

## Protocolo estadístico multilenguaje (36 tareas)

[`benchmarks/statistical_protocol_36_tasks.json`](../benchmarks/statistical_protocol_36_tasks.json) define **36 tareas y 108 celdas pareadas**: Graphtyn, Gra…ify y agente sin grafo. Cubre seis familias tecnológicas y seis repositorios: Python/ASGI, Unity/C#, .NET, PHP/Laravel, TypeScript/React y Go. Cada tarea exige prompt y al menos tres hechos atómicos; la variante se aleatoriza dentro de cada bloque y un reintento solo se admite por fallo de transporte, conservando ambos costos.

Las revisiones están fijadas. El caso TypeScript/React limita explícitamente el índice a `src/auth`, porque sus seis tareas pertenecen a autenticación; ese alcance produjo 153 nodos/212 aristas en 0.11 s. El checkout completo contiene 4,929 archivos TS/TSX y no terminó su primera indexación en 90 s, por lo que se registra como prueba de estrés pendiente y no se oculta dentro de las cifras del alcance. El repositorio Go completo produjo 493 nodos/1,184 aristas en 1.30 s.

`graphtyn benchmark-suite --protocol ...` valida tamaño, unicidad, tecnologías y comparadores. Con `--results resultados.json --control no_graph|competitor` calcula delta pareado de tokens, bootstrap IC95, diferencia de calidad, tamaño de efecto `dz` y prueba de permutación por cambio de signo. El manifiesto está listo, pero no contiene resultados inventados: ejecutar las 108 llamadas externas es una fase experimental separada y potencialmente costosa.

Mediciones reales, reproducibles en el hardware de referencia. Cada tabla indica fecha, proyecto y comando exacto de reproducción.

## Context Planner — UnityCommerceDemo (21 ago 2026)

Consulta real: `GameHUDController.cs`, `GameManager` y `PlayerNameServiceTests.GeneratedNames_RespectMaxLength`, profundidad 1.

| Variante | Nodos | Enlaces | Tokens estimados | Reducción vs fuente |
|---|---:|---:|---:|---:|
| Unión anterior, límite por símbolo | 31 | 36 | 5,577 | 71.37% |
| `relevance-v1`, presupuesto global 20 | 20 | 26 | 3,895 | 78.80% |
| `relevance-v1`, presupuesto global 12 (predeterminado) | 12 | 10 | 2,003 | 88.96% |

Los tokens se estiman como caracteres UTF-8/4 y no equivalen a facturación de un proveedor. El planificador informa `omitted.nodes`, `omitted.links` y `truncated`; no oculta el descarte. Para contextos pequeños puede existir expansión negativa y se reporta como tal.

Las relaciones `AMBIGUOUS` indican varios destinos estructuralmente compatibles, no errores demostrados. En UnityCommerceDemo, parte surge de métodos homónimos (`Exit`, `ShowTurnOrderRoll`) y copias bajo `LegacyEditorBackup`. Reducir la cifra sin perder recall requiere inferencia de receptor, despacho por interfaz y perfiles de alcance; simplemente borrar candidatos maquillaría la métrica.

El índice activo medido contiene 67 aristas ambiguas de 1,689. El perfil `production` elimina cruces con pruebas/backups y deja 53 de 1,304; las 14 restantes no se borran porque requieren mejor resolución del receptor. El perfil `legacy` contiene 103 nodos y 114 enlaces sin ambigüedad interna. Estas cifras describen el índice activo y pueden cambiar tras reindexar.

### Resolución estructural v5

Una reindexación limpia sobre el índice completo añadió tipos de campos y propiedades, además de cadenas de receptores como `GameManager.Instance.hud`. El resultado pasó de **67 relaciones ambiguas a 3** sobre 901 nodos y 1,482 enlaces. Las llamadas de código ambiguas quedaron en **0**; las tres restantes son referencias textuales `usa` desde `architecture_review.md`, donde nombres como `Show`, `Hide` y una sobrecarga de `StartGame` no identifican un único símbolo.

Ejemplo resuelto con evidencia: `GameManager.Instance.hud.ShowTurnOrderRoll(...)` se dirige únicamente a `GameHUDController.ShowTurnOrderRoll`, aun cuando existen tres métodos con ese nombre. La resolución registra `receiver_chain`, `receiver_type`, archivo y línea. La ejecución fría medida tardó 1.20 segundos y la ejecución desde caché 0.7 segundos en el hardware de prueba.

Qwen 2.5 Coder 3B sigue siendo la capa local de enriquecimiento semántico y ranking. Tree-sitter conserva la autoridad sobre hechos estructurales verificables; el modelo no inventa aristas de llamadas.

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
| Graphtyn v4 | **100%** (25 TP, 0 FP) | **100%** | **1.000** | **0/1,088 (0%)** |
| Gra…ify 0.9.48, AST code-only | 100% (20 TP, 0 FP) | 80% | 0.889 | no expone métrica equivalente en este export |

Gra…ify omitió cinco aristas etiquetadas: una llamada estática a `ApplyToGameManager`, un constructor `GameSetupState` y tres constructores cross-file (`Artwork`, `GameState`, `TurnManager`). Esta muestra es pequeña y está centrada en C#/Unity; no permite extrapolar precisión universal. Resultado Gra…ify reproducible con `graphtyn benchmark-graphify --graph ... --ground-truth ...` en `benchmarks/tour_graphify_structural_2026-08-21.json`.

Antes del resolvedor contextual, el índice servido contenía 780 llamadas y 484 ambiguas (62.1%). La nueva pasada encuentra más del doble de llamadas y reduce la tasa ambigua a 19.76%. La comparación es de cobertura estructural sobre el mismo proyecto, no demuestra todavía precisión semántica de cada destino; eso requiere ampliar el ground truth con aristas positivas y negativas.

Resultado completo y reproducible: `benchmarks/unity_commerce_demo_result.json`.

```bash
graphtyn benchmark \
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

**Comando:** `graphtyn reindex --path <proyecto> --engine ast_pure` (mide el roundtrip CLI→daemon; el scan directo del parser se mide aparte).

| Proyecto | Archivos | Nodos | Conectores | Tiempo | Tokens |
|---|---|---|---|---|---|
| graphtyn (propio) | 11 | 50 | 44 | 0.147 s | 0 |
| 366metrics-cdk (AWS CDK, Python) | 22 `.py` | 108 | 95+ | **0.406 s** (scan directo: 0.327 s) | 0 |

*Medido: 18 ago 2026. Escala ~lineal con el tamaño del proyecto (~2.2× más grande → ~2.8× el tiempo del README base).*

## 🧠 2. AST + Enriquecimiento Local (Ollama, GPU) — 0 Tokens (Local)

**Comando:** `OLLAMA_MODEL=qwen2.5-coder:3b graphtyn reindex --path <proyecto> --engine ast_local_llm`

| Proyecto | Modelo | Tiempo Full | Enriquecidos | Tokens |
|---|---|---|---|---|
| graphtyn (propio) | qwen2.5-coder:3b | ~50 s | ~40 símbolos | 0 (local) |
| 366metrics-cdk | qwen2.5-coder:3b | **96.3 s** (incluye carga en frío) | 26 archivos + 69 símbolos + `ai_summary` global | 0 (local) |

**Reindexado incremental** (solo archivos cambiados según `git status`, sin untracked):

| Escenario | Tiempo |
|---|---|
| 366metrics-cdk, 0 cambios reales (contexto reutilizado) | **2.57 s** |
| Referencia README: proyecto de 277 archivos, 0 cambios | 5-8 s (vs ~5 min full) |

*El incremental detecta cambios con `git status --porcelain` y solo re-enriquece los archivos realmente modificados; el resto conserva su contexto cacheado.*

## 🦙 3. Benchmark de Modelos Locales (vía Ollama)

Prompts reales de Graphtyn (resumen de arquitectura global + resumen de archivo), temperatura 0.2.

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

Sesión real de un agente (OpenClaw + Gemini 3.1 Pro) conectado al MCP de Graphtyn sobre 366metrics-cdk: **4.15M tokens en 125 llamadas al modelo**. Desglose:

| Componente | Tokens |
|---|---|
| Entrada total (historial + system prompt reenviados por el agente) | 4.09M |
| Salida del modelo | 56.6K |
| Bucle de reintentos de una tool (20 llamadas a `graph_register_project`) | 928K |

**Lectura:** el costo dominante no es el análisis de Graphtyn (0 tokens), sino el mecanismo del agente de reenviar su contexto completo en cada llamada. Graphtyn reduce la fracción que toca el código: el mapa completo en 1 consulta (~16K tokens) reemplaza la lectura de 22 archivos (~150K+ tokens).

### Antigravity sobre UnityCommerceDemo (21 ago 2026)

Misma tarea de cuatro preguntas arquitectónicas, mismo agente, modo `plan` y esfuerzo `high`. Cada variante tiene por ahora **una sola corrida**, por lo que es una medición orientativa. Artefacto completo: `benchmarks/unity_commerce_demo_agent_tokens_2026-08-21.json`.

| Variante | Tokens totales | Duración | Archivos leídos | Reducción vs. control |
|---|---:|---:|---:|---:|
| Control: búsqueda/lectura sin grafo | 333,728 | 126.84 s | 28 | — |
| Graphtyn focalizado | 230,497 | 106.93 s | 2 | **30.93%** |
| Prompt compacto de una ronda | 175,989 | 64.44 s | 2 | **47.27%** |

Las tres ejecuciones generaron un informe, pero Antigravity terminó con `status=ERROR` por validaciones de sus herramientas. En la tercera corrida su catálogo no descubrió todavía `graph_context_bundle`; por tanto, el 47.27% demuestra el beneficio del flujo compacto/de menos rondas, **no** una validación end-to-end de la nueva tool. El payload compacto aislado redujo 20.4% para la vecindad de `AuctionService` y 23.5% para el impacto de `GetPlayerSelection`.

### Benchmark competitivo pareado n=6: Graphtyn vs Gra…ify vs lectura directa

Se replicó el diseño de código de Gra…ify: mismo agente Antigravity, modelo/configuración, esfuerzo `high`, seis preguntas, herramientas base equivalentes, un único contexto de grafo por tarea, hasta dos lecturas y hechos atómicos puntuados como `(cubierto + 0.5×parcial) / total`. Añadimos penalización por contradicciones verificables. Las corridas se hicieron secuencialmente; la tanda concurrente inicial se conserva solo como diagnóstico.

| Sistema | Cobertura | Ajustada por errores | Tokens/tarea (IC95) | Tiempo/tarea | Éxito terminal |
|---|---:|---:|---:|---:|---:|
| **Graphtyn CLI context** | **92.50%** | **92.50%** (0 errores) | **50,968** (42,495–59,441) | **16.34 s** | 4/6 |
| Gra…ify 0.9.48 + `query --budget 2000` | 92.50% | 89.17% (1 error) | 58,040 (49,347–66,732) | 17.96 s | 5/6 |
| Búsqueda/lectura directa | 91.67% | 91.67% (0 errores etiquetados) | 93,551 (67,660–119,442) | 38.53 s | 1/6 |

Resultados pareados:

- Graphtyn vs lectura directa: **45.52% menos tokens**, IC95 del delta −74,251 a −10,915, `dz=-1.076`, permutación exacta `p=0.0625`; tiempo −57.60%.
- Graphtyn vs Gra…ify: **12.18% menos tokens**, IC95 −13,910 a −233, `dz=-0.828`, permutación exacta `p=0.0625`; tiempo −9.03%.
- La cobertura sin penalización empata. Graphtyn gana una tarea al penalizar el falso positivo de Gra…ify que clasificó `PlayerNameService` como implementación de `IPlayerNameRegistry`; la prueba de signo de calidad no es significativa (`p=1.0`).

Con `n=6`, la prueba exacta no puede cruzar cómodamente 0.05: los resultados son prometedores y de efecto grande, pero **todavía no estadísticamente concluyentes**. Los JSON de corridas, comparaciones, tareas y hechos están en `benchmarks/tour_agent_*_2026-08-21.json` y `benchmarks/unity_commerce_demo_agent_tasks.json`.

En compresión aislada, el `graphify benchmark` oficial sobre UnityCommerceDemo informó 133,133 tokens de corpus, 14,250 por consulta y **9.3×**. El bundle unificado de Graphtyn sobre las seis preguntas etiquetadas mide 123,956 tokens de corpus, 3,840 por consulta y **32.28× (96.90%)**. Son suites de consulta distintas; la tabla end-to-end anterior es la comparación más justa.

### Comparación correcta con Gra…ify

Gra…ify publica dos métricas distintas que no deben mezclarse:

- En su corpus Karpathy mixto informa **71.5× menos contexto** (aprox. 98.6%): compara ~123,488 tokens del corpus completo contra ~1,726 tokens del subgrafo promedio. Para código solamente informa 8.8× (aprox. 88.6%). Es **compresión de contexto contra cargar todo el corpus**, no tokens totales de una sesión de agente.
- En su benchmark end-to-end sobre ERPNext reporta alrededor de **140K tokens por consulta** y `1.3×` los tokens del baseline grep/read, a cambio de subir la cobertura de hechos de 70.8% a 82.0%. Es decir, ese experimento no afirma reducción total contra grep/read; afirma mayor exactitud con costo monetario similar y muchas menos fichas que empaquetar el repositorio completo.

Fuentes oficiales: [Gra…ify BENCHMARKS v8](https://github.com/Gra…ify-Labs/graphify/blob/v8/BENCHMARKS.md) y [benchmark Karpathy](https://github.com/Gra…ify-Labs/graphify/blob/v8/worked/karpathy-repos/review.md).

### OpenCode `x-preview-f-free`: MCP compacto `evidence-v1`

Prueba end-to-end sobre la raíz completa de UnityCommerceDemo, con seis tareas pareadas, MCPs aislados y el mismo modelo. `evidence-v1` declara cada ruta una vez, usa aliases para nodos, codifica relaciones como tuplas y ajusta el presupuesto al número de símbolos. Los ceros de `coverage` son evidencia negativa cuando `complete=true`, evitando búsquedas redundantes.

| Variante | Calidad | Tokens/tarea | Tiempo/tarea | Llamadas | Errores |
|---|---:|---:|---:|---:|---:|
| Graphtyn anterior | 77.78% | 20,248 | 79.93 s | 31 | 0 |
| **Graphtyn `evidence-v1`** | **75.00%** | **10,970** | 89.30 s | 38 | 0 |
| Gra…ify 0.9.48 | 63.61% | 12,251 | 75.20 s | 65 | 1* |
| Lectura directa sin grafo | 68.89% | 22,917 | 145.61 s | 81 | 1* |

`evidence-v1` redujo **45.82%** los tokens frente al Graphtyn anterior y **52.13%** frente a lectura directa. La diferencia de calidad contra la versión anterior fue −2.78 puntos en `n=6`, sin significancia concluyente. Una optimización posterior de cobertura negativa redujo el peor caso `AuctionService` de 181.14 s/9 llamadas/9,023 tokens a **47.44 s/2 llamadas/4,393 tokens**, y elevó su cobertura de 25.00% a 58.33%.

\* El patrón automático de contradicción sobre `PlayerNameService` puede producir un falso positivo cuando la respuesta dice que referencia o instancia la implementación, no que implemente la interfaz. Se conservan tanto calidad bruta como ajustada para auditoría. Artefactos: `benchmarks/x_preview_f_free_root_2026-08-21/`, `benchmarks/x_preview_f_free_compact_2026-08-21/` y `benchmarks/x_preview_f_free_latency_2026-08-21/`.

### Validación externa: `ardalis/CleanArchitecture` v11.1.1

Prueba sobre la revisión fija `859b115072337b3b7074007f8231d19f24966f1a`, distinta del proyecto usado durante el desarrollo. Se evaluaron cuatro tareas y 24 hechos sobre creación, borrado/eventos, bindings de infraestructura y consultas paginadas. Las tres variantes usaron OpenCode con `opencode/x-preview-f-free`; las herramientas de escritura estuvieron deshabilitadas. Las celdas que terminaron `ERROR` recibieron un único reintento y se conservó la última corrida. El modelo gratuito mostró alta variación temporal: un intento de Graphtyn agotó 600 s y su reintento terminó en 120.39 s.

| Variante | Calidad ajustada | Tokens/tarea | Tiempo/tarea | Llamadas/tarea | Éxito | Errores factuales |
|---|---:|---:|---:|---:|---:|---:|
| Graphtyn `evidence-v1` + miembros v6 | 31.25% | 31,623 | 191.66 s | **13.25** | 4/4 | 0 |
| Gra…ify 0.9.48 | 54.17% | **19,553** | **167.85 s** | 24.00 | 4/4 | 0 |
| Lectura directa sin grafo | **100.00%** | 24,808 | 182.70 s | 23.75 | 4/4 | 0 |

En esta suite Graphtyn hizo 44.21% menos llamadas que la lectura directa, pero consumió 27.47% más tokens y perdió 68.75 puntos de calidad. Gra…ify consumió 21.18% menos tokens que el baseline, pero perdió 45.83 puntos. El resultado contradice el benchmark de UnityCommerceDemo y delimita la ventaja actual: el grafo funciona bien para topología y radio de impacto, pero no basta para preguntas cuyo ground truth vive en cuerpos de método (`AddScoped`, `Publish`, `Skip/Take`, `CountAsync`, validadores y constantes).

La siguiente mejora debe ser una representación compacta y determinista de operaciones internas —accesos a miembros, asignaciones, retornos, creación de objetos, argumentos relevantes y llamadas externas sin target local— servida por intención (`flow`, `bindings`, `persistence`, `tests`). Añadir más prosa de Qwen no resolvería por sí solo esta ausencia de evidencia. Artefactos completos, tareas y resumen: `benchmarks/cleanarchitecture_x_preview_f_free_2026-08-21/` y `benchmarks/cleanarchitecture_agent_tasks.json`.

#### Repetición con operaciones internas v7

Se implementó la mejora indicada por la primera corrida: los métodos ahora conservan operaciones compactas y ubicadas (`call`, `new`, `assign`, `declare`, `return`, `control`), incluidas llamadas a frameworks sin nodo local. El MCP selecciona hasta diez por entidad según la intención y prioriza acciones como `AddScoped`, `Publish`, `DeleteAsync`, `Skip`, `Take`, `CountAsync` y `AddInterceptors`. Se repitieron las cuatro tareas con el mismo repositorio, revisión, modelo y política; solo una celda `ERROR` recibió un reintento.

| Variante | Calidad ajustada | Tokens/tarea | Tiempo/tarea | Llamadas/tarea | Éxito |
|---|---:|---:|---:|---:|---:|
| Graphtyn v6 (miembros, sin operaciones) | 31.25% | 31,623 | 191.66 s | 13.25 | 4/4 |
| **Graphtyn v7 (`ops`)** | **75.00%** | **22,372** | **146.43 s** | **8.75** | 4/4 |
| Gra…ify 0.9.48 | 54.17% | 19,553 | 167.85 s | 24.00 | 4/4 |
| Lectura directa sin grafo | 100.00% | 24,808 | 182.70 s | 23.75 | 4/4 |

V7 elevó la calidad **+43.75 puntos**, redujo tokens **29.25%**, tiempo **23.62%** y llamadas **33.96%** frente a v6. Frente a Gra…ify obtuvo +20.83 puntos de calidad, 12.76% menos tiempo y 63.54% menos llamadas, aunque usó 14.42% más tokens. Frente a lectura directa redujo tokens 9.82%, tiempo 19.85% y llamadas 63.16%, con una brecha de calidad de 25 puntos.

Tres tareas alcanzaron 100%. `infrastructure-bindings` puntuó 0% porque `x-preview-f-free` terminó una respuesta después de la primera sección pese a devolver estado `SUCCESS`; se conservó sin reintento para evitar selección favorable. El paquete sí contenía los bindings y ambas selecciones de base de datos. Por tanto, el 75% mezcla calidad del índice con estabilidad de generación del proveedor. Artefactos: `benchmarks/cleanarchitecture_x_preview_f_free_v7_2026-08-21/`.

#### Perfil MCP de intención única v8

El trace de v7 mostró que OpenCode seguía llamando herramientas antiguas antes y después del nuevo planificador. Se añadió `graph_query_intent`, contexto diferencial mediante `context_id`, señales `complete_for`/`do_not_expand`, expansión bilingüe de conceptos y un perfil MCP predeterminado que expone solamente esta tool. El catálogo completo permanece disponible con `--tool-profile full`.

Se repitieron las dos tareas críticas de la suite externa, con 12 hechos totales:

| Variante (mismas 2 tareas) | Calidad | Tokens/tarea | Tiempo/tarea | Llamadas/tarea |
|---|---:|---:|---:|---:|
| **Graphtyn v8 · perfil `intent`** | **100.00%** | **8,574** | **50.53 s** | **1.50** |
| Gra…ify 0.9.48 | 54.17% | 15,663 | 156.32 s | 23.00 |
| Lectura directa | **100.00%** | 23,218 | 149.24 s | 20.00 |

V8 mantuvo la calidad del baseline con **63.07% menos tokens**, 66.14% menos tiempo y 92.50% menos llamadas. Frente a Gra…ify obtuvo +45.83 puntos, 45.26% menos tokens y 93.48% menos llamadas. Frente al intento con `graph_query_intent` pero catálogo completo, redujo tokens 67.09% y llamadas 82.35%, demostrando que el costo dominante era la estrategia multiherramienta, no el payload individual. Resultados por tarea: borrado/eventos 100%, 7,290 tokens y una llamada; bindings 100%, 9,858 tokens y dos llamadas. Artefactos: `benchmarks/cleanarchitecture_x_preview_f_free_intent_v2_2026-08-22/`.

## 🔁 Reproducción

```bash
# 1. Pasada determinista
time graphtyn reindex --path /ruta/proyecto --engine ast_pure

# 2. Enriquecimiento local (requiere Ollama con qwen2.5-coder:3b)
OLLAMA_MODEL=qwen2.5-coder:3b time graphtyn reindex --path /ruta/proyecto --engine ast_local_llm

# 3. Incremental (segunda corrida, sin cambios)
OLLAMA_MODEL=qwen2.5-coder:3b time graphtyn reindex --path /ruta/proyecto --engine ast_local_llm

# 4. Payloads MCP
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"graph_neighborhood","arguments":{"symbol":"NombreSimbolo","depth":2}}}' | graphtyn mcp --path /ruta/proyecto
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
## Validación externa Python/ASGI: Starlette (2026-08-22)

Se repitió el protocolo competitivo en un segundo repositorio y ecosistema: `encode/starlette`, revisión fija `398e5a3430eb1ddd33e1d48d766efe41426e231f`. Se usaron cuatro tareas auditables (pila ASGI, dispatch del router, sesiones firmadas y CORS), seis hechos atómicos por tarea y `opencode/x-preview-f-free`. OpenCode solo pudo leer el repositorio; los tratamientos MCP tuvieron deshabilitadas lectura, grep, glob y shell.

| Variante | Calidad (24 hechos) | Tokens/tarea | Segundos/tarea | Llamadas/tarea |
|---|---:|---:|---:|---:|
| **Graphtyn intent v2** | **95.84%** | **10,183** | **81.65** | **1.75** |
| OpenCode directo | 93.75% | 21,741 | 153.00 | 9.50 |
| Gra…ify 0.9.48 | 62.50% | 21,880 | 228.98 | 26.75 |

Graphtyn redujo 53.16% de tokens y 81.58% de llamadas frente a lectura directa, con +2.09 puntos de calidad. Frente a Gra…ify redujo 53.46% de tokens y 93.46% de llamadas, con +33.34 puntos de calidad. Los tres resultados finales completaron 4/4 tareas y no activaron afirmaciones prohibidas.

La primera corrida de Graphtyn obtuvo 50% y expuso dos defectos que el benchmark C# no detectaba: un nodo sintáctico Python vacío causaba `IndexError`, y los componentes nombrados exactamente podían quedar desplazados por métodos genéricos con muchas operaciones. Se corrigieron ambos, se agregaron regresiones automatizadas y se repitió Graphtyn. Los artefactos iniciales y finales se conservan; los fallos transitorios de finalización/SQLite de OpenCode se reintentaron por tarea, sin repetir resultados exitosos de Gra…ify.

Artefactos: `benchmarks/starlette_agent_tasks.json`, `benchmarks/starlette_x_preview_f_free_2026-08-22/` y `benchmarks/starlette_x_preview_f_free_intent_v2_2026-08-22/summary.json`.
## Diagnóstico corporativo Laravel/React: ZERP (2026-08-22)

Repositorio `zerp-pk/zerp`, revisión `7e12392a3882682018cd86071d4d51ac7f142076`: Laravel 12, PHP, Blade/HTML, CSS/Tailwind, JavaScript, React 18, TypeScript e Inertia. Se evaluaron bootstrap web y tres flujos ERP con 24 hechos por variante.

| Variante | Calidad bruta | Tokens/tarea | Segundos/tarea | Llamadas/tarea | Completadas |
|---|---:|---:|---:|---:|---:|
| Graphtyn | 8.33% | 6,004 | 222.41 | 1.75 | 3/4 |
| Gra…ify | 22.92% | 32,460 | 206.67 | 30.25 | 4/4 |
| OpenCode directo | 64.59% | 34,644 | 263.28 | 31.75 | 3/4 |

Este resultado **no demuestra ahorro útil de Graphtyn**: el contexto fue barato porque faltó evidencia. Excluyendo la tarea bootstrap que falló en Graphtyn y baseline, las tres tareas empresariales puntuaron 11.11%, 30.55% y 86.11%, respectivamente. El diagnóstico originó `treesitter-v9-laravel`: Tree-sitter PHP y resolución de rutas→controladores→FormRequests→modelos/eventos, además de enlaces Inertia entre nombres de ruta y llamadas TSX. Estas cifras se conservan como baseline previo al arreglo y requieren una nueva corrida para medir el resultado posterior.

Artefactos: `benchmarks/zerp_agent_tasks.json` y `benchmarks/zerp_x_preview_f_free_2026-08-22/`.

### Resultado posterior: `treesitter-v9-laravel`

La implementación posterior indexó 572 archivos con Tree-sitter y extrajo relaciones Laravel/Inertia deterministas: rutas resource y explícitas, dispatch a controller, FormRequests, creación de modelos, dispatch de eventos y llamadas `route(...)` desde TS/TSX. En ZERP produjo 249 rutas, 233 dispatches a controller, 369 invocaciones Inertia, 31 enlaces de validación, 98 creaciones de modelo y 41 eventos despachados.

La tarea evaluable `purchase-return-lifecycle` subió de **8.33% a 83.33%**, usando 7,968 tokens y una llamada MCP. Las otras dos corridas posteriores no son puntuables: `x-preview-f-free` cerró una sin respuesta final y devolvió sólo un encabezado en otra. No se publica un promedio post-fix sesgado; se conservan artefactos crudos en `benchmarks/zerp_x_preview_f_free_laravel_v9_2026-08-22/`.

Una regresión posterior de recuperación entre capas corrigió el hecho faltante de esa tarea: las aristas `invoca ruta` que parten de un archivo TSX ahora se proyectan al símbolo React que contiene la línea exacta, priorizando callers frontend antes de expandir rutas backend. La evidencia de precisión se centra en la línea de la arista, no al inicio del componente. Sobre la misma revisión de ZERP, el paquete determinista conserva 11 nodos y 22 enlaces y aporta 3 fragmentos/3,850 caracteres que contienen las condiciones UI `draft`/`approved`, ambos permisos y ambas llamadas `router.post`. Esto demuestra cobertura de los seis hechos requeridos en el contexto; no se publica como nueva puntuación del agente hasta repetir la celda completa con el mismo modelo.

## Validación externa Go: go-chi (2026-08-22)

Repositorio `go-chi/chi`, revisión fija `735ae2b87f8c733d616e809ae86e0985c1bc3350`.
Se probaron cuatro flujos internos con 24 hechos atómicos: ciclo de petición,
orden de middleware, seguridad del contexto y manejo de panic/timeout. Las tres
variantes usaron `opencode/x-preview-f-free`; los tratamientos MCP no tuvieron
acceso a lectura, grep, glob ni shell.

| Variante | Calidad ajustada | Tokens/tarea | Segundos/tarea | Llamadas/tarea |
|---|---:|---:|---:|---:|
| OpenCode directo | **95.84%** | 16,491 | 145.30 | 10.25 |
| Gra…ify 0.9.48 | 31.25% | 15,123 | 107.01 | 14.50 |
| **Graphtyn** | 72.92% | **10,515** | **95.82** | **1.25** |

Graphtyn redujo tokens 36.24% y tiempo 34.05% frente a lectura directa, pero
perdió 22.92 puntos de calidad. Frente a Gra…ify redujo tokens 30.47%, ganó
41.67 puntos de calidad y evitó el único error factual detectado. No hay una
conclusión de significancia todavía: una repetición de cuatro pares produce
`p=0.125` en la prueba de signos. El informe auditable, respuestas crudas,
calificaciones y comparaciones pareadas están en
`benchmarks/go_chi_x_preview_f_free_2026-08-22/`.

### Regresión híbrida dirigida

Al añadir fragmentos acotados para preguntas de orden, condiciones y ciclo de
vida, Graphtyn subió de 72.92% a **85.42%**, bajó de 10,515 a **8,624 tokens por
tarea** y de 95.82 a **71.50 segundos por tarea** en una nueva repetición de sus
cuatro celdas. Dos tareas alcanzaron 100%; no hubo errores ni reintentos. El hueco
restante reveló una colisión entre métodos Go homónimos que también quedó
corregida y cubierta por pruebas, sin adjudicarle una cifra remota todavía.
Artefactos: `benchmarks/go_chi_x_preview_f_free_hybrid_v2_2026-08-22/`.

## Antigravity / Gemini 3.7 Flash: Starlette y go-chi (2026-08-25)

Se ejecutó una matriz real de cuatro tareas y tres tratamientos con
`gemini-3.7-flash-high`: lectura directa, Gra…ify 0.9.49 y Graphtyn. La corrida
original obtuvo respectivamente 100.00%, 78.75% y 56.25% de calidad, con 137,742,
107,192 y 60,317 tokens medios. Los fallos de selección hallados en Graphtyn se
corrigieron; una repetición dirigida de esas dos celdas, combinada con las dos
celdas ya correctas, alcanzó 100.00% y 41,306 tokens medios. Esta última cifra es
una regresión posterior, no una matriz completa nueva ni evidencia estadística.

El informe, protocolo, commits, resultados crudos, costes y validación de memoria
OpenClaw están en
`benchmarks/antigravity_gemini37_real_2026-08-25/REPORT.md`.

## Bootstrap de memoria histórica multiagente (2026-08-25)

Los adaptadores se ejecutaron en modo lectura contra historiales reales, sin
publicar ni importar contenido: OpenClaw/Career produjo 57 sesiones y 1,328
mensajes desde 57 JSONL útiles en 1.23 s vía SSH; otros 57 archivos de trayectoria
se excluyeron. Hermes/Nexus produjo 9 sesiones y 261 mensajes desde su
SQLite real. Los contratos sintéticos cubren JSON/JSONL anidado, SQLite,
atribución, fechas, alias de proyectos, bloqueo de mezcla entre proyectos,
reimportación idempotente, búsqueda posterior y contexto federado. La suite sin
el módulo API bloqueado obtuvo 196 passed y 3 skipped.

Artefacto: `benchmarks/shared_memory_bootstrap_2026-08-25.json`. Esto valida
compatibilidad estructural, no calidad semántica de todo el historial: la
importación real requiere consentimiento y después debe medirse sobre preguntas
privadas elegidas por el usuario.
