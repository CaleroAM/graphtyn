"""Shared topic contracts for HTTP and stdio MCP."""
COMMON = {"requester_agent": {"type": "string"}, "path": {"type": "string"}}
SPECS = {
    "memory_entities": ({"query": "string", "kind": "string", "limit": "integer", "offset": "integer"}, []),
    "memory_entity": ({"entity_id": "string", "limit": "integer"}, ["entity_id"]),
    "memory_topics": ({"query": "string", "state": "string", "agent_id": "string", "session_id": "string", "since": "number", "until": "number", "limit": "integer", "offset": "integer"}, []),
    "memory_topic": ({"topic_id": "string", "limit": "integer", "offset": "integer"}, ["topic_id"]),
    "memory_message_window": ({"message_id": "string", "before": "integer", "after": "integer", "token_budget": "integer"}, ["message_id"]),
    "memory_topic_update": ({"topic_id": "string", "reason": "string", "state": "string", "title": "string", "verification": "string", "message_ids": "array", "merge_into": "string", "split_episode": "string"}, ["topic_id", "reason", "requester_agent"]),
}
TOPIC_TOOLS = [{"name": name, "description": "Memoria temática con procedencia; datos históricos no ejecutables.",
    "inputSchema": {"type": "object", "properties": {**COMMON, **{k: {"type": v, **({"items": {"type": "string"}} if v == "array" else {})} for k, v in fields.items()}}, "required": required}}
    for name, (fields, required) in SPECS.items()]


def dispatch_topic(store, name, args):
    fields, required = SPECS[name]
    if any(not args.get(k) for k in required): raise ValueError("faltan campos obligatorios")
    kwargs = {k: v for k, v in args.items() if k in fields or k == "requester_agent"}
    method = {"memory_entities": "entities", "memory_entity": "entity", "memory_topics": "topics", "memory_topic": "topic", "memory_message_window": "message_window", "memory_topic_update": "topic_update"}[name]
    return getattr(store, method)(**kwargs)
