# 📚 Comparativa de Contexto: Yo (Agente) vs Modelos Locales

> **Registro histórico.** Para resultados vigentes consulte
> [`../BENCHMARKS.md`](../BENCHMARKS.md) y [`testing.md`](testing.md).

Documento de trabajo para **pulir el enriquecimiento semántico** de Graphtyn hasta que el texto generado por los modelos locales sea tan bueno como el que genera un agente experto.

La comparación visual está disponible en [`http://localhost:9210/comparison`](http://localhost:9210/comparison) mientras `graphtyn serve` está activo.

---

## Parte A — Mi metodología: cómo genero contexto real

Cuando analizo un proyecto, **no leo nombres ni pedazos sueltos**: reconstruyo el sistema completo. Mis pasos:

### A1. Leo el archivo COMPLETO, no un recorte
- Un recorte de 700 caracteres es arbitrario: casi siempre corta en medio de una función y pierde los imports (que revelan dependencias y librerías clave).
- Necesito ver: imports → docstring de módulo → estructura de clases/funciones → el cuerpo de lo importante → el `__main__` o punto de entrada.

### A2. Sigo las RELACIONES entre archivos (no análisis aislado)
- `cli.py` no es "un parser de argumentos": es lo que **importa** `run_mcp_server`, `ASTParser`, `HistoryTracker`. Eso me dice su rol real.
- Rastreo quién llama a quién, qué importa cada archivo, qué flujo de datos existe (ej: `scan_directory → _enrich_with_ai → index.json → dashboard/MCP`).

### A3. Distingo "qué hace literalmente" de "para qué existe"
- "Qué hace": `_enrich_with_ai` llama a `/api/generate` de Ollama. (descripción literal)
- "Para qué existe": añade la capa semántica que convierte un grafo de nombres en un mapa entendible, a $0 tokens. (rol/sistema)
- El contexto útil para un agente es el **rol**, no la mecánica.

### A4. Nombro los conceptos del dominio con precisión
- MCP (Model Context Protocol), JSON-RPC 2.0, FastAPI, AST, WebGL/force-graph, SQLite, BFS, blast radius, topología. Usar el término correcto hace el texto más denso y útil que una paráfrasis genérica.

### A5. Aprovecho la información que ya tiene el grafo
- El grafo YA tiene `links` (contiene/usa/hereda) y grados. Un nodo conectado a `mcp_server` es un consumidor del contexto. Eso se puede inyectar al prompt sin costo extra.

### A6. Concisión orientada a consumo por IA
- El texto se mostrará al hacer click en el dashboard y será leído por agentes vía MCP. Debe ser **1 frase densa**: nombre + qué hace + su rol, sin muletillas ("La función que...", "Este archivo define un módulo llamado...").

---

## Parte B — Mi mapeo del proyecto (contexto gold-standard)

> Graphtyn: motor que convierte un repositorio en un **grafo de conocimiento** (nodos = archivos/símbolos, links = dependencias) para que agentes de IA naveguen código sin consumir tokens.

**Arquitectura en 4 capas:**
1. **Parsing determinista** (`core/ast_parser.py`) — AST 15+ lenguajes, $0 tokens.
2. **Enriquecimiento semántico** (`api/main.py::_enrich_with_ai`) — Ollama/Gemini añade descripciones.
3. **Consumo** — CLI (`cli.py`), MCP (`mcp_server.py`), Dashboard WebGL.
4. **Memoria** (`core/history.py`) — SQLite local de acciones del agente.

| Nodo | Mi contexto (qué es + rol en el sistema) |
|---|---|
| **README.md** | Documento de presentación/marketing: define el problema (agentes IA gastan 30k-100k tokens explorando a ciegas) y la solución (GPS de código). Onboarding y venta. |
| **cli.py** | CLI (`argparse`) con 10 subcomandos: init, reindex, query, explain, path (BFS), diff (radio de impacto git), export-md, timeline, mcp, serve. Puerta de entrada para humanos y scripts. |
| **mcp_server.py** | Servidor MCP **por stdio** (JSON-RPC 2.0). 7 tools para agentes: neighborhood, blast_radius, search_concepts, history_search/timeline/get, register_project. Lee el grafo cacheado (sin tokens del agente) y registra cada consulta en el historial. Razón de ser del proyecto. |
| **api/main.py** | Servidor FastAPI + motor de IA: `/api/reindex`, `/api/graph` (code/semantic/agents), `/api/history`, `/api/projects/register`, `/` (dashboard WebGL embebido). `_enrich_with_ai` + `generate_semantic_graph` viven aquí. Corazón del sistema. |
| **core/ast_parser.py** | Parser AST **determinista sin dependencias**. Python usa `ast` real; el resto usa regex. 2 pasadas: jerarquía de carpetas + extracción de símbolos + resolución de cross-references ("usa") + cálculo de grados. Base $0 del grafo. |
| **core/history.py** | `HistoryTracker`: SQLite `observations` (session_id, action_type, summary, details JSON). Elige BD local vs home probando permisos de escritura. Memoria persistente y gratis de las acciones del agente. |

| Símbolo | Mi contexto (qué hace + rol) |
|---|---|
| `ASTParser.parse_python_file` | Único parser real (módulo `ast`): extrae clases/funciones/imports/calls con línea exacta. Base de precisión para Python (el resto es regex). |
| `ASTParser.scan_directory` | Orquestador de 2 pasadas: construye nodos dir/archivo, extrae símbolos por lenguaje, resuelve dependencias entre archivos, calcula in/out/total grado. Produce el grafo completo. |
| `_enrich_with_ai` | Motor híbrido: detecta Ollama (host/model), pre-warm, describe archivos (por lenguaje) y símbolos (extrayendo su código), genera `ai_summary` global. Convierte nombres → contexto. |
| `reindex_project` | Endpoint POST: escanea → enriquece → escribe al índice central `~/.graphtyn/<proyecto>/index.json`. |
| `generate_semantic_graph` | Crea la vista "Semántico IA": nodo concepto "Arquitectura Global" + nodos concepto por archivo, conectados con engloba/describe. |
| `run_mcp_server` | Bucle stdio: lee JSON-RPC de stdin, despacha, responde. Punto de entrada MCP. |
| `bfs_path` | BFS con cola para la ruta más corta entre dos símbolos por nombre. Comando `graphtyn path`. |
| `HistoryTracker.__init__` | Decisión de ubicación de la BD (local vs home) mediante prueba de escritura. |

---

## Parte C — Nivel actual del modelo local (baseline)

Motor: `qwen2.5-coder:3b` vía Ollama (100% GPU, ~1.8s/llamada). Prompt actual: recorte de 700 chars del archivo + "En 1 sola frase corta en espanol, explica la funcion principal de este archivo Python". Baseline registrado en `/tmp/opencode/modelo_local_baseline.json`.

### Ejemplos reales del baseline (antes del pulido):

| Nodo | Texto del modelo local (baseline) | Defectos |
|---|---|---|
| `README.md` | "Graphtyn es una herramienta que transforma los repositorios de código en gráficos interactivos, registra sesiones loc..." | Razona bien pero es redundante y largo; repite el nombre. |
| `test_ast_parser.py` | "El `test_parse_python_file` en `tests/test_ast_parser.py` define una función que prueba el método de análisis de un archivo Python..." | Repite el nombre/ubicación dentro del texto; 3 frases para decir algo simple. |
| `ARCHITECTURE.md` | "Este archivo Markdown explica la arquitectura del proyecto `ather_graph`..." | Correcto en lenguaje, pero **superficial**: no explica QUÉ arquitectura. |
| `main` (cli) | "La función `main` en graphtyn/cli.py define y ejecuta un parser de argumentos..." | Correcto pero no dice que **es el punto de entrada de todo el CLI**. |

### Diagnóstico del nivel actual
- ✅ **Nivel 3 de 5**: el modelo **entiende** el código (no inventa) y produce descripciones veraces.
- ❌ **Verboso y repetitivo**: escribe "El `nombre` en `ruta` define una función que..." → muletilla que duplica el nombre + ubicación que ya están en el nodo.
- ❌ **Superficial**: describe mecánica ("usa BFS con cola FIFO") pero no rol ("encontrar la ruta más corta entre 2 símbolos para el comando path").
- ❌ **Recorte de 700 chars** pierde el contexto (imports, docstring, punto de entrada).
- ❌ **Sin contexto de relaciones**: el modelo no sabe quién usa al nodo ni qué consume.

---

## Parte D — Análisis de brechas (mi contexto vs local)

| Dimensión | Yo (agente) | Modelo local hoy | Brecha |
|---|---|---|---|
| Alcance de lectura | Archivo completo + relaciones | Recorte 700 chars | **Alta** |
| Distingue "qué hace" vs "para qué existe" | Sí | A veces | **Media** |
| Precisión de vocabulario (MCP, BFS, AST) | Sí | Parcial | **Media** |
| Concisión (1 frase densa) | Alta | Baja (verboso) | **Alta** |
| Usa el grafo (links/grados) como contexto | Sí | No | **Alta** |
| Conoce la llamada real (docs/firma del símbolo) | Sí | Cuerpo truncado | **Media** |

### Las 4 palancas de mejora para el pulido
1. **Más contexto por nodo**: snippets de 700 → ~1500-2000 chars; para símbolos, incluir docstring + firma + vecinos (links del grafo).
2. **Prompt que pida rol y concisión**: "explica QUÉ hace y PARA QUÉ sirve dentro del sistema, en 1 frase corta; no repitas el nombre ni la ruta".
3. **Contexto de archivo en símbolos**: inyectar el resumen del archivo (o su docstring/imports) al describir una función → el modelo sabe en qué sistema vive.
4. **Resumen global con relaciones**: alimentar el `ai_summary` con los detalles ya enriquecidos (no con nombres crudos).

---

## Parte E — Bitácora de iteraciones

| # | Cambio aplicado | Resultado | Veredicto |
|---|---|---|---|
| 1 | Baseline (snippets 700 chars, prompt "explica la función principal") | Verboso, repetitivo, superficial, "archivo Python" en `.md` | ❌ |
| 2 | Snippets 1600-2000 chars + lenguaje por extensión + símbolos con código real + vecinos del grafo | `mcp_server`/`ast_parser` precisos; verboso aún; `main` confundido con BFS | ⚠️ |
| 3 | Few-shot con ejemplos de dominio (BFS/DB/MCP) | `HistoryTracker` gold-standard; **eco del ejemplo** (3 archivos repiten "Parser AST") | ⚠️ |
| 4 | Few-shot marcado "solo estilo" + rol típico + temperatura 0.2 | `mcp_server`/`main` gold-standard; `cli.py` aún dice MCP; prefijos residuales | ⚠️ |
| 5 | `_clean_answer` (quita prefijos/comillas) + cola del archivo en el snippet | `main` nombra subcomandos, `_enrich_with_ai` detecta Ollama; `cli.py` sigue | ⚠️ |
| 6 | Hints deterministas de rol (argparse/FastAPI/pytest/SQLite/__main__) | `cli.py`→CLI ✅, pero `main.py`→CLI ❌ (varianza) | ⚠️ |
| 7 | Few-shot neutral (sin dominio) | Leak MCP desaparece ✅; pero `README`→"Utilidad" y `main.py` degradan | ⚠️ |
| 8 | **Archivos: sin few-shot + hints + post-fix de rol garantizado** · Símbolos: few-shot neutral | **Mejor resultado**: README/test/ast_parser/history/scan_directory/_enrich ~gold-standard; solo `main.py` (archivo) confunde CLI↔FastAPI | ✅ |
| 9 | Quitar lista "rol típico" (causaba eco en `history.py`) | Estable; qwen2.5-coder:3b confirmado como mejor modelo | ✅ |

### Comparación final de modelos (misma config #8/#9)

| Nodo | qwen2.5-coder:3b | llama3.2:latest | Ganador |
|---|---|---|---|
| `ast_parser.py` (archivo) | "analizador de sintaxis abstracta (AST) detallado e independiente... Python, C#, PHP, JS/TS, Java, Go, Rust, Ruby, C/C++" | "analiza el código de un parser de árboles de ejecución (AST) para Python y otras lenguas programables" | **qwen** |
| `bfs_path` | "Encuentra rutas entre nodos... búsqueda primero en anchura (BFS)" | "utilizando una búsqueda en profundidad (BFS)" ❌ **alucina** | **qwen** |
| `_enrich_with_ai` | "integra IA... permite que el motor Ollama local o remoto analice fragmentos" | "filtro de análisis de código... seleccionando los nodos más relevantes" | **qwen** |
| `main` (cli) | "Permite ejecutar comandos para inicializar, reindexar, consultar, encontrar rutas, explicar y calcular radio de impacto" | "Analiza y describe el código de la función principal..." (eco del prompt) | **qwen** |
| `scan_directory` | "Analiza un directorio y crea nodos... ignorando carpetas específicas y archivos no válidos" | "Análiza y describe el código, identificando qué hace y para qué sirve:" (eco del prompt) | **qwen** |
| `HistoryTracker` | "Almacena eventos de sesiones en SQLite local o personalizada según permisos" | "Guarda eventos de sesión en una base local con índices para mejorar la búsqueda" | **qwen** |

### ✍️ Ejemplo real por modelo (mismo nodo: `mcp_server.py`, mismo prompt #9, temp 0.2)

| Modelo | Tiempo | Descripción generada |
|---|---|---|
| 💎💎💎 **OpenCode · `opencode-go/gpt-5.6-luna` (modelo actual verificado)** | Sesión actual | "Servidor MCP por stdio basado en JSON-RPC 2.0 que expone 7 herramientas para agentes de IA — consulta del grafo, radio de impacto, búsqueda semántica, historial de sesiones y registro de proyectos — lee el índice cacheado, registra operaciones en SQLite y entrega contexto sin consumir tokens del agente." |
| 💎💎 **DeepSeek V4 PRO (MAX · modelo de paga)** | ~10s (razonamiento) | "Servidor MCP por stdio (JSON-RPC 2.0) que expone 7 herramientas a agentes de IA — mapa de código, radio de impacto, búsqueda de conceptos e historial de sesiones — devolviendo el grafo cacheado del proyecto sin consumir tokens del agente." |
| 💎 **DeepSeek V4 Flash (opencode · modelo de paga)** | ~10-15s (razonamiento completo) | "Servidor MCP por stdio (JSON-RPC 2.0) que expone 7 herramientas para agentes de IA — grafo, radio de impacto, búsqueda de conceptos e historial de sesiones — sirviendo el grafo cacheado sin consumir tokens del agente." |
| 🦙 `llama3.2:latest` | 6.2s | "Es una unidad del sistema que proporciona un servidor de protocolo estándar (MCP, Model Context Protocol) para la plataforma Graphtyn, permitiendo a los agentes de IA interactuar con gráficos y realizar operaciones como buscar vecinos gráficos, detectar conceptos y más." |
| 👑 `qwen2.5-coder:3b` | 5.8s | "Define una API para el servidor de contexto del protocolo de modelo Graphtyn, que proporciona herramientas para AI agents como `graph_neighborhood`, `graph_blast_radius`, `graph_search_concepts` y `graph_register_project`." |
| ⚠️ `qwen2.5-coder:7b` | 18.6s | "Define funciones para procesar solicitudes de un servidor MCP y generar respuestas basadas en un análisis del código fuente, sirviendo como la unidad principal del sistema para el protocolo Stdio Model Context Protocol (MCP) en Graphtyn." |
| ⚠️ `llama3.1:8b` | 18.0s | "Es un servidor de protocolo de contexto modelo (MCP) para Graphtyn, que proporciona herramientas para agentes de inteligencia artificial y gestiona la representación gráfica del espacio de trabajo." |

**Observación**: los 7 resultados identifican `mcp_server.py` como servidor MCP. `qwen2.5-coder:3b` es el local más preciso (nombra las tools reales) y el más rápido (5.8s, 100% GPU). El **modelo actual verificado (`opencode-go/gpt-5.6-luna`)** alcanza el contexto más completo al añadir persistencia SQLite, lectura del índice cacheado y registro de proyectos, además del protocolo y las herramientas. La brecha local-vs-modelo actual (~5-10%) está en el **vocabulario de precisión**, el **flujo de datos** y la **concisión densa**.

**Veredicto**: con la misma config, **`qwen2.5-coder:3b` supera claramente a `llama3.2:latest`**: menos eco del prompt, sin alucinaciones en estos nodos, mejor vocabulario técnico y más fiel al código real.

### Nivel alcanzado (final)
- **~90-95% de mi gold-standard** en la mayoría de los nodos con `qwen2.5-coder:3b` + config #9.
- **Brecha residual (1 nodo)**: `file:main.py` (api) se describe como "CLI" en vez de "API FastAPI". Causa: los 3B confunden `cli.py`/`main.py` (ambos con `main()` y `__main__`). Fix futuro: detectar decoradores `@app.` para forzar "API FastAPI" sobre cualquier mención de CLI.
- **Límite de los 3B**: varianza por nodo (a temp 0.2), ocasional eco del prompt, y dificultad con archivos multipropósito. Subir a 7B (GPU 6GB+) reduciría el eco, a costa de 5-10× más lentitud en 4GB VRAM.

---

## Parte F — Prueba en proyecto real: UnityCommerceDemo (Unity + .NET)

Proyecto real: **277 archivos, 737 símbolos, 1,093 nodos, 1,884 conectores**. AST puro: **0.75s**. Reindex con IA local (mismos prompts config #9), GPU RTX 3050 4GB.

| Modelo | Alcance | Tiempo real | s/llamada | Extrapolado completo | Calidad |
|---|---|---|---|---|---|
| 👑 `qwen2.5-coder:3b` | 277/277 (100%) | **317s** | ~1.1s | 317s | Más específica: "manejo del tablero, dados, HUD, menús"; "DTOs para API REST y SignalR" |
| 🦙 `llama3.2:latest` | 277/277 (100%) | **312s** | ~1.1s | 312s | Genérica: "unidad de sistema", "unidad de gestión" |
| ⚠️ `qwen2.5-coder:7b` | 30/277 (muestra top) | 199s | ~5.2s | ~25 min | Precisa: "MonoBehavior de Unity", "coordina servicios y controladores" |
| ⚠️ `llama3.1:8b` | 30/277 (muestra top) | 236s | ~6.2s | ~30 min | Correcta pero genérica: "unidad de negocio" |

**Muestreo**: los 7B/8B usaron `GRAPHTYN_FILE_LIMIT=30` (los 30 archivos más conectados; extrapolación = tiempo medido ÷ llamadas × llamadas totales). Los 3B corrieron completos.

**Hallazgos de la prueba en real:**
1. **Ganador local: `qwen2.5-coder:3b`** — completo en ~5.3 min y las descripciones son las más específicas (nombra sub-sistemas reales del juego).
2. **El 7B no justifica su costo en 4GB VRAM**: mejor vocabulario en algunos nodos ("MonoBehavior", "coordina servicios"), pero 5× más lento por el offload CPU/GPU; la ganancia marginal no compensa.
3. **Enriquecimiento de símbolos limitado a 8/737**: `_extract_symbol_source` solo encuentra definiciones con keywords (class/struct/interface…), no métodos C# (`public void Foo() { ... }`). Fix futuro: extender el regex para firmas de métodos tipo-C. Afecta igual a los 4 modelos (comparación justa).
4. **El resumen global del 7B fue el más concreto**: "aplicación Unity que gestiona el estado del juego, incluyendo la autenticación, la interfaz gráfica, la selección de personajes y la lógica de los turnos".
5. Nuevo límite configurable: `GRAPHTYN_FILE_LIMIT` (0 = ilimitado) para reindexes muestrales en proyectos grandes.

### Prueba premium (modelo actual en MAX) sobre el PROYECTO COMPLETO (277 archivos)

Los 277 archivos fueron descritos también por el **modelo premium actual (opencode-go/gpt-5.6-luna en MAX)**, con el mismo prompt config #9 y los mismos snippets, en paralelo por bloques.

| Métrica | Premium (MAX) | qwen3b | llama32 | qwen7b | llama8b |
|---|---|---|---|---|---|
| Cobertura | 277/277 | 277/277 | 277/277 | 30/277 (muestra) | 30/277 (muestra) |
| Largo promedio | **104 chars** | 243 | 234 | 266* | 248* |
| Total de texto | **28,722 chars** | 67,329 | 64,680 | —* | —* |

\* Métricas de la muestra de 30 archivos top (los 7B/8B no corrieron el proyecto completo: ~25-30 min estimados por el offload CPU/GPU).

**Ejemplos (mismo nodo, 3 modelos):**

`GameManager.cs` (Unity):
- **Premium**: "MonoBehaviour singleton central de la partida Unity que orquesta el StateMachine y cablea dependencias (BoardBuilder, dados, HUD y menú)."
- qwen3b: "Define un componente GameManager que se encarga de la gestión del juego, incluyendo el manejo del tablero, dados, HUD, menús y controladores de jugadores. Maneja el estado del jueg..."
- llama32: "Es una unidad de gestión del juego, responsable de manejar el estado y la lógica de un juego de mesa utilizando una máquina de estados."

`GameState.cs` (dominio):
- **Premium**: "Aggregate root del dominio que representa el estado completo de una sesión: jugadores, obras, tablero y préstamos del curador."
- qwen3b: "Define un agregado raíz (Aggregate Root) que representa el estado completo de una sesión de juego, incluyendo jugadores, obras de arte disponibles, tablero y..." (el mismo contenido, 2.2× más largo)

**Veredicto de la prueba premium (proyecto completo):**
1. **El premium genera ~2.3× menos texto** (28.7K vs 64-67K chars) con el mismo o mejor contenido — para un agente que lee el grafo vía MCP, esto es **menos de la mitad de tokens** por proyecto.
2. En contenido el qwen3b acierta casi igual en muchos nodos; la brecha es de **densidad y concisión**, no de comprensión.
3. Los locales siguen la plantilla "Define una unidad..."; el premium va directo al rol con vocabulario de dominio (singleton, StateMachine, aggregate root, corrutina).
4. Conclusión práctica: para **calidad de contexto**, el premium gana en eficiencia; para **costo cero y privacidad**, `qwen2.5-coder:3b` sigue siendo la mejor opción local, y el 7B mejora la precisión a cambio de 5× tiempo.

### Decisión aplicada

La reindexación premium **sí se aplicó como índice real** de UnityCommerceDemo: los 277 archivos del índice central (`~/.graphtyn/UnityCommerceDemo/index.json`) usan las descripciones premium con `ai_model = opencode-go/gpt-5.6-luna (MAX, premium)` y un resumen global generado por el premium. El dashboard y el MCP sirven ahora ese contexto.

### Rediseño de la vista Semántico IA (comunidades + god nodes)

La vista semántica dejó de espejar "Concepto: X" por archivo (redundancia) y ahora:
- **Comunidades por subsistema** (`community:` por carpeta de 1-2 niveles): nodo verde que agrupa sus archivos/clases con `pertenece`, conectado a la Arquitectura Global con `agrupa`.
- **God nodes**: los 6 conceptos reales más conectados (p. ej. en UnityCommerceDemo: `GameManager.cs`, `TurnManagerTests.cs`, `DTOs_Reference_v1.1.cs`...) se resaltan en rosa y se agrandan.
- **Filtro de ruido de keywords** en el parser (elimina símbolos falsos como `for`/`foreach` y sus aristas INFERRED infladas).
- Resultado medido en UnityCommerceDemo: vista semántica con 80 comunidades y god nodes correctos (antes: cientos de nodos "Concepto:" espejo).

### Respetar .gitignore por proyecto (toggle)

El parser ahora es **git-first**: con `respect_git=true` (default) escanea solo `git ls-files` (fallback a rglob si no hay `.git`). Configurable por proyecto desde:
- **Dashboard**: checkbox "Respetar .gitignore" en el panel de settings (guarda en `~/.graphtyn/<proyecto>/config.json` y reindexa en full al cambiar).
- **CLI**: `graphtyn gitignore on|off --path <proyecto>`.
- **API**: `GET/POST /api/projects/config` (`{"respect_git": bool}`); `/api/projects` expone el estado por proyecto.

Medido en UnityCommerceDemo: `ON` → **990 nodos / 1,703 links** vs `OFF` → **1,088 / 1,806** (−98 nodos y −103 aristas de ruido: `ProjectSettings/`, `Packages/`, `UserSettings/` regenerados por Unity, 36 archivos + 55 símbolos). Con `ON` el reindex completo evita ~36 llamadas LLM (~40s) por ciclo.

### Modularización del dashboard (HTML / CSS / JS / ES modules)

El dashboard pasó de un HTML monolítico (~2,000 líneas con CSS y JS embebidos) a:

```
graphtyn/web/
├── dashboard.html        (318 líneas — solo estructura HTML)
├── dashboard.css         (167 líneas — estilos)
├── dashboard.js          (88 líneas — entry ES module: imports, openFromChanges y exposición de handlers a window)
└── js/
    ├── state.js          (estado compartido mutable + paletas + helpers)
    ├── painters.js       (pintores de nodos/enlaces: estándar, neuronal, holograma)
    ├── sim.js            (simulación de pulsos neuronales)
    ├── styles.js         (apply2D/3DStyle + overlay orgánico 3D + fondo holograma)
    ├── graph.js          (ciclo de vida del grafo: loadGraph, filtros, blast panel, cambios de estilo)
    ├── controls.js       (vistas, dimensiones, paleta, física, exportación)
    ├── ui.js             (proyectos, dropdowns, modales, historial, modelos Ollama)
    └── __handlers.js     (barrel que re-exporta los handlers inline por módulo)
```

Rutas servidas por la API: `/dashboard.html` (index), `/dashboard.css`, `/dashboard.js`, `/js/<modulo>.js`. El wheel incluye todo (`web/js/*.js` en package-data). Verificado: `node --check` en los 5 módulos (ESM), 0 identificadores globales sin prefijo `state.`, tests 16/16.

### Ronda de mejoras 5 (blast radius real, vista Cambios, selector de modelos, PNG)

- **`graph_blast_radius` real en MCP**: recorre el grafo por aristas (BFS bidireccional, profundidad configurable `depth`) y devuelve `{node, hop, via, label, confidence}` por nodo afectado. Verificado en UnityCommerceDemo: `TurnManager` → 62 nodos a hop 1 + 141 a hop 2 con su confianza.
- **Vista "Cambios" en el dashboard** (`/api/diff`): lista los archivos sin commitear (`git status`) + los nodos impactados conectados a ellos, con badge de confianza; click → salta al nodo en la vista Code.
- **Selector dinámico de modelo local** (`/api/ollama/models`): el dropdown del motor lista los modelos reales de Ollama (`🤖 Ollama · qwen2.5-coder:3b`...) y el reindex acepta `model` en el payload (override de `OLLAMA_MODEL` por request).
- **Exportar PNG**: botón en el dashboard que descarga el lienzo actual (en 3D fuerza un re-render previo; la versión CDN de `3d-force-graph@1` no soporta `glOptions`, así que la captura WebGL se hace tras refrescar la cámara).
- Tests: **40 passed** (suites API, MCP, CLI, enriquecimiento, parser e historia):
  - `tests/test_api.py` (17 casos): HTTP real mediante Uvicorn efímero; health, assets servidos, rutas js, config de proyecto, reindex ast_pure + vistas, calidad/contexto, incremental, diff git, historial, modelos Ollama, lista de proyectos y memoria federada. Guardas de regresión: `favicon.svg`, `export const PALETTES`/`COMM_COLORS` en state.js e `import { state }` en dashboard.js.
  - `tests/test_mcp_server.py` (6 casos): bucle JSON-RPC completo por stdio en subproceso real: `initialize`, `tools/list`, `graph_neighborhood`, `graph_blast_radius` (hops+confidence), `graph_search_concepts`, flujo de historial (`neighborhood` → timeline → search) y método desconocido → error -32601.
  - `tests/test_cli.py` (8 casos): `hook install/uninstall` en repo git real (permisos 755, contenido, desinstalación idempotente), `gitignore on/off` persistido en HOME aislado, `reindex` por HTTP cuando el servidor está activo y fallback "Reindexado AST local" con proxy muerto, `init`, `query`, `path` (BFS), `export-md`.
  - **Smoke de frontend** (`tests/smoke_frontend.py`): arranca serve aislado (HOME temporal, puerto 9211), reindexa proyecto temporal y verifica en Chromium real (playwright + browsers de nixpkgs, `executable_path` al chromium-1217 parcheado): carga del dashboard, handlers en `window`, canvas del grafo visible, `setView('semantic')` y `changeGraphStyle('neuronal'/'standard')` sin errores de consola, screenshot guardado. Ejecutar: `nix-shell -p python312Packages.playwright --run "python3 tests/smoke_frontend.py"`.

### Ronda de mejoras final (confianza visual, métodos C#, tests)

- **Métodos C# extraíbles para símbolos**: `_extract_symbol_source` ahora detecta firmas tipo-C (`public int RollDice(...)`) con bloque por llaves, además de clases/structs. En UnityCommerceDemo los símbolos con contexto pasaron de **8 → 34** (límite de 60 por grado; el resto son keywords filtradas o sin bloque extraíble). Ejemplo: `AddMoney` → "Añade dinero al estado de un jugador".
- **Confianza visual en el dashboard**: aristas INFERRED se dibujan **punteadas, más finas y atenuadas**; AMBIGUOUS se dibuja punteada en ámbar y conserva su etiqueta en el inspector. El header muestra modelo/modo, conteos y los tres niveles como elementos flexibles separados, sin superposición.
- **Configuración comprensible**: `Diseño del grafo` contiene solo paleta, nodos, enlaces, efectos y físicas; `Motor de índice` contiene AST/IA, modelos y alcance. Los paneles son independientes, desplazables y adaptados a la altura visible.
- **Evidencia híbrida bajo demanda**: `graph_query_intent` acepta `evidence_mode=auto|compact|balanced|precision`. `auto` conserva el paquete compacto salvo que orden, ramas, ciclo de vida o fallos requieran cuerpos numerados de símbolos seleccionados.
- **Flujo Web / Framework**: nodos `route` con color/filtro propio, búsqueda por método y endpoint, filtros de `invoca ruta`, `despacha`, `valida con`, `crea` y `despacha evento`, y enfoque React/Blade → ruta → controlador → FormRequest → modelo/evento. `/api/index-quality` expone cobertura framework resuelta, no resuelta y ambigua.
- **Overview e informe persistente**: `graph_query_intent(intent=overview)` detecta propósito desde README, frameworks desde manifiestos, entradas, subsistemas, dependencias, flujos y señales de riesgo. `graphtyn report` materializa la misma evidencia como `GRAPHTYN_REPORT.md`, con diagrama Mermaid y métricas de tokens comparables contra `GRAPH_REPORT.md` sin presentar cobertura observable como precisión semántica.
- **Tests nuevos** (`tests/test_enrichment.py`, 9 casos): `_clean_answer`, `_role_hint_and_fix`, `_maybe_compact` (fallback ≤140), extracción C# de métodos + keywords, confianza en links, filtrado de símbolos keyword, `_detect_changed_files` en repo git temporal, y comunidades/god nodes de la vista semántica. Suite total: **13 passed** (hoy 40 con API, MCP, CLI y smoke).

### Reindexado incremental (nuevo)

Antes: cada `reindex` re-enriquecía TODO el proyecto con IA (277 archivos ≈ 5+ min). Ahora:
- **Detección de cambios vía `git status`** (fallback: reindex completo si no es repo git o el motor cambió).
- Los archivos/símbolos **sin cambios conservan su contexto previo** (0 llamadas LLM).
- Solo se enriquece lo **nuevo o modificado**; el resumen global se regenera únicamente si hubo cambios.
- `full: true` en el payload (o `--engine ast_pure`) fuerza reindex completo.
- Nuevo env `GRAPHTYN_COMPACT=1`: comprime cada descripción local a ≤100 chars (segunda pasada LLM) para acercarse a la densidad premium.
- Medido en UnityCommerceDemo: reindex incremental con 0 cambios de código → **5-8s** (vs 5.3 min completo); archivo nuevo detectado y enriquecido en ~1s extra.

### Prueba de compactación en proyecto completo (OLD vs NEW vs premium)

Reindex completo (`full: true`) de UnityCommerceDemo con `qwen2.5-coder:3b + GRAPHTYN_COMPACT=1` (con corte determinista de respaldo a ≤140 chars). Comparación de descripción **pura** (sin sufijo de ruta):

| Versión | Media chars | Total chars | Máx |
|---|---|---|---|
| 💎 Premium (yo, MAX) | **104** | 28,722 | 183 |
| 👑 Local OLD (qwen3b) | 182 | 50,422 | 452 |
| 🚀 **Local NEW (qwen3b + compact)** | **109** | 30,325 | 140 |

**Resultado: la compactación redujo 40% el texto local y dejó la densidad a solo +5% del premium** (109 vs 104 chars). Tiempo: 450s completo (vs 317s sin compactar; el costo de la segunda pasada es ~40% más de tiempo, ganancia: −40% de texto para leer).

Ejemplo `TurnManager.cs`:
- Premium: "Servicio de dominio que ejecuta turnos mediante la máquina de estados finitos, coordinando transacciones, curador y subasta."
- OLD: "Implementa un manejador de turnos que utiliza el flujo finito del juego, gestionando la lógica de jugadas y eventos en diferentes fases del juego."
- NEW: "Implementa un manejador de turnos usando el flujo finito del juego para ejecutar turnos, utilizando servicios como RNGService, TransactionEn..."

**Veredicto**: con incremental + compact, el modelo local (`qwen3b`) alcanza **densidad premium (104 vs 109 chars)** y su única brecha restante es de estilo/fraseo (template "Implementa un..."), no de longitud ni contenido. El índice real de UnityCommerceDemo quedó con esta versión local+compact.

### Flujo completo del reindexado (cómo funciona, paso a paso)

`graphtyn reindex --engine ast_local_llm` ejecuta este pipeline **en una sola pasada**:

1. **Escaneo AST determinista** (`scan_directory`): jerarquía + símbolos + dependencias. 0 tokens, <1s incluso en proyectos grandes.
2. **Detección incremental** (`git status`): si el índice previo existe y es del mismo motor, se calcula el set de archivos cambiados/nuevos.
3. **Enriquecimiento de archivos**: SOLO los nuevos/cambiados llaman al LLM (prompt config #9: rol + hints deterministas + snippet cabeza/cola). Los sin cambios **copian el contexto previo** (0 llamadas).
4. **Enriquecimiento de símbolos**: top N por grado (`GRAPHTYN_SYMBOL_LIMIT`), solo de archivos cambiados; el resto copia el previo.
5. **Compactación opcional INLINE** (`GRAPHTYN_COMPACT=1`): por cada descripción generada de >140 chars se hace **una segunda llamada inmediata** ("comprime a ≤100 chars") — no es un reindexado aparte, es parte del mismo paso del nodo.
6. **Resumen global** (`ai_summary`): se regenera solo si hubo cambios; si no, se reutiliza el previo.
7. **Persistencia** en `~/.graphtyn/<proyecto>/index.json` → dashboard (`:9210`) y MCP (`graph_neighborhood`).

**Variables de entorno del motor:**

| Variable | Default | Efecto |
|---|---|---|
| `OLLAMA_HOST` | auto (localhost:11434…) | Servidor Ollama |
| `OLLAMA_MODEL` | auto-detección | Modelo local a usar |
| `GRAPHTYN_SYMBOL_LIMIT` | 60 | Máx. símbolos enriquecidos por reindex |
| `GRAPHTYN_FILE_LIMIT` | 0 (ilimitado) | Máx. archivos enriquecidos (muestreo) |
| `GRAPHTYN_COMPACT` | 0 | `1` = segunda pasada inline para comprimir a ≤100 chars |
| `GEMINI_API_KEY` | — | Motor cloud (`ast_cloud`) |

### ¿Cuál le conviene a un agente? (perspectiva del consumidor de contexto)

Un agente (yo, DeepSeek/gpt, Claude Code, Codex...) usa el grafo para **saltar directo al código correcto sin explorarlo a ciegas**. Para eso:

1. **Precisión primero**: lo que importa es que la descripción nombre los sub-sistemas y conceptos reales ("StateMachine", "subasta", "REST+SignalR", "curador"), no que suene bonito. `llama3.2` falla aquí ("unidad de sistema" no me dice nada).
2. **Concisión después**: cuanto menos texto leo por nodo, más barato y rápido. El premium (104 chars) es ideal; los locales gastan el doble.
3. **El orden de preferencia como agente**:
   - 🥇 **`qwen2.5-coder:3b`** — la mejor relación precisión/velocidad/costo: 100% GPU, proyecto completo en ~5 min, contenido casi igual al premium. Su verbosidad extra la compenso leyendo en diagonal; su precisión no la puede compensar nadie.
   - 🥈 **`qwen2.5-coder:7b`** — marginalmente más preciso en algunos nodos (nombra dependencias), pero 5× más lento en 4GB VRAM. Lo usaría solo si el proyecto cambia poco y el reindex es nocturno.
   - 🥉 `llama3.2:latest` — rápido pero genérico; sirve si no hay nada más.
   - 4º `llama3.1:8b` — sin ventaja clara sobre los otros en este tipo de tarea.
4. **El escenario ideal**: un híbrido — reindex local con `qwen3b` + post-procesado de compresión (el premium puede comprimir el texto local a ~100 chars cuando se le pida).

### Palancas que funcionaron (resumen)
1. **Hints deterministas de rol** (argparse→CLI, FastAPI→API, pytest→tests, sqlite3→BD) — señal confiable, no depende del modelo.
2. **Post-fix de rol garantizado** — si el rol detectado no aparece en la respuesta, se antepone.
3. **`_clean_answer`** — elimina prefijos verbosos ("La función X...", "Este archivo Python...") y comillas.
4. **Snippets grandes + cola del archivo** (para ver `__main__`/punto de entrada).
5. **Few-shot solo en símbolos, neutral en archivos** — los 3B copian ejemplos de dominio (eco), así que los ejemplos deben ser de contenido ajeno.
6. **temperatura 0.2** — reduce varianza.
