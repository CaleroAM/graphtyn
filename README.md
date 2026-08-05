# AetherGraph (`aether-graph`)

> **Motor de contexto de código determinista — Grafo AST + Semántico híbrido con visualizador WebGL y protocolo MCP para agentes de IA.**

---

## Propósito

AetherGraph analiza la estructura real de un proyecto de software usando **AST (Abstract Syntax Tree)** determinista y la convierte en un **grafo interactivo de nodos y conexiones** navegable en 2D y 3D. Proporciona contexto estructural preciso a agentes de IA (Antigravity, Claude Code, Cursor, Gemini, OpenClaw) vía protocolo MCP, sin consumir tokens de LLM para el análisis base.

A diferencia de herramientas de grafo que dependen de embeddings o llamadas a LLM para construir el mapa del código, AetherGraph lo hace en **milisegundos a costo $0** utilizando el árbol de sintaxis abstracto del lenguaje (Python, C#, JavaScript/TypeScript).

---

## Valor de Mercado — Por qué elegir AetherGraph vs otras herramientas

| Característica | AetherGraph | Graphify / Obsidian Graph | CodeGraph / Sourcegraph |
|---|---|---|---|
| Analiza código real (AST) | **Si** | No (solo Markdown) | Si (requiere servidor pesado) |
| Costo de indexación | **$0 USD** | $0 | $$$ Cloud |
| Velocidad de indexación | **<50ms** | — | Minutos |
| Motor IA local opcional | **Si (Ollama)** | No | No |
| Motor IA Cloud opcional | **Si (Gemini/Claude)** | No | Si |
| Protocolo MCP estándar | **Si** | No | No |
| Topología de agentes IA | **Si (OpenClaw/Hermes)** | No | No |
| Proyectos Unity / C# | **Si** | No | Limitado |
| Visualizador 2D + 3D | **Si** | Solo 2D | Solo 2D |
| Configurable por agente IA | **Si (AGY, Claude, Codex)** | No | No |
| Licencia | **MIT** | MIT | Propietaria |

---

## Motor de Reindexación — IA Local vs IA Cloud

AetherGraph soporta tres motores de reindexación. **No hay que escoger uno solo** — puedes usar el motor puro para indexación rápida y cambiar a semántico cuando necesitas profundidad.

| Criterio | AST Puro (Cero tokens) | IA Local (Ollama) | IA Cloud (Gemini/Claude/OpenAI) |
|---|---|---|---|
| **Costo** | $0.00 | $0.00 (hardware local) | $0.001–$0.02 / 1K tokens |
| **Velocidad** | <50 ms | 2–10 s (depende del modelo) | 1–5 s (depende de la red) |
| **Privacidad** | Total — sin envío de datos | Total — todo local | Código se envía al proveedor |
| **Calidad semántica** | Estructural (no semántico) | Alta (Qwen2.5-Coder, Nomic) | Muy alta (Gemini, Claude) |
| **Requiere conexión** | No | No | Si |
| **Tamaño proyecto** | Ilimitado | Limitado por RAM/GPU | Limitado por contexto del API |
| **Modelos soportados** | — | `qwen2.5-coder`, `nomic-embed-text`, `codellama`, `deepseek-coder` | `gemini-2.0-flash`, `claude-sonnet-4`, `gpt-4o` |
| **Configurable por agente** | Si | Si (AGY, Claude Code, Codex) | Si (AGY, Claude Code, Codex) |

> **Recomendación:** Usa **AST Puro** para indexación cotidiana rápida. Usa **Ollama + `nomic-embed-text`** (el mismo modelo que usa OpenClaw) para análisis semántico profundo sin costo. Usa **Cloud API** cuando necesitas máxima precisión en proyectos complejos.

---

## Modelos de IA Recomendados

### IA Local (Ollama — $0 / Privacidad Total)
```bash
# Instalación única
curl -fsSL https://ollama.com/install.sh | sh

# Para análisis de código (generación / comprensión)
ollama run qwen2.5-coder

# Para embeddings semánticos (el mismo que usa OpenClaw internamente)
ollama pull nomic-embed-text

# Para proyectos grandes
ollama run codellama:13b
```

AetherGraph se conecta automáticamente a `http://localhost:11434` (o a `OLLAMA_HOST` si está definido).

### IA Cloud API (Gemini / Claude / OpenAI)
```bash
# Gemini (recomendado — mismo ecosistema que AGY / Antigravity)
export GEMINI_API_KEY="AIzaSy..."

# Claude (excelente para razonamiento sobre código)
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI / Codex
export OPENAI_API_KEY="sk-..."
```

O añade las llaves en el archivo `.env` (ver `.env.example`).

### Configuración por Agente de IA (AGY, Claude Code, Codex)
Un agente de IA puede registrar proyectos, cambiar el motor de reindexación y lanzar la reindexación de forma autónoma vía MCP:

```json
// ~/.claude/claude.json  (Claude Code)
{
  "mcpServers": {
    "aether-graph": {
      "command": "aether-graph",
      "args": ["mcp"]
    }
  }
}
```

```jsonc
// AGY (Antigravity) — skills / MCP sidecar
{
  "name": "aether-graph",
  "command": "aether-graph mcp",
  "env": { "GEMINI_API_KEY": "..." }
}
```

---

## Instalación Rápida

```bash
pip install -e .
cp .env.example .env   # Configura tus llaves opcionalmente

# Levantar el visualizador (puerto 9210)
aether-graph serve --port 9210
```

O con Docker:

```bash
docker compose up -d
```

---

## Uso CLI

```bash
# Indexar el proyecto actual
aether-graph build

# Consultar radio de impacto de una función
aether-graph query "MiFuncion"

# Levantar servidor WebGL
aether-graph serve --port 9210
```

---

## Patrón de Desarrollo Autónomo (Hot-Reload)

```yaml
services:
  aether-graph:
    build: .
    container_name: aether-graph-daemon
    ports:
      - "9210:9210"
    volumes:
      - ./.aether-graph:/app/.aether-graph
      - ./aether_graph:/app/aether_graph   # live code mount
      - ../:/workspace:ro
    command: ["aether-graph", "serve", "--host", "0.0.0.0", "--port", "9210", "--reload"]
    restart: unless-stopped
```

---

## Licencia

MIT License — Libre para uso personal, Open Source y Comercial.
