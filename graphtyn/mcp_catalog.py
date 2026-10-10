"""Declarative MCP tool catalogue and profile filtering."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .core.topic_contracts import TOPIC_TOOLS


_BASE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "graph_query_intent",
        "description": "Ruta principal adaptativa. Usa grafo compacto y, cuando la pregunta exige orden/condiciones/ciclo de vida, adjunta fragmentos mínimos de fuente. Devuelve complete_for y do_not_expand.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "Pregunta o tarea completa"},
                "intent": {"type": "string", "enum": ["auto", "overview", "flow", "bindings", "persistence", "tests", "impact"]},
                "limit": {"type": "integer", "description": "Máximo de entidades; default 10"},
                "evidence_mode": {"type": "string", "enum": ["auto", "compact", "balanced", "precision"], "description": "auto amplía solo preguntas que necesitan evidencia del cuerpo"},
                "extends_context_id": {"type": "string", "description": "Contexto previo para devolver sólo evidencia nueva"},
                "expected_project": {"type": "string", "description": "Nombre, ID o ruta que el cliente espera; la llamada falla si no coincide"},
                "path": {"type": "string", "description": "Ruta del proyecto; si se omite usa el workspace del MCP"}
            },
            "required": ["request"]
        }
    },
    {
        "name": "graph_analyze_change",
        "description": "Primera opción para flujos, bindings, persistencia e impacto. Devuelve targets, contratos, estado y operaciones internas compactas (ops). Responde con esa evidencia; expande sólo si falta un hecho y cita aliases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "Issue, requisito o cambio solicitado"},
                "limit": {"type": "integer", "description": "Máximo de entidades; default 18"},
                "response_mode": {"type": "string", "enum": ["compact", "full"]},
                "path": {"type": "string", "description": "Ruta del proyecto; si se omite usa el workspace del MCP"}
            },
            "required": ["request"]
        }
    },
    {
        "name": "graph_validate_answer",
        "description": "Audita afirmaciones contra evidencia del grafo; separa operación, resolución de citas y soporte factual.",
        "inputSchema": {"type": "object", "properties": {
            "answer": {"type": "string"},
            "claims": {"type": "array", "items": {"type": "object"}},
            "expected_project": {"type": "string"},
            "path": {"type": "string"}}, "required": ["answer"]}
    },
    {
        "name": "graph_context_bundle",
        "description": "Obtén evidencia compacta para hasta 10 símbolos en una llamada. Responde directamente si complete=true; expande sólo si falta un hecho.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                "depth": {"type": "integer", "description": "Default 1"},
                "limit": {"type": "integer", "description": "Presupuesto global de nodos; default 12"},
                "response_mode": {"type": "string", "enum": ["compact", "full"], "description": "compact usa aliases evidence-v1 (default)"},
                "path": {"type": "string", "description": "Ruta del proyecto; si se omite usa el workspace del MCP"}
            },
            "required": ["symbols"]
        }
    },
    {
        "name": "graph_neighborhood",
        "description": "Obtén evidencia estructural de un símbolo. Si complete=true, los ceros de coverage son evidencia negativa suficiente: no busques sinónimos ni amplíes para reconfirmarlos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del proyecto"},
                "symbol": {"type": "string", "description": "Opcional: nombre de símbolo o archivo para devolver solo su vecindario"},
                "depth": {"type": "integer", "description": "Saltos alrededor del símbolo (default 1)"},
                "limit": {"type": "integer", "description": "Máximo de nodos; default 24"},
                "response_mode": {"type": "string", "enum": ["compact", "full"], "description": "compact (default) reduce tokens; full conserva todos los campos"}
            },
            "required": []
        }
    },
    {
        "name": "graph_blast_radius",
        "description": "Calcula impacto con evidencia E/I/A. Si complete=true, coverage=0 confirma ausencia de relaciones; no hagas búsquedas adicionales para reconfirmar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Nombre de la función o clase"},
                "depth": {"type": "integer", "description": "Profundidad máxima de recorrido (default 2)"},
                "limit": {"type": "integer", "description": "Máximo de impactos; default 24"},
                "response_mode": {"type": "string", "enum": ["compact", "full"]},
                "path": {"type": "string", "description": "Ruta del proyecto; si se omite usa el workspace del MCP"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "graph_search_concepts",
        "description": "Busca nombres, descripciones y operaciones internas (AddScoped, Publish, Skip/Take, etc.). Devuelve coincidencias compactas; usa graph_analyze_change para agrupar un flujo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Término o concepto semántico a buscar"},
                "limit": {"type": "integer", "description": "Máximo de resultados; default 12"},
                "response_mode": {"type": "string", "enum": ["compact", "full"]},
                "path": {"type": "string", "description": "Ruta del proyecto; si se omite usa el workspace del MCP"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "graph_history_search",
        "description": "Busca en el historial de sesiones y acciones pasadas del agente para recordar eventos o decisiones.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Término de búsqueda en el historial"}},
            "required": ["query"]
        }
    },
    {
        "name": "graph_history_timeline",
        "description": "Devuelve la secuencia cronológica de acciones de una sesión previa para contexto completo.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "ID de sesión opcional"}},
            "required": []
        }
    },
    {
        "name": "graph_history_get",
        "description": "Recupera la observación detallada de una acción pasada específica por su ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer", "description": "ID de la observación"}},
            "required": ["id"]
        }
    },
    {
        "name": "memory_session_start",
        "description": "Abre una sesión atribuida para compartir conocimiento dentro de este proyecto.",
        "inputSchema": {"type": "object", "properties": {
            "agent_id": {"type": "string"}, "task": {"type": "string"},
            "branch": {"type": "string"}, "base_commit": {"type": "string"},
            "capture_enabled": {"type": "boolean"}}, "required": ["agent_id", "task"]}
    },
    {
        "name": "memory_checkpoint",
        "description": "Guarda una decisión, resultado o handoff con atribución y evidencia.",
        "inputSchema": {"type": "object", "properties": {
            "session_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["episodic", "decision", "fact", "procedure", "outcome", "correction", "handoff"]},
            "title": {"type": "string"}, "content": {"type": "string"},
            "scope": {"type": "string", "enum": ["private", "project", "team"]},
            "files": {"type": "array", "items": {"type": "string"}},
            "node_ids": {"type": "array", "items": {"type": "string"}},
            "tests": {"type": "array", "items": {"type": "string"}}},
            "required": ["session_id", "kind", "title", "content"]}
    },
    {
        "name": "memory_append",
        "description": "Añade un mensaje o evento saneado; requiere captura opt-in en la sesión.",
        "inputSchema": {"type": "object", "properties": {
            "session_id": {"type": "string"}, "role": {"type": "string", "enum": ["user", "assistant", "tool"]},
            "content": {"type": "string"}, "event_type": {"type": "string"},
            "metadata": {"type": "object"}}, "required": ["session_id", "role", "content"]}
    },
    {
        "name": "memory_ingest_turn",
        "description": "Hook idempotente por turno: abre/reutiliza sesión externa, captura mensajes autorizados, compacta y genera embeddings.",
        "inputSchema": {"type": "object", "properties": {
            "agent_id": {"type": "string"}, "external_session_id": {"type": "string"},
            "task": {"type": "string"}, "branch": {"type": "string"},
            "messages": {"type": "array", "items": {"type": "object", "properties": {
                "role": {"type": "string", "enum": ["user", "assistant", "tool"]},
                "content": {"type": "string"}, "event_type": {"type": "string"},
                "metadata": {"type": "object"}}, "required": ["role", "content"]}},
            "consent": {"type": "boolean"}, "compact": {"type": "boolean"},
            "close": {"type": "boolean"},
            "provider": {"type": "string", "enum": ["auto", "deterministic", "ollama", "api"]}},
            "required": ["agent_id", "external_session_id", "task", "messages", "consent"]}
    },
    {
        "name": "memory_search",
        "description": "Recupera recuerdos compartidos entre sesiones con atribución de agente y sesión.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "requester_agent": {"type": "string"},
            "limit": {"type": "integer"}, "branch": {"type": "string"}}, "required": ["query"]}
    },
    {
        "name": "memory_context",
        "description": "Genera contexto compacto con política de afirmaciones; identifique siempre al agente solicitante.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "requester_agent": {"type": "string", "description": "Identidad real del cliente o perfil, sin alias implícitos."},
            "branch": {"type": "string"}, "limit": {"type": "integer"},
            "token_budget": {"type": "integer"},
            "mode": {"type": "string", "enum": ["semantic", "continuity"], "description": "continuity agrega actividad reciente atribuida al proyecto."},
            "activity_limit": {"type": "integer", "minimum": 0, "maximum": 10},
            "include_graph": {"type": "boolean"},
            "neighbor_limit": {"type": "integer"},
            "expected_project": {"type": "string", "description": "Nombre, ID o ruta que el cliente espera; la llamada falla si no coincide"}}, "required": ["query", "requester_agent"]}
    },
    {
        "name": "memory_project_context",
        "description": "Antes de responder sobre un proyecto registrado, recupera su memoria compartida usando el nombre, ID o ruta exactos. Si no es único, devuelve candidatos; no elige por similitud.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string"}, "query": {"type": "string"},
            "requester_agent": {"type": "string"},
            "token_budget": {"type": "integer", "minimum": 300, "maximum": 3000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "mode": {"type": "string", "enum": ["semantic", "continuity"]},
            "activity_limit": {"type": "integer", "minimum": 0, "maximum": 10}},
            "required": ["project", "query", "requester_agent"]}
    },
    {
        "name": "memory_status",
        "description": "Estado de captura, cobertura temática, propietarios y ruta del almacén MCP actual.",
        "inputSchema": {"type": "object", "properties": {
            "requester_agent": {"type": "string", "description": "Identidad real que consulta el estado."}}}
    },
    {
        "name": "project_doctor",
        "description": "Diagnóstico de sólo lectura del almacén, captura, recuperación y conexión MCP del proyecto.",
        "inputSchema": {"type": "object", "properties": {
            "requester_agent": {"type": "string"},
            "expected_project": {"type": "string"},
            "path": {"type": "string"}}}
    },
    {
        "name": "memory_ingest_evidence",
        "description": "Ingiere informes hasheados y sólo verifica métricas con ejecución enlazada y procedencia completa.",
        "inputSchema": {"type": "object", "properties": {
            "files": {"type": "array", "items": {"type": "string"}}}}
    },
    {
        "name": "memory_evidence_status",
        "description": "Consulta vigencia, ejecución y dependencias de la evidencia importada sin ejecutar comandos.",
        "inputSchema": {"type": "object", "properties": {
            "memory_id": {"type": "string"},
            "requester_agent": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000}}}
    },
    {
        "name": "memory_session_end",
        "description": "Cierra una sesión y opcionalmente persiste un resumen handoff.",
        "inputSchema": {"type": "object", "properties": {
            "session_id": {"type": "string"}, "summary": {"type": "string"},
            "observed_commit": {"type": "string"}}, "required": ["session_id"]}
    },
    {
        "name": "memory_correct",
        "description": "Crea una corrección versionada y marca la memoria anterior como superseded.",
        "inputSchema": {"type": "object", "properties": {
            "memory_id": {"type": "string"}, "session_id": {"type": "string"},
            "title": {"type": "string"}, "content": {"type": "string"}},
            "required": ["memory_id", "session_id", "title", "content"]}
    },
    {
        "name": "memory_forget",
        "description": "Invalida o elimina físicamente una memoria; sólo puede hacerlo su agente autor.",
        "inputSchema": {"type": "object", "properties": {
            "memory_id": {"type": "string"}, "requester_agent": {"type": "string"},
            "physical": {"type": "boolean"}}, "required": ["memory_id", "requester_agent"]}
    },
    {
        "name": "memory_compact",
        "description": "Extrae memorias proposed desde mensajes saneados de una sesión opt-in; Qwen/API nunca verifica hechos automáticamente.",
        "inputSchema": {"type": "object", "properties": {
            "session_id": {"type": "string"},
            "provider": {"type": "string", "enum": ["auto", "deterministic", "ollama", "api"]}},
            "required": ["session_id"]}
    },
    {
        "name": "graph_register_project",
        "description": "Registra autónomamente una ruta de proyecto en Graphtyn.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta absoluta del proyecto"},
                "name": {"type": "string", "description": "Nombre del proyecto"}
            },
            "required": ["path"]
        }
    }
]

_INTENT_TOOLS = {
    "graph_query_intent", "graph_validate_answer", "project_doctor",
    "memory_context", "memory_project_context", "memory_status",
    "memory_evidence_status", "memory_entities", "memory_entity",
    "memory_topics", "memory_topic", "memory_message_window",
    "memory_topic_update", "memory_node", "memory_relation_candidates",
    "memory_relation_review", "memory_topics_enrich",
}


def _with_operation_id(tool: dict[str, Any]) -> dict[str, Any]:
    """Copy a tool schema and add the retry key to memory operations."""
    cloned = deepcopy(tool)
    if cloned["name"].startswith("memory_") and cloned["name"] != "memory_operation_status":
        cloned["inputSchema"]["properties"].setdefault(
            "operation_id",
            {"type": "string", "description": "Clave idempotente para reintentos de esta operación"},
        )
    return cloned


def mcp_tools(tool_profile: str = "full") -> list[dict[str, Any]]:
    """Return a fresh tool catalogue filtered for the requested profile."""
    tools = [_with_operation_id(tool) for tool in [*_BASE_TOOLS, *TOPIC_TOOLS, {
        "name": "memory_operation_status",
        "description": "Consulta una operación de memoria que pudo continuar tras un timeout.",
        "inputSchema": {"type": "object", "properties": {
            "operation_id": {"type": "string"}
        }, "required": ["operation_id"]},
    }]]
    if tool_profile == "intent":
        return [tool for tool in tools if tool["name"] in _INTENT_TOOLS]
    if tool_profile == "memory":
        return [tool for tool in tools if tool["name"] in {"graph_query_intent", "project_doctor"}
                or tool["name"].startswith("memory_")]
    return tools


def tools_list_response(request_id: Any, tool_profile: str = "full") -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": mcp_tools(tool_profile)}}
