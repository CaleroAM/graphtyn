# 🌌 AetherGraph

[![PyPI Version](https://img.shields.io/badge/pypi-v0.1.0-blue.svg)](https://pypi.org/project/aether-graph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Compatible](https://img.shields.io/badge/MCP-Standard--Compatible-10b981.svg)](https://modelcontextprotocol.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab.svg)](https://www.python.org/)

**El motor de mapa topológico de código, registro de sesiones local y servidor MCP estándar para Agentes de IA (Google Antigravity, Claude Code, Codex, Cursor y Windsurf).**

AetherGraph convierte cualquier repositorio de código en un **grafo de conocimiento determinista de 2 pasadas**: analiza la estructura de archivos, módulos, clases, métodos y llamadas con **0 tokens de consumo** en menos de 0.5 segundos (medido) y enriquece semánticamente los nodos principales mediante **IA Local (Ollama Qwen2.5)** o **Cloud APIs (Gemini/Claude)**.

---

## 🎯 Propósito y Valor del Proyecto

Cuando un agente de IA explora un proyecto grande sin un mapa de código, recurre a búsquedas masivas a ciegas (`grep` o lectura completa de archivos). Esto provoca:
* 💸 **Consumo masivo e innecesario de tokens** (30k - 100k tokens por tarea).
* ⏳ **Lentitud extrema y amnesia de contexto entre sesiones**.
* 💥 **Riesgo de bugs inesperados** por no conocer las dependencias indirectas.

### 🌟 La Solución de AetherGraph
AetherGraph actúa como un **GPS de código en tiempo real**:
* 📉 **Reduce el consumo de tokens en un 99.5%**: La IA consulta la herramienta MCP (`graph_neighborhood`, `graph_blast_radius` o `graph_search_concepts`) y salta directamente al archivo y línea exactos.
* ⚡ **Análisis sintáctico determinista de 23 lenguajes** a costo **$0 USD y <0.5 segundos**.
* 🕒 **Línea de Tiempo y Memoria de Sesiones Local (100% Gratis / SQLite)**: Registra el historial de acciones y decisiones de la IA en `.aether-graph/history.db` sin pagar servicios externos ni consumir tokens.
* 🎯 **Radio de Impacto en vivo y pre-Commit**: Permite evaluar exactamente qué clases y métodos se verán afectados antes de hacer `git push` (`aether-graph diff`).
* 📝 **Generador de ARCHITECTURE.md**: Exporta un mapa de arquitectura conciso (~150 tokens) que cualquier Agente de IA puede leer al iniciar (`aether-graph export-md`).
 * 🌐 **Dashboard Interactivo WebGL 2D/3D (`:9210`)**:
   - **Selector Nativo del OS (`📂 Seleccionar...`)**: Abre el explorador de archivos nativo de tu sistema operativo (Windows, macOS, Linux).
   - **Paneles Colapsables (`◀` / `▶`)**: Botones flotantes centrados para expandir el lienzo 2D/3D a pantalla completa.
   - **Auto-descubrimiento Multiplataforma**: Cero rutas estáticas (*hardcoded*); descubre automáticamente los proyectos del desarrollador.
   - **Grafo Semántico de IA e Historial**: Integra precalentamiento con Ollama (`llama3.2`, `qwen2.5`) para generar descripciones de código y el grafo de Arquitectura Global interconectado.
   - **Vista Semántica rediseñada**: comunidades por subsistema (`Subsistema: src/GameEngine.Core`) + **god nodes** destacados (los conceptos más conectados), con aristas etiquetadas `EXTRACTED`/`INFERRED`.
   - **Respetar `.gitignore` por proyecto**: toggle en el panel de settings (o `aether-graph gitignore on|off`) — con `on` solo los archivos versionados entran al grafo (menos ruido, menos llamadas LLM); `off` incluye todo lo escaneable.
   - **Estilos de grafo y forma de nodos (Paleta & Motor)**: selector de estilo — **Estándar** y **Neuronal** (tejido orgánico). **Neuronal en 3D** tiene dos modos: **Dibujo orgánico 2D en 3D** (default: halos respirando, enlaces con botones sinápticos y cometas — el estilo del 2D proyectado sobre el grafo 3D, respetando el **Estilo de Enlaces** sólido/punteado/curvo) y modo luces (vista Estándar + cometas, parpadeo de vértices y destello de nodos al recibir). En 2D también respeta el Estilo de Enlaces. Colores configurables: **Color de Nodos**, **Color de Ráfaga** y **Color de Vértices**. Selector de forma de nodos: **Círculos · Esferas** o **Cuadrados · Cubos**.
   - **Laboratorio de Comparación de Modelos**: Disponible en [`/comparison`](http://localhost:9210/comparison), compara el contexto generado por modelos locales y modelos de paga con el mismo nodo y prompt.

---

## 🛠️ Lenguajes Soportados Nativamente (23 Lenguajes a $0 Tokens)

AetherGraph incluye un motor sintáctico determinista que soporta nativamente el parsing de clases, funciones, módulos, herencia y llamadas en los siguientes lenguajes:

| Lenguaje / Framework | Extensiones | Elementos Extraídos |
|---|---|---|
| 🐍 **Python** | `.py` | Módulos, Clases, Funciones, Métodos, AST Python, Llamadas |
| 🐘 **PHP / Laravel** | `.php` | Namespaces, Clases, Traits, Interfaces, Métodos, Extends/Implements |
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

Además del código, AetherGraph indexa documentos en el mismo grafo:

| Formato | Extensiones | Qué extrae |
|---|---|---|
| **Docs** | `.md`, `.mdx`, `.rst`, `.txt` | Nodos de documento + aristas `referencia` entre docs (enlaces Markdown `[texto](ruta)` y `[[wikilinks]]`) — determinista, $0 |
| **PDF** | `.pdf` | Texto completo (Pasada 1, $0 local) → resumen semántico por LLM en la Pasada 2 |
| **Word** | `.docx` | Párrafos → resumen semántico |
| **Excel** | `.xlsx`, `.xlsm` | Hojas y filas → resumen semántico |
| **Imágenes** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp` | Descripción semántica por modelo de visión local (Ollama) |
| **Audio / Video** | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi` | Transcripción local (Whisper, CPU $0) → resumen semántico por LLM |

Las librerías de documentos son **opcionales** (el MCP stdio sigue siendo 100% stdlib):

```bash
pip install "aether-graph[multimodal]"   # pypdf + python-docx + openpyxl
pip install "aether-graph[media]"        # faster-whisper (transcripción local)
```

**Modelos de visión local** (RTX 3050 4GB):

```bash
ollama pull qwen3-vl:2b        # calidad (recomendado, ~15-40s/imagen)
ollama pull minicpm-v4.6:1b    # velocidad (~2-3s/imagen, 900MB VRAM)
```

Configuración: `AETHER_VISION_MODEL` (default `qwen3-vl:2b`), `AETHER_IMAGE_LIMIT` (0=ilimitado), `AETHER_WHISPER_MODEL` (default `small`), `AETHER_MEDIA_LIMIT` (0=ilimitado). Sin los extras instalados, los documentos igual entran al grafo como nodos (sin extracción de texto).

---

## 📦 Instalación Sencilla (1 Solo Comando - Sin Docker)

Instalar AetherGraph en cualquier sistema operativo requiere un único comando nativo de Pip:

```bash
# Instalar AetherGraph globalmente
pip install git+https://github.com/CaleroAM/openclaw.git#subdirectory=code-graph-host

# Iniciar el Dashboard WebGL interactivo en http://localhost:9210
aether-graph serve
```

---

## 🚀 Comandos CLI

AetherGraph incluye herramientas CLI integradas para interactuar directamente desde la terminal o scripts de automatización:

```bash
# Inicializar AetherGraph en el repositorio actual
aether-graph init

# Iniciar el servidor MCP por stdio para Agentes de IA
aether-graph mcp

# Iniciar el Dashboard WebGL interactivo en el puerto 9210
aether-graph serve

# Consultar la línea de tiempo del historial de acciones de la IA (SQLite Local)
aether-graph timeline

# Evaluar el radio de impacto de cambios sin confirmar (git status / git diff)
aether-graph diff

# Generar un archivo ARCHITECTURE.md compacto (~150 tokens) para Agentes de IA
aether-graph export-md

# Consultar conceptos o símbolos en el grafo
aether-graph query "sistema de autenticación"

# Explicar la responsabilidad y conexiones de un módulo o clase
aether-graph explain "TurnManager"

# Encontrar la ruta de conexiones más corta entre dos símbolos
aether-graph path "AuthService" "Database"

# Reindexar el repositorio con el motor de IA deseado
aether-graph reindex --engine ast_local_llm

# Instalar el hook post-commit: reindexado incremental automático tras cada commit
aether-graph hook install

# Configurar si el grafo respeta .gitignore (por proyecto)
aether-graph gitignore on --path .    # solo archivos versionados (default)
aether-graph gitignore off --path .   # incluir también lo ignorado
```

---

## 💻 Especificaciones de Hardware y Tiempos de Benchmark (Pruebas Reales)

### ⚙️ Hardware de Referencia de Pruebas
* **Procesador:** Intel Core i5-12500H (12a Gen, 16 Hilos / Cores)
* **Memoria RAM:** 15 GB RAM
* **Tarjeta de Video Dedicada:** **NVIDIA GeForce RTX 3050 Mobile (4 GB VRAM)** — CUDA activo
* **Gráficos Integrados:** Intel Iris Xe Graphics
* **Sistema Operativo:** NixOS 26.05 (Linux) — **Ollama 0.30.6** (con soporte CUDA 12.9)
* **Modelo IA Local (Ollama):** `llama3.2:latest`, `qwen2.5-coder:3b`, `qwen2.5-coder:7b`, `llama3.1:8b`

### 📊 Tiempos Reales de Reindexación (Proyecto AetherGraph: 50 Nodos · 44 Conectores · 11 Archivos)

| Motor Seleccionado | Tiempo Real (GPU RTX 3050 4GB) | Consumo de Tokens |
|---|---|---|
| `Solo AST (Puro)` | **0.147 seg** | **0 Tokens** |
| `AST + Local (Ollama qwen2.5-coder:3b)` | **~50 seg** (11 archivos + ~40 símbolos enriquecidos) | **0 Tokens (Local)** |

> El reindexado con IA local enriquece semánticamente cada **archivo**, cada **función/clase/método** (símbolo) y genera el resumen de arquitectura global (`ai_summary`), todo a **costo $0 USD** sin salir de tu máquina.
>
> **Modo incremental**: si el índice ya existe y el proyecto es un repo git, el reindex detecta los archivos cambiados con `git status` y **solo enriquece lo nuevo/modificado** (el resto conserva su contexto; ej. 0 cambios → 5-8s en un proyecto de 277 archivos vs ~5 min completos). Fuerza el reindex completo con `full: true` en el payload.
>
> **Configuración del motor** (env): `OLLAMA_HOST`, `OLLAMA_MODEL`, `AETHER_SYMBOL_LIMIT` (60), `AETHER_FILE_LIMIT` (0=ilimitado, para muestreo) y `AETHER_COMPACT=1` (segunda pasada inline que comprime cada descripción larga a ≤100 chars). Detalle completo del flujo en [`docs/contexto-comparativo.md`](docs/contexto-comparativo.md).

---

### 🤖 Benchmark Real de Modelos Locales (vía Ollama, GPU RTX 3050 4GB)

Pruebas ejecutadas con los **prompts reales de AetherGraph** (resumen de arquitectura global + resumen de archivo de código) sobre la instancia local de Ollama (`http://localhost:11434`). El modelo se selecciona vía la variable `OLLAMA_MODEL` (o auto-detección si no está definida):

```bash
OLLAMA_MODEL=qwen2.5-coder:3b aether-graph reindex --path . --engine ast_local_llm
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

Mismo nodo (`mcp_server.py`), mismo prompt real de AetherGraph (config #9), misma temperatura (0.2). Resultado crudo de cada modelo — incluida la respuesta del modelo actual verificado (**OpenCode · `opencode-go/gpt-5.6-luna`**), además de referencias históricas de DeepSeek:

| Modelo | Tiempo | Ejemplo de descripción generada |
|---|---|---|
| 💎💎💎 **OpenCode · `opencode-go/gpt-5.6-luna` (modelo actual verificado)** | Sesión actual | "Servidor MCP por stdio basado en JSON-RPC 2.0 que expone 7 herramientas para agentes de IA — consulta del grafo, radio de impacto, búsqueda semántica, historial de sesiones y registro de proyectos — lee el índice cacheado, registra operaciones en SQLite y entrega contexto sin consumir tokens del agente." |
| 💎💎 **DeepSeek V4 PRO (MAX · modelo de paga)** | ~10s (razonamiento) | "Servidor MCP por stdio (JSON-RPC 2.0) que expone 7 herramientas a agentes de IA — mapa de código, radio de impacto, búsqueda de conceptos e historial de sesiones — devolviendo el grafo cacheado del proyecto sin consumir tokens del agente." |
| 💎 **DeepSeek V4 Flash (opencode · modelo de paga)** | ~10-15s (razonamiento completo) | "Servidor MCP por stdio (JSON-RPC 2.0) que expone 7 herramientas para agentes de IA — grafo, radio de impacto, búsqueda de conceptos e historial de sesiones — sirviendo el grafo cacheado sin consumir tokens del agente." |
| 🦙 **`llama3.2:latest`** | 6.2s | "Es una unidad del sistema que proporciona un servidor de protocolo estándar (MCP, Model Context Protocol) para la plataforma AetherGraph, permitiendo a los agentes de IA interactuar con gráficos y realizar operaciones como buscar vecinos gráficos, detectar conceptos y más." |
| 👑 **`qwen2.5-coder:3b`** | 5.8s | "Define una API para el servidor de contexto del protocolo de modelo AetherGraph, que proporciona herramientas para AI agents como `graph_neighborhood`, `graph_blast_radius`, `graph_search_concepts` y `graph_register_project`." |
| ⚠️ **`qwen2.5-coder:7b`** | 18.6s | "Define funciones para procesar solicitudes de un servidor MCP y generar respuestas basadas en un análisis del código fuente, sirviendo como la unidad principal del sistema para el protocolo Stdio Model Context Protocol (MCP) en AetherGraph." |
| ⚠️ **`llama3.1:8b`** | 18.0s | "Es un servidor de protocolo de contexto modelo (MCP) para AetherGraph, que proporciona herramientas para agentes de inteligencia artificial y gestiona la representación gráfica del espacio de trabajo." |

> Los 7 resultados identifican correctamente `mcp_server.py` como servidor MCP. **`qwen2.5-coder:3b` es el local más preciso** (nombra las tools reales, 5.8s, 100% GPU), y su calidad se acerca al **90-95% del modelo actual verificado**. El modelo actual añade el nivel más completo de contexto: protocolo, herramientas, flujo de lectura, persistencia SQLite y ausencia de consumo de tokens.

---

## 🤖 Integración con Agentes de IA (MCP Protocol)

AetherGraph es un servidor MCP estándar por entrada/salida estándar (`stdio`) que expone **7 herramientas** a los agentes de IA, organizadas en tres grupos: **mapa de código**, **memoria de sesiones** e **integración**.

### 🧭 Herramientas de Mapa de Código (0 Tokens)

| Herramienta | Qué hace | Parámetros |
|---|---|---|
| `graph_neighborhood` | Devuelve el mapa del proyecto: nodos (archivos, clases, funciones), conectores con confianza `EXTRACTED`/`INFERRED` y descripciones semánticas por nodo. Con `symbol` devuelve solo el subgrafo alrededor de ese símbolo (payload compacto para el agente). | `path`, `symbol`, `depth` (todos opcionales) |
| `graph_blast_radius` | Calcula el radio de impacto de modificar un símbolo o archivo: recorre el grafo y devuelve los nodos afectados por salto (hop) con la confianza de cada arista. | `symbol` (obligatorio), `depth` (default 2) |
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
| `graph_register_project` | Registra autónomamente una ruta de proyecto en AetherGraph para que aparezca en el dashboard (`:9210`). | `path` (obligatorio), `name` (opcional) |

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
    "aether-graph": {
      "command": "aether-graph",
      "args": ["mcp", "--path", "/ruta/a/tu/proyecto"]
    }
  }
}
```

### 2. Anthropic Claude Code
Agrega en tu archivo `~/.claude/CLAUDE.md`:

```markdown
- **AetherGraph MCP**: Servidor de contexto topológico AST, radio de impacto e historial de sesiones.
  Comando MCP: `aether-graph mcp`
```

### 3. OpenAI Codex / Cursor / Windsurf
Agrega en tu configuración `AGENTS.md` o archivo `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "aether-graph": {
      "command": "aether-graph",
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
    "aether-graph": {
      "type": "local",
      "command": ["aether-graph", "mcp", "--path", "/ruta/a/tu/proyecto"],
      "enabled": true
    }
  }
}
```

Las herramientas quedan disponibles como `aether-graph_graph_neighborhood`, `aether-graph_graph_blast_radius`, etc. El argumento `--path` fija el proyecto del grafo; si lo omites, el servidor usa el directorio de trabajo actual.

### 5. Entornos Aislados (Contenedores / VMs)
El MCP por `stdio` es **100% stdlib de Python** (no requiere `fastapi`/`uvicorn` ni instalación vía pip). Para ejecutarlo dentro de un contenedor Docker o una VM sin paquete instalado, basta con montar o compartir el código fuente y definir `PYTHONPATH`:

```bash
export PYTHONPATH="/ruta/compartida/aether-graph${PYTHONPATH:+:$PYTHONPATH}"
export AETHER_DAEMON_URL="http://IP_DEL_HOST:9210"   # opcional: daemon del dashboard para graph_register_project
python3 -m aether_graph.cli mcp --path /ruta/al/proyecto
```

- `AETHER_DAEMON_URL`: dentro de un contenedor, `127.0.0.1:9210` no apunta al daemon del dashboard (que vive en el host). Apunta esta variable a la IP del host (ej. la IP gateway de la VM) para que `graph_register_project` registre proyectos en el dashboard.
- Las herramientas de grafo e historial funcionan standalone (leen el índice cacheado o escanean el código) sin depender del daemon.

#### Ejemplo real: OpenClaw en una VM (wrapper `mcp_openclaw.sh`)
El repositorio incluye [`mcp_openclaw.sh`](mcp_openclaw.sh), un wrapper usado para conectar AetherGraph con un agente **OpenClaw** que corre dentro de una VM: el contenedor `openclaw-agent` monta por bind el `Documentos` del host en `/home/node/proyectos`, así que el script exporta el `PYTHONPATH` con la ruta del contenedor, apunta `AETHER_DAEMON_URL` a la IP gateway de la VM (`192.168.122.1`) y arranca el MCP con la ruta del proyecto en el contenedor. Se registra en el `openclaw.json` del agente:

```json
{
  "mcp": {
    "servers": {
      "aether-graph": {
        "command": "bash",
        "args": ["/ruta/en/el/contenedor/aether-graph/mcp_openclaw.sh"]
      }
    }
  }
}
```

Copia el wrapper y ajusta las tres rutas/env a tu infraestructura (es un ejemplo de tu entorno, no parte del paquete PyPI).

---

## 🏆 Comparativa de Mercado

*Verificado contra la versión actual de Graphify (Graphify-Labs, v8) y LSIF/Sourcegraph (ago 2026). Fuentes: README v8 de `Graphify-Labs/graphify` (GitHub), graphify.com y benchmarks publicados (BENCHMARKS.md, LOCOMO, LongMemEval-S).*

| Característica | 📦 Graphify (v8) | 🌐 Sourcegraph / LSIF | 🌌 AetherGraph |
|---|---|---|---|
| **Parsing Estático Multi-Lenguaje** | **Sí** (tree-sitter, 37+ gramáticas + Apex/Terraform/OCaml/Lisp, local, $0) | Sí (LSIF, preciso vía language servers) | Sí (AST nativo 23 lenguajes a $0) |
| **Descripción semántica por nodo de CÓDIGO (rol en lenguaje natural)** | ❌ No: "code is parsed with tree-sitter AST: deterministic, no LLM"; el pase semántico es solo para docs/PDFs/media | ❌ No | ✅ **Sí: cada archivo/clase/función tiene descripción de rol generada por LLM local o cloud** |
| **Etiquetas de confianza en aristas** | ✅ EXTRACTED / INFERRED / AMBIGUOUS por arista | Parcial | ✅ **EXTRACTED (contiene/hereda) / INFERRED (usa cross-file) / AMBIGUOUS (nombre repetido en varios símbolos)** |
| **Consumo de Tokens (grafo de código)** | 0 (tree-sitter local) | 0 (dump LSP) | **0 en Pasada 1** + Enriquecimiento Opcional (local = 0) |
| **Reindexado incremental** | ✅ `--update` + hook post-commit (AST) | ❌ Dump completo típicamente | ✅ **git-status (solo versionados) + solo nodos cambiados (medido: 2.6s vs 96s full)** |
| **Compactación de densidad (≤140 chars/nodo)** | N/A (no describe código con LLM) | N/A | ✅ `AETHER_COMPACT=1` (local a +5% de la densidad premium) |
| **Memoria de historial de acciones del agente** | ❌ (query log opcional; no timeline de acciones) | ❌ | ✅ **SQLite local (`graph_history_*`) gratuito + `tokens_avoided` por consulta** |
| **Visualizador** | graph.html estático interactivo (comunidades, click) | No | Dashboard WebGL 2D/3D en vivo (`:9210`) |
| **Impacto de cambios** | ✅ PR impact / triage / conflictos entre PRs (`graphify prs`) | Parcial en CLI | ✅ `aether-graph diff` (git, pre-commit) + inspector |
| **MCP** | ✅ stdio + HTTP compartido con API key (7 tools: query_graph/get_node/get_neighbors/shortest_path/list_prs/get_pr_impact/triage_prs) | No nativo | ✅ stdio (7 tools: grafo + historial + registro), 100% stdlib (corre en contenedores sin instalación) |
| **Multi-modal (docs/PDFs/imagen/video en el mismo grafo)** | ✅ docs, PDFs, imágenes, video/audio, SQL, configs | Parcial | ✅ docs (MD/RST/TXT con aristas de referencia), PDF, DOCX, XLSX, **imágenes por visión local** y **audio/video por transcripción local** — todo $0 |
| **Benchmarks publicados** | ✅ LOCOMO recall@10 0.497 · LongMemEval-S 76% QA (metodología reproducible) | Parcial | ✅ [BENCHMARKS.md](BENCHMARKS.md) (tiempos reales de reindex, modelos locales, payloads MCP) |
| **Ecosistema / Plataformas** | ✅ 20+ asistentes con instalador oficial (incluye OpenCode y OpenClaw), 108k estrellas | Empresa | ✅ MCP estándar (Antigravity, Claude Code, Codex/Cursor/Windsurf, OpenCode, OpenClaw) |
| **Soporte Offline** | ✅ código 100% local; docs requieren API | Depende del servidor | ✅ 100% offline con Ollama local |

**Lectura honesta:** Graphify es más maduro en cobertura de lenguajes (37+), ecosistema (20+ asistentes, 108k estrellas), flujo de PRs (impact/triage/conflictos), multi-modalidad y benchmarks de calidad de respuestas. AetherGraph gana en **contexto semántico en lenguaje natural sobre el código** (archivos/clases/funciones con rol — Graphify explícitamente no usa LLM sobre código), **historial de sesiones del agente con métricas de ahorro**, **compactación de densidad**, **portabilidad extrema del MCP** (stdlib puro, sin instalación) y **reindexado incremental medido**. Las tres herramientas comparten la base determinista de $0 tokens; AetherGraph añade la capa semántica que Graphify aplica solo a documentos.

---

## 📜 Licencia

Publicado bajo la Licencia **MIT** — Código libre para la comunidad de desarrolladores e investigadores de IA.
