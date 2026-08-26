# 🌌 Graphtyn

[![PyPI Version](https://img.shields.io/badge/pypi-v0.6.0-blue.svg)](https://pypi.org/project/graphtyn/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Compatible](https://img.shields.io/badge/MCP-Standard--Compatible-10b981.svg)](https://modelcontextprotocol.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab.svg)](https://www.python.org/)

**El motor de mapa topológico de código, registro de sesiones local y servidor MCP estándar para Agentes de IA (Google Antigravity, Claude Code, Codex, Cursor y Windsurf).**

> **Estado:** desarrollo activo `0.5.x`. El grafo, MCP, dashboard y memoria
> multiagente están implementados; la matriz competitiva de 108 celdas sigue
> pendiente. No se afirma superioridad general a partir de pruebas parciales.

**Navegación:** [arquitectura](ARCHITECTURE.md) ·
[memoria compartida](docs/shared-memory.md) · [pruebas](docs/testing.md) ·
[benchmarks](BENCHMARKS.md) · [mercado](docs/market-study.md) ·
[documentación completa](docs/index.md)

Graphtyn convierte cualquier repositorio de código en un **grafo de conocimiento determinista de 2 pasadas**: analiza la estructura de archivos, módulos, clases, métodos y llamadas con **0 tokens de consumo** en menos de 0.5 segundos (medido) y enriquece semánticamente los nodos principales mediante **IA Local (Ollama Qwen2.5)** o **Cloud APIs (Gemini/Claude)**.

---

## 🎯 Propósito y Valor del Proyecto

Cuando un agente de IA explora un proyecto grande sin un mapa de código, recurre a búsquedas masivas a ciegas (`grep` o lectura completa de archivos). Esto provoca:
* 💸 **Consumo masivo e innecesario de tokens** (30k - 100k tokens por tarea).
* ⏳ **Lentitud extrema y amnesia de contexto entre sesiones**.
* 💥 **Riesgo de bugs inesperados** por no conocer las dependencias indirectas.

### 🌟 La Solución de Graphtyn
Graphtyn actúa como un **GPS de código en tiempo real**:
* 📉 **Reduce contexto sin ocultar el costo real**: en la matriz pareada actual de cuatro tareas usó **50.3% menos tokens que lectura directa**; el resultado varió entre 19.8% y 78.4% según la tarea. Las cifras, calidad y casos desfavorables están versionados en la sección de benchmarks.
* ⚡ **Análisis sintáctico determinista de 23 lenguajes** a costo **$0 USD y <0.5 segundos**.
* 🕒 **Línea de Tiempo y Memoria de Sesiones Local (100% Gratis / SQLite)**: Registra el historial de acciones y decisiones de la IA en `.graphtyn/history.db` sin pagar servicios externos ni consumir tokens.
* 🎯 **Radio de Impacto en vivo y pre-Commit**: Permite evaluar exactamente qué clases y métodos se verán afectados antes de hacer `git push` (`graphtyn diff`).
* 📝 **Generador de ARCHITECTURE.md**: Exporta un mapa de arquitectura conciso (~150 tokens) que cualquier Agente de IA puede leer al iniciar (`graphtyn export-md`).
 * 🌐 **Dashboard Interactivo WebGL 2D/3D (`:9210`)**:
   - **Calidad & Contexto**: reporta salud observable del índice (parser, cobertura de ubicación y confianza de aristas) sin confundirla con precisión contra ground truth. Permite agrupar hasta 10 símbolos, generar `context_bundle`, copiar su JSON y comparar tokens estimados contra los archivos fuente incluidos. El planificador `relevance-v1` aplica un presupuesto global (12 nodos por defecto), conserva los símbolos solicitados y prioriza llamadas, herencia e implementación sobre enlaces contenedores.
   - **Flujo Web / Framework**: los endpoints tienen filtro, color y metadatos propios (método HTTP, ruta, archivo y resolución). Desde una ruta, controlador, frontend, FormRequest, modelo o evento, **Ver flujo web** aísla `React/Blade → ruta → controlador → validación → persistencia → evento`; **Restablecer grafo completo** elimina el enfoque.
   - **Filtros Laravel y confianza**: permite alternar `invoca ruta`, `despacha`, `valida con`, `crea` y `despacha evento`. La búsqueda incluye endpoint, método HTTP, archivo, contenedor, namespace e ID. `AMBIGUOUS` conserva su etiqueta real y se dibuja punteada en ámbar, separada de `EXTRACTED` e `INFERRED`.
   - **Cobertura framework auditable**: Calidad & Contexto muestra rutas detectadas/resueltas/sin controlador, llamadas frontend y relaciones framework ambiguas. Los mismos contadores están en `GET /api/index-quality?path=/ruta/proyecto&scope=all`, dentro de `framework`.
   - **Perfiles de alcance**: separa el índice completo, producción, pruebas y copias legacy/backups para que duplicados históricos no contaminen una consulta productiva. La selección afecta tanto las métricas como el contexto generado.
   - **Selector Nativo del OS (`📂 Seleccionar...`)**: Abre el explorador de archivos nativo de tu sistema operativo (Windows, macOS, Linux).
   - **Paneles Colapsables (`◀` / `▶`)**: Botones flotantes centrados para expandir el lienzo 2D/3D a pantalla completa.
   - **Auto-descubrimiento Multiplataforma**: Cero rutas estáticas (*hardcoded*); descubre automáticamente los proyectos del desarrollador.
   - **Grafo Semántico de IA e Historial**: Integra precalentamiento con Ollama (`llama3.2`, `qwen2.5`) para generar descripciones de código y el grafo de Arquitectura Global interconectado.
   - **Vista Semántica rediseñada**: comunidades por subsistema (`Subsistema: src/GameEngine.Core`) + **god nodes** destacados (los conceptos más conectados), con aristas etiquetadas `EXTRACTED`/`INFERRED`. Incluye imágenes, documentos y audio/video enriquecidos, y crea un máximo acotado de relaciones `similitud semántica` a partir de sus descripciones locales cacheadas (sin volver a invocar al modelo al abrir la vista).
   - **Respetar `.gitignore` por proyecto**: toggle en el panel de settings (o `graphtyn gitignore on|off`) — con `on` solo los archivos versionados entran al grafo (menos ruido, menos llamadas LLM); `off` incluye todo lo escaneable.
   - **Actualización automática (`--watch`)**: detecta archivos creados, modificados y eliminados, actualiza el índice estructural local y refresca el proyecto activo en el dashboard sin pulsar “Reindexar”.
   - **Diseño del grafo y Motor de índice separados**: `Diseño del grafo` agrupa paleta, estilo Estándar/Neuronal, forma, enlaces, colores y físicas sin alterar datos. `Motor de índice` agrupa AST puro, Ollama/cloud, modelos de código/visión y `.gitignore`; sus cambios se aplican al reindexar. Ambos paneles tienen desplazamiento interno y altura adaptativa para mostrar todas las opciones con zoom 100%. El estado superior distribuye modelo/modo, nodos/conectores y la leyenda EXTRACTED/INFERRED/AMBIGUOUS en filas flexibles para evitar superposición.
   - **Laboratorio de Comparación de Modelos**: Disponible en [`/comparison`](http://localhost:9210/comparison), compara el contexto generado por modelos locales y modelos de paga con el mismo nodo y prompt.

---

## 🛠️ Lenguajes Soportados Nativamente (23 Lenguajes a $0 Tokens)

Graphtyn incluye un motor sintáctico determinista que soporta nativamente el parsing de clases, funciones, módulos, herencia y llamadas en los siguientes lenguajes:

Para C#, JavaScript, TypeScript/TSX, Python, Java, Go y Rust puede utilizar el backend opcional **tree-sitter**. Este produce nodos con `file`, `line`, `end_line`, firma, contenedor, namespace y `parser: tree-sitter`, además de aristas `contiene`, `declara`, `hereda`, `implementa` y `llama` con evidencia verificable. En C# también indexa **campos, propiedades y eventos** como entidades tipadas, permitiendo razonar sobre estado y contratos sin enviar el archivo completo. El resolvedor cross-file pondera receptor/tipo inferido, clase contenedora, aridad, imports, namespace y ensamblado; conserva `AMBIGUOUS` cuando los mejores candidatos empatan. En Unity reconoce el `.asmdef` ancestro más cercano y sus referencias. Es una resolución contextual determinista, no equivale aún a la información de tipos completa de Roslyn/LSP. Si una gramática no está instalada, se conserva automáticamente el extractor integrado. Los fragmentos se cachean por SHA-256 en `structural_cache.json`.

| Lenguaje / Framework | Extensiones | Elementos Extraídos |
|---|---|---|
| 🐍 **Python** | `.py` | Módulos, Clases, Funciones, Métodos, AST Python, Llamadas |
| 🐘 **PHP / Laravel** | `.php` | Tree-sitter: namespaces, clases, traits, métodos, llamadas y operaciones; rutas→controllers→FormRequests→modelos/eventos e invocaciones Inertia/TSX |
| 🟨 **JavaScript / TypeScript** | `.js`, `.ts`, `.jsx`, `.tsx` | Classes, Interfaces, Types, Export Functions, Arrow Functions |
| 🔷 **C# / .NET** | `.cs` | Namespaces, Structs, Classes, Interfaces, Enums, Inheritance |
| ☕ **Java** | `.java` | Packages, Classes, Interfaces, Enums, Public Methods |
| 🐹 **Go (Golang)** | `.go` | Packages, Structs, Interfaces, Functions, Methods |
| 🦀 **Rust** | `.rs` | Structs, Enums, Impl Blocks, Functions (`fn`), Traits |
| 💎 **Ruby** | `.rb` | Modules, Classes, Methods (`def`), Inheritance |
| ⚙️ **C / C++** | `.c`, `.cpp`, `.h`, `.hpp` | Structs, Classes, Functions, Header Dependencies |
| 📱 **Kotlin** | `.kt`, `.kts` | Classes, Interfaces, Objects, Functions (`fun`), Extension Functions |
| 🍎 **Swift** | `.swift` | Classes, Structs, Protocols, Extensions, Functions (`func`) |
| 🎯 **Dart / Flutter** | `.dart` | Classes, Mixins, Abstract Classes, Top-level Functions |
| 🐚 **Shell / Bash** | `.sh`, `.bash` | Function definitions, Script modules, Subroutines |
| 🗄️ **SQL / Database** | `.sql` | Schemas, Tables, Stored Procedures, Views |
| ⚡ **Vue.js / Svelte** | `.vue`, `.svelte` | Single File Components, Script Blocks, Exported Properties |
| 🎮 **Unity Engine Assets** | `.unity`, `.prefab`, `.asset`, `.shader`, `.uxml` | Prefabs, Scenes, ScriptableObjects, Shaders, UI Toolkit layouts |
| 🔴 **Scala** | `.scala` | Classes, Objects, Traits, Case Classes, Defs |
| 🌙 **Lua** | `.lua` | Functions, Local Functions, Requires |
| 🟣 **Julia** | `.jl` | Functions, Structs, Modules |
| ⚡ **Zig** | `.zig` | Functions (`fn`), Constants, Structs |
| 💧 **Elixir** | `.ex`, `.exs` | Modules (`defmodule`), Functions (`def`/`defp`), Macros |
| 🏗️ **Terraform / HCL** | `.tf`, `.tfvars` | Resources, Data Sources, Modules, Variables, Outputs |
| ☁️ **Salesforce Apex** | `.cls`, `.trigger` | Classes, Interfaces, Methods, Triggers |

### 📄 Documentos Multi-Modal (Docs · PDF · Office)

Además del código, Graphtyn indexa documentos en el mismo grafo:

| Formato | Extensiones | Qué extrae |
|---|---|---|
| **Docs** | `.md`, `.mdx`, `.rst`, `.txt` | Nodos de documento + aristas `referencia` entre docs (enlaces Markdown `[texto](ruta)` y `[[wikilinks]]`) — determinista, $0 |
| **PDF** | `.pdf` | Texto completo (Pasada 1, $0 local) → resumen semántico por LLM en la Pasada 2 |
| **Word** | `.docx` | Párrafos → resumen semántico |
| **Excel** | `.xlsx`, `.xlsm` | Hojas y filas → resumen semántico |
| **Imágenes** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp` | Descripción semántica por modelo de visión local (Ollama) |
| **Audio / Video** | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi` | Transcripción local (Whisper, CPU $0) → resumen semántico por LLM |

En **Semántico IA**, los nodos `image`, `doc` y `media` se mantienen dentro de su comunidad y se conectan con hasta dos contenidos afines. Las aristas se calculan sobre las descripciones ya enriquecidas, se etiquetan `similitud semántica · N%` y llevan confianza `INFERRED`. Es una heurística local, explicable y acotada; no pretende sustituir todavía a embeddings ni a extracción relacional mediante un LLM.

Cada relación multimodal inferida incluye evidencia auditable: método utilizado, términos compartidos y fragmentos de las dos descripciones cacheadas. Así, una conexión puede inspeccionarse y rechazarse sin confiar ciegamente en una puntuación opaca.

Las librerías de documentos son **opcionales** (el MCP stdio sigue siendo 100% stdlib):

```bash
pip install "graphtyn[multimodal]"   # pypdf + python-docx + openpyxl
pip install "graphtyn[media]"        # faster-whisper (transcripción local)
pip install "graphtyn[treesitter]"   # parser preciso C#, JavaScript y TypeScript/TSX
```

**Modelos de visión local** (RTX 3050 4GB):

```bash
ollama pull qwen3-vl:2b        # calidad (recomendado, ~15-40s/imagen)
ollama pull minicpm-v4.6:1b    # velocidad (~2-3s/imagen, 900MB VRAM)
```

Configuración: `GRAPHTYN_VISION_MODEL` (default `qwen3-vl:2b`), `GRAPHTYN_IMAGE_LIMIT` (0=ilimitado), `GRAPHTYN_WHISPER_MODEL` (default `small`), `GRAPHTYN_MEDIA_LIMIT` (0=ilimitado). Sin los extras instalados, los documentos igual entran al grafo como nodos (sin extracción de texto).

---

## 📦 Instalación Sencilla (1 Solo Comando - Sin Docker)

Instalar Graphtyn en cualquier sistema operativo requiere un único comando nativo de Pip:

```bash
# Instalar Graphtyn globalmente
pip install git+https://github.com/CaleroAM/openclaw.git#subdirectory=code-graph-host

# Iniciar el Dashboard WebGL interactivo en http://localhost:9210
graphtyn serve
```

---

## 🚀 Comandos CLI

Graphtyn incluye herramientas CLI integradas para interactuar directamente desde la terminal o scripts de automatización:

```bash
# Inicializar Graphtyn en el repositorio actual
graphtyn init

# Iniciar el servidor MCP por stdio para Agentes de IA
graphtyn mcp

# Iniciar el Dashboard WebGL interactivo en el puerto 9210
graphtyn serve

# Mantener el grafo actualizado mientras editas el proyecto
graphtyn serve --watch --path /ruta/al/proyecto

# Benchmark reproducible con ground truth
graphtyn benchmark --path /ruta/proyecto --ground-truth benchmarks/ground_truth.json --output resultado.json

# Validar la matriz estadística de 36 tareas (108 celdas pareadas)
graphtyn benchmark-suite --protocol benchmarks/statistical_protocol_36_tasks.json

# Detectar Roslyn/dotnet, TypeScript, Pyright y PHPStan disponibles
graphtyn type-status --path .

# Comparar corridas JSON de un agente con y sin Graphtyn
graphtyn agent-benchmark --treatment con-grafo.json --baseline sin-grafo.json --output comparacion.json

# Riesgo e impacto de una rama/PR; simula conflictos sin modificar el repositorio
graphtyn pr-impact --path /ruta/proyecto --base main

# Consultar la línea de tiempo del historial de acciones de la IA (SQLite Local)
graphtyn timeline

# Evaluar el radio de impacto de cambios sin confirmar (git status / git diff)
graphtyn diff

# Convertir un requisito en targets, estado, contratos, pruebas y riesgos verificables
graphtyn analyze-change "Cambiar la subasta y notificar cada nueva oferta" --path /ruta/proyecto

# Generar un archivo ARCHITECTURE.md compacto (~150 tokens) para Agentes de IA
graphtyn export-md

# Consultar conceptos o símbolos en el grafo
graphtyn query "sistema de autenticación"

# Contexto compacto de varios símbolos con un presupuesto global
graphtyn context GameManager PlayerService --depth 1 --limit 12 --path /ruta/proyecto

# Resolver una tarea completa con selección automática o explícita de intención
graphtyn query-intent "Traza la creación de una propuesta" --intent flow --limit 12 --path /ruta/proyecto

# Para orden, condiciones o ciclo de vida, auto añade sólo los cuerpos seleccionados
graphtyn query-intent "Explica el orden exacto de Mux.ServeHTTP" --intent flow --evidence-mode auto --path /ruta/proyecto

# Control explícito del presupuesto: compact, balanced o precision
graphtyn query-intent "Audita cuándo se cancela Timeout" --evidence-mode precision --path /ruta/proyecto

# Explicar propósito, tecnologías, entradas y arquitectura del repositorio
graphtyn query-intent "¿De qué trata este repositorio?" --intent overview --limit 10 --path /ruta/proyecto

# Generar el informe persistente; compara tokens si existe GRAPH_REPORT.md
graphtyn report --path /ruta/proyecto --output GRAPHTYN_REPORT.md
graphtyn report --path /ruta/proyecto --graphify-report /ruta/proyecto/graphify-out/GRAPH_REPORT.md

# Puntuar respuestas de agentes contra hechos atómicos auditables
graphtyn agent-grade --runs corridas.json --tasks tareas.json --output puntuadas.json

# Evaluar el graph.json del comparador Gra…ify con el mismo ground truth
graphtyn benchmark-graphify --graph graphify-out/graph.json --ground-truth benchmarks/ground_truth.json --output graphify-score.json

# Perfiles de reindexado: AST rápido, IA local, análisis profundo o profundo+verificación
graphtyn reindex --mode fast --path .
graphtyn reindex --mode balanced --path .
graphtyn reindex --mode deep --path .
graphtyn reindex --mode verified --path .

# Registrar y consultar varios repositorios como un grafo global
graphtyn global add --as backend --path /ruta/backend
graphtyn global add --as frontend --path /ruta/frontend
graphtyn global list
graphtyn global query "CustomerContract"

# Guardar el resultado real de una respuesta y crear una capa de aprendizaje
graphtyn memory save --question "¿Dónde se valida el pago?" --answer "PaymentService" \
  --nodes PaymentService --files src/payment.py --outcome useful --path .
graphtyn memory reflect --path .

# Revisar una PR y generar un artefacto Markdown; código 2 si excede la política
graphtyn ci-check --base origin/main --max-risk medium --output graphtyn-pr.md --path .
graphtyn ci-install github --max-risk medium --path .

# Verificación diferencial conservadora (Python): identidad AST o abstención honesta
graphtyn verify-edit --base HEAD~1 --json --path .

# Configurar instrucciones para los agentes detectados o uno específico
graphtyn agent-install all --path .
```

### Capacidades de equipo y verificación

El **grafo global** vive en `~/.graphtyn/global-graph.json`. Cada ID se prefija con el alias del repositorio para impedir colisiones. Las coincidencias de símbolos entre proyectos se publican como `possible_cross_project_contract` con confianza `AMBIGUOUS`: sirven para descubrir un posible contrato, pero exigen verificarlo en código o documentación. Puede usarse un registro aislado mediante `--registry`.

La **memoria de resultados** guarda señales `useful`, `dead_end` y `corrected` dentro de `.graphtyn/memory/`. `memory reflect` aplica decaimiento temporal, genera `.graphtyn/learning-overlay.json` y `LESSONS.md`, y compara SHA-256 de los archivos citados. Una lección cuyo código cambió se marca `source changed; re-verify` y no debe reutilizarse como evidencia vigente.

`ci-check` combina el diff real, símbolos modificados, consumidores, conflictos y un plan de verificación. `ci-install github` genera un workflow de pull requests; `ci-install gitlab` genera una plantilla incluible desde `.gitlab-ci.yml`. La política `--max-risk` permite usarlo como aviso o compuerta reproducible sin enviar código a un servicio externo.

`verify-edit` es el primer nivel de **verificación diferencial local**. Actualmente solo declara `equivalent` cuando la función Python tiene un AST canónico idéntico; una función agregada/eliminada se distingue estructuralmente y cualquier edición semántica produce `unsupported`. No ejecuta código del repositorio ni presenta pruebas heurísticas como demostraciones. Los futuros tiers de solver o property testing deberán conservar estos mismos veredictos explícitos.

Los perfiles de análisis tienen costos previsibles: `fast` usa AST puro, `balanced` usa enriquecimiento local incremental, `deep` solicita una pasada completa con IA y `verified` añade el tier diferencial. En ausencia del daemon local, todos conservan un fallback AST funcional; por ello la indexación estructural nunca depende de una API de pago.

### Precisión, recuperación híbrida e incrementalidad

Cada reindex normaliza el grafo antes de servirlo: elimina relaciones lógicas duplicadas, conserva la evidencia más fuerte y añade `confidence_score` auditable sin convertir una relación `AMBIGUOUS` en hecho. El radio de impacto `directional-consumers-v2` recorre consumidores entrantes, implementaciones, herencia, eventos y relaciones de framework; un cambio de firma amplía automáticamente el análisis hasta tres saltos y devuelve categorías de contratos, consumidores, configuración, pruebas y relaciones por revisar.

La recuperación combina coincidencia exacta/operaciones con un índice de embeddings local persistente. Sin configuración utiliza feature hashing bilingüe determinista de 384 dimensiones y **0 tokens**; exige solapamiento léxico para evitar que una colisión hash se presente como similitud semántica. Con `GRAPHTYN_EMBED_MODEL=nomic-embed-text` usa Ollama local y permite similitud vectorial real. `semantic_index.json` conserva SHA-256 por nodo: las siguientes reindexaciones reutilizan vectores sin recalcular nodos intactos. El planner `adaptive-intent-v2` ajusta el presupuesto a intención y complejidad, y detiene expansión cuando ya existe evidencia suficiente y válida.

Los analizadores de tipos son opcionales y explícitos. `graphtyn type-status` detecta `dotnet`/Roslyn, TypeScript (`tsc`), Pyright y PHPStan. Graphtyn no ejecuta código ni compiladores del proyecto automáticamente: CI o el desarrollador pueden escribir relaciones comprobadas en `.graphtyn/type-evidence.json`; al reindexar se validan IDs y se incorporan con confianza `TYPED`. Esto permite precisión de compilador sin hacer que el modo AST puro dependa del entorno.

La caché estructural informa archivos reutilizados, analizados e invalidados. El enriquecimiento semántico y los embeddings conservan resultados cuyo hash no cambió; archivos eliminados salen tanto del grafo como de las cachés. La validación previa comprueba nodos/aristas colgantes, ubicación de evidencia y ambigüedad, mientras `validate-answer` detecta respuestas truncadas, fences o paréntesis sin cerrar y afirmaciones sin respaldo.

El dashboard queda disponible en [`http://127.0.0.1:9210`](http://127.0.0.1:9210). El flujo web no agrega otro comando CLI: se usa desde **Filtros → Flujo Web / Framework** y desde **Ver flujo web** en la ficha Radio de Impacto.

### Instrucciones para agentes

El repositorio incluye dos plantillas listas para usar:

- [`AGENTS.md`](AGENTS.md): política de proyecto para que el agente consulte `graph_query_intent` antes de explorar ampliamente, resuelva referencias conversacionales como “ese cambio” y respete `complete_for`/`do_not_expand`.
- [`skills/graphtyn/SKILL.md`](skills/graphtyn/SKILL.md): skill portable y autodescubrible para agentes compatibles. Puede copiarse a la carpeta de skills del agente o distribuirse con el proyecto; incluye metadata en `skills/graphtyn/agents/openai.yaml`.

Ambas usan un presupuesto inicial de 10 entidades, reutilizan `context_id` mediante `extends_context_id` y obligan a diferenciar evidencia `EXTRACTED`, `INFERRED` y `AMBIGUOUS`.

### Actualización automática

`graphtyn serve --watch` observa el proyecto indicado por `--path` y cualquier otro proyecto que abras en el dashboard. El watcher es local y portátil: compara un manifiesto SHA-256, detecta altas, modificaciones y bajas, reutiliza los fragmentos tree-sitter cacheados de archivos sin cambios y escribe `index.json` de forma atómica. No llama a Ollama ni consume tokens; conserva el enriquecimiento semántico previo de los nodos que no cambiaron.

El intervalo predeterminado es un segundo y puede configurarse con `GRAPHTYN_WATCH_INTERVAL`. El estado se expone en `/api/watch/status`; el dashboard lo consulta y recarga automáticamente el grafo activo cuando cambia su versión. En lenguajes que aún usan los extractores integrados se vuelve a ejecutar el parser estructural al ensamblar el grafo, por lo que esta primera versión no pretende ser incremental a nivel de fragmento para los 23 lenguajes.

### MCP HTTP autenticado

El transporte HTTP se sirve en `POST /mcp` y permanece deshabilitado si no existe un token. Para equipos, inicia el servidor con una variable secreta y envía `Authorization: Bearer <token>`:

```bash
GRAPHTYN_MCP_TOKEN='un-secreto-largo-y-aleatorio' graphtyn serve --path /ruta/proyecto
curl -X POST http://127.0.0.1:9210/mcp \
  -H 'Authorization: Bearer un-secreto-largo-y-aleatorio' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

El endpoint usa comparación de token resistente a timing y expone vecindario, radio de impacto, búsqueda semántica y análisis de PR. Para exponerlo fuera de localhost todavía se recomienda colocarlo detrás de TLS y un proxy con límites de solicitudes.

### Impacto por símbolo

`diff` y `pr-impact` leen hunks de `git diff --unified=0`, cruzan los rangos modificados con `line/end_line` y usan como semillas los métodos, clases o funciones tocados. Los cambios se clasifican como `logic`, `signature`, `configuration`, `documentation` o `asset`. Para relaciones `llama`/`usa`, el impacto se propaga hacia los consumidores; ya no expande automáticamente todos los símbolos de cada archivo modificado. La vista **Cambios** muestra estos símbolos y permite indicar una rama base.

# Explicar la responsabilidad y conexiones de un módulo o clase
graphtyn explain "TurnManager"

# Encontrar la ruta de conexiones más corta entre dos símbolos
graphtyn path "AuthService" "Database"

# Reindexar el repositorio con el motor de IA deseado
graphtyn reindex --engine ast_local_llm

# Instalar el hook post-commit: reindexado incremental automático tras cada commit
graphtyn hook install

# Configurar si el grafo respeta .gitignore (por proyecto)
graphtyn gitignore on --path .    # solo archivos versionados (default)
graphtyn gitignore off --path .   # incluir también lo ignorado
```

---

## 💻 Resumen de benchmarks

Los artefactos, condiciones y estados `FULL/PARTIAL/HISTORICAL` viven en
[`BENCHMARKS.md`](BENCHMARKS.md). Esta sección es introductoria y no debe usarse
aislada para comparar proveedores.

### Comparación pareada actual: Graphtyn, Gra…ify y agente sin grafo

La prueba reproducible del 22 de agosto de 2026 usa el mismo `opencode/x-preview-f-free`, prompts y ground truth atómico sobre dos repositorios reales de tecnologías distintas: un **framework Python/ASGI** y un **juego empresarial por turnos desarrollado con Unity/C#**. **Sin grafo** significa que OpenCode no recibió Graphtyn ni Gra…ify: resolvió la tarea únicamente con lectura y búsqueda local. Para las dos tareas corregidas se usa la regresión v2; los comparadores son las corridas pareadas del mismo día.

| Tipo de tarea | Graphtyn tokens · calidad | Gra…ify tokens · calidad | Sin grafo tokens · calidad | Reducción vs Gra…ify | Reducción vs sin grafo |
|---|---:|---:|---:|---:|---:|
| Seguridad / sesión firmada | 8,155 · **100.0%** | 28,094 · 50.0% | 11,112 · 16.7% | **71.0%** | **26.6%** |
| Arquitectura / dispatch de rutas | 15,453 · **100.0%** | 14,218 · 75.0% | 19,270 · **100.0%** | −8.7% | **19.8%** |
| Radio de impacto | 8,800 · 60.0% | **7,992 · 80.0%** | 18,263 · **80.0%** | −10.1% | **51.8%** |
| Servicio / flujo de dominio | **6,307 · 66.7%** | 13,493 · 50.0% | 29,196 · **83.3%** | **53.3%** | **78.4%** |
| **Promedio (4 tareas)** | **9,679 · 81.7%** | 15,949 · 63.8% | 19,460 · 70.0% | **39.3%** | **50.3%** |

Un porcentaje negativo significa que Graphtyn gastó más tokens en esa tarea; no se ocultan esos casos. La muestra es pequeña y mezcla una regresión enfocada con la matriz original, por lo que demuestra funcionamiento y orienta optimizaciones, pero no prueba superioridad universal. Estadística consolidada legible por máquinas: [`benchmarks/task_type_comparison_2026-08-22.json`](benchmarks/task_type_comparison_2026-08-22.json). Evidencia cruda: [`benchmarks/real_repos_current_2026-08-22/REPORT.md`](benchmarks/real_repos_current_2026-08-22/REPORT.md) y [`benchmarks/quality_v2_real_2026-08-22/REPORT.md`](benchmarks/quality_v2_real_2026-08-22/REPORT.md).

### ⚙️ Hardware de Referencia de Pruebas
* **Procesador:** Intel Core i5-12500H (12a Gen, 16 Hilos / Cores)
* **Memoria RAM:** 15 GB RAM
* **Tarjeta de Video Dedicada:** **NVIDIA GeForce RTX 3050 Mobile (4 GB VRAM)** — CUDA activo
* **Gráficos Integrados:** Intel Iris Xe Graphics
* **Sistema Operativo:** NixOS 26.05 (Linux) — **Ollama 0.30.6** (con soporte CUDA 12.9)
* **Modelo IA Local (Ollama):** `llama3.2:latest`, `qwen2.5-coder:3b`, `qwen2.5-coder:7b`, `llama3.1:8b`

### 📊 Tiempos Reales de Reindexación (Proyecto Graphtyn: 50 Nodos · 44 Conectores · 11 Archivos)

| Motor Seleccionado | Tiempo Real (GPU RTX 3050 4GB) | Consumo de Tokens |
|---|---|---|
| `Solo AST (Puro)` | **0.147 seg** | **0 Tokens** |
| `AST + Local (Ollama qwen2.5-coder:3b)` | **~50 seg** (11 archivos + ~40 símbolos enriquecidos) | **0 Tokens (Local)** |

> El reindexado con IA local enriquece semánticamente cada **archivo**, cada **función/clase/método** (símbolo) y genera el resumen de arquitectura global (`ai_summary`), todo a **costo $0 USD** sin salir de tu máquina.
>
> **Modo incremental**: si el índice ya existe y el proyecto es un repo git, el reindex detecta los archivos cambiados con `git status` y **solo enriquece lo nuevo/modificado** (el resto conserva su contexto; ej. 0 cambios → 5-8s en un proyecto de 277 archivos vs ~5 min completos). Fuerza el reindex completo con `full: true` en el payload.
>
> **Configuración del motor** (env): `OLLAMA_HOST`, `OLLAMA_MODEL`, `GRAPHTYN_SYMBOL_LIMIT` (60), `GRAPHTYN_FILE_LIMIT` (0=ilimitado, para muestreo) y `GRAPHTYN_COMPACT=1` (segunda pasada inline que comprime cada descripción larga a ≤100 chars). Detalle completo del flujo en [`docs/contexto-comparativo.md`](docs/contexto-comparativo.md).

---

### 🤖 Benchmark Real de Modelos Locales (vía Ollama, GPU RTX 3050 4GB)

Pruebas ejecutadas con los **prompts reales de Graphtyn** (resumen de arquitectura global + resumen de archivo de código) sobre la instancia local de Ollama (`http://localhost:11434`). El modelo se selecciona vía la variable `OLLAMA_MODEL` (o auto-detección si no está definida):

```bash
OLLAMA_MODEL=qwen2.5-coder:3b graphtyn reindex --path . --engine ast_local_llm
```

| Modelo Local (Ollama) | Tamaño | Resumen Arquitectura | Resumen Archivo | Distribución GPU/CPU | Veredicto |
|---|---|---|---|---|---|
| 🦙 **`llama3.2:latest`** (3B) | ~2.0 GB | ⚡ **0.98s** / 45 tok | ⚡ **0.85s** / 36 tok | **100% GPU** | **(Recomendado por Defecto)** Ideal para laptops con 4GB VRAM. |
| 👑 **`qwen2.5-coder:3b`** | ~1.9 GB | ⚡ 1.83s* / 160 tok | ⚡ **1.83s** / 97 tok | **100% GPU** | **(Mejor para Código)** Mejor calidad de resúmenes de código, totalmente en VRAM. |
| ⚠️ **`qwen2.5-coder:7b`** | ~4.7 GB | 🐢 **16.1s** / 24 tok | 🐢 **10.3s** / 110 tok | **53% CPU / 47% GPU** | No cabe en 4GB VRAM; derrama a CPU y se vuelve 5-10× más lento. |
| ⚠️ **`llama3.1:8b`** | ~4.9 GB | 🐢 **19.2s** / 66 tok | 🐢 **4.1s** / 36 tok | **55% CPU / 45% GPU** | No cabe en 4GB VRAM; requiere 6GB+ VRAM o solo CPU con mucha RAM. |

\* La primera llamada de `qwen2.5-coder:3b` (7.87s) incluye la carga en frío del modelo; las siguientes van a ~1.8s.

**Conclusión de las pruebas reales**: en hardware con **4 GB de VRAM**, los modelos 3B (`llama3.2:latest` / `qwen2.5-coder:3b`) cargan **100% en GPU** y generan en ~1 segundo por llamada. Los modelos 7B/8B no caben en la VRAM, se reparten CPU/GPU y tardan 10-20 segundos, sin aportar una mejora proporcional para resúmenes de una frase. Para GPUs de 6 GB+ VRAM, `qwen2.5-coder:7b` ofrece la mejor precisión sintáctica en código.

### ✍️ Ejemplo Real de Enriquecimiento Semántico por Modelo

Mismo nodo (`mcp_server.py`), mismo prompt real de Graphtyn (config #9), misma temperatura (0.2). Resultado crudo de cada modelo — incluida la respuesta del modelo actual verificado (**OpenCode · `opencode-go/gpt-5.6-luna`**), además de referencias históricas de DeepSeek:

| Modelo | Tiempo | Ejemplo de descripción generada |
|---|---|---|
| 💎💎💎 **OpenCode · `opencode-go/gpt-5.6-luna` (modelo actual verificado)** | Sesión actual | "Servidor MCP por stdio basado en JSON-RPC 2.0 que expone 7 herramientas para agentes de IA — consulta del grafo, radio de impacto, búsqueda semántica, historial de sesiones y registro de proyectos — lee el índice cacheado, registra operaciones en SQLite y entrega contexto sin consumir tokens del agente." |
| 💎💎 **DeepSeek V4 PRO (MAX · modelo de paga)** | ~10s (razonamiento) | "Servidor MCP por stdio (JSON-RPC 2.0) que expone 7 herramientas a agentes de IA — mapa de código, radio de impacto, búsqueda de conceptos e historial de sesiones — devolviendo el grafo cacheado del proyecto sin consumir tokens del agente." |
| 💎 **DeepSeek V4 Flash (opencode · modelo de paga)** | ~10-15s (razonamiento completo) | "Servidor MCP por stdio (JSON-RPC 2.0) que expone 7 herramientas para agentes de IA — grafo, radio de impacto, búsqueda de conceptos e historial de sesiones — sirviendo el grafo cacheado sin consumir tokens del agente." |
| 🦙 **`llama3.2:latest`** | 6.2s | "Es una unidad del sistema que proporciona un servidor de protocolo estándar (MCP, Model Context Protocol) para la plataforma Graphtyn, permitiendo a los agentes de IA interactuar con gráficos y realizar operaciones como buscar vecinos gráficos, detectar conceptos y más." |
| 👑 **`qwen2.5-coder:3b`** | 5.8s | "Define una API para el servidor de contexto del protocolo de modelo Graphtyn, que proporciona herramientas para AI agents como `graph_neighborhood`, `graph_blast_radius`, `graph_search_concepts` y `graph_register_project`." |
| ⚠️ **`qwen2.5-coder:7b`** | 18.6s | "Define funciones para procesar solicitudes de un servidor MCP y generar respuestas basadas en un análisis del código fuente, sirviendo como la unidad principal del sistema para el protocolo Stdio Model Context Protocol (MCP) en Graphtyn." |
| ⚠️ **`llama3.1:8b`** | 18.0s | "Es un servidor de protocolo de contexto modelo (MCP) para Graphtyn, que proporciona herramientas para agentes de inteligencia artificial y gestiona la representación gráfica del espacio de trabajo." |

> Los 7 resultados identifican correctamente `mcp_server.py` como servidor MCP. **`qwen2.5-coder:3b` es el local más preciso** (nombra las tools reales, 5.8s, 100% GPU), y su calidad se acerca al **90-95% del modelo actual verificado**. El modelo actual añade el nivel más completo de contexto: protocolo, herramientas, flujo de lectura, persistencia SQLite y ausencia de consumo de tokens.

---

## 🤖 Integración con Agentes de IA (MCP Protocol)

Graphtyn es un servidor MCP estándar por entrada/salida estándar (`stdio`). El
perfil predeterminado `intent` expone únicamente `graph_query_intent` y
`memory_context`; `--tool-profile memory` añade el ciclo de escritura compartida
y `--tool-profile full` conserva el catálogo completo para diagnóstico.

> **Arquitectura disponible — memoria semántica compartida:** AGY, OpenCode,
> OpenClaw, Codex, Claude y Hermes pueden compartir conversaciones, decisiones,
> resultados y handoffs con atribución, embeddings, retrieval híbrido y vigencia
> por rama/commit. El diseño y protocolo están especificados en
> [`docs/shared_semantic_memory_plan.md`](docs/shared_semantic_memory_plan.md).
> Las funciones actuales de historial y outcomes son la base, no se presentan aún
> como RAG conversacional completa.

La primera base de memoria compartida v2 ya está disponible. Funciona entre
sesiones y clientes distintos mediante un almacén SQLite por proyecto:

```bash
graphtyn memory session-start --agent agy --task "Refactor de autenticación" --path .
# Añade --capture únicamente cuando el usuario autorice guardar conversación.
graphtyn memory append --session SESIÓN --role assistant \
  --content "AuthService quedó probado" --event-type result --path .
graphtyn memory checkpoint --session SESIÓN --kind decision \
  --title "JWT centralizado" --content "AuthService valida los tokens" \
  --files src/AuthService.ts --path .
graphtyn memory search "¿quién valida los tokens?" --agent opencode --path .
graphtyn memory context "¿cómo se comprueba la identidad?" \
  --agent openclaw --branch feature/auth --token-budget 1800 --path .
# Opcional: --neighbor-limit 12 o --no-graph
graphtyn memory ingest-turn --agent opencode --external-session CHAT_ID \
  --task "Cambio actual" --role assistant --content "Resultado conciso" \
  --consent --provider auto --path .
graphtyn memory session-end --session SESIÓN --summary "Cambio probado" --path .
graphtyn memory migrate --path .       # importa history.db y memory/*.json una vez
graphtyn memory reindex --path .       # reutiliza vectores cuyo contenido no cambió
graphtyn memory ingest-evidence --path . # benchmarks verificados y ligados a Git
graphtyn memory status --path .
graphtyn memory correct --memory MEMORIA --session SESIÓN \
  --title "Decisión corregida" --content "Ahora se usa PostgreSQL" --path .
graphtyn memory forget --memory MEMORIA --agent agy --path .
```

`memory_ingest_turn` y `memory_context` incluyen telemetría persistente por
operación: tokens locales de entrada/salida, caracteres vectorizados, tokens del
contexto compacto, historial bruto evitado y latencia. `graphtyn memory status
--path .` agrega estas métricas. Los conteos usan `bytes UTF-8 / 4`: son
estimaciones comparativas, no facturación. Con Qwen y Nomic en Ollama,
`local_provider_billed_tokens` permanece en cero; el proveedor remoto sólo recibe
`remote_context_tokens` cuando el cliente incorpora el resultado a su prompt.

Las tools MCP equivalentes son `memory_session_start`, `memory_checkpoint`,
`memory_ingest_turn`, `memory_search`, `memory_context`, `memory_compact` y
`memory_session_end`. `memory_ingest_turn` es la ruta recomendada para adaptadores:
reutiliza de forma idempotente el ID de conversación externo, captura uno o varios
mensajes y compacta automáticamente cuando el turno contiene una respuesta del
asistente. La búsqueda fusiona
FTS5 y embeddings locales por RRF, favorece la rama actual, explica cada score y
marca recuerdos stale cuando cambian sus archivos de evidencia. El fallback
`feature-hash-v2` funciona sin dependencias; `GRAPHTYN_EMBED_MODEL` permite usar
Ollama y, si no responde, Graphtyn mantiene disponible el fallback local.
`memory_context` expande solamente vecinos directos explicables: consumidores,
dependencias y relaciones estructurales de los archivos/símbolos citados. Además
compara el commit observado con el `HEAD` actual y advierte ramas divergentes.
Cada memoria incluye una puerta compacta `claim_policy`: `verified_measured`,
`verified_fact`, `historical_only`, `proposed_only`, `contested`, `stale` o
`unsupported`. El agente debe citar evidencia para las dos primeras y no puede
convertir las demás en hechos. `memory_ingest_evidence` importa benchmarks de
forma idempotente, conserva hash/archivo/commit y supersede versiones modificadas.

La captura está desactivada por defecto. `memory_append` rechaza roles `system`,
aplica límites, redacta credenciales tanto por contenido como por claves de
metadatos y deduplica eventos. El cierre de una sesión opt-in crea un handoff
determinista. Las memorias recuperadas se etiquetan como datos históricos no
confiables: nunca se interpretan como instrucciones ni autorización.

Compactación asistida opcional:

```bash
GRAPHTYN_MEMORY_SUMMARY_MODEL=qwen2.5-coder:3b \
  graphtyn memory compact --session SESIÓN --provider ollama --path .

# API externa: requiere consentimiento explícito, además de URL/modelo/clave
GRAPHTYN_MEMORY_ALLOW_API=1 graphtyn memory compact \
  --session SESIÓN --provider api --path .
```

Para el flujo automático local recomendado, inicie el daemon con ambos modelos:

```bash
export GRAPHTYN_MEMORY_SUMMARY_MODEL=qwen2.5-coder:3b
export GRAPHTYN_EMBED_MODEL=nomic-embed-text:latest
```

Qwen recibe únicamente la conversación ya saneada y propone recuerdos; Nomic
vectoriza cada recuerdo resultante. Los mensajes crudos permanecen asociados a
su sesión y no se convierten individualmente en resultados de búsqueda.

Qwen/API sólo generan recuerdos `proposed`, con confianza máxima 0.85 y mensajes
fuente validados. Nunca convierten por sí solos una afirmación en `verified`.

### Memoria compartida en HTTP y dashboard

El dashboard de `http://127.0.0.1:9210` incluye una vista independiente
**Memoria compartida** con buscador, sesiones recientes, atribución, vigencia,
corrección y olvido. **Ver mapa por agente** colorea memorias y referencias con
un color estable por autor y dibuja `creó memoria`, `consultó`, `corrige` y
`respalda`; al abrir un nodo se muestran agente, sesión, estado y commit observado.
Todos los clientes operan sobre la misma `memory-v2.db`.

La pestaña principal **Memoria del proyecto** carga ese grafo automáticamente al
seleccionar un proyecto; no exige escribir una consulta. **Semántico del código**
es otra vista: conecta código, documentos y multimedia por similitud temática.
Ambas usan recuperación semántica, pero la primera conserva trabajo y procedencia
de agentes, mientras la segunda describe el contenido indexado del repositorio.
**Buscar en memoria** queda como herramienta opcional para investigar un tema.

```text
GET  /api/memory/status
GET  /api/memory/sessions
POST /api/memory/search
POST /api/memory/context
POST /api/memory/compact
POST /api/memory/correct
POST /api/memory/forget
```

Para exigir autenticación:

```bash
GRAPHTYN_MEMORY_HTTP_TOKEN="un-token-largo" graphtyn serve \
  --host 127.0.0.1 --port 9210 --path .
```

Si no existe esa variable se reutiliza `GRAPHTYN_MCP_TOKEN`; sin cualquiera de
las dos se conserva el modo local sin token para compatibilidad.

Diagnóstico y benchmark reproducible:

```bash
graphtyn memory doctor --path .
graphtyn memory benchmark --dataset benchmarks/shared_memory_v1.json \
  --output benchmarks/shared_memory_v1_result.json --path .
```

Resultados, evolución y límites: [`docs/shared_memory_benchmark.md`](docs/shared_memory_benchmark.md).

Suite de estabilidad ampliada:

```bash
graphtyn memory benchmark --suite stability \
  --output benchmarks/shared_memory_stability_result.json --path .
```

Diseño 30×3×3, resultados y guardrails: [`docs/shared_memory_stability.md`](docs/shared_memory_stability.md).

### Cerebros de agentes (memoria personal sin repositorio)

Además de la memoria por proyecto, cada agente u orquestador puede tener su propio
**cerebro**: un almacén de memoria sin código asociado para conversaciones por tema
(entrevistas, planes de carrera, práctica de idiomas). La separación recomendada es:

- **Un cerebro por agente autónomo** (todas sus conversaciones en un grafo).
- **Un cerebro por orquestador** que incluye las conversaciones de sus subagentes,
  atribuidas individualmente.
- **La memoria de proyecto**, aparte, con la evidencia técnica verificable.

El flujo típico consulta primero a nivel conversacional (el cerebro) y baja a la
memoria del proyecto sólo si necesita evidencia de código.

Creación con autodescubrimiento de agentes (lee `IDENTITY.md`/`SOUL.md` de cada
subcarpeta, registra su perfil atribuido y lo añade al dashboard):

```bash
graphtyn memory brain-init \
  --brain-path ~/memoria-personal/cerebro-agent-alpha \
  --name "Cerebro · Orchestrator" \
  --agents-dir /ruta/al/directorio/de/workspaces \
  --register
```

**Identidades de agente sin editar código.** Las variantes de nombre se resuelven
en tres capas: tabla `agent_aliases` de cada almacén, archivo global opcional
`$GRAPHTYN_HOME/agent-aliases.json`, y defaults integrados. Se importan en bloque:

```bash
# En un almacén concreto y, además, en la configuración global
graphtyn memory alias-import --pairs "alias-local=identidad-canonica" --global-config --path .

# Desde un archivo JSON {"alias": "canonico"}
graphtyn memory alias-import --json-file aliases.json --path .
```

Al vincular un workspace de agente (`POST /api/memory/agent-profile` o el botón
**Vincular agente** del panel "Buscar en memoria"), Graphtyn descubre y persiste
sus alias automáticamente: no hay nada hardcodeado.

**Búsqueda federada.** Una sola consulta puede cubrir varios cerebros y proyectos:

```bash
curl -X POST http://127.0.0.1:9210/api/memory/search-all \
  -H 'Authorization: Bearer TOKEN' -H 'Content-Type: application/json' \
  -d '{"paths":["~/memoria-personal/cerebro-agent-alpha","/ruta/proyecto"],
       "query":"problemas resueltos esta semana","requester_agent":"nexus"}'
```

En el dashboard, el interruptor **Todos los espacios** activa esa búsqueda
federada; cada resultado indica su espacio de origen.

**Captura automática y frescura.** Cada agente debe ejecutar `memory ingest-turn`
al cerrar una conversación (ver bloque "Memoria compartida Graphtyn" en su
`AGENTS.md`). El panel muestra "última captura hace N días" para detectar
espacios desactualizados.

**Mantenimiento de almacenes.** Lista los espacios existentes con conteos y
elimina residuos generados por tests:

```bash
graphtyn memory stores              # inventario
graphtyn memory stores --clean-test # elimina almacenes test_*
```


### Importar conversaciones anteriores a Graphtyn

La ruta recomendada para una instalación nueva es primero previsualizar y luego
aplicar. No modifica archivos fuente del repositorio:

```bash
pipx install graphtyn
graphtyn setup --path .                 # detección, sin cambios
graphtyn setup --path . --apply         # configura agentes/fuentes y token privado
```

El bootstrap histórico descubre JSON, JSONL y bases SQLite de OpenClaw, Hermes,
Codex, Antigravity/AGY, OpenCode y Claude. La primera ejecución sólo genera una
previsualización; importar requiere consentimiento explícito y es idempotente:

```bash
graphtyn memory bootstrap --provider openclaw --source ~/.openclaw --path . \
  --output import-plan.json
graphtyn memory bootstrap --provider openclaw --source ~/.openclaw --path . \
  --apply --consent
graphtyn memory sync --provider openclaw --source ~/.openclaw --path . --consent
```

Para agentes en otra máquina, use la ruta persistente visible desde SSH (se copia
a un temporal que se elimina al terminar):

```bash
graphtyn memory bootstrap --provider openclaw \
  --source ssh://usuario@servidor/ruta/persistente/openclaw/agents \
  --path . --output import-plan.json
```

La ubicación se configura, no se deduce de nombres de contenedor, usuarios o IPs:

```bash
# Host local
graphtyn memory sources add --provider openclaw --source ~/.openclaw/agents
# Docker local
graphtyn memory sources add --provider openclaw --source docker://mi-contenedor/home/node/.openclaw/agents
# VPS o host remoto
graphtyn memory sources add --provider openclaw --source ssh://usuario@host/ruta/agents
# Docker dentro de un VPS
graphtyn memory sources add --provider openclaw --source ssh+docker://usuario@host:mi-contenedor/home/node/.openclaw/agents
graphtyn memory sources list
```

Para conservar conversaciones de proyectos desconocidos sin mezclarlas con el
proyecto abierto, use un cerebro histórico explícito:

```bash
graphtyn memory bootstrap --archive-all --apply --consent \
  --path ~/.graphtyn/brains/historical-agent-memory
graphtyn memory export --include-messages \
  --output ~/.graphtyn/exports/agent-conversations.json \
  --path ~/.graphtyn/brains/historical-agent-memory
```

Los mensajes se saneán, segmentan y compactan antes de generar embeddings. Se
preservan proveedor, agente, sesión, fuente y fecha original con
`capture_mode=historical_import`; reejecutar el comando reutiliza fingerprints y
no duplica conversaciones. Las rutas ambiguas se reportan para revisión.

Los adaptadores integrados no son una lista cerrada. Un proveedor adicional se
declara mediante un manifiesto JSON, sin editar Graphtyn:

```json
{"name":"mi-agente","format":"jsonl","extensions":["jsonl"],"version":1}
```

```bash
graphtyn adapter validate adapter.json
graphtyn adapter install adapter.json
graphtyn adapter list
graphtyn memory sources add --provider mi-agente --source /ruta/historial
graphtyn memory sources test --provider mi-agente --source /ruta/historial
```

Una conversación puede aparecer en varios archivos o crecer después de cerrarse.
El importador fusiona fragmentos por proveedor, agente e ID externo; deduplica
rol+contenido, conserva todas las fuentes como procedencia y no reabre sesiones
normales. Por ello los registros de origen pueden superar a las sesiones lógicas.
Nunca exporta prompts del sistema, razonamiento oculto ni vectores; secretos
reconocibles se redactan y los archivos exportados usan permisos `0600`.

### Operación, seguridad y recuperación

```bash
# Servicio persistente (genera el artefacto; el usuario decide instalarlo)
graphtyn service install --kind systemd --output ~/.config/systemd/user/graphtyn-sync.service --path .
graphtyn service install --kind compose --output compose.graphtyn.yml --path .

# Token por rol/proyecto, almacenado con modo 0600
graphtyn token rotate --role writer --project /ruta/proyecto
export GRAPHTYN_MEMORY_TOKENS_FILE="$HOME/.graphtyn/memory-tokens.json"

# TLS nativo de Uvicorn
graphtyn serve --host 0.0.0.0 --ssl-certfile cert.pem --ssl-keyfile key.pem --path .

# Backup consistente mediante SQLite backup API; restore es preview por defecto
graphtyn backup --output memory.zip --path .
graphtyn backup-verify memory.zip
graphtyn restore memory.zip --path /ruta/destino
graphtyn restore memory.zip --path /ruta/destino --apply
```

El dashboard permite guardar, probar y eliminar fuentes, además de administrar
alias observados→identidad canónica. Docker Compose exige un token en `.env`, usa
usuario sin privilegios, filesystem de sólo lectura y volumen separado para estado.

La prueba real del 25 de agosto de 2026 procesó 91 registros de sesión y 2,834
registros de mensaje desde Codex local, OpenClaw remoto y Hermes remoto. Tras
fusionar fragmentos y duplicados produjo 85 sesiones lógicas, 2,665 mensajes
saneados y 166 memorias; una segunda pasada reutilizó las 91 entradas con cero
errores. El artefacto auditable es
[`benchmarks/history_export_real_2026-08-25.json`](benchmarks/history_export_real_2026-08-25.json).

Limitación: `auto` reconoce estructuras JSON/JSONL/SQLite comunes. Un formato
binario o esquema propietario necesita un adaptador que lo convierta al contrato
neutral de sesión/rol/contenido. La memoria importada sigue siendo histórica y no
se presenta como verdad verificada hasta vincular evidencia vigente.

La API estable ofrece `POST /api/v1/memory/ingest`, `POST /api/v1/context`,
eventos de ciclo de sesión, identidad global de proyectos, jobs de importación y
progreso SSE bajo `/api/v1/imports`. `GRAPHTYN_MEMORY_TOKENS` acepta un JSON
`{"token":"reader|writer|admin"}`; el token MCP anterior conserva rol admin.
También están disponibles el cliente Python `graphtyn.client.GraphtynClient` y
el cliente TypeScript de referencia `graphtyn/client.ts`.

Para aislamiento por proyecto, cada valor también puede ser
`{"role":"writer","projects":["/ruta/permitida"]}`. El límite predeterminado es
120 solicitudes/minuto por token (`GRAPHTYN_MEMORY_RATE_LIMIT`). SQLite y su
directorio reciben permisos `0600/0700`; para cifrar títulos, memorias y mensajes
instale `graphtyn[security]` y defina `GRAPHTYN_MEMORY_ENCRYPTION_KEY`. Con cifrado,
la recuperación usa embeddings y no deja el contenido en FTS.

Gobernanza:

```bash
graphtyn memory export --output memory-export.json --path .
graphtyn memory retention --days 90 --path .          # previsualiza
graphtyn memory retention --days 90 --apply --path .  # conserva verified por defecto
graphtyn memory projects --path .
```

### OpenClaw en host, contenedor o VPS

Graphtyn no presupone dónde corre OpenClaw. Si ambos están en el host puede usar
stdio o HTTP local. Si están en contenedores/VPS distintos, Graphtyn debe escuchar
en una interfaz alcanzable por el cliente:

```bash
export GRAPHTYN_MCP_TOKEN="un-token-largo-y-aleatorio"
export GRAPHTYN_MCP_PATH="/ruta/del/proyecto/en-el-host"
export GRAPHTYN_HOME="$HOME/.graphtyn" # estado central compartido, no dentro del checkout
export GRAPHTYN_EMBED_MODEL="nomic-embed-text:latest" # embedding neuronal local vía Ollama
export GRAPHTYN_HTTP_TOOL_PROFILE="memory"
graphtyn serve --host 0.0.0.0 --port 9210 --path "$GRAPHTYN_MCP_PATH"
```

OpenClaw debe registrar la URL alcanzable `http://<host-graphtyn>:9210/mcp` y header
`Authorization: Bearer <GRAPHTYN_MCP_TOKEN>`. La ruta del proyecto es la ruta vista
por el host Graphtyn, no una ruta privada del sandbox. Restrinja el puerto 9210
mediante firewall; no lo publique sin token.

Cuando `GRAPHTYN_HOME` está definido, esa ubicación es autoritativa aunque el
checkout también sea escribible. Así OpenClaw, Codex, AGY y OpenCode resuelven la
misma `memory-v2.db` aunque sus sandboxes tengan permisos distintos. Para guardar
mensajes de conversación, el agente debe abrir la sesión con
`capture_enabled=true`; omitirlo mantiene el modo privado por defecto y
`memory_append` devuelve un error MCP estructurado. Los checkpoints explícitos
siguen disponibles sin captura automática.

Graphtyn no trata cada línea del chat como una memoria independiente. Con captura
autorizada conserva mensajes saneados; `memory_compact` extrae decisiones,
hechos, procedimientos y resultados, y esos recuerdos sí reciben un embedding
incremental. Con `GRAPHTYN_EMBED_MODEL` usa Ollama y similitud coseno normalizada;
sin esa variable conserva el fallback determinista `feature-hash-v2`. Verifique
proveedor, cobertura e integridad con `graphtyn memory doctor --path .`.

Si el cliente OpenClaw instalado sólo admite MCP `stdio`, use el wrapper
`graphtyn_openclaw.sh` ya incluido y un bind mount compartido. El transporte HTTP
ahora expone el ciclo completo de memoria, por lo que ambos modos leen la misma
`memory-v2.db`.

### 🧭 Herramientas de Mapa de Código (0 Tokens)

| Herramienta | Qué hace | Parámetros |
|---|---|---|
| `graph_query_intent` | Ruta predeterminada adaptativa. Clasifica la intención y usa grafo compacto; para orden exacto, condiciones, seguridad o ciclo de vida añade únicamente cuerpos de símbolos ya seleccionados, con límites de líneas y caracteres. `evidence_mode` permite `auto`, `compact`, `balanced` o `precision`. | `request`, `intent`, `limit`, `evidence_mode`, `extends_context_id` |
| `graph_analyze_change` | Convierte un issue o requisito en un plan verificable con targets, archivos, contratos, estado, pruebas y riesgos. Puede alimentar a Qwen/API; la IA debe citar aliases y no inventar aristas. | `request`, `limit`, `response_mode` |
| `graph_neighborhood` | Devuelve el subgrafo con evidencia. Por defecto usa respuesta compacta, máximo 40 nodos y descripciones de 240 caracteres; `response_mode=full` es opt-in. | `path`, `symbol`, `depth`, `limit`, `response_mode` |
| `graph_blast_radius` | Calcula impacto por salto. La salida compacta limita el contexto a 40 impactos y avisa si hubo truncamiento. | `symbol`, `depth`, `limit`, `response_mode` |
| `graph_context_bundle` | Agrupa vecindad e impacto de hasta 10 símbolos en una sola llamada, reduciendo rondas y reenvío acumulativo de contexto. | `symbols`, `depth`, `limit` |

`limit` es un presupuesto global, no un límite repetido por cada símbolo. La respuesta incluye `planner`, `budget` y `omitted`, de modo que un agente puede detectar truncamiento y solicitar una expansión deliberada. El dashboard usa 12 nodos por defecto.

En `evidence_mode=auto`, una consulta común permanece en `compact`. Las preguntas
que exigen orden, ramas, mutaciones, `defer`, panic, timeout o ciclo de vida pasan
a `precision`: se incluyen como máximo tres cuerpos seleccionados, 120 líneas por
símbolo y 12,000 caracteres totales. No se escanea ni se envía un archivo ajeno a
los nodos elegidos por el grafo. La salida declara `requested_obligations`,
`source_retrieval` y `source_evidence` para auditar por qué creció el contexto.

### GRAPHTYN_REPORT.md

`graphtyn report` genera un informe verificable con propósito extraído del README, lenguajes y frameworks detectados desde manifiestos, puntos de entrada, diagrama Mermaid, dependencias entre subsistemas, flujos representativos, hotspots y señales de deuda. Cada reindexado HTTP también guarda una copia central junto a `index.json`; puede consultarse sin escribir en el repositorio mediante `GET /api/report?path=/ruta/proyecto`.

El bloque **Report metrics** estima tokens del informe y de la evidencia documental seleccionada. Si se proporciona un `GRAPH_REPORT.md`, añade `graphify_report_tokens`, diferencia de tokens y `graphify_observable_coverage` usando las mismas seis dimensiones. Esta cobertura compara presencia de evidencia/secciones; no se presenta como precisión semántica contra ground truth.

La indexación híbrida conserva responsabilidades separadas: **Tree-sitter** extrae símbolos y aristas verificables; **Qwen 2.5 Coder 3B** enriquece descripciones, conceptos y señales semánticas locales. Qwen sigue siendo útil para significado y ranking, pero no sustituye evidencia estructural ni convierte una inferencia en una llamada demostrada.

El **Analista de Cambios** aplica primero un ranking determinista sobre el índice y entrega un paquete `evidence-v1` acotado. Puede responderse directamente o pasarse a Qwen/API para redactar una estrategia más rica. En ese segundo caso, el modelo recibe targets, métodos, estado, contratos, pruebas, riesgos y operaciones internas ya filtrados; cada afirmación debe citar aliases `N*` y los hechos ausentes no deben inventarse. La reindexación estructural no consume tokens y el uso del modelo ocurre solamente al solicitar razonamiento semántico.

El parser v8 representa cuerpos de método sin enviar el código completo. Cada método puede incluir `ops`: tuplas compactas con tipo, nombre, línea y evidencia para llamadas locales o externas, creación de objetos, asignaciones, declaraciones, retornos y controles. El ranking conserva primero las operaciones relacionadas con la consulta y acciones de alto valor como `AddScoped`, `Publish`, `SaveChanges`, `Skip`, `Take` o `CountAsync`; también preserva la firma de la clase propietaria para contratos inyectados en constructores primarios.

```bash
# Recomendado para consulta: dos tools y menor costo acumulado
graphtyn mcp --path /ruta/proyecto

# Ciclo de memoria completo sin catálogo legado del grafo
graphtyn mcp --path /ruta/proyecto --tool-profile memory

# Catálogo histórico completo para diagnóstico
graphtyn mcp --path /ruta/proyecto --tool-profile full
```

El resolvedor estructural v6 sigue receptores encadenados mediante los tipos declarados de campos y propiedades. Por ejemplo, `GameManager.Instance.hud.ShowTurnOrderRoll(...)` se resuelve como `GameHUDController.ShowTurnOrderRoll`; el grafo conserva la cadena, el tipo inferido, archivo y línea como evidencia auditable. Las ambigüedades de llamadas de código se reportan separadas de referencias textuales en documentación.
| `graph_search_concepts` | Busca conceptos semánticos o palabras clave en las descripciones explicativas de nodos (archivos/clases/funciones) y en los nombres de símbolos. | `query` (obligatorio) |

### 🕒 Herramientas de Memoria de Sesiones (SQLite Local, Gratis)

| Herramienta | Qué hace | Parámetros |
|---|---|---|
| `graph_history_search` | Busca en el historial de sesiones y acciones pasadas del agente para recordar eventos o decisiones. | `query` (obligatorio) |
| `graph_history_timeline` | Devuelve la secuencia cronológica completa de acciones de una sesión previa para recuperar contexto. | `session_id` (opcional) |
| `graph_history_get` | Recupera la observación detallada de una acción pasada específica por su ID. | `id` (obligatorio, entero) |

### 🔌 Herramientas de Integración

| Herramienta | Qué hace | Parámetros |
|---|---|---|
| `graph_register_project` | Registra autónomamente una ruta de proyecto en Graphtyn para que aparezca en el dashboard (`:9210`). | `path` (obligatorio), `name` (opcional) |

### 💬 Ejemplos de Prompt para el Agente

- **Mapa completo**: "Usa `graph_neighborhood` para mostrarme la arquitectura del proyecto."
- **Impacto pre-cambio**: "Antes de modificar `TurnManager`, usa `graph_blast_radius` con depth 2 para saber qué se vería afectado."
- **Búsqueda semántica**: "Busca con `graph_search_concepts` dónde se maneja el sistema de autenticación."
- **Memoria de sesiones**: "Consulta `graph_history_timeline` para recordar qué decidimos en la sesión anterior sobre el esquema de la base de datos."

### 1. Google Antigravity (AGY)
Agrega lo siguiente en tu archivo de configuración de MCP (`mcp_config.json`):

```json
{
  "mcpServers": {
    "graphtyn": {
      "command": "graphtyn",
      "args": ["mcp", "--path", "/ruta/a/tu/proyecto"]
    }
  }
}
```

### 2. Anthropic Claude Code
Agrega en tu archivo `~/.claude/CLAUDE.md`:

```markdown
- **Graphtyn MCP**: Servidor de contexto topológico AST, radio de impacto e historial de sesiones.
  Comando MCP: `graphtyn mcp`
```

### 3. OpenAI Codex / Cursor / Windsurf
Agrega en tu configuración `AGENTS.md` o archivo `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "graphtyn": {
      "command": "graphtyn",
      "args": ["mcp"]
    }
  }
}
```

### 4. OpenCode
Agrega en tu configuración global `~/.config/opencode/opencode.json` (o en el `opencode.json` de la raíz del proyecto):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "graphtyn": {
      "type": "local",
      "command": ["graphtyn", "mcp", "--path", "/ruta/a/tu/proyecto"],
      "enabled": true
    }
  }
}
```

Las herramientas quedan disponibles como `graphtyn_graph_neighborhood`, `graphtyn_graph_blast_radius`, etc. El argumento `--path` fija el proyecto del grafo; si lo omites, el servidor usa el directorio de trabajo actual.

### 5. Entornos Aislados (Contenedores / VMs)
El MCP por `stdio` es **100% stdlib de Python** (no requiere `fastapi`/`uvicorn` ni instalación vía pip). Para ejecutarlo dentro de un contenedor Docker o una VM sin paquete instalado, basta con montar o compartir el código fuente y definir `PYTHONPATH`:

```bash
export PYTHONPATH="/ruta/compartida/graphtyn${PYTHONPATH:+:$PYTHONPATH}"
export GRAPHTYN_DAEMON_URL="http://IP_DEL_HOST:9210"   # opcional: daemon del dashboard para graph_register_project
python3 -m graphtyn.cli mcp --path /ruta/al/proyecto
```

- `GRAPHTYN_DAEMON_URL`: dentro de un contenedor, `127.0.0.1:9210` no apunta al daemon del dashboard (que vive en el host). Apunta esta variable a la IP del host (ej. la IP gateway de la VM) para que `graph_register_project` registre proyectos en el dashboard.
- Las herramientas de grafo e historial funcionan standalone (leen el índice cacheado o escanean el código) sin depender del daemon.

#### Wrapper stdio portable para OpenClaw
[`graphtyn_openclaw.sh`](graphtyn_openclaw.sh) no contiene rutas, identidades,
contenedores ni direcciones de una máquina concreta. Configure en el runtime
`GRAPHTYN_PROJECT_PATH` y, sólo si no instaló el paquete, `GRAPHTYN_SOURCE_PATH`.

```json
{
  "mcp": {
    "servers": {
      "graphtyn": {
        "command": "bash",
        "args": ["/ruta/en/el/contenedor/graphtyn/graphtyn_openclaw.sh"]
      }
    }
  }
}
```

Copia el wrapper y ajusta las tres rutas/env a tu infraestructura (es un ejemplo de tu entorno, no parte del paquete PyPI).

---

## 🏆 Comparativa de Mercado

*Revisión de capacidades: agosto de 2026. Para evitar convertir esta documentación en publicidad de terceros, los productos comparados se identifican como **Gra…ify** y **Sou…aph**. Las fuentes primarias auditables permanecen enlazadas: [README v8](https://github.com/Graphify-Labs/graphify/blob/v8/README.md), [pipeline técnico](https://github.com/Graphify-Labs/graphify/blob/v8/docs/how-it-works.md), [navegación precisa](https://sourcegraph.com/docs/code-navigation/precise-code-navigation) y [MCP empresarial](https://sourcegraph.com/docs/api/mcp). Esta tabla compara enfoques; no constituye un benchmark de superioridad.*

| Característica | 📦 Gra…ify (v8) | 🌐 Sou…aph / LSIF | 🌌 Graphtyn |
|---|---|---|---|
| **Parsing Estático Multi-Lenguaje** | **Sí** (36 gramáticas tree-sitter más extractores especializados, local, $0) | Sí (índices SCIP por lenguaje, con precisión de compilador cuando están configurados) | Sí (tree-sitter para 7 lenguajes + extractores integrados para el resto, local, $0) |
| **Descripción semántica persistente por nodo de CÓDIGO** | No en el pipeline normal: el código usa tree-sitter; el pase con modelo se reserva para docs/PDFs/media | No como propiedad equivalente del índice SCIP | ✅ **Sí: cada archivo/clase/función puede recibir una descripción de rol mediante LLM local o cloud** |
| **Etiquetas de confianza en aristas** | ✅ EXTRACTED / INFERRED / AMBIGUOUS por arista | Parcial | ✅ **EXTRACTED/INFERRED/AMBIGUOUS con evidencia y puntuación de resolución contextual** |
| **Consumo de Tokens (grafo de código)** | 0 (tree-sitter local) | 0 (dump LSP) | **0 en Pasada 1** + Enriquecimiento Opcional (local = 0) |
| **Reindexado incremental / automático** | ✅ actualización, modo `--watch` y hook que regenera tras commits | ✅ auto-indexación o indexación SCIP en CI; depende del indexador/lenguaje | ✅ **`--watch` + manifiesto SHA-256 + caché tree-sitter por archivo; git-status y hook post-commit opcional** |
| **Compactación de densidad (≤140 chars/nodo)** | N/A (no describe código con LLM) | N/A | ✅ `GRAPHTYN_COMPACT=1` (local a +5% de la densidad premium) |
| **Memoria de historial de acciones del agente** | ❌ (query log opcional; no timeline de acciones) | ❌ | ✅ **SQLite local (`graph_history_*`) gratuito + `tokens_avoided` por consulta** |
| **Visualizador** | `graph.html` interactivo (comunidades, filtros, nodos) | Navegación web de código, referencias y dependencias; no es un dashboard de grafo equivalente | Dashboard WebGL 2D/3D en vivo (`:9210`) |
| **Impacto de cambios** | ✅ PR impact / triage / conflictos entre PRs (`graphify prs`) | Parcial en CLI | ✅ `diff` + `pr-impact`: hunks → símbolos, riesgo directo/transitivo y simulación no destructiva de conflictos Git |
| **MCP** | ✅ stdio + HTTP compartido con API key (7 tools) | ✅ MCP empresarial (search, navegación, historial y Deep Search) | ✅ stdio + HTTP opcional protegido con Bearer; transporte local por defecto |
| **Multi-modal (docs/PDFs/imagen/video en el mismo grafo)** | ✅ pase semántico sobre docs, PDFs, imágenes y transcripciones mediante el modelo del asistente/backend configurado | No es su objetivo principal | ✅ docs, PDF, DOCX, XLSX, visión local y transcripción local; **relaciones de similitud cacheadas y offline** |
| **Benchmarks publicados** | ✅ recuperación/memoria y agente sobre ERPNext; distingue compresión de corpus de tokens end-to-end | Benchmarks y documentación empresarial | ✅ [BENCHMARKS.md](BENCHMARKS.md): baseline real sin grafo y comparador Gra…ify, con tokens y calidad desglosados por tipo de tarea |
| **Ecosistema / Plataformas** | ✅ instalador para 20+ asistentes | ✅ plataforma empresarial e integraciones de código | ✅ MCP estándar para Antigravity, Claude Code, Codex, Cursor, Windsurf, OpenCode y OpenClaw |
| **Soporte Offline** | ✅ código local; el pase semántico multimodal necesita un backend/modelo configurado | Depende del despliegue e índices | ✅ 100% offline con Ollama y Whisper locales |

**Lectura honesta:** Gra…ify es más maduro en cobertura y precisión del parser, integraciones, flujo de PRs, servidor MCP compartido, extracción relacional multimodal y benchmarks de calidad. Sou…aph domina la navegación precisa y cross-repository cuando existen índices SCIP, además de ofrecer MCP empresarial. Graphtyn se diferencia por **describir también el rol del código con modelos locales**, mantener **historial local del agente**, ofrecer un **dashboard WebGL 2D/3D**, ejecutar visión/transcripción y similitud multimodal **completamente offline**, y conservar un MCP stdio muy portátil. La tesis competitiva actual es “alternativa local-first, visual y semántica”, no “reemplazo universal”.

### Brechas antes de afirmar superioridad

## Flujo de confianza, cambios Git y operación

La entrega de producción expone los ocho controles tanto por CLI como en el dashboard de `http://127.0.0.1:9210`:

```bash
# 1. Auditar si una respuesta está respaldada por símbolos, relaciones y archivo:línea
graphtyn validate-answer --answer @respuesta.md --path .

# 2. Reindexar y consultar duración, archivos +/~/- y llamadas a IA local
graphtyn reindex --mode balanced --path .
curl 'http://127.0.0.1:9210/api/index-update?path=/ruta/absoluta'

# 3. Revisar relaciones ambiguas; las decisiones quedan en .graphtyn/
graphtyn review --ambiguities --path .
graphtyn review --key CLAVE --decision accept --note 'verificado en código' --path .

# 4 y 5. Analizar Git y generar GRAPHTYN_CHANGE_REPORT.md
graphtyn impact --base main --head HEAD --path .
graphtyn review --staged --path .

# Reporte estable del repositorio
graphtyn report --path .
```

`validate-answer` mide **trazabilidad**, no verdad formal: `SUPPORTED` significa que hay evidencia indexada identificable. Las aristas `INFERRED` deben verificarse y una `AMBIGUOUS` nunca debe presentarse como hecho. Las decisiones aceptar/rechazar/corregir son locales, persistentes y vuelven a aplicarse después de reindexar.

La IA local es selectiva: en modo incremental solo resume archivos o símbolos nuevos/modificados y reutiliza lo demás. Tree-sitter conserva autoridad sobre declaraciones y relaciones; Qwen/Ollama no convierte una inferencia en evidencia extraída. El estado indica `local_ai_calls` y `estimated_paid_tokens`; Ollama tiene costo de proveedor cero, aunque sí consume cómputo local.

### Instalación y adopción

```bash
pipx install 'graphtyn[treesitter]'
graphtyn serve --host 127.0.0.1 --port 9210 --watch --path /ruta/proyecto

# Alternativa reproducible
docker compose up --build

# Instrucciones para agentes y checks de PR
graphtyn agent-install all --path .
graphtyn ci-install github --max-risk medium --path .
```

Docker publica únicamente `127.0.0.1:9210`, monta el repositorio para poder escribir los reportes solicitados y persiste el índice en un volumen separado. También se incluyen plantillas para GitHub Actions/GitLab y políticas para Codex, OpenCode, Claude, Cursor, Gemini y Copilot.

### Alcance honesto pendiente

1. Extender el parsing incremental por fragmento a los lenguajes que todavía usan extractores integrados y evaluar LSP/SCIP para resolución cross-file de compilador.
2. Ampliar el ground truth del repositorio Unity/C# a un corpus etiquetado estadísticamente útil y comparar calidad de respuestas contra Gra…ify y un baseline sin grafo.
3. Añadir TLS, rotación de credenciales, rate limiting y coordinación segura de índices para equipos al MCP HTTP.
4. Incorporar triage entre múltiples PRs y defensas contra prompt injection en documentos.
5. Validar con repositorios externos grandes; las cifras de ahorro de tokens deben reportar metodología, corpus, promedio y dispersión.

---

## 📜 Licencia

Publicado bajo la Licencia **MIT** — Código libre para la comunidad de desarrolladores e investigadores de IA.
