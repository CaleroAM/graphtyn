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
* 📉 **Reduce el consumo de tokens en un 99.5%**: La IA consulta la herramienta MCP (`graph_neighborhood`, `graph_blast_radius` o `graph_search_concepts`) y salta directamente al archivo y línea exactos.
* ⚡ **Análisis sintáctico determinista de 15+ lenguajes** (`C#`, `PHP`, `Python`, `JS/TS`, `Java`, `Go`, `Rust`, `Ruby`, `C/C++`, `Kotlin`, `Swift`, `Dart`, `Shell`, `SQL`, `Vue`, `Svelte`, `Unity Assets`).
* 🎯 **Radio de Impacto en vivo**: Permite ver exactamente qué módulos se romperán antes de editar una línea.
* 🌐 **Dashboard Interactivo WebGL 2D/3D**: Visualizador en el puerto `9210` con 9 paletas de color, físicamente dinámicas, auto-rotación 3D y 3 modos de vista.

---

## 📦 Guía de Instalación (Con Docker y Sin Docker)

AetherGraph se puede ejecutar en cualquier sistema operativo en segundos. Elige la opción que prefieras:

### 1️⃣ Opción A: Instalación Directa sin Docker (Desde GitHub - Recomendada)
Para usuarios que no usan Docker. Puedes instalarlo directamente en 1 comando desde GitHub:

```bash
# Instalar directamente desde el repositorio (Próximamente en PyPI via pip install aether-graph)
pip install git+https://github.com/CaleroAM/openclaw.git#subdirectory=code-graph-host

# Iniciar el Dashboard visual en http://localhost:9210
aether-graph serve
```

---

### 2️⃣ Opción B: Ejecución con Docker (Para Servidores o Entornos Aislados)
Si prefieres mantener tu sistema aislado o correr en servidores:

```bash
# Ejecutar contenedor Docker montando tu código local
docker run -d -p 9210:9210 -v /ruta/a/tu/proyecto:/workspace --name aether-graph ghcr.io/caleroam/aether-graph
```

---

### 3️⃣ Opción C: Desde Código Fuente (Para Desarrolladores)
Si deseas modificar el código o contribuir al proyecto:

```bash
git clone https://github.com/CaleroAM/openclaw.git
cd openclaw/code-graph-host
pip install -e .
aether-graph serve --reload
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

> 💡 **Nota sobre la VRAM / Memoria de Video:**  
> Si ejecutas en Linux y observas que Ollama corre en CPU en lugar de la GPU NVIDIA RTX 3050, se debe habitualmente a una desincronización temporal del módulo del kernel tras una actualización del paquete del sistema (`NVML driver mismatch`). Tras un reinicio del equipo, Docker/Ollama toman automáticamente la **NVIDIA RTX 3050 de 4GB VRAM**, acelerando la reindexación con IA hasta **10 veces más rápido**.

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
| **Parsing Estático Multi-Lenguaje** | No (Llama a API pagada de Claude) | Sí (LSIF estático) | **Sí (AST Nativo 15+ lenguajes a $0)** |
| **Consumo de Tokens** | **Alto** (Paga por cada archivo leído) | 0 Tokens | **0 Tokens en Pasada 1** + Enriquecimiento Opcional |
| **Visualizador Interactivo** | Exporta HTML estático plano | No tiene | **Dashboard WebGL 2D/3D en Vivo (`:9210`)** |
| **Radio de Impacto Interactivo** | No | Parcial en CLI | **Sí (Inspector interactivo con aislamiento y foco)** |
| **Vistas de Grafo** | 1 (Notas / Markdown) | 1 (Código) | **3 Vistas: Code AST, Semántico IA, Harness Topology** |
| **Soporte Offline sin Internet** | No (Requiere Anthropic API) | Depende del servidor | **100% Funcional Offline con Ollama Local** |

---

## 📜 Licencia

Publicado bajo la Licencia **MIT** — Código libre para la comunidad de desarrolladores e investigadores de IA.
