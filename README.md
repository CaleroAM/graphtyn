# 🌌 AetherGraph (`aether-graph`)

> **Zero-Token AST Deterministic + Hybrid Semantic RAG Graph for AI Coding Agents (MCP & CLI)**

`AetherGraph` es un motor de contexto e indexación determinista ultra-rápido para agentes de código (Claude Code, Cursor, Windsurf, Antigravity, OpenClaw).

A diferencia de las herramientas de grafos pesadas basadas en LLMs que consumen miles de dólares en tokens y sufren de alucinaciones, `AetherGraph` analiza la estructura real del código usando **AST (Abstract Syntax Tree)** determinista en milisegundos a costo **$0.00 USD**.

---

## 🌟 Características Principales

1. **Zero-Token AST Code Engine:** Extrae clases, funciones, llamadas e importaciones sin realizar una sola llamada a APIs de LLMs.
2. **Protocolo MCP Estándar (Model Context Protocol):** Expone las herramientas `graph_neighborhood` y `graph_blast_radius` directamente a agentes de IA vía `stdio`.
3. **Estructura por Repositorio (`.aether-graph/`):** Almacena el mapa del proyecto localmente de forma limpia sin ensuciar la raíz del código.
4. **Visualizador WebGL 3D/2D Local:** Servidor en vivo (puerto `9210`) para explorar visualmente la red del código y gobernanza de agentes.
5. **Cero Dependencias Pesadas:** Cero servidores Docker obligatorios para desarrollo local; instalable con un simple `pip install -e .`.

---

## 🚀 Uso Rápido (CLI)

```bash
# Inicializar .aether-graph/ en el proyecto actual
aether-graph init

# Construir el mapa AST determinista
aether-graph build

# Consultar relaciones y radio de impacto de una función
aether-graph query "MyFunction"

# Levantar el servidor WebGL 3D visualizador (puerto 9210)
aether-graph serve --port 9210
```

---

## ⚙️ Conexión como Servidor MCP (Claude Code / Cursor / Windsurf)

Agrega lo siguiente a tu archivo `mcpServers` (ej. `~/.claude/claude.json`):

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

## 🐳 Despliegue con Docker / Docker Compose

```bash
docker compose up -d
```

El demonio estará disponible en `http://localhost:9210`.

---

## 📜 Licencia

MIT License — Libre para uso personal, Open Source y Comercial.
