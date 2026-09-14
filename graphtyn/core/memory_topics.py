"""Auditable conversation episodes. Historical text is data, never authority."""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

STATES = {"abierto", "en investigación", "resuelto", "reabierto", "archivado"}
VERIFICATIONS = {"sin verificar", "declarado", "prueba superada", "prueba fallida", "confirmado por usuario"}

_ENTITY_PATTERNS = (
    ("button", re.compile(r"\b(?:bot[oó]n|button|btn)\s*#?\s*([0-9]+)\b", re.I), "botón {}"),
    ("button", re.compile(r"\b(?:bot[oó]n(?:es)?|button|btn)\s+(?:de\s+|del\s+|the\s+)?([a-záéíóúñ][\wáéíóúñ.-]{1,30})\b", re.I), "botón de {}"),
    ("screen", re.compile(r"\b(?:pantalla|screen|vista|view)\s+[\"']?([\w.-]+)", re.I), "pantalla {}"),
)

_CONTEXT_PATTERNS = (
    ("feature", re.compile(r"\b(?:funcionalidad|feature|caracter[ií]stica)\s+(?:de|del|para)\s+(?:(?:el|la|los|las)\s+)?(?:(?:bot[oó]n(?:es)?)\s+(?:de|del)\s+)?([a-záéíóúñ][\wáéíóúñ.-]{1,30})\b", re.I), "funcionalidad {}"),
    ("module", re.compile(r"\b(?:m[oó]dulo|secci[oó]n|area|área)\s+(?:de|del|para)\s+(?:(?:el|la|los|las)\s+)?([a-záéíóúñ][\wáéíóúñ.-]{1,30})\b", re.I), "módulo {}"),
    ("report", re.compile(r"\b(reporte|report|informe)\b", re.I), "reporte"),
    ("report", re.compile(r"\b(?:reporte|report|informe)\s+(?:de|del|para)\s+([a-záéíóúñ][\wáéíóúñ.-]{1,30})\b", re.I), "reporte {}"),
    ("platform", re.compile(r"\b(android|ios|apk|unity|web|m[oó]vil)\b", re.I), "plataforma {}"),
    ("python_function", re.compile(r"\b(?:funci[oó]n|function|def)\s+(?:de\s+)?([A-Za-z_]\w*)", re.I), "función {}"),
    ("python_class", re.compile(r"\b(?:clase|class)\s+(?:de\s+)?([A-Za-z_]\w*)", re.I), "clase {}"),
    ("python_method", re.compile(r"\b(?:m[eé]todo|method)\s+(?:de\s+)?([A-Za-z_]\w*)", re.I), "método {}"),
)

_FILE_REFERENCE_RE = re.compile(
    r"(?<![\w./-])(?P<absolute>/(?:[A-Za-z0-9_@+.-]+/)*[A-Za-z0-9_@+.-]+\.(?:pyi?|js|jsx|ts|tsx|mjs|cjs|html|css|scss|jsonc?|ya?ml|toml|md|sql|sh|bash|cs|java|go|rs|php|rb|kt|swift|c|h|cpp|hpp|vue|svelte|xml|env|ini|cfg|txt|prefab|unity|asset|asmdef|shader|compute|mat|uxml|uss|meta|csproj|sln|gradle|dart|ipynb|properties))"
    r"|(?<![\w./-])(?P<relative>(?:[A-Za-z0-9_@+.-]+/)*[A-Za-z0-9_@+.-]+\.(?:pyi?|js|jsx|ts|tsx|mjs|cjs|html|css|scss|jsonc?|ya?ml|toml|md|sql|sh|bash|cs|java|go|rs|php|rb|kt|swift|c|h|cpp|hpp|vue|svelte|xml|env|ini|cfg|txt|prefab|unity|asset|asmdef|shader|compute|mat|uxml|uss|meta|csproj|sln|gradle|dart|ipynb|properties))"
    r"(?=$|[#:\s`'\"<>()\[\]{},;!?])",
    re.IGNORECASE,
)

_RELATION_STOPWORDS = {
    "about", "additional_metadata", "actualmente", "agente", "agentes", "ahora",
    "assistant", "archivo", "archivos", "branch", "cambio", "cambios", "change",
    "changed", "changes", "claude", "codex", "commit", "como", "conversation",
    "conversacion", "context", "contexto", "current", "doesn", "entonces", "exact",
    "file", "files", "flash", "gemini", "graphtyn", "human", "memoria", "memory",
    "openclaw", "opencode", "porque", "project", "proyecto", "prueba", "pruebas",
    "question", "repository", "respuesta", "result", "session", "sesion", "source",
    "sigue", "todo", "todos", "tool", "tools", "user", "version",
}


def encoded_tokens(value):
    # Same UTF-8/4 estimate as existing telemetry, now including the full
    # response. This is not a model-specific tokenizer or a billing measure.
    return (len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()) + 3) // 4


class TopicMemoryMixin:
    def _init_topics(self):
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT 'asunto', state TEXT NOT NULL DEFAULT 'abierto',
              verification TEXT NOT NULL DEFAULT 'sin verificar', created_at REAL NOT NULL,
              updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS topic_episodes (
              id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
              session_id TEXT NOT NULL REFERENCES sessions(id), agent_id TEXT NOT NULL,
              problem TEXT NOT NULL, decisions TEXT NOT NULL DEFAULT '',
              result TEXT NOT NULL DEFAULT '', extraction TEXT NOT NULL,
              created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS topic_episodes_topic ON topic_episodes(topic_id, created_at, id);
            CREATE TABLE IF NOT EXISTS topic_messages (
              episode_id TEXT NOT NULL REFERENCES topic_episodes(id),
              message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
              PRIMARY KEY(episode_id,message_id));
            CREATE TABLE IF NOT EXISTS topic_events (
              id INTEGER PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
              actor TEXT NOT NULL, action TEXT NOT NULL, details_json TEXT NOT NULL,
              created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS topic_progress (
              session_id TEXT PRIMARY KEY REFERENCES sessions(id), cursor INTEGER NOT NULL DEFAULT 0,
              processed INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS topic_file_progress (
              session_id TEXT PRIMARY KEY REFERENCES sessions(id), cursor INTEGER NOT NULL DEFAULT 0,
              processed INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS topic_memory_links (
              topic_id TEXT NOT NULL REFERENCES topics(id), memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
              PRIMARY KEY(topic_id,memory_id));
            CREATE TABLE IF NOT EXISTS entities (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_key TEXT NOT NULL,
              name TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at REAL NOT NULL, updated_at REAL NOT NULL,
              UNIQUE(kind, entity_key));
            CREATE TABLE IF NOT EXISTS topic_entities (
              topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
              relation TEXT NOT NULL DEFAULT 'afecta_a',
              confidence TEXT NOT NULL DEFAULT 'EXTRACTED',
              source_message_id TEXT REFERENCES messages(id), created_at REAL NOT NULL,
              PRIMARY KEY(topic_id, entity_id));
            CREATE INDEX IF NOT EXISTS topic_entities_entity ON topic_entities(entity_id, topic_id);
            CREATE TABLE IF NOT EXISTS topic_entity_evidence (
              topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
              source_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
              created_at REAL NOT NULL,
              PRIMARY KEY(topic_id,entity_id,source_message_id));
            CREATE INDEX IF NOT EXISTS topic_entity_evidence_message ON topic_entity_evidence(source_message_id);
            CREATE TABLE IF NOT EXISTS topic_work_terms (
              topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              term TEXT NOT NULL, PRIMARY KEY(topic_id, term));
            CREATE TABLE IF NOT EXISTS topic_relations (
              source_topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              target_topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              relation TEXT NOT NULL, confidence TEXT NOT NULL,
              reason TEXT NOT NULL DEFAULT '', source_message_id TEXT REFERENCES messages(id),
              created_at REAL NOT NULL,
              PRIMARY KEY(source_topic_id, target_topic_id, relation));
            CREATE INDEX IF NOT EXISTS topic_relations_target ON topic_relations(target_topic_id);
            CREATE TABLE IF NOT EXISTS memory_node_references (
              reference TEXT PRIMARY KEY, kind TEXT NOT NULL, node_id TEXT NOT NULL,
              created_at REAL NOT NULL, UNIQUE(kind, node_id)
            );
            CREATE INDEX IF NOT EXISTS memory_node_refs_node ON memory_node_references(kind, node_id);
            CREATE TABLE IF NOT EXISTS topic_relation_reviews (
              id TEXT PRIMARY KEY, source_topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              target_topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              relation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              reason TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]',
              actor TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
              UNIQUE(source_topic_id, target_topic_id, relation)
            );
            CREATE INDEX IF NOT EXISTS topic_relation_reviews_status ON topic_relation_reviews(status, updated_at);
            CREATE TABLE IF NOT EXISTS topic_enrichment_state (
              topic_id TEXT PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
              source_fingerprint TEXT NOT NULL DEFAULT '', source_revision INTEGER NOT NULL DEFAULT 0,
              model TEXT NOT NULL DEFAULT '', prompt_version TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','enriched','stale','failed','not_applicable')),
              attempt_count INTEGER NOT NULL DEFAULT 0, manual_protected INTEGER NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '', processed_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS topic_enrichment_state_status ON topic_enrichment_state(status, updated_at);
            CREATE TABLE IF NOT EXISTS topic_enrichment_queue (
              id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              source_fingerprint TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', prompt_version TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','completed','failed')),
              attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
              UNIQUE(topic_id,source_fingerprint,model,prompt_version)
            );
            CREATE INDEX IF NOT EXISTS topic_enrichment_queue_ready ON topic_enrichment_queue(status,next_attempt_at);
            """)
            db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(3,?)", (time.time(),))
            db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(4,?)", (time.time(),))
            db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(5,?)", (time.time(),))
            db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(6,?)", (time.time(),))
            db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(8,?)", (time.time(),))

    def _node_reference(self, db, kind: str, node_id: str) -> str:
        """Return a stable human-facing reference for any memory graph node."""
        kind, node_id = str(kind), str(node_id)
        row = db.execute("SELECT reference FROM memory_node_references WHERE kind=? AND node_id=?",
                         (kind, node_id)).fetchone()
        if row:
            return row[0]
        next_number = db.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(reference,3) AS INTEGER)),0)+1 FROM memory_node_references"
        ).fetchone()[0]
        reference = f"N-{int(next_number):06d}"
        db.execute("INSERT OR IGNORE INTO memory_node_references(reference,kind,node_id,created_at) VALUES(?,?,?,?)",
                   (reference, kind, node_id, time.time()))
        return db.execute("SELECT reference FROM memory_node_references WHERE kind=? AND node_id=?",
                          (kind, node_id)).fetchone()[0]

    @staticmethod
    def _node_kind_for_id(node_id: str) -> str:
        return str(node_id).split(":", 1)[0] if ":" in str(node_id) else "memory"

    def _topic_owner_predicate(self, topic_id_expression):
        """Hide legacy topics whose shared title or evidence crosses brain owners."""
        if self.memory_scope()["space_type"] != "agent_brain":
            return "1=1", []
        owners = self._effective_agent_ids()
        if owners is None:
            return "1=1", []
        if not owners:
            return "0", []
        marks = ",".join("?" for _ in owners)
        return (f"NOT EXISTS (SELECT 1 FROM topic_episodes isolated_owner "
                f"WHERE isolated_owner.topic_id={topic_id_expression} "
                f"AND lower(isolated_owner.agent_id) NOT IN ({marks}))", owners)

    def _decorate_node_refs(self, nodes: list[dict]) -> list[dict]:
        with self._connect() as db:
            for node in nodes:
                kind = str(node.get("kind") or self._node_kind_for_id(node.get("id", "")))
                id_field = {"memory_topic": "topic_id", "memory_episode": "episode_id",
                            "memory_entity": "entity_id"}.get(kind)
                node_id = str(node.get(id_field) if id_field and node.get(id_field) else node.get("id") or "")
                node["reference"] = self._node_reference(db, kind, node_id)
                node["public_id"] = node["reference"]
        return nodes

    def resolve_node_reference(self, reference: str, *, requester_agent=None, limit=20, offset=0, agent_ids=None):
        with self._connect() as db:
            row = db.execute("SELECT kind,node_id,reference FROM memory_node_references WHERE reference=?",
                             (str(reference).strip().upper(),)).fetchone()
        if not row:
            raise ValueError("referencia de nodo inexistente")
        kind, node_id = row["kind"], row["node_id"]
        authorized_agents = self._effective_agent_ids(agent_ids)
        if kind == "memory_topic":
            result = self.topic(node_id, requester_agent=requester_agent, limit=limit, agent_ids=authorized_agents)
        elif kind == "memory_entity":
            result = self.entity(node_id, requester_agent=requester_agent, limit=limit, agent_ids=authorized_agents)
        elif kind == "memory_session":
            session_id = str(node_id).removeprefix("session:")
            with self._connect() as db:
                session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                if authorized_agents is not None and session and str(session["agent_id"]).casefold() not in authorized_agents:
                    session = None
                if not session or (not session["capture_enabled"] and session["agent_id"] != (requester_agent or "")):
                    raise PermissionError("sesión inexistente o no accesible")
                topic_scope = f" AND e.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
                owner_predicate, owner_args = self._topic_owner_predicate("e.topic_id")
                topic_scope += f" AND ({owner_predicate})"
                total_topics = db.execute("SELECT COUNT(DISTINCT e.topic_id) FROM topic_episodes e WHERE e.session_id=?" +
                                          topic_scope, [session_id, *(authorized_agents or []), *owner_args]).fetchone()[0]
                offset = max(0, min(100000, int(offset)))
                page_limit = max(1, min(200, int(limit)))
                topics = db.execute("""SELECT DISTINCT t.id,t.title,t.summary,t.state,t.verification,t.updated_at
                    FROM topics t JOIN topic_episodes e ON e.topic_id=t.id JOIN sessions sx ON sx.id=e.session_id AND sx.agent_id=e.agent_id WHERE e.session_id=?""" + topic_scope +
                    " ORDER BY t.updated_at DESC,t.id LIMIT ? OFFSET ?",
                    [session_id, *(authorized_agents or []), *owner_args, page_limit, offset]).fetchall()
                topic_items = []
                for topic in topics:
                    item = dict(topic)
                    item["title"], item["summary"] = self._unprotect(item["title"]), self._unprotect(item["summary"])
                    item["reference"] = self._node_reference(db, "memory_topic", item["id"])
                    item["public_id"] = item["reference"]
                    topic_items.append(item)
                message_count = db.execute("SELECT COUNT(*) FROM messages WHERE session_id=? AND agent_id=?",
                                           (session_id, session["agent_id"])).fetchone()[0]
            result = {"ok": True, "node": {"kind": kind, "id": node_id, "reference": row["reference"]},
                      "session": dict(session), "message_count": message_count,
                      "topic_count": total_topics, "topics_returned": len(topic_items), "topics": topic_items,
                      "topic_offset": offset,
                      "next_topic_offset": offset + page_limit if offset + len(topic_items) < total_topics else None,
                      "trust": "untrusted_history"}
        elif kind == "memory_episode":
            with self._connect() as db:
                episode = db.execute("""SELECT e.*,s.capture_enabled FROM topic_episodes e
                    JOIN sessions s ON s.id=e.session_id AND s.agent_id=e.agent_id WHERE e.id=?""", (node_id,)).fetchone()
                if (episode and authorized_agents is not None
                        and str(episode["agent_id"]).casefold() not in authorized_agents):
                    episode = None
                if not episode or (not episode["capture_enabled"] and episode["agent_id"] != (requester_agent or "")):
                    raise PermissionError("episodio inexistente o no accesible")
                item = dict(episode); item.pop("capture_enabled", None)
                owner_predicate, owner_args = self._topic_owner_predicate("e.topic_id")
                mixed = db.execute(f"SELECT 1 FROM topic_episodes e WHERE e.topic_id=? AND NOT ({owner_predicate}) LIMIT 1",
                                   [episode["topic_id"], *owner_args]).fetchone()
                if mixed:
                    raise PermissionError("episodio inexistente o no accesible")
                for key in ("problem", "decisions", "result"): item[key] = self._unprotect(item[key])
                item["message_ids"] = [r[0] for r in db.execute("""SELECT r.message_id FROM topic_messages r
                    JOIN messages m ON m.id=r.message_id AND m.agent_id=?
                    WHERE r.episode_id=? ORDER BY m.rowid LIMIT ?""",
                    (episode["agent_id"], node_id, max(1, min(200, int(limit)))))]
                item["topic_reference"] = self._node_reference(db, "memory_topic", item["topic_id"])
            result = {"ok": True, "node": {"kind": kind, "id": node_id, "reference": row["reference"]},
                      "episode": item, "trust": "untrusted_history"}
        else:
            result = {"ok": True, "node": {"kind": kind, "id": node_id, "reference": row["reference"]}}
        result["reference"] = row["reference"]
        result["node_kind"] = kind
        result["node_id"] = node_id
        return result

    @staticmethod
    def _subject_terms(content):
        """Extract stable entity keys and work terms without treating words as identity."""
        text = str(content or "")
        entities = []
        for kind, pattern, name_template in _ENTITY_PATTERNS:
            for match in pattern.finditer(text):
                raw_value = match.group(1)
                value = raw_value.casefold()
                if value in {"de", "del", "the", "el", "la", "los", "las", "button", "boton", "botón", "color", "tamaño", "tamano", "diseño", "diseno", "estilo"}:
                    continue
                # A bare plural such as "botones textura" is a category or
                # description, not a named control. Accept a name after an
                # explicit "de" or a deliberately capitalized/known label.
                if kind == "button" and not raw_value.isdigit() and not re.search(r"\b(?:de|del|the)\s+", match.group(0), re.I):
                    known = {"jugar", "fichas", "ajustes", "volver"}
                    if value not in known and not raw_value[:1].isupper():
                        continue
                if kind == "screen" and value in {"debe", "para", "sale", "se", "tan", "todavía", "todavia"}:
                    continue
                entities.append({"kind": kind, "key": value,
                                 "name": name_template.format(value)})
        for kind, pattern, name_template in _CONTEXT_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1).casefold()
                if value in {"de", "del", "para", "el", "la", "los", "las", "botón", "boton", "button", "color", "tamaño", "tamano", "diseño", "diseno", "estilo"}:
                    continue
                entities.append({"kind": kind, "key": value,
                                 "name": name_template.format(value)})
        # A shared design subject gives named controls a meaningful hub while
        # preserving an independent topic for each control.
        button_entities = {entity["key"] for entity in entities if entity["kind"] == "button"}
        design_context = re.search(
            r"\b(?:diseñ[oa]|estilo|apariencia|color(?:es)?|tema)\b.{0,35}\bbot[oó]n(?:es)?\b|"
            r"\bbot[oó]n(?:es)?\b.{0,35}\b(?:diseñ[oa]|estilo|apariencia|color(?:es)?|tema)\b",
            text, re.I | re.S)
        if button_entities:
            entities.append({"kind": "component_type", "key": "button", "name": "botones"})
        if design_context or button_entities:
            entities.append({"kind": "design_group", "key": "buttons", "name": "diseño de botones"})
        stopwords = {"cambia", "cambiar", "change", "el", "la", "los", "las", "un", "una", "por", "para", "del", "de", "que", "ahora", "también", "tambien", "debe", "deben", "quiero", "botón", "botones", "boton", "button", "btn", "pantalla", "screen"}
        terms = {term for term in re.findall(r"[\wáéíóúñ]{4,}", text.casefold())
                 if term not in stopwords and not term.isdigit()}
        terms -= {entity["key"] for entity in entities}
        action_terms = {
            "cambia": "change", "cambiar": "change", "cambié": "change", "change": "change",
            "ajusta": "adjust", "ajustar": "adjust", "mejora": "improve", "mejorar": "improve",
            "corrige": "correct", "corregir": "correct", "revisa": "review", "revisar": "review",
            "verifica": "verify", "verificar": "verify", "prueba": "test", "probar": "test",
            "usa": "set", "usar": "set",
        }
        for word, action in action_terms.items():
            if re.search(rf"\b{re.escape(word)}\b", text, re.I):
                terms.add("__action_" + action + "__")
        if re.search(r"\b(?:ahora|también|tambien|sigue|continuar|retoma|retomar)\b", text, re.I):
            terms.add("__continuation__")
        return entities, terms

    def _file_references(self, content, *, maximum=50):
        """Extract safe, workspace-scoped file mentions from any visible message role."""
        text = re.sub(r"https?://\S+", " ", str(content or ""), flags=re.I)
        root = self.workspace.resolve()
        found = {}
        for match in _FILE_REFERENCE_RE.finditer(text):
            raw = match.group("absolute") or match.group("relative") or ""
            candidate = Path(raw)
            if candidate.is_absolute():
                try:
                    relative = candidate.resolve(strict=False).relative_to(root)
                except (OSError, ValueError):
                    continue
                key = relative.as_posix()
                scope = "workspace_relative"
            else:
                candidate = Path(raw)
                if any(part == ".." for part in candidate.parts):
                    continue
                normalized = candidate.as_posix().removeprefix("./")
                if "/" in normalized:
                    key, scope = normalized, "workspace_relative"
                else:
                    try:
                        existing = (root / candidate).resolve(strict=False)
                        existing.relative_to(root)
                        is_workspace_file = existing.is_file()
                    except (OSError, ValueError):
                        is_workspace_file = False
                    if is_workspace_file:
                        key, scope = existing.relative_to(root).as_posix(), "workspace_relative"
                    else:
                        key, scope = candidate.name, "basename_only"
            if not key or len(key) > 512 or key.startswith("../"):
                continue
            found[(key.casefold(), scope)] = {
                "kind": "file", "key": key, "name": key,
                "metadata": {"path_scope": scope, "evidence": "explicit_message_mention"},
            }
            if len(found) >= max(1, min(100, int(maximum))):
                break
        return list(found.values())

    def _entity_ids(self, db, entities, source_message_id, now):
        ids = []
        for entity in entities:
            metadata = entity.get("metadata") or {}
            row = db.execute("SELECT id,metadata_json FROM entities WHERE kind=? AND entity_key=?",
                             (entity["kind"], entity["key"])).fetchone()
            if row:
                entity_id = row[0]
                try:
                    prior_metadata = json.loads(row["metadata_json"] or "{}")
                except (TypeError, ValueError):
                    prior_metadata = {}
                merged_metadata = {**prior_metadata, **metadata}
                db.execute("UPDATE entities SET name=?,metadata_json=?,updated_at=? WHERE id=?",
                           (entity["name"], json.dumps(merged_metadata, ensure_ascii=False), now, entity_id))
            else:
                entity_id = "ent_" + hashlib.sha256((entity["kind"] + "\0" + entity["key"]).encode()).hexdigest()[:24]
                db.execute("INSERT INTO entities(id,kind,entity_key,name,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                           (entity_id, entity["kind"], entity["key"], entity["name"],
                            json.dumps(metadata, ensure_ascii=False), now, now))
            ids.append(entity_id)
        return ids

    def _find_topic_match(self, db, session_id, entity_ids, terms, owner_agent=None):
        if not entity_ids:
            return None
        owner_clause = (" AND EXISTS (SELECT 1 FROM topic_episodes owner_episode "
                        "WHERE owner_episode.topic_id=t.id AND owner_episode.agent_id=?) "
                        "AND NOT EXISTS (SELECT 1 FROM topic_episodes foreign_episode "
                        "WHERE foreign_episode.topic_id=t.id AND lower(foreign_episode.agent_id)!=lower(?))") if owner_agent else ""
        args = [*entity_ids, *([owner_agent, owner_agent] if owner_agent else [])]
        candidates = db.execute("""SELECT DISTINCT t.id,t.state,t.updated_at
            FROM topics t JOIN topic_entities te ON te.topic_id=t.id
            JOIN entities candidate_entity ON candidate_entity.id=te.entity_id
            WHERE te.entity_id IN ({})
              AND candidate_entity.kind NOT IN ('component_type','design_group','platform')
              AND t.state IN ('abierto','en investigación','reabierto')""".format(",".join("?" for _ in entity_ids)) + owner_clause +
            " ORDER BY t.updated_at DESC", args).fetchall()
        best = None
        for row in candidates:
            existing = {r[0] for r in db.execute("SELECT term FROM topic_work_terms WHERE topic_id=?", (row[0],))}
            overlap = len(existing & terms)
            score = 3 + min(3, overlap)
            # Same entity alone is insufficient for separate work items. A
            # repeated request with at least one stable work term continues it.
            if overlap < 2 and "__continuation__" not in terms:
                continue
            candidate = (score, row[2], row[0])
            if best is None or candidate > best:
                best = candidate
        return best[2] if best else None

    def _link_topic_entities(self, db, topic_id, entity_ids, terms, source_message_id, now,
                             owner_agent=None, allow_cross_agent=True):
        for entity_id in entity_ids:
            entity = db.execute("SELECT kind,metadata_json FROM entities WHERE id=?", (entity_id,)).fetchone()
            kind = entity["kind"]
            try:
                metadata = json.loads(entity["metadata_json"] or "{}")
            except (TypeError, ValueError):
                metadata = {}
            exact_file = kind == "file" and metadata.get("path_scope") == "workspace_relative"
            relation = {"component_type": "mismo tipo", "design_group": "tema de diseño",
                        "feature": "implementa", "module": "afecta_a", "report": "afecta_a",
                        "platform": "usa", "file": "archivo mencionado"}.get(kind, "afecta_a")
            confidence = "EXTRACTED" if kind != "file" or exact_file else "AMBIGUOUS"
            if kind == "file" and not exact_file:
                relation = "nombre de archivo (ambiguo)"
            db.execute("""INSERT INTO topic_entities(topic_id,entity_id,relation,confidence,source_message_id,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(topic_id,entity_id) DO UPDATE SET
                relation=excluded.relation,
                confidence=CASE WHEN excluded.confidence='EXTRACTED' THEN excluded.confidence ELSE topic_entities.confidence END""",
                (topic_id, entity_id, relation, confidence, source_message_id, now))
            db.execute("INSERT OR IGNORE INTO topic_entity_evidence(topic_id,entity_id,source_message_id,created_at) VALUES(?,?,?,?)",
                       (topic_id, entity_id, source_message_id, now))
            prior_sql = "SELECT DISTINCT te.topic_id FROM topic_entities te WHERE te.entity_id=? AND te.topic_id!=?"
            prior_args = [entity_id, topic_id]
            if not allow_cross_agent:
                prior_sql += " AND EXISTS (SELECT 1 FROM topic_episodes owned WHERE owned.topic_id=te.topic_id AND lower(owned.agent_id)=lower(?))"
                prior_args.append(owner_agent or "")
                prior_sql += " AND NOT EXISTS (SELECT 1 FROM topic_episodes foreign_ep WHERE foreign_ep.topic_id=te.topic_id AND lower(foreign_ep.agent_id)!=lower(?))"
                prior_args.append(owner_agent or "")
            prior = db.execute(prior_sql, prior_args).fetchall()
            for (other_id,) in prior:
                if kind == "file" and not exact_file:
                    continue
                relation = {"component_type": "mismo tipo", "design_group": "tema de diseño",
                            "feature": "mismo concepto", "module": "mismo concepto",
                            "report": "mismo concepto", "platform": "misma plataforma",
                            "python_function": "mismo símbolo", "python_class": "mismo símbolo",
                            "python_method": "mismo símbolo", "file": "mismo archivo"}.get(kind, "mismo elemento")
                db.execute("""INSERT OR IGNORE INTO topic_relations
                    (source_topic_id,target_topic_id,relation,confidence,reason,source_message_id,created_at)
                    VALUES(?,?,?,?,?,?,?)""", (topic_id, other_id, relation, "EXTRACTED",
                    "comparten una referencia explícita y normalizada" if kind == "file" else
                    "comparten una entidad identificada explícitamente", source_message_id, now))
        for term in terms:
            db.execute("INSERT OR IGNORE INTO topic_work_terms(topic_id,term) VALUES(?,?)", (topic_id, term))

    def backup(self, destination):
        target = Path(destination).expanduser().resolve()
        if target == self.db_path.resolve() or target.exists():
            raise ValueError("backup requiere un archivo nuevo")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source, sqlite3.connect(target) as dest:
            source.backup(dest)
        target.chmod(0o600)
        return {"ok": True, "source": str(self.db_path.resolve()), "backup": str(target)}

    def topic_graph(self, *, requester_agent="dashboard", limit=400, detail=False,
                    session_id=None, topic_offset=0, session_offset=0,
                    session_limit=100, session_query="", agent_ids=None):
        """Return a bounded topic/session/agent graph for the dashboard.

        Messages remain references opened from an episode; they are deliberately
        not rendered as thousands of force-layout nodes.
        """
        limit = max(1, min(1000, int(limit)))
        topic_offset = max(0, min(100000, int(topic_offset)))
        session_offset = max(0, min(100000, int(session_offset)))
        session_limit = max(1, min(100, int(session_limit)))
        requester = requester_agent or ""
        authorized_agents = self._effective_agent_ids(agent_ids)
        scope_marks = ",".join("?" for _ in (authorized_agents or []))
        focus_session_id = str(session_id or "").removeprefix("session:") or None
        with self._connect() as db:
            selected_where = ["(s0.capture_enabled=1 OR s0.agent_id=?)"]
            selected_args = [requester]
            selected_owner_predicate, selected_owner_args = self._topic_owner_predicate("t0.id")
            selected_where.append(f"({selected_owner_predicate})")
            selected_args.extend(selected_owner_args)
            selected_where.append("NOT EXISTS (SELECT 1 FROM topic_episodes hidden JOIN sessions hs ON hs.id=hidden.session_id WHERE hidden.topic_id=t0.id AND hs.capture_enabled=0 AND hs.agent_id!=?)")
            selected_args.append(requester)
            if authorized_agents is not None:
                selected_where.append(f"s0.agent_id IN ({scope_marks})")
                selected_args.extend(authorized_agents)
            if focus_session_id:
                selected_where.append("e0.session_id=?")
                selected_args.append(focus_session_id)
            selected_predicate = " AND ".join(selected_where)
            outer_where = ["(s.capture_enabled=1 OR s.agent_id=?)"]
            outer_args = []
            if authorized_agents is not None:
                outer_where.append(f"s.agent_id IN ({scope_marks})")
                outer_args.extend(authorized_agents)
            if focus_session_id:
                outer_where.append("e.session_id=?")
                outer_args.append(focus_session_id)
            outer_predicate = " AND ".join(outer_where)
            rows = db.execute(f"""
              WITH selected_topics AS (
                SELECT t0.id FROM topics t0 JOIN topic_episodes e0 ON e0.topic_id=t0.id
                JOIN sessions s0 ON s0.id=e0.session_id AND e0.agent_id=s0.agent_id
                WHERE {selected_predicate}
                GROUP BY t0.id ORDER BY t0.updated_at DESC, t0.id LIMIT ? OFFSET ?
              )
              SELECT DISTINCT t.id, t.title, t.summary, t.state, t.verification,
                     t.updated_at, e.session_id, e.agent_id,
                     COALESCE(ai.status, CASE WHEN ?!='' THEN 'pending' ELSE 'not_applicable' END) AS ai_status,
                     ai.model AS ai_model, ai.source_revision AS ai_source_revision,
                     ai.prompt_version AS ai_prompt_version, ai.last_error AS ai_error,
                     ai.processed_at AS ai_processed_at
              FROM topics t JOIN topic_episodes e ON e.topic_id=t.id
              JOIN sessions s ON s.id=e.session_id AND e.agent_id=s.agent_id
              LEFT JOIN topic_enrichment_state ai ON ai.topic_id=t.id
              JOIN selected_topics st ON st.id=t.id
              WHERE {outer_predicate}
              ORDER BY t.updated_at DESC, t.id""", (*selected_args, limit, topic_offset,
                os.environ.get("GRAPHTYN_MEMORY_SUMMARY_MODEL") or os.environ.get("OLLAMA_MODEL") or "",
                requester, *outer_args)).fetchall()
            total_topic_where = ["(s.capture_enabled=1 OR s.agent_id=?)"]
            total_topic_args: list[Any] = [requester]
            total_owner_predicate, total_owner_args = self._topic_owner_predicate("e.topic_id")
            total_topic_where.append(f"({total_owner_predicate})")
            total_topic_args.extend(total_owner_args)
            total_topic_where.append("NOT EXISTS (SELECT 1 FROM topic_episodes hidden JOIN sessions hs ON hs.id=hidden.session_id WHERE hidden.topic_id=e.topic_id AND hs.capture_enabled=0 AND hs.agent_id!=?)")
            total_topic_args.append(requester)
            if authorized_agents is not None:
                total_topic_where.append(f"s.agent_id IN ({scope_marks})")
                total_topic_args.extend(authorized_agents)
            if focus_session_id:
                total_topic_where.append("e.session_id=?")
                total_topic_args.append(focus_session_id)
            topic_total = db.execute("""SELECT COUNT(DISTINCT e.topic_id)
                FROM topic_episodes e JOIN sessions s ON s.id=e.session_id AND e.agent_id=s.agent_id
                WHERE """ + " AND ".join(total_topic_where), total_topic_args).fetchone()[0]

            session_where = ["(s.capture_enabled=1 OR s.agent_id=?)"]
            session_args: list[Any] = [requester]
            if authorized_agents is not None:
                session_where.append(f"s.agent_id IN ({scope_marks})")
                session_args.extend(authorized_agents)
            if focus_session_id:
                session_where.append("s.id=?")
                session_args.append(focus_session_id)
            if session_query:
                session_where.append("LOWER(s.id || ' ' || COALESCE(s.task,'') || ' ' || s.agent_id) LIKE ?")
                session_args.append("%" + str(session_query).casefold() + "%")
            session_predicate = " AND ".join(session_where)
            session_total = db.execute("SELECT COUNT(*) FROM sessions s WHERE " + session_predicate,
                                       session_args).fetchone()[0]
            session_sql = """SELECT s.*, COUNT(DISTINCT e.topic_id) AS topic_count,
                    COUNT(DISTINCT msg.id) AS message_count
                FROM sessions s LEFT JOIN topic_episodes e ON e.session_id=s.id AND e.agent_id=s.agent_id
                LEFT JOIN messages msg ON msg.session_id=s.id AND msg.agent_id=s.agent_id
                WHERE """ + session_predicate + """ GROUP BY s.id
                ORDER BY s.started_at DESC, s.id DESC LIMIT ? OFFSET ?"""
            session_rows = db.execute(session_sql,
                [*session_args, session_limit, session_offset]).fetchall()
        nodes, links, agents, sessions = {}, [], set(), set()
        session_catalog = {str(row["id"]): row for row in session_rows}
        for row in session_rows:
            session_node_id = "session:" + str(row["id"])
            agent_node_id = "agent:" + str(row["agent_id"])
            nodes.setdefault(session_node_id, {"id": session_node_id, "kind": "memory_session",
                "name": row["task"] or row["id"], "details": "Sesión de conversación",
                "session_id": row["id"], "agent_id": row["agent_id"],
                "task": row["task"], "status": row["status"],
                "topic_count": row["topic_count"], "message_count": row["message_count"]})
            nodes.setdefault(agent_node_id, {"id": agent_node_id, "kind": "memory_agent",
                "name": row["agent_id"], "details": "Agente participante"})
            sessions.add(session_node_id); agents.add(agent_node_id)
        topic_rows = []
        for row in rows:
            topic_id = "topic:" + row["id"]
            session_node_id = "session:" + row["session_id"]
            agent_id = "agent:" + row["agent_id"]
            title = self._unprotect(row["title"])
            nodes.setdefault(topic_id, {"id": topic_id, "kind": "memory_topic", "name": title,
                "details": self._unprotect(row["summary"]), "topic_id": row["id"],
                "state": row["state"], "verification": row["verification"],
                "session_id": row["session_id"], "agent_id": row["agent_id"],
                "agent_ids": [row["agent_id"]],
                "ai_status": row["ai_status"], "ai_model": row["ai_model"],
                "ai_source_revision": row["ai_source_revision"], "ai_prompt_version": row["ai_prompt_version"],
                "ai_error": row["ai_error"], "ai_processed_at": row["ai_processed_at"]})
            topic_node = nodes[topic_id]
            if row["agent_id"] not in topic_node["agent_ids"]:
                topic_node["agent_ids"].append(row["agent_id"])
                topic_node["agent_ids"].sort()
            session_meta = session_catalog.get(str(row["session_id"]))
            nodes.setdefault(session_node_id, {"id": session_node_id, "kind": "memory_session",
                "name": (session_meta["task"] if session_meta else None) or row["session_id"],
                "details": "Sesión de conversación",
                "session_id": row["session_id"], "agent_id": row["agent_id"],
                "task": session_meta["task"] if session_meta else None,
                "status": session_meta["status"] if session_meta else None,
                "topic_count": session_meta["topic_count"] if session_meta else None,
                "message_count": session_meta["message_count"] if session_meta else None})
            nodes.setdefault(agent_id, {"id": agent_id, "kind": "memory_agent",
                "name": row["agent_id"], "details": "Agente participante"})
            sessions.add(session_node_id); agents.add(agent_id)
            links.append({"source": topic_id, "target": session_node_id, "label": "episodio", "confidence": "EXTRACTED"})
            links.append({"source": topic_id, "target": agent_id, "label": "participó", "confidence": "EXTRACTED"})
            topic_rows.append(row)
        # Episode order remains available through the topic detail. Temporal
        # adjacency alone is not evidence that two subjects are related.
        seen_topic_links = set()
        topic_ids = {row["id"] for row in topic_rows}
        if topic_ids:
            placeholders = ",".join("?" for _ in topic_ids)
            with self._connect() as db:
                relations = db.execute(f"""SELECT source_topic_id,target_topic_id,relation,confidence,reason,source_message_id
                    FROM topic_relations WHERE source_topic_id IN ({placeholders})
                    AND target_topic_id IN ({placeholders})""", [*topic_ids, *topic_ids]).fetchall()
                candidates = db.execute(f"""SELECT id,source_topic_id,target_topic_id,relation,reason,evidence_json
                    FROM topic_relation_reviews WHERE status='pending'
                    AND source_topic_id IN ({placeholders}) AND target_topic_id IN ({placeholders})
                    ORDER BY updated_at DESC LIMIT 1000""", [*topic_ids, *topic_ids]).fetchall()
                term_frequency, topic_count, agent_terms = self._topic_relation_term_stats(
                    db, requester_agent=requester, agent_ids=authorized_agents)
            for relation in relations:
                source, target = "topic:" + relation[0], "topic:" + relation[1]
                links.append({"source": source, "target": target, "label": relation[2],
                              "confidence": relation[3], "reason": relation[4],
                              "source_message_id": relation[5]})
                if relation[2] not in {"misma plataforma"}:
                    seen_topic_links.add(tuple(sorted((source, target))))
            for candidate in candidates:
                source, target = "topic:" + candidate["source_topic_id"], "topic:" + candidate["target_topic_id"]
                if tuple(sorted((source, target))) in seen_topic_links:
                    continue
                try:
                    evidence = json.loads(candidate["evidence_json"] or "[]")
                except (TypeError, ValueError):
                    evidence = []
                if not isinstance(evidence, dict):
                    evidence = {}
                specific_terms = self._specific_shared_terms(
                    evidence.get("shared_terms", []), term_frequency, topic_count, agent_terms)
                shared_entities = evidence.get("shared_entity_ids", [])
                if len(specific_terms) < 2 and not (shared_entities and specific_terms):
                    continue
                evidence["shared_terms"] = specific_terms[:12]
                evidence["requires_review"] = True
                links.append({"source": source, "target": target, "label": candidate["relation"],
                              "confidence": "AMBIGUOUS", "status": "pending", "relation_id": candidate["id"],
                              "reason": candidate["reason"], "evidence": evidence})
        if detail and nodes:
            topic_ids = [node["topic_id"] for node in nodes.values() if node["kind"] == "memory_topic"]
            placeholders = ",".join("?" for _ in topic_ids)
            with self._connect() as db:
                entity_scope = f" AND ep.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
                entities = db.execute(f"""SELECT DISTINCT e.id,e.kind,e.entity_key,e.name,e.metadata_json
                    FROM entities e JOIN topic_entities te ON te.entity_id=e.id
                    JOIN topic_episodes ep ON ep.topic_id=te.topic_id JOIN sessions es ON es.id=ep.session_id
                    WHERE te.topic_id IN ({placeholders}) AND (es.capture_enabled=1 OR es.agent_id=?)
                    {entity_scope}""", [*topic_ids, requester, *(authorized_agents or [])]).fetchall()
                episode_scope = f" AND e.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
                episodes = db.execute(f"""SELECT e.id,e.topic_id,e.session_id,e.agent_id,e.problem,e.result,
                    (SELECT COUNT(*) FROM topic_messages tm JOIN messages mm ON mm.id=tm.message_id AND mm.agent_id=e.agent_id WHERE tm.episode_id=e.id) AS message_count
                    FROM topic_episodes e JOIN sessions es ON es.id=e.session_id AND es.agent_id=e.agent_id
                    WHERE e.topic_id IN ({placeholders}) AND (es.capture_enabled=1 OR es.agent_id=?)
                    {episode_scope} ORDER BY e.created_at,e.id""", [*topic_ids, requester, *(authorized_agents or [])]).fetchall()
            for entity in entities:
                entity_id = "entity:" + entity["id"]
                try:
                    entity_metadata = json.loads(entity["metadata_json"] or "{}")
                except (TypeError, ValueError):
                    entity_metadata = {}
                nodes[entity_id] = {"id": entity_id, "kind": "memory_entity", "name": entity["name"],
                                    "details": f"{entity['kind']}:{entity['entity_key']}",
                                    "entity_id": entity["id"], "entity_kind": entity["kind"],
                                    "entity_key": entity["entity_key"], "metadata": entity_metadata}
                for topic_id in topic_ids:
                    with self._connect() as db:
                        linked = db.execute("SELECT relation,confidence,source_message_id FROM topic_entities WHERE topic_id=? AND entity_id=?",
                                            (topic_id, entity["id"])).fetchone()
                    if linked:
                        links.append({"source": "topic:" + topic_id, "target": entity_id,
                                      "label": linked[0], "confidence": linked[1],
                                      "source_message_id": linked[2]})
            for episode in episodes[: max(1, min(1200, limit * 4))]:
                episode_id = "episode:" + episode["id"]
                topic_id = "topic:" + episode["topic_id"]
                nodes[episode_id] = {"id": episode_id, "kind": "memory_episode",
                    "name": self._unprotect(episode["problem"])[:160],
                    "details": self._unprotect(episode["result"] or ""),
                    "episode_id": episode["id"], "topic_id": episode["topic_id"],
                    "session_id": episode["session_id"], "agent_id": episode["agent_id"],
                    "message_count": episode["message_count"]}
                links.append({"source": topic_id, "target": episode_id, "label": "episodio", "confidence": "EXTRACTED"})
                links.append({"source": episode_id, "target": "session:" + episode["session_id"], "label": "ocurrió en", "confidence": "EXTRACTED"})
        node_list = self._decorate_node_refs(list(nodes.values()))
        returned_topics = len({row["id"] for row in topic_rows})
        returned_sessions = len({node for node in sessions if node.startswith("session:")})
        return {"ok": True, "view": "topics", "nodes": node_list, "links": links,
                "agents": [{"id": node.removeprefix("agent:"), "color": "#22d3ee"} for node in sorted(agents)],
                "consulters": [], "metadata": {"topic_count": len([n for n in node_list if n["kind"] == "memory_topic"]),
                    "topic_total": topic_total, "topic_offset": topic_offset, "topic_returned": returned_topics,
                    "next_topic_offset": topic_offset + limit if topic_offset + returned_topics < topic_total else None,
                    "session_count": returned_sessions, "session_offset": session_offset, "session_total": session_total,
                    "session_returned": returned_sessions,
                    "next_session_offset": session_offset + session_limit if session_offset + returned_sessions < session_total else None,
                    "session_focus": focus_session_id,
                    "episode_count": len([n for n in node_list if n["kind"] == "memory_episode"]),
                    "entity_count": len([n for n in node_list if n["kind"] == "memory_entity"]),
                    "mode": "detailed" if detail else "simplified",
                    "message_rendering": "panel_on_demand", "coverage": self.topic_coverage(requester_agent, authorized_agents)}}

    def relation_candidates(self, *, requester_agent=None, status="pending", limit=50, propose=True,
                            agent_ids=None):
        """List cautious thematic candidates; graph edges stay marked ambiguous until reviewed."""
        limit = max(1, min(200, int(limit)))
        authorized_agents = self._effective_agent_ids(agent_ids)
        if propose:
            self._propose_relation_candidates(requester_agent=requester_agent, agent_ids=authorized_agents)
        with self._connect() as db:
            relation_scope = ""
            relation_args = [status, status, requester_agent or "", requester_agent or ""]
            source_owner_predicate, source_owner_args = self._topic_owner_predicate("r.source_topic_id")
            target_owner_predicate, target_owner_args = self._topic_owner_predicate("r.target_topic_id")
            relation_scope += f" AND ({source_owner_predicate}) AND ({target_owner_predicate})"
            relation_args.extend(source_owner_args); relation_args.extend(target_owner_args)
            if authorized_agents is not None:
                marks = ",".join("?" for _ in authorized_agents)
                relation_scope += f" AND se.agent_id IN ({marks}) AND te.agent_id IN ({marks})"
                relation_args.extend(authorized_agents); relation_args.extend(authorized_agents)
            fetch_limit = 1000 if status == "pending" else limit
            rows = db.execute("""SELECT DISTINCT r.*,s.title AS source_title,t.title AS target_title
                FROM topic_relation_reviews r JOIN topics s ON s.id=r.source_topic_id
                JOIN topics t ON t.id=r.target_topic_id
                JOIN topic_episodes se ON se.topic_id=s.id JOIN sessions ss ON ss.id=se.session_id
                JOIN topic_episodes te ON te.topic_id=t.id JOIN sessions ts ON ts.id=te.session_id
                WHERE (? IS NULL OR r.status=?)
                  AND (ss.capture_enabled=1 OR ss.agent_id=?)
                  AND (ts.capture_enabled=1 OR ts.agent_id=?)
                """ + relation_scope + " ORDER BY r.updated_at DESC,r.id LIMIT ?",
                [*relation_args, fetch_limit]).fetchall()
            term_frequency, topic_count, agent_terms = self._topic_relation_term_stats(
                db, requester_agent=requester_agent, agent_ids=authorized_agents)
            result = []; suppressed = 0
            for row in rows:
                item = dict(row)
                item["source_title"] = self._unprotect(item["source_title"])
                item["target_title"] = self._unprotect(item["target_title"])
                item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
                if status == "pending":
                    if not isinstance(item["evidence"], dict):
                        item["evidence"] = {}
                    specific_terms = self._specific_shared_terms(
                        item["evidence"].get("shared_terms", []), term_frequency, topic_count, agent_terms)
                    shared_entities = item["evidence"].get("shared_entity_ids", [])
                    if len(specific_terms) < 2 and not (shared_entities and specific_terms):
                        suppressed += 1
                        continue
                    item["evidence"]["shared_terms"] = specific_terms[:12]
                    item["evidence"]["requires_review"] = True
                item["source_reference"] = self._node_reference(db, "memory_topic", item["source_topic_id"])
                item["target_reference"] = self._node_reference(db, "memory_topic", item["target_topic_id"])
                result.append(item)
                if len(result) >= limit:
                    break
        return {"ok": True, "candidates": result, "status": status, "suppressed_low_specificity": suppressed,
                "retrieval": "specific-lexical-candidates-review"}

    def _ai_review_candidates(self, limit=20, agent_ids=None):
        from .memory_extraction import configured_summary_model
        if not configured_summary_model():
            return 0
        from .memory_extraction import assisted_relation_review
        reviewed = 0
        authorized_agents = self._effective_agent_ids(agent_ids)
        with self._connect() as db:
            if authorized_agents is not None:
                marks = ",".join("?" for _ in authorized_agents)
                source_owner_predicate, source_owner_args = self._topic_owner_predicate("r.source_topic_id")
                target_owner_predicate, target_owner_args = self._topic_owner_predicate("r.target_topic_id")
                query = f"""SELECT DISTINCT r.* FROM topic_relation_reviews r
                    JOIN topic_episodes e ON e.topic_id=r.source_topic_id JOIN sessions s ON s.id=e.session_id
                    JOIN topic_episodes te ON te.topic_id=r.target_topic_id
                    WHERE r.status='pending' AND e.agent_id IN ({marks}) AND te.agent_id IN ({marks})
                    AND ({source_owner_predicate}) AND ({target_owner_predicate})
                    ORDER BY r.updated_at DESC LIMIT ?"""
                rows = db.execute(query, [*(authorized_agents or []), *(authorized_agents or []),
                                          *source_owner_args, *target_owner_args,
                                          max(1, min(20, limit))]).fetchall()
            else:
                rows = db.execute("SELECT * FROM topic_relation_reviews WHERE status='pending' ORDER BY updated_at DESC LIMIT ?", (max(1, min(20, limit)),)).fetchall()
        for row in rows:
            with self._connect() as db:
                left = db.execute("SELECT id,title,summary FROM topics WHERE id=?", (row["source_topic_id"],)).fetchone()
                right = db.execute("SELECT id,title,summary FROM topics WHERE id=?", (row["target_topic_id"],)).fetchone()
            evidence = json.loads(row["evidence_json"] or "{}")
            if not isinstance(evidence, dict):
                evidence = {"raw_evidence": evidence}
            base_evidence = {key: value for key, value in evidence.items() if not str(key).startswith("model_")}
            candidate_fingerprint = hashlib.sha256(json.dumps(base_evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if evidence.get("model_source_fingerprint") == candidate_fingerprint and evidence.get("model_classification"):
                continue
            review, provider = assisted_relation_review(
                {"id": left["id"], "title": self._unprotect(left["title"]), "summary": self._unprotect(left["summary"])},
                {"id": right["id"], "title": self._unprotect(right["title"]), "summary": self._unprotect(right["summary"])}, evidence)
            if review:
                evidence.update({"model_classification": review["classification"], "model_reason": review["reason"], "model_provider": provider,
                                 "model_source_fingerprint": candidate_fingerprint, "model_prompt_version": "relation-review-v1"})
                with self._connect() as db:
                    db.execute("UPDATE topic_relation_reviews SET reason=?,evidence_json=?,updated_at=? WHERE id=?",
                               (review["reason"] or row["reason"], json.dumps(evidence, ensure_ascii=False), time.time(), row["id"]))
                reviewed += 1
        return reviewed

    def _propose_relation_candidates(self, requester_agent=None, agent_ids=None):
        authorized_agents = self._effective_agent_ids(agent_ids)
        with self._connect() as db:
            scope = ""
            args = [requester_agent or ""]
            owner_predicate, owner_args = self._topic_owner_predicate("t.id")
            scope += f" AND ({owner_predicate})"
            args.extend(owner_args)
            if authorized_agents is not None:
                marks = ",".join("?" for _ in authorized_agents)
                scope += f" AND e.agent_id IN ({marks})"
                args.extend(authorized_agents)
            rows = db.execute("""SELECT DISTINCT t.id,t.title,t.summary,e.session_id,e.agent_id
                FROM topics t JOIN topic_episodes e ON e.topic_id=t.id JOIN sessions s ON s.id=e.session_id
                WHERE t.state!='archivado' AND (s.capture_enabled=1 OR s.agent_id=?)
                """ + scope + " ORDER BY t.updated_at DESC LIMIT 500", args).fetchall()
            items = []
            for row in rows:
                text = (self._unprotect(row["title"]) + " " + self._unprotect(row["summary"])).casefold()
                terms = {term for term in re.findall(r"[\wáéíóúñ]{5,}", text)
                         if term not in _RELATION_STOPWORDS}
                entities = {r[0] for r in db.execute("SELECT entity_id FROM topic_entities WHERE topic_id=?", (row["id"],))}
                items.append((row, terms, entities))
            term_frequency = {}
            for _, candidate_terms, _ in items:
                for term in candidate_terms:
                    term_frequency[term] = term_frequency.get(term, 0) + 1
            specificity_threshold = max(4, math.ceil(len(items) * 0.015))
            agent_terms = {token for row, _, _ in items
                           for token in re.findall(r"[\wáéíóúñ]{5,}", str(row["agent_id"] if "agent_id" in row.keys() else "").casefold())}
            now = time.time()
            for index, (left, left_terms, left_entities) in enumerate(items):
                for right, right_terms, right_entities in items[index + 1:]:
                    if left["id"] == right["id"]: continue
                    shared_terms_all = sorted(left_terms & right_terms)
                    shared_terms = [term for term in shared_terms_all
                                    if term_frequency.get(term, 0) <= specificity_threshold
                                    and term not in agent_terms]
                    shared_entities = sorted(left_entities & right_entities)
                    # Avoid connecting topics merely because both mention the
                    # project, a provider, or another high-frequency term.
                    if len(shared_terms) < 2 and not (shared_entities and shared_terms):
                        continue
                    source, target = sorted((left["id"], right["id"]))
                    evidence = {"shared_terms": shared_terms[:12],
                                "suppressed_common_terms": [term for term in shared_terms_all if term not in shared_terms][:12],
                                "shared_entity_ids": shared_entities[:12],
                                "method": "lexical_candidate", "requires_review": True}
                    relation_id = "rel_" + hashlib.sha256((source + "\0" + target + "\0possible").encode()).hexdigest()[:24]
                    db.execute("""INSERT INTO topic_relation_reviews
                        (id,source_topic_id,target_topic_id,relation,status,reason,evidence_json,actor,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(source_topic_id,target_topic_id,relation) DO UPDATE SET
                          evidence_json=excluded.evidence_json, updated_at=excluded.updated_at
                        WHERE topic_relation_reviews.status='pending'""", (relation_id, source, target, "posible relación", "pending",
                        "coincidencia candidata; requiere evidencia humana o de IA", json.dumps(evidence, ensure_ascii=False), "system", now, now))

    def _topic_relation_term_stats(self, db, *, requester_agent=None, agent_ids=None):
        """Count topic-level term frequency within the caller's visible memory scope."""
        authorized_agents = self._effective_agent_ids(agent_ids)
        owner_predicate, owner_args = self._topic_owner_predicate("e.topic_id")
        where = ["t.state!='archivado'", "(s.capture_enabled=1 OR s.agent_id=?)", owner_predicate]
        args: list[Any] = [requester_agent or "", *owner_args]
        if authorized_agents is not None:
            marks = ",".join("?" for _ in authorized_agents)
            where.append(f"e.agent_id IN ({marks})")
            args.extend(authorized_agents)
        predicate = " AND ".join(f"({clause})" for clause in where)
        rows = db.execute("""SELECT tw.term,COUNT(DISTINCT t.id) AS frequency
            FROM topic_work_terms tw JOIN topics t ON t.id=tw.topic_id
            JOIN topic_episodes e ON e.topic_id=t.id JOIN sessions s ON s.id=e.session_id
            WHERE """ + predicate + " GROUP BY tw.term", args).fetchall()
        count = db.execute("""SELECT COUNT(DISTINCT t.id)
            FROM topics t JOIN topic_episodes e ON e.topic_id=t.id
            JOIN sessions s ON s.id=e.session_id WHERE """ + predicate, args).fetchone()[0]
        agents = db.execute("""SELECT DISTINCT e.agent_id FROM topic_episodes e
            JOIN topics t ON t.id=e.topic_id JOIN sessions s ON s.id=e.session_id
            WHERE """ + predicate, args).fetchall()
        agent_terms = {token for row in agents
                       for token in re.findall(r"[\wáéíóúñ]{5,}", str(row[0] or "").casefold())}
        return ({str(row["term"]).casefold(): int(row["frequency"]) for row in rows},
                int(count), agent_terms)

    @staticmethod
    def _specific_shared_terms(terms, term_frequency, topic_count, agent_terms=()):
        threshold = max(4, math.ceil(int(topic_count or 0) * 0.015))
        return [str(term).casefold() for term in terms
                if str(term).casefold() not in _RELATION_STOPWORDS
                and str(term).casefold() not in agent_terms
                and term_frequency.get(str(term).casefold(), 0) <= threshold]

    def relation_review(self, relation_id, *, status, actor, reason, agent_ids=None):
        if status not in {"accepted", "rejected"}:
            raise ValueError("estado de revisión inválido")
        if not str(actor).strip() or not str(reason).strip():
            raise ValueError("actor y motivo son obligatorios")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM topic_relation_reviews WHERE id=?", (relation_id,)).fetchone()
            if not row: raise ValueError("candidata inexistente")
            authorized_agents = self._effective_agent_ids(agent_ids)
            if authorized_agents is not None:
                marks = ",".join("?" for _ in authorized_agents)
                visible = db.execute("""SELECT 1 FROM topic_episodes se JOIN topic_episodes te
                    ON te.topic_id=? JOIN sessions ss ON ss.id=se.session_id JOIN sessions ts ON ts.id=te.session_id
                    WHERE se.topic_id=? AND se.agent_id IN (""" + marks + ") AND te.agent_id IN (" + marks + ") LIMIT 1",
                    [row["target_topic_id"], row["source_topic_id"], *(authorized_agents or []), *(authorized_agents or [])]).fetchone()
                if not visible:
                    raise PermissionError("candidata inexistente o no accesible")
            db.execute("UPDATE topic_relation_reviews SET status=?,actor=?,reason=?,updated_at=? WHERE id=?",
                       (status, actor, reason, time.time(), relation_id))
            if status == "accepted":
                db.execute("""INSERT OR REPLACE INTO topic_relations
                    (source_topic_id,target_topic_id,relation,confidence,reason,source_message_id,created_at)
                    VALUES(?,?,?,?,?,?,?)""", (row["source_topic_id"], row["target_topic_id"], row["relation"],
                    "REVIEWED", reason, None, time.time()))
            else:
                db.execute("DELETE FROM topic_relations WHERE source_topic_id=? AND target_topic_id=? AND relation=?",
                           (row["source_topic_id"], row["target_topic_id"], row["relation"]))
        return {"ok": True, "relation_id": relation_id, "status": status, "actor": actor}

    def topic_coverage(self, requester_agent=None, agent_ids=None):
        authorized_agents = self._effective_agent_ids(agent_ids)
        scope_clause = ""
        scope_args = []
        if authorized_agents is not None:
            marks = ",".join("?" for _ in authorized_agents)
            scope_clause = f" AND s.agent_id IN ({marks})"
            scope_args = authorized_agents
        with self._connect() as db:
            row = db.execute("""SELECT COUNT(*) AS discovered,
                COALESCE(SUM(CASE WHEN m.rowid<=COALESCE(p.cursor,0) THEN 1 ELSE 0 END),0) AS processed
                FROM messages m JOIN sessions s ON s.id=m.session_id AND s.agent_id=m.agent_id
                LEFT JOIN topic_progress p ON p.session_id=s.id
                WHERE s.status!='quarantined' AND (s.capture_enabled=1 OR s.agent_id=?)""" + scope_clause,
                [requester_agent or "", *scope_args]).fetchone()
        return {**dict(row), "pending": row["discovered"] - row["processed"],
                "scope": "persisted_messages", "extraction_quality": "limited; processing is not recall",
                "source_exclusions": "not measured"}

    def process_topics(self, session_id, *, batch_messages=30, batch_tokens=6000):
        session = self.get_session(session_id)
        if not session or not session["capture_enabled"]:
            raise PermissionError("sesión sin autorización de captura")
        memory_scope = self.memory_scope()
        allow_cross_agent = memory_scope["space_type"] != "agent_brain"
        # Topics keep their authoring agent identity in project stores too.
        # Cross-agent continuity is represented by evidence-backed edges.
        match_owner = session["agent_id"]
        total = 0
        while True:
            with self._connect() as db:
                # Cursor, episodes and references commit atomically. Concurrent
                # ingest/compaction cannot consume the same batch twice.
                db.execute("BEGIN IMMEDIATE")
                progress = db.execute("SELECT cursor FROM topic_progress WHERE session_id=?", (session_id,)).fetchone()
                cursor = progress[0] if progress else 0
                rows = db.execute("SELECT rowid AS seq,* FROM messages WHERE session_id=? AND agent_id=? AND rowid>? ORDER BY rowid LIMIT ?",
                                  (session_id, session["agent_id"], cursor, max(1, min(100, batch_messages)))).fetchall()
                if not rows:
                    break
                batch, cost = [], 0
                for row in rows:
                    msg = self._message_row(row)
                    size = encoded_tokens(msg)
                    if batch and cost + size > batch_tokens:
                        break
                    batch.append(msg)
                    cost += size
                # Deterministic mode associates a new turn only when an
                # explicit entity and stable work term support continuation.
                # A shared category such as "button" alone never merges work.
                prior = db.execute("SELECT e.* FROM topic_episodes e JOIN topic_messages r ON r.episode_id=e.id JOIN messages m ON m.id=r.message_id AND m.agent_id=e.agent_id WHERE e.session_id=? AND e.agent_id=? ORDER BY m.rowid DESC LIMIT 1", (session_id, session["agent_id"])).fetchone()
                episode = dict(prior) if prior else None
                for msg in batch:
                    if msg["role"] == "user":
                        entities, terms = self._subject_terms(msg["content"])
                        entities.extend(self._file_references(msg["content"]))
                        entity_ids = self._entity_ids(db, entities, msg["id"], msg["created_at"])
                        matched_topic = self._find_topic_match(db, session_id, entity_ids, terms,
                                                               owner_agent=match_owner)
                        key = hashlib.sha256((session_id + msg["id"]).encode()).hexdigest()[:24]
                        topic_id, episode_id = matched_topic or "top_" + key, "epi_" + key
                        title = re.sub(r"\s+", " ", msg["content"]).strip()[:180] or "Asunto sin texto"
                        now = msg["created_at"]
                        db.execute("INSERT OR IGNORE INTO topics(id,title,summary,created_at,updated_at) VALUES(?,?,?,?,?)",
                                   (topic_id, self._protect(title), self._protect(msg["content"][:1200]), now, now))
                        db.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, topic_id))
                        db.execute("INSERT OR IGNORE INTO topic_episodes(id,topic_id,session_id,agent_id,problem,extraction,created_at) VALUES(?,?,?,?,?,?,?)",
                                   (episode_id, topic_id, session_id, msg["agent_id"], self._protect(msg["content"][:2400]), "deterministic-limited", now))
                        episode = {"id": episode_id, "topic_id": topic_id}
                        db.execute("INSERT INTO topic_events(topic_id,actor,action,details_json,created_at) VALUES(?,?,?,?,?)",
                                   (topic_id, msg["agent_id"], "continued" if matched_topic else "created",
                                    json.dumps({"message_id": msg["id"], "extraction": "deterministic-limited",
                                                "matched_existing": bool(matched_topic), "entity_ids": entity_ids}), time.time()))
                        self._link_topic_entities(db, topic_id, entity_ids, terms, msg["id"], now,
                                                  owner_agent=msg["agent_id"], allow_cross_agent=allow_cross_agent)
                    elif episode is None:
                        key = hashlib.sha256((session_id + msg["id"]).encode()).hexdigest()[:24]
                        topic_id, episode_id = "top_" + key, "epi_" + key
                        now = msg["created_at"]
                        title = re.sub(r"\s+", " ", msg["content"]).strip()[:180] or "Asunto sin texto"
                        db.execute("INSERT OR IGNORE INTO topics(id,title,summary,created_at,updated_at) VALUES(?,?,?,?,?)",
                                   (topic_id, self._protect(title), self._protect(msg["content"][:1200]), now, now))
                        db.execute("INSERT OR IGNORE INTO topic_episodes(id,topic_id,session_id,agent_id,problem,extraction,created_at) VALUES(?,?,?,?,?,?,?)",
                                   (episode_id, topic_id, session_id, msg["agent_id"], self._protect(msg["content"][:2400]), "deterministic-limited", now))
                        episode = {"id": episode_id, "topic_id": topic_id}
                        db.execute("INSERT INTO topic_events(topic_id,actor,action,details_json,created_at) VALUES(?,?,?,?,?)",
                                   (topic_id, msg["agent_id"], "created", json.dumps({"message_id": msg["id"], "extraction": "deterministic-limited"}), time.time()))
                    db.execute("INSERT OR IGNORE INTO topic_messages VALUES(?,?)", (episode["id"], msg["id"]))
                    if msg["role"] == "assistant":
                        db.execute("UPDATE topic_episodes SET result=? WHERE id=?", (self._protect(msg["content"][:2400]), episode["id"]))
                last = batch[-1]["seq"]
                db.execute("INSERT INTO topic_progress VALUES(?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET cursor=excluded.cursor,processed=topic_progress.processed+excluded.processed,updated_at=excluded.updated_at",
                           (session_id, last, len(batch), time.time()))
                total += len(batch)
        # File references use an independent cursor so existing topic histories
        # can be enriched without resetting their main thematic cursor.
        file_references_processed = 0
        while True:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                progress = db.execute("SELECT cursor FROM topic_file_progress WHERE session_id=?", (session_id,)).fetchone()
                cursor = progress[0] if progress else 0
                rows = db.execute("""SELECT m.rowid AS seq,m.id,m.agent_id,m.role,m.content,m.created_at,
                        (SELECT tm.episode_id FROM topic_messages tm JOIN topic_episodes e ON e.id=tm.episode_id
                         WHERE tm.message_id=m.id AND e.agent_id=m.agent_id ORDER BY e.created_at,e.id LIMIT 1) AS episode_id,
                        (SELECT e.topic_id FROM topic_messages tm JOIN topic_episodes e ON e.id=tm.episode_id
                         WHERE tm.message_id=m.id AND e.agent_id=m.agent_id ORDER BY e.created_at,e.id LIMIT 1) AS topic_id
                    FROM messages m WHERE m.session_id=? AND m.agent_id=? AND m.rowid>? ORDER BY m.rowid LIMIT ?""",
                    (session_id, session["agent_id"], cursor, max(1, min(100, batch_messages)))).fetchall()
                if not rows:
                    break
                batch, cost = [], 0
                for row in rows:
                    size = encoded_tokens(row["content"] or "")
                    if batch and cost + size > batch_tokens:
                        break
                    batch.append(row)
                    cost += size
                for row in batch:
                    if not row["topic_id"]:
                        continue
                    references = self._file_references(self._unprotect(row["content"]))
                    if not references:
                        continue
                    entity_ids = self._entity_ids(db, references, row["id"], row["created_at"])
                    owner = db.execute("SELECT agent_id FROM topic_episodes WHERE id=?", (row["episode_id"],)).fetchone()
                    self._link_topic_entities(db, row["topic_id"], entity_ids, set(), row["id"],
                                              row["created_at"], owner_agent=owner[0] if owner else row["agent_id"],
                                              allow_cross_agent=allow_cross_agent)
                    file_references_processed += len(entity_ids)
                last = batch[-1]["seq"]
                db.execute("""INSERT INTO topic_file_progress VALUES(?,?,?,?)
                    ON CONFLICT(session_id) DO UPDATE SET cursor=excluded.cursor,
                    processed=topic_file_progress.processed+excluded.processed,updated_at=excluded.updated_at""",
                    (session_id, last, len(batch), time.time()))
        return {"ok": True, "processed": total, "file_references_processed": file_references_processed,
                "coverage": self.topic_coverage(), "extraction": "deterministic-limited"}

    def _topic_source_snapshot(self, db, topic_id):
        """Hash every source message while retaining a bounded, useful context."""
        digest = hashlib.sha256()
        cursor = db.execute("""SELECT m.rowid AS seq,m.id,m.role,m.content,m.created_at
            FROM topic_messages tm JOIN messages m ON m.id=tm.message_id
            JOIN topic_episodes e ON e.id=tm.episode_id
            WHERE e.topic_id=? AND m.agent_id=e.agent_id ORDER BY m.rowid""", (topic_id,))
        first_user = None; latest = []
        count = 0; revision = 0
        for row in cursor:
            content = self._unprotect(row["content"])
            digest.update(json.dumps([row["id"], row["role"], row["created_at"], content], ensure_ascii=False, separators=(",", ":")).encode())
            count += 1; revision = max(revision, int(row["seq"]))
            item = {"id": row["id"], "role": row["role"], "content": content, "created_at": row["created_at"], "seq": row["seq"]}
            if first_user is None and row["role"] == "user": first_user = item
            latest.append(item)
            if len(latest) > 18: latest.pop(0)
        selected = ([] if first_user is None else [first_user]) + [item for item in latest if not first_user or item["id"] != first_user["id"]]
        # Reserve a bounded prompt budget even for very long topics.
        while selected and encoded_tokens(selected) > 9000:
            selected.pop(1 if len(selected) > 1 else 0)
        return digest.hexdigest(), revision, count, selected

    def _queue_topic_enrichment(self, db, topic_id, fingerprint, model, prompt_version, now, force=False, source_revision=0):
        state = db.execute("SELECT * FROM topic_enrichment_state WHERE topic_id=?", (topic_id,)).fetchone()
        # Upgrade stores enriched by Graphtyn <=0.7 without invoking the model
        # again: the old event is evidence that the current source was already
        # handled when no newer topic message exists.
        if state is None and not force:
            topic_row = db.execute("SELECT updated_at FROM topics WHERE id=?", (topic_id,)).fetchone()
            old = db.execute("SELECT details_json,created_at FROM topic_events WHERE topic_id=? AND action='enriched' ORDER BY id DESC LIMIT 1", (topic_id,)).fetchone()
            if old and topic_row and float(old["created_at"] or 0) >= float(topic_row["updated_at"] or 0) - 1e-6:
                try: details = json.loads(old["details_json"] or "{}")
                except (TypeError, ValueError): details = {}
                old_provider = str(details.get("provider") or "")
                old_model = str(details.get("model") or (old_provider.split(":", 1)[1] if ":" in old_provider else model))
                db.execute("""INSERT INTO topic_enrichment_state(topic_id,source_fingerprint,source_revision,model,prompt_version,status,processed_at,created_at,updated_at)
                    VALUES(?,?,?,?,?,'enriched',?,?,?)""", (topic_id, fingerprint, source_revision, old_model, prompt_version, old["created_at"], now, now))
                state = db.execute("SELECT * FROM topic_enrichment_state WHERE topic_id=?", (topic_id,)).fetchone()
        if state and state["manual_protected"] and not force:
            db.execute("""INSERT INTO topic_enrichment_state(topic_id,source_fingerprint,source_revision,model,prompt_version,status,manual_protected,last_error,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET source_fingerprint=excluded.source_fingerprint,status='not_applicable',last_error='manual_edit_protected',updated_at=excluded.updated_at""",
                       (topic_id, fingerprint, source_revision, model, prompt_version, "not_applicable", 1, "manual_edit_protected", now, now))
            return False, "manual_protected"
        if state and not force and state["status"] == "enriched" and state["source_fingerprint"] == fingerprint and (state["model"] != model or state["prompt_version"] != prompt_version):
            db.execute("UPDATE topic_enrichment_state SET status='stale',last_error='model_or_prompt_changed; use force',updated_at=? WHERE topic_id=?", (now, topic_id))
            return False, "model_changed"
        if state and not force and state["status"] == "enriched" and state["source_fingerprint"] == fingerprint and state["model"] == model and state["prompt_version"] == prompt_version:
            return False, "unchanged"
        queue_id = "enq_" + hashlib.sha256((topic_id + fingerprint + model + prompt_version).encode()).hexdigest()[:28]
        prior_queue = db.execute("SELECT attempts,status FROM topic_enrichment_queue WHERE topic_id=? AND source_fingerprint=? AND model=? AND prompt_version=?", (topic_id, fingerprint, model, prompt_version)).fetchone()
        if prior_queue and prior_queue["status"] == "failed" and prior_queue["attempts"] >= 2 and not force:
            return False, "failed_retry_required"
        db.execute("""INSERT INTO topic_enrichment_queue(id,topic_id,source_fingerprint,model,prompt_version,status,attempts,next_attempt_at,last_error,created_at,updated_at)
            VALUES(?,?,?,?,?,'queued',0,0,'',?,?) ON CONFLICT(topic_id,source_fingerprint,model,prompt_version) DO UPDATE SET status='queued',next_attempt_at=0,last_error='',updated_at=excluded.updated_at""",
                   (queue_id, topic_id, fingerprint, model, prompt_version, now, now))
        db.execute("""INSERT INTO topic_enrichment_state(topic_id,source_fingerprint,source_revision,model,prompt_version,status,attempt_count,last_error,created_at,updated_at)
            VALUES(?,?,?,?,?,'pending',0,'',?,?) ON CONFLICT(topic_id) DO UPDATE SET source_fingerprint=excluded.source_fingerprint,model=excluded.model,prompt_version=excluded.prompt_version,status='pending',last_error='',updated_at=excluded.updated_at""",
                   (topic_id, fingerprint, source_revision, model, prompt_version, now, now))
        return True, "queued"

    def enrich_topics(self, session_id=None, provider="auto", force=False, progress=None,
                      retry_failed=False, agent_ids=None):
        """Index deterministic evidence and enrich only new or changed topics."""
        topic_ids, processed = set(), 0
        allow_cross_agent = self.memory_scope()["space_type"] != "agent_brain"
        with self._connect() as db:
            authorized_agents = self._effective_agent_ids(agent_ids)
            clauses, args = [], []
            owner_predicate, owner_args = self._topic_owner_predicate("e.topic_id")
            clauses.append(owner_predicate); args.extend(owner_args)
            if session_id is not None:
                clauses.append("e.session_id=?"); args.append(session_id)
            if authorized_agents is not None:
                marks = ",".join("?" for _ in authorized_agents)
                clauses.append(f"e.agent_id IN ({marks})"); args.extend(authorized_agents)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = db.execute(f"""SELECT DISTINCT e.topic_id,e.agent_id,m.id AS message_id,m.content,m.created_at
                FROM topic_episodes e JOIN topic_messages tm ON tm.episode_id=e.id JOIN messages m ON m.id=tm.message_id
                JOIN sessions s ON s.id=e.session_id AND s.status!='quarantined'
                {where} {('AND' if where else 'WHERE')} m.role='user' ORDER BY m.rowid""", args).fetchall()
            for row in rows:
                topic_ids.add(row["topic_id"])
                entities, terms = self._subject_terms(self._unprotect(row["content"]))
                entities.extend(self._file_references(self._unprotect(row["content"])))
                entity_ids = self._entity_ids(db, entities, row["message_id"], row["created_at"])
                if entity_ids or terms:
                    self._link_topic_entities(db, row["topic_id"], entity_ids, terms, row["message_id"],
                                              row["created_at"], owner_agent=row["agent_id"],
                                              allow_cross_agent=allow_cross_agent); processed += 1
        from .memory_extraction import configured_summary_model, TOPIC_PROMPT_VERSION, assisted_topic_enrichment
        model = configured_summary_model(); ai_provider = "deterministic"; work = []; skipped = 0; protected = 0
        now = time.time()
        with self._connect() as db:
            for topic_id in sorted(topic_ids):
                fingerprint, revision, count, context = self._topic_source_snapshot(db, topic_id)
                topic = db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
                state_row = db.execute("SELECT status FROM topic_enrichment_state WHERE topic_id=?", (topic_id,)).fetchone()
                if retry_failed and (not state_row or state_row["status"] != "failed"):
                    continue
                if not model or provider == "deterministic":
                    db.execute("""INSERT INTO topic_enrichment_state(topic_id,source_fingerprint,source_revision,status,last_error,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET source_fingerprint=excluded.source_fingerprint,source_revision=excluded.source_revision,status='not_applicable',last_error='',updated_at=excluded.updated_at""",
                               (topic_id, fingerprint, revision, "not_applicable", "", now, now)); continue
                queued, reason = self._queue_topic_enrichment(db, topic_id, fingerprint, model, TOPIC_PROMPT_VERSION, now, force=force, source_revision=revision)
                if queued: work.append((topic_id, dict(topic), context, fingerprint, revision, count))
                elif reason == "manual_protected": protected += 1
                else: skipped += 1
        total = len(work); ai_enriched = 0; failed = 0; model_calls = 0
        for index, (topic_id, topic, context, fingerprint, revision, count) in enumerate(work, 1):
            with self._connect() as db:
                db.execute("UPDATE topic_enrichment_queue SET status='processing',attempts=attempts+1,updated_at=? WHERE topic_id=? AND source_fingerprint=?", (time.time(), topic_id, fingerprint))
                db.execute("UPDATE topic_enrichment_state SET status='processing',attempt_count=attempt_count+1,source_revision=?,updated_at=? WHERE topic_id=?", (revision, time.time(), topic_id))
            proposal, used = assisted_topic_enrichment(topic, context, provider); model_calls += 1; ai_provider = used
            # A transient local-model timeout/invalid response gets one
            # immediate retry. Further attempts require an explicit rerun.
            for _ in range(1):
                if proposal or used not in {"ollama-unavailable", "ollama-invalid"}:
                    break
                with self._connect() as db:
                    db.execute("UPDATE topic_enrichment_queue SET attempts=attempts+1,updated_at=? WHERE topic_id=? AND source_fingerprint=?", (time.time(), topic_id, fingerprint))
                proposal, used = assisted_topic_enrichment(topic, context, provider); model_calls += 1; ai_provider = used
            success = bool(proposal and proposal.get("title"))
            with self._connect() as db:
                state = db.execute("SELECT manual_protected FROM topic_enrichment_state WHERE topic_id=?", (topic_id,)).fetchone()
                current_fingerprint, current_revision, _, _ = self._topic_source_snapshot(db, topic_id)
                source_changed = current_fingerprint != fingerprint
                details = {"provider": used, "model": model, "prompt_version": TOPIC_PROMPT_VERSION, "source_fingerprint": fingerprint,
                           "source_revision": revision, "source_message_ids": proposal.get("source_message_ids") if proposal else [m["id"] for m in context],
                           "fields": [key for key in ("title", "summary", "category", "decisions", "result") if proposal and proposal.get(key)],
                           "source_changed_during_generation": source_changed, "current_source_revision": current_revision}
                if success and not source_changed and not (state and state["manual_protected"]):
                    db.execute("UPDATE topics SET title=?,summary=?,category=?,updated_at=? WHERE id=?", (self._protect(proposal["title"]), self._protect(proposal["summary"]), proposal.get("category") or topic.get("category") or "asunto", time.time(), topic_id))
                    db.execute("INSERT INTO topic_events(topic_id,actor,action,details_json,created_at) VALUES(?,?,?,?,?)", (topic_id, "local-model", "enriched", json.dumps(details, ensure_ascii=False), time.time()))
                    db.execute("UPDATE topic_enrichment_state SET status='enriched',last_error='',processed_at=?,updated_at=? WHERE topic_id=?", (time.time(), time.time(), topic_id))
                    db.execute("UPDATE topic_enrichment_queue SET status='completed',last_error='',updated_at=? WHERE topic_id=? AND source_fingerprint=?", (time.time(), topic_id, fingerprint)); ai_enriched += 1
                else:
                    error = used if not success else ("source_changed_during_generation" if source_changed else "manual_edit_protected")
                    db.execute("INSERT INTO topic_events(topic_id,actor,action,details_json,created_at) VALUES(?,?,?,?,?)", (topic_id, "local-model", "ai_proposal" if success else "enrichment_failed", json.dumps({**details, "error": error}, ensure_ascii=False), time.time()))
                    db.execute("UPDATE topic_enrichment_state SET status=?,source_revision=?,last_error=?,updated_at=? WHERE topic_id=?", ("stale" if success or source_changed else "failed", current_revision if source_changed else revision, error, time.time(), topic_id))
                    db.execute("UPDATE topic_enrichment_queue SET status=?,last_error=?,updated_at=? WHERE topic_id=? AND source_fingerprint=?", ("failed", error, time.time(), topic_id, fingerprint)); failed += 1
            if progress: progress(int(index * 100 / max(1, total)), json.dumps({"processed": index, "total": total, "topic_id": topic_id, "status": "enriched" if success else "failed"}))
        self._propose_relation_candidates(requester_agent=None, agent_ids=agent_ids)
        reviewed_candidates = self._ai_review_candidates(limit=20, agent_ids=agent_ids)
        return {"ok": True, "processed": processed, "sessions": 1 if session_id else None, "topics": len(topic_ids),
                "queued": total, "ai_enriched": ai_enriched, "ai_skipped": skipped, "manual_protected": protected, "failed": failed,
                "model_calls": model_calls, "reviewed_candidates": reviewed_candidates,
                "coverage": self.topic_coverage(agent_ids=authorized_agents),
                "extraction": ai_provider if model else "deterministic-limited"}

    def topics(self, query="", *, requester_agent=None, state=None, agent_id=None,
               session_id=None, since=None, until=None, limit=20, offset=0, agent_ids=None):
        where, args = ["(s.capture_enabled=1 OR s.agent_id=?)", "NOT EXISTS (SELECT 1 FROM topic_episodes hidden JOIN sessions hs ON hs.id=hidden.session_id WHERE hidden.topic_id=t.id AND hs.capture_enabled=0 AND hs.agent_id!=?)"], [requester_agent or "", requester_agent or ""]
        authorized_agents = self._effective_agent_ids(agent_ids)
        owner_predicate, owner_args = self._topic_owner_predicate("t.id")
        where.append(f"({owner_predicate})")
        args.extend(owner_args)
        if authorized_agents is not None:
            marks = ",".join("?" for _ in authorized_agents)
            where.append(f"e.agent_id IN ({marks})")
            args.extend(authorized_agents)
        for clause, value in (("t.state=?", state), ("e.agent_id=?", agent_id), ("e.session_id=?", session_id),
                              ("e.created_at>=?", since), ("e.created_at<=?", until)):
            if value is not None:
                where.append(clause); args.append(value)
        # Content may be encrypted, so lexical matching takes place after
        # decryption. This bounded page scan reports that it is not semantic recall.
        semantic = set()
        if query:
            memory_ids = [m["id"] for m in self.search(query, requester_agent=requester_agent, limit=30,
                                                         agent_ids=authorized_agents)]
            with self._connect() as db:
                for mid in memory_ids:
                    semantic.update(r[0] for r in db.execute("SELECT topic_id FROM topic_memory_links WHERE memory_id=?", (mid,)))
        start, count = max(0, min(10000, offset)), max(1, min(100, limit))
        matches = []
        words = re.findall(r"\w+", query.casefold())
        with self._connect() as db:
            cursor = db.execute("SELECT DISTINCT t.* FROM topics t JOIN topic_episodes e ON e.topic_id=t.id JOIN sessions s ON s.id=e.session_id WHERE " + " AND ".join(where) + " ORDER BY t.updated_at DESC,t.id", args)
            for row in cursor:
                item = dict(row)
                item["title"], item["summary"] = self._unprotect(item["title"]), self._unprotect(item["summary"])
                ai = db.execute("SELECT status,model,source_revision,prompt_version,last_error,processed_at FROM topic_enrichment_state WHERE topic_id=?", (item["id"],)).fetchone()
                if ai:
                    item.update({"ai_status": ai["status"], "ai_model": ai["model"] or None, "ai_source_revision": ai["source_revision"], "ai_prompt_version": ai["prompt_version"] or None, "ai_error": ai["last_error"] or None, "ai_processed_at": ai["processed_at"]})
                else:
                    configured = os.environ.get("GRAPHTYN_MEMORY_SUMMARY_MODEL") or os.environ.get("OLLAMA_MODEL") or ""
                    item.update({"ai_status": "pending" if configured else "not_applicable", "ai_model": configured or None, "ai_source_revision": None, "ai_prompt_version": None, "ai_error": None, "ai_processed_at": None})
                entity_scope = f" AND ep.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
                entity_rows = db.execute("""SELECT DISTINCT e.kind,e.entity_key,e.name,te.relation,te.confidence
                    FROM topic_entities te JOIN entities e ON e.id=te.entity_id
                    JOIN topic_episodes ep ON ep.topic_id=te.topic_id JOIN sessions es ON es.id=ep.session_id
                    WHERE te.topic_id=? AND (es.capture_enabled=1 OR es.agent_id=?)""" + entity_scope,
                    [item["id"], requester_agent or "", *(authorized_agents or [])]).fetchall()
                item["entities"] = [dict(entity) for entity in entity_rows]
                entity_text = " ".join(f"{entity['kind']} {entity['entity_key']} {entity['name']}" for entity in entity_rows)
                haystack = (item["title"] + " " + item["summary"] + " " + entity_text).casefold()
                if words and not all(w in haystack for w in words) and item["id"] not in semantic:
                    continue
                lexical = sum(w in haystack for w in words) / max(1, len(words))
                score = (2.0 if words and all(w in haystack for w in words) else 0.0) + lexical + (.1 if item["id"] in semantic else 0)
                item["retrieval_score"] = score
                item["reference"] = self._node_reference(db, "memory_topic", item["id"])
                item["public_id"] = item["reference"]
                candidate = (score, item["updated_at"], item["id"], item)
                heapq.heappush(matches, candidate)
                if len(matches) > start + count + 1:
                    heapq.heappop(matches)
        matches = [entry[-1] for entry in sorted(matches, reverse=True)]
        more = len(matches) > start + count
        return {"ok": True, "topics": matches[start:start + count], "next_offset": start + count if more else None,
                "coverage": self.topic_coverage(requester_agent, authorized_agents),
                "retrieval": "lexical+linked-memory-candidates", "trust": "untrusted_history"}

    def topic(self, topic_id, *, requester_agent=None, limit=20, offset=0, agent_ids=None):
        with self._connect() as db:
            authorized_agents = self._effective_agent_ids(agent_ids)
            owner_predicate, owner_args = self._topic_owner_predicate("e.topic_id")
            mixed = db.execute(f"SELECT 1 FROM topic_episodes e WHERE e.topic_id=? AND NOT ({owner_predicate}) LIMIT 1",
                               [topic_id, *owner_args]).fetchone()
            scope = f" AND e.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
            allowed = db.execute("SELECT 1 FROM topic_episodes e JOIN sessions s ON s.id=e.session_id WHERE e.topic_id=? AND (s.capture_enabled=1 OR s.agent_id=?)" + scope + " LIMIT 1",
                                 [topic_id, requester_agent or "", *(authorized_agents or [])]).fetchone()
            hidden = db.execute("SELECT 1 FROM topic_episodes e JOIN sessions s ON s.id=e.session_id WHERE e.topic_id=? AND s.capture_enabled=0 AND s.agent_id!=?" + scope + " LIMIT 1",
                                [topic_id, requester_agent or "", *(authorized_agents or [])]).fetchone()
            if mixed or not allowed or hidden:
                raise PermissionError("tema inexistente o no accesible")
            item = dict(db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone())
            participants = db.execute("""SELECT DISTINCT e.agent_id FROM topic_episodes e
                JOIN sessions s ON s.id=e.session_id
                WHERE e.topic_id=? AND (s.capture_enabled=1 OR s.agent_id=?)""" + scope +
                " ORDER BY e.agent_id", [topic_id, requester_agent or "", *(authorized_agents or [])]).fetchall()
            item["agent_ids"] = [row[0] for row in participants]
            rows = db.execute("SELECT e.* FROM topic_episodes e JOIN sessions s ON s.id=e.session_id WHERE e.topic_id=? AND (s.capture_enabled=1 OR s.agent_id=?)" + scope + " ORDER BY e.created_at,e.id LIMIT ? OFFSET ?",
                              [topic_id, requester_agent or "", *(authorized_agents or []), min(100, max(1, limit)) + 1, max(0, offset)]).fetchall()
            episodes = []
            for row in rows[:limit]:
                ep = dict(row)
                for k in ("problem", "decisions", "result"): ep[k] = self._unprotect(ep[k])
                ep["message_ids"] = [r[0] for r in db.execute("SELECT r.message_id FROM topic_messages r JOIN messages m ON m.id=r.message_id AND m.agent_id=? WHERE r.episode_id=? ORDER BY m.rowid LIMIT 21", (ep["agent_id"], ep["id"]))]
                episodes.append(ep)
            entity_scope = f" AND ep.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
            entities = [dict(r) for r in db.execute("""SELECT DISTINCT e.id,e.kind,e.entity_key,e.name,e.metadata_json,
                te.relation,te.confidence,te.source_message_id
                FROM topic_entities te JOIN entities e ON e.id=te.entity_id
                JOIN topic_episodes ep ON ep.topic_id=te.topic_id JOIN sessions es ON es.id=ep.session_id
                WHERE te.topic_id=? AND (es.capture_enabled=1 OR es.agent_id=?)""" + entity_scope,
                [topic_id, requester_agent or "", *(authorized_agents or [])])]
            for entity in entities:
                try:
                    entity["metadata"] = json.loads(entity.pop("metadata_json") or "{}")
                except (TypeError, ValueError):
                    entity["metadata"] = {}
                evidence = db.execute("""SELECT source_message_id FROM topic_entity_evidence
                    WHERE topic_id=? AND entity_id=? ORDER BY created_at,source_message_id LIMIT 100""",
                    (topic_id, entity["id"])).fetchall()
                entity["source_message_ids"] = [row[0] for row in evidence]
            relation_scope = ""
            relation_args = [topic_id, topic_id, requester_agent or "", requester_agent or ""]
            if authorized_agents is not None:
                relation_marks = ",".join("?" for _ in authorized_agents)
                relation_scope = f" AND se.agent_id IN ({relation_marks}) AND te.agent_id IN ({relation_marks})"
                relation_args.extend(authorized_agents); relation_args.extend(authorized_agents)
            elif self.memory_scope()["space_type"] == "agent_brain":
                relation_scope = " AND (ss.agent_id=ts.agent_id OR ss.agent_id=? OR ts.agent_id=?)"
                relation_args.extend([requester_agent or "", requester_agent or ""])
            relations = [dict(r) for r in db.execute("""SELECT DISTINCT tr.source_topic_id,tr.target_topic_id,tr.relation,tr.confidence,tr.reason,tr.source_message_id
                FROM topic_relations tr
                JOIN topic_episodes se ON se.topic_id=tr.source_topic_id JOIN sessions ss ON ss.id=se.session_id
                JOIN topic_episodes te ON te.topic_id=tr.target_topic_id JOIN sessions ts ON ts.id=te.session_id
                WHERE (tr.source_topic_id=? OR tr.target_topic_id=?)
                  AND (ss.capture_enabled=1 OR ss.agent_id=?) AND (ts.capture_enabled=1 OR ts.agent_id=?)
                """ + relation_scope + " ORDER BY tr.created_at DESC LIMIT 100", relation_args)]
            events = [dict(r) for r in db.execute("SELECT * FROM topic_events WHERE topic_id=? ORDER BY id DESC LIMIT 100", (topic_id,))]
        for k in ("title", "summary"): item[k] = self._unprotect(item[k])
        with self._connect() as db:
            item["reference"] = self._node_reference(db, "memory_topic", item["id"])
            item["public_id"] = item["reference"]
            ai = db.execute("SELECT status,model,source_revision,prompt_version,last_error,processed_at FROM topic_enrichment_state WHERE topic_id=?", (item["id"],)).fetchone()
            if ai:
                item.update({"ai_status": ai["status"], "ai_model": ai["model"] or None, "ai_source_revision": ai["source_revision"], "ai_prompt_version": ai["prompt_version"] or None, "ai_error": ai["last_error"] or None, "ai_processed_at": ai["processed_at"]})
            for episode in episodes:
                episode["reference"] = self._node_reference(db, "memory_episode", episode["id"])
                episode["public_id"] = episode["reference"]
            for entity in entities:
                entity["reference"] = self._node_reference(db, "memory_entity", entity["id"])
                entity["public_id"] = entity["reference"]
            for relation in relations:
                relation["source_reference"] = self._node_reference(db, "memory_topic", relation["source_topic_id"])
                relation["target_reference"] = self._node_reference(db, "memory_topic", relation["target_topic_id"])
        return {"ok": True, "topic": item, "entities": entities, "relations": relations, "episodes": episodes, "events": events,
                "next_offset": offset + limit if len(rows) > limit else None, "trust": "untrusted_history"}

    def entities(self, query="", *, requester_agent=None, kind=None, limit=50, offset=0, agent_ids=None):
        """List concrete project elements and the topics attached to them."""
        limit, offset = max(1, min(100, int(limit))), max(0, min(10000, int(offset)))
        words = [word for word in re.findall(r"[\wáéíóúñ.-]+", str(query).casefold()) if word]
        authorized_agents = self._effective_agent_ids(agent_ids)
        with self._connect() as db:
            where = ["(s.capture_enabled=1 OR s.agent_id=?)"]
            args = [requester_agent or ""]
            if authorized_agents is not None:
                marks = ",".join("?" for _ in authorized_agents)
                where.append(f"s.agent_id IN ({marks})")
                args.extend(authorized_agents)
            if kind:
                where.append("e.kind=?"); args.append(kind)
            rows = db.execute("""SELECT DISTINCT e.id,e.kind,e.entity_key,e.name,e.metadata_json,
                    e.created_at,e.updated_at
                FROM entities e JOIN topic_entities te ON te.entity_id=e.id
                JOIN topic_episodes ep ON ep.topic_id=te.topic_id
                JOIN sessions s ON s.id=ep.session_id
                WHERE """ + " AND ".join(where) + " ORDER BY e.updated_at DESC,e.id", args).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                haystack = f"{item['kind']} {item['entity_key']} {item['name']}".casefold()
                if words and not all(word in haystack for word in words):
                    continue
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
                item["topic_ids"] = [r[0] for r in db.execute("SELECT topic_id FROM topic_entities WHERE entity_id=?", (item["id"],))]
                item["reference"] = self._node_reference(db, "memory_entity", item["id"])
                item["public_id"] = item["reference"]
                result.append(item)
        page = result[offset:offset + limit]
        return {"ok": True, "entities": page, "next_offset": offset + limit if len(result) > offset + limit else None,
                "retrieval": "lexical-entity-index", "trust": "untrusted_history"}

    def entity(self, entity_id, *, requester_agent=None, limit=50, agent_ids=None):
        with self._connect() as db:
            row = db.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
            if not row:
                raise ValueError("entidad inexistente")
            authorized_agents = self._effective_agent_ids(agent_ids)
            scope = f" AND s.agent_id IN ({','.join('?' for _ in authorized_agents)})" if authorized_agents is not None else ""
            allowed = db.execute("""SELECT 1 FROM topic_entities te JOIN topic_episodes ep ON ep.topic_id=te.topic_id
                JOIN sessions s ON s.id=ep.session_id WHERE te.entity_id=? AND (s.capture_enabled=1 OR s.agent_id=?)""" + scope + " LIMIT 1",
                                [entity_id, requester_agent or "", *(authorized_agents or [])]).fetchone()
            if not allowed:
                raise PermissionError("entidad no accesible")
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            item["reference"] = self._node_reference(db, "memory_entity", item["id"])
            item["public_id"] = item["reference"]
            topics = [dict(r) for r in db.execute("""SELECT t.id,t.title,t.summary,t.state,t.verification,te.relation,te.confidence
                FROM topic_entities te JOIN topics t ON t.id=te.topic_id
                JOIN topic_episodes ep ON ep.topic_id=te.topic_id
                JOIN sessions s ON s.id=ep.session_id
                WHERE te.entity_id=?""" + scope + " ORDER BY t.updated_at DESC LIMIT ?",
                [entity_id, *(authorized_agents or []), max(1, min(100, limit))]).fetchall()]
            for topic in topics:
                topic["title"], topic["summary"] = self._unprotect(topic["title"]), self._unprotect(topic["summary"])
                topic["reference"] = self._node_reference(db, "memory_topic", topic["id"])
        return {"ok": True, "entity": item, "topics": topics, "trust": "untrusted_history"}

    def topic_update(self, topic_id, *, requester_agent, reason, state=None, title=None,
                     verification=None, message_ids=None, merge_into=None, split_episode=None, agent_ids=None):
        if not str(requester_agent).strip() or not str(reason).strip():
            raise ValueError("actor y motivo son obligatorios")
        self.topic(topic_id, requester_agent=requester_agent, agent_ids=agent_ids)
        if state is not None and state not in STATES: raise ValueError("estado inválido")
        if verification is not None and verification not in VERIFICATIONS: raise ValueError("verificación inválida")
        if verification in {"prueba superada", "prueba fallida", "confirmado por usuario"} and not message_ids:
            raise ValueError("verificación requiere mensajes fuente")
        if merge_into:
            if merge_into == topic_id: raise ValueError("no se puede fusionar consigo mismo")
            self.topic(merge_into, requester_agent=requester_agent, agent_ids=agent_ids)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for mid in message_ids or []:
                row = db.execute("SELECT m.role FROM topic_messages r JOIN topic_episodes e ON e.id=r.episode_id JOIN messages m ON m.id=r.message_id AND m.agent_id=e.agent_id WHERE e.topic_id=? AND m.id=?", (topic_id, mid)).fetchone()
                if not row or not self.get_message(mid, requester_agent, agent_ids): raise ValueError("referencia ajena al tema")
                if verification == "confirmado por usuario" and row[0] != "user": raise ValueError("confirmación requiere mensaje del usuario")
                if verification in {"prueba superada", "prueba fallida"} and row[0] != "tool": raise ValueError("prueba requiere evidencia de herramienta")
            old = dict(db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone())
            updates = {k: v for k, v in (("state", state), ("verification", verification), ("title", title)) if v is not None}
            if title is not None:
                safe, _ = self._sanitize(title, 180)
                if not safe.strip(): raise ValueError("título vacío")
                updates["title"] = self._protect(safe)
            for k, v in updates.items(): db.execute(f"UPDATE topics SET {k}=?,updated_at=? WHERE id=?", (v, time.time(), topic_id))
            if merge_into:
                db.execute("UPDATE topic_episodes SET topic_id=? WHERE topic_id=?", (merge_into, topic_id))
                db.execute("UPDATE topics SET state='archivado' WHERE id=?", (topic_id,))
            new_id = None
            if split_episode:
                ep = db.execute("SELECT * FROM topic_episodes WHERE id=? AND topic_id=?", (split_episode, topic_id)).fetchone()
                if not ep: raise ValueError("episodio ajeno al tema")
                new_id = "top_" + hashlib.sha256((split_episode + str(time.time_ns())).encode()).hexdigest()[:24]
                db.execute("INSERT INTO topics VALUES(?,?,?,?,?,?,?,?)", (new_id, old["title"], ep["problem"], old["category"], "abierto", "sin verificar", time.time(), time.time()))
                db.execute("UPDATE topic_episodes SET topic_id=? WHERE id=?", (new_id, split_episode))
            details, _ = self._sanitize_json({"reason": reason, "before": old, "changes": updates, "message_ids": message_ids or [], "merge_into": merge_into, "split_topic": new_id, "split_episode": split_episode})
            for target in {topic_id, merge_into, new_id} - {None}:
                db.execute("INSERT INTO topic_events(topic_id,actor,action,details_json,created_at) VALUES(?,?,?,?,?)", (target, requester_agent, "update", json.dumps(details), time.time()))
            if title is not None:
                now = time.time()
                db.execute("""INSERT INTO topic_enrichment_state(topic_id,status,manual_protected,last_error,created_at,updated_at)
                    VALUES(?,'not_applicable',1,'manual_edit_protected',?,?)
                    ON CONFLICT(topic_id) DO UPDATE SET manual_protected=1,status='not_applicable',last_error='manual_edit_protected',updated_at=excluded.updated_at""", (topic_id, now, now))
        return {"ok": True, "topic_id": topic_id, "merge_into": merge_into, "split_topic": new_id}

    def message_window(self, message_id, *, requester_agent=None, before=10, after=10, token_budget=3000,
                       agent_ids=None):
        center = self.get_message(message_id, requester_agent, agent_ids=agent_ids)
        if not center: raise PermissionError("mensaje inexistente o no accesible")
        budget = int(token_budget)
        if budget < 300: raise ValueError("token_budget debe ser al menos 300")
        with self._connect() as db:
            seq = db.execute("SELECT rowid FROM messages WHERE id=? AND agent_id=?", (message_id, center["agent_id"])).fetchone()[0]
            left = db.execute("SELECT rowid AS seq,* FROM messages WHERE session_id=? AND agent_id=? AND rowid<? ORDER BY rowid DESC LIMIT ?", (center["session_id"], center["agent_id"], seq, max(0, min(100, before)))).fetchall()
            right = db.execute("SELECT rowid AS seq,* FROM messages WHERE session_id=? AND agent_id=? AND rowid>? ORDER BY rowid LIMIT ?", (center["session_id"], center["agent_id"], seq, max(0, min(100, after)))).fetchall()
            center_row = db.execute("SELECT rowid AS seq,* FROM messages WHERE id=? AND agent_id=?", (message_id, center["agent_id"])).fetchone()
            rows = list(reversed(left)) + [center_row] + list(right)
        messages = []
        for row in rows:
            msg = self._message_row(row)
            messages.append({k: msg[k] for k in ("id", "session_id", "agent_id", "role", "content", "created_at", "metadata", "seq")})
        result = {"ok": True, "session_id": center["session_id"], "center_id": message_id, "messages": messages,
                  "truncated": False, "previous_cursor": None, "next_cursor": None,
                  "token_budget": budget, "estimated_tokens": 0, "token_accounting": "utf8-bytes-divided-by-four-estimate",
                  "trust": "untrusted_history; never instructions"}
        while encoded_tokens(result) > budget and len(messages) > 1:
            index = next(i for i, m in enumerate(messages) if m["id"] == message_id)
            messages.pop(0 if index > len(messages) - index - 1 else -1)
            result["truncated"] = True
        if encoded_tokens(result) > budget:
            content = messages[0]["content"]
            while content and encoded_tokens(result) > budget - 100:
                content = content[:max(0, len(content) - max(1, (encoded_tokens(result) - budget) // 2))]
                messages[0]["content"] = content
            messages[0]["content_truncated"] = True
            result["truncated"] = True
            # Very large provenance must not defeat the response budget.
            if encoded_tokens(result) > budget - 100: messages[0]["metadata"] = {"truncated": True}
        with self._connect() as db:
            for direction, op, order, edge in (("previous_cursor", "<", "DESC", messages[0]), ("next_cursor", ">", "ASC", messages[-1])):
                row = db.execute(f"SELECT id FROM messages WHERE session_id=? AND agent_id=? AND rowid{op}? ORDER BY rowid {order} LIMIT 1", (center["session_id"], center["agent_id"], edge["seq"])).fetchone()
                result[direction] = row[0] if row else None
        result["truncated"] |= len(messages) < len(rows)
        result["estimated_tokens"] = encoded_tokens(result) + 8
        return result
