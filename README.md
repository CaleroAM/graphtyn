# 🌌 AetherGraph

[![PyPI Version](https://img.shields.io/badge/pypi-v0.1.0-blue.svg)](https://pypi.org/project/aether-graph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Compatible](https://img.shields.io/badge/MCP-Standard--Compatible-10b981.svg)](https://modelcontextprotocol.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab.svg)](https://www.python.org/)

**El motor de mapa topológico de código y servidor MCP estándar para Agentes de IA (Google Antigravity, Claude Code, Codex, Cursor y Windsurf).**

AetherGraph convierte cualquier repositorio de código en un **grafo de conocimiento determinista de 2 pasadas**: analiza la estructura de archivos, módulos, clases, métodos y llamadas con **0 tokens de consumo** en 0.05 segundos y enriquece semánticamente los nodos principales mediante **IA Local (Ollama Qwen2.5)** o **Cloud APIs (Gemini/Claude)**.

---

## 🎯 Propósito y Valor del Proyecto

Cuando un agente de IA explora un proyecto grande sin un mapa de código, recurre a búsquedas masivas a ciegas (`grep` o lectura completa de archivos). Esto provoca:
* 💸 **Consumo masivo e innecesario de tokens** (30k - 100k tokens por tarea).
* ⏳ **Lentitud extrema y pérdida de foco**.
* 💥 **Riesgo de bugs inesperados** por no conocer las dependencias indirectas.

### 🌟 La Solución de AetherGraph
AetherGraph actúa como un **GPS de código en tiempo real**:
* 📉 **Reduce el consumo de tokens en un 99.5%**: La IA consulta la herramienta MCP (`graph_neighborhood` o `graph_blast_radius`) y salta directamente al archivo y línea exactos.
* ⚡ **Análisis sintáctico determinista de 10 lenguajes** (`C#`, `PHP`, `Python`, `JS/TS`, `Java`, `Go`, `Rust`, `Ruby`, `C/C++`, `Unity Assets`).
* 🎯 **Radio de Impacto en vivo**: Permite ver exactamente qué módulos se romperán antes de editar una línea.
* 🌐 **Dashboard Interactivo WebGL 2D/3D**: Visualizador en el puerto `9210` con 9 paletas de color, físicamente dinámicas, auto-rotación 3D y 3 modos de vista.

---

## 📦 Instalación

```bash
pip install aether-graph
```

O clonando el repositorio para desarrollo local:

```bash
git clone https://github.com/CaleroAM/openclaw.git
cd openclaw/code-graph-host
pip install -e .
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
aether-graph serve --reload

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

## 💻 Especificaciones de Rendimiento y Tiempos Reales

### ⚙️ Hardware de Referencia de Pruebas
* **Procesador:** Intel Core i7 / AMD Ryzen 7
* **Memoria RAM:** 32 GB RAM
* **Gráficos:** iGPU / GPU integrada Linux Ubuntu 24.04
* **Modelo IA Local:** `qwen2.5-coder:0.5b` (Vía Ollama local)

### 📊 Tiempos Reales de Reindexación

| Proyecto | Archivos / Símbolos | Motor Seleccionado | Tiempo Estimado / Real | Consumo de Tokens |
|---|---|---|---|---|
| **calculadora-stats** | 15 Nodos · 14 Conectores | `Solo AST (Puro)` | **0.03 segundos** | **0 Tokens** |
| **calculadora-stats** | 15 Nodos · 14 Conectores | `AST + Local (Ollama)` | **~1.5 segundos** | **0 Tokens (Local)** |
| **UnityCommerceDemo** | 970 Nodos · 1,682 Conectores | `Solo AST (Puro)` | **0.05 segundos** | **0 Tokens** |
| **UnityCommerceDemo** | 970 Nodos · 1,682 Conectores | `AST + Local (Ollama)` | **~2.5 minutos** | **0 Tokens (Local)** |
| **t-magneto** (Laravel/PHP) | 2,250 Nodos · 7,426 Conectores (8,700 .php) | `Solo AST (Puro)` | **0.08 segundos** | **0 Tokens** |
| **t-magneto** (Laravel/PHP) | 2,250 Nodos · 7,426 Conectores (8,700 .php) | `AST + Local (Ollama)` | **~6.5 minutos** | **0 Tokens (Local)** |

> 💡 **Nota para equipos de alto rendimiento:** Si cuentas con una GPU dedicada (NVIDIA RTX 3080/4090), puedes utilizar modelos locales más grandes como `qwen2.5-coder:7b` o `qwen2.5-coder:14b`, obteniendo respuestas sub-segundo con máxima riqueza en la descripción de conceptos.

---

## 🤖 Integración con Agentes de IA (MCP Protocol)

AetherGraph es un servidor MCP estándar por entrada/salida estándar (`stdio`).

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
- **AetherGraph MCP**: Servidor de contexto topológico AST y radio de impacto.
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

| Característica | 📦 Graphify Labs | 🌐 Sourcegraph / LSIF | 🌌 AetherGraph |
|---|---|---|---|
| **Parsing Estático Multi-Lenguaje** | No (Llama a API pagada de Claude) | Sí (LSIF estático) | **Sí (AST Nativo 10 lenguajes a $0)** |
| **Consumo de Tokens** | **Alto** (Paga por cada archivo leído) | 0 Tokens | **0 Tokens en Pasada 1** + Enriquecimiento Opcional |
| **Visualizador Interactivo** | Exporta HTML estático plano | No tiene | **Dashboard WebGL 2D/3D en Vivo (`:9210`)** |
| **Radio de Impacto Interactivo** | No | Parcial en CLI | **Sí (Inspector interactivo con aislamiento y foco)** |
| **Vistas de Grafo** | 1 (Notas / Markdown) | 1 (Código) | **3 Vistas: Code AST, Semántico IA, Harness Topology** |
| **Soporte Offline sin Internet** | No (Requiere Anthropic API) | Depende del servidor | **100% Funcional Offline con Ollama Local** |

---

## 📜 Licencia

Publicado bajo la Licencia **MIT** — Código libre para la comunidad de desarrolladores e investigadores de IA.
