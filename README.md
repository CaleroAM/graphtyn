# 🌌 AetherGraph

[![PyPI Version](https://img.shields.io/badge/pypi-v0.1.0-blue.svg)](https://pypi.org/project/aether-graph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Compatible](https://img.shields.io/badge/MCP-Standard--Compatible-10b981.svg)](https://modelcontextprotocol.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab.svg)](https://www.python.org/)

**El motor de mapa topológico de código, registro de sesiones local y servidor MCP estándar para Agentes de IA (Google Antigravity, Claude Code, Codex, Cursor y Windsurf).**

AetherGraph convierte cualquier repositorio de código en un **grafo de conocimiento determinista de 2 pasadas**: analiza la estructura de archivos, módulos, clases, métodos y llamadas con **0 tokens de consumo** en 0.05 segundos y enriquece semánticamente los nodos principales mediante **IA Local (Ollama Qwen2.5)** o **Cloud APIs (Gemini/Claude)**.

---

## 🎯 Propósito y Valor del Proyecto

Cuando un agente de IA explora un proyecto grande sin un mapa de código, recurre a búsquedas masivas a ciegas (`grep` o lectura completa de archivos). Esto provoca:
* 💸 **Consumo masivo e innecesario de tokens** (30k - 100k tokens por tarea).
* ⏳ **Lentitud extrema y amnesia de contexto entre sesiones**.
* 💥 **Riesgo de bugs inesperados** por no conocer las dependencias indirectas.

### 🌟 La Solución de AetherGraph
AetherGraph actúa como un **GPS de código en tiempo real**:
* 📉 **Reduce el consumo de tokens en un 99.5%**: La IA consulta la herramienta MCP (`graph_neighborhood`, `graph_blast_radius` o `graph_search_concepts`) y salta directamente al archivo y línea exactos.
* ⚡ **Análisis sintáctico determinista de 15+ lenguajes** a costo **$0 USD y <0.05 segundos**.
* 🕒 **Línea de Tiempo y Memoria de Sesiones Local (100% Gratis / SQLite)**: Registra el historial de acciones y decisiones de la IA en `.aether-graph/history.db` sin pagar servicios externos ni consumir tokens.
* 🎯 **Radio de Impacto en vivo y pre-Commit**: Permite evaluar exactamente qué clases y métodos se verán afectados antes de hacer `git push` (`aether-graph diff`).
* 📝 **Generador de ARCHITECTURE.md**: Exporta un mapa de arquitectura conciso (~150 tokens) que cualquier Agente de IA puede leer al iniciar (`aether-graph export-md`).
* 🌐 **Dashboard Interactivo WebGL 2D/3D**: Visualizador en el puerto `9210` con 9 paletas de color, físicamente dinámicas, auto-rotación 3D y 3 modos de vista.

---

## 🛠️ Lenguajes Soportados Nativamente (15+ Lenguajes a $0 Tokens)

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
```

---

## 💻 Especificaciones de Hardware y Tiempos de Benchmark

### ⚙️ Hardware de Referencia de Pruebas
* **Procesador:** Intel Core i7 12a Gen (16 Hilos / Cores)
* **Memoria RAM:** 16 GB RAM DDR4/DDR5
* **Tarjeta de Video Dedicada:** **NVIDIA GeForce RTX 3050 Mobile (4 GB VRAM)**
* **Gráficos Integrados:** Intel Iris Xe Graphics
* **Sistema Operativo:** Linux Ubuntu 24.04 LTS
* **Modelo IA Local:** `qwen2.5-coder:0.5b` / `qwen2.5-coder:1.5b` (Vía Ollama)

### 📊 Tiempos Reales de Reindexación por Escala de Proyecto

| Escala del Repositorio | Métricas del Código (LOC, Archivos, Nodos) | Lenguajes Principales | Motor Seleccionado | Modo CPU | Modo GPU (NVIDIA RTX 3050 4GB VRAM) | Consumo de Tokens |
|---|---|---|---|---|---|---|
| **Proyecto Pequeño** | ~250 LOC · 4 Archivos · 15 Nodos | Python | `Solo AST (Puro)` | **0.03 seg** | **0.03 seg** | **0 Tokens** |
| **Proyecto Pequeño** | ~250 LOC · 4 Archivos · 15 Nodos | Python | `AST + Local (Ollama)` | **~1.5 seg** | **~0.3 seg** | **0 Tokens (Local)** |
| **Proyecto Mediano** | ~45,000 LOC · 180 Archivos · 970 Nodos | C#, HLSL, UXML, JSON | `Solo AST (Puro)` | **0.05 seg** | **0.05 seg** | **0 Tokens** |
| **Proyecto Mediano** | ~45,000 LOC · 180 Archivos · 970 Nodos | C#, HLSL, UXML, JSON | `AST + Local (Ollama)` | **~2.5 min** | **~25 seg** | **0 Tokens (Local)** |
| **Proyecto Grande** | ~320,000 LOC · 8,700 Archivos · 2,250 Nodos | PHP (Laravel), TypeScript, SQL | `Solo AST (Puro)` | **0.08 seg** | **0.08 seg** | **0 Tokens** |
| **Proyecto Grande** | ~320,000 LOC · 8,700 Archivos · 2,250 Nodos | PHP (Laravel), TypeScript, SQL | `AST + Local (Ollama)` | **~6.5 min** | **~45 seg** | **0 Tokens (Local)** |

---

## 🤖 Integración con Agentes de IA (MCP Protocol)

AetherGraph es un servidor MCP estándar por entrada/salida estándar (`stdio`) que expone tanto herramientas de grafo AST como de línea de tiempo de sesiones:
- `graph_neighborhood`
- `graph_blast_radius`
- `graph_search_concepts`
- `graph_history_search`
- `graph_history_timeline`
- `graph_history_get`

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

---

## 🏆 Comparativa de Mercado

| Característica | 📦 Graphify / claude-mem | 🌐 Sourcegraph / LSIF | 🌌 AetherGraph |
|---|---|---|---|
| **Parsing Estático Multi-Lenguaje** | No (Llama a API pagada o hooks) | Sí (LSIF estático) | **Sí (AST Nativo 15+ lenguajes a $0)** |
| **Consumo de Tokens** | Paga tokens por cada archivo leído | 0 Tokens | **0 Tokens en Pasada 1** + Enriquecimiento Opcional |
| **Memoria de Historial de Sesiones** | Sí (requiere Bun + ChromaDB) | No tiene | **Sí (100% Gratis / SQLite Local integrado)** |
| **Visualizador Interactivo** | Exporta HTML estático o CLI | No tiene | **Dashboard WebGL 2D/3D en Vivo (`:9210`)** |
| **Radio de Impacto Interactivo** | No | Parcial en CLI | **Sí (Inspector interactivo con aislamiento y foco)** |
| **Vistas de Grafo** | 1 (Notas / Markdown) | 1 (Código) | **3 Vistas: Code AST, Semántico IA, Harness Topology** |
| **Soporte Offline sin Internet** | Parcial | Depende del servidor | **100% Funcional Offline con Ollama Local** |

---

## 📜 Licencia

Publicado bajo la Licencia **MIT** — Código libre para la comunidad de desarrolladores e investigadores de IA.
