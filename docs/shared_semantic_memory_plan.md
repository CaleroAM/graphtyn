# Diseño y registro de implementación de memoria semántica multiagente

> **Estado 2026-08-25:** almacén, captura, embeddings incrementales, recuperación
> híbrida, dashboard y endurecimiento básico están implementados. Se conserva el
> diseño original junto con los criterios aún pendientes de validar a escala.

**Estado:** implementación incremental iniciada (Fases 1–6; Fase 7 núcleo)  
**Alcance:** Graphtyn local-first, por proyecto, accesible desde cualquier cliente MCP  
**Objetivo:** permitir que AGY, OpenCode, OpenClaw, Codex, Claude, Hermes y otros
agentes escriban y recuperen conocimiento verificable producido por sesiones distintas.

## 1. Resultado esperado

Un agente conectado a un proyecto debe poder preguntar «¿qué ocurrió con el cambio
de autenticación?» y recibir un paquete compacto que indique:

- qué se decidió y por qué;
- qué agente y sesión lo registraron;
- archivos, símbolos, rama y commit relacionados;
- cambios, comandos y pruebas observados;
- si el recuerdo sigue vigente respecto al código actual;
- contradicciones o correcciones posteriores;
- fragmentos de conversación únicamente cuando sean necesarios como evidencia.

La memoria pertenece al proyecto, no al cliente. Dos agentes pueden trabajar en
ramas y tareas distintas sin compartir una ventana de contexto, pero consultan el
mismo almacén Graphtyn y conservan atribución explícita.

## 2. Principios y límites

1. **Evidencia antes que narrativa.** Una frase de un agente no se convierte en
   hecho verificado sin archivo, commit, prueba, aprobación o resultado observable.
2. **Atribución obligatoria.** Toda memoria conserva agente, cliente, sesión,
   timestamp y origen. Nunca se atribuye al agente actual el trabajo de otro.
3. **Proyecto y revisión primero.** Recuperar dentro del proyecto, rama/worktree y
   commit actuales; advertir cuando el recuerdo pertenece a otra rama.
4. **Híbrido, no solo vectorial.** Combinar FTS/BM25, embeddings, grafo, recencia,
   vigencia y calidad. Los nodos vecinos amplían un candidato, no lo originan todo.
5. **Contexto acotado.** Recuperar memorias compactas; abrir transcripciones solo
   para resolver una obligación concreta.
6. **Local y portable.** SQLite funciona sin servicios externos. Ollama y
   `sqlite-vec` son mejoras opcionales, no requisitos para instalar Graphtyn.
7. **Captura con consentimiento.** No ingerir conversaciones automáticamente sin
   configuración explícita. Nunca almacenar secretos ni razonamiento interno.
8. **Corrección y olvido.** Toda memoria puede ser corregida, invalidada, exportada
   o eliminada; las versiones previas permanecen auditables salvo borrado solicitado.

Fuera del alcance inicial: sincronización cloud entre máquinas, edición colaborativa
en tiempo real, identidad empresarial/SSO y uso de una memoria como autorización.

## 3. Arquitectura objetivo

```text
AGY / OpenCode / OpenClaw / Codex / Claude / Hermes
                         │
                MCP stdio o MCP HTTP
                         │
               SharedMemoryService
        ┌────────────────┼────────────────┐
        │                │                │
   Ingestión        Recuperación      Gobernanza
   de eventos       híbrida           y privacidad
        │                │                │
        └────────────────┼────────────────┘
                         │
      ~/.graphtyn/<proyecto-hash>/memory-v2.db
        ├─ sesiones y mensajes
        ├─ memorias/decisiones/resultados
        ├─ FTS5 y embeddings
        ├─ enlaces a nodos del grafo
        └─ auditoría, correcciones y tombstones
```

El grafo de código continúa en `index.json`; no se duplica dentro de SQLite. La
memoria guarda referencias estables a `node_id`, archivo, línea y fingerprint.

## 4. Modelo de datos v2

### 4.1 Entidades

| Entidad | Propósito |
|---|---|
| `agents` | Identidad normalizada del cliente: `agy`, `opencode`, `openclaw`, etc. |
| `sessions` | Tarea, rama, worktree, commit base, inicio/fin y estado de captura. |
| `messages` | Transcript opt-in con rol, contenido saneado y hash de deduplicación. |
| `memories` | Unidad recuperable: decisión, hecho, resultado, procedimiento o resumen. |
| `memory_versions` | Correcciones y evolución sin sobrescribir procedencia. |
| `memory_links` | Relaciones entre memoria, símbolo, archivo, commit, prueba o sesión. |
| `embeddings` | Vector, proveedor, modelo, dimensión y hash del texto embebido. |
| `evidence` | Citas verificables y estado de vigencia. |
| `retrieval_feedback` | Útil, irrelevante, incorrecta o corregida para calibrar ranking. |
| `audit_log` | Escritura, lectura sensible, exportación, corrección y borrado. |

### 4.2 Campos mínimos de una memoria

```json
{
  "id": "mem_01...",
  "project_id": "crm-a81f...",
  "kind": "decision",
  "scope": "team",
  "status": "verified",
  "title": "Autenticación centralizada en AuthService",
  "content": "AGY reemplazó la validación JWT manual...",
  "agent_id": "agy",
  "session_id": "ses_01...",
  "task_id": "auth-refactor",
  "branch": "feature/auth",
  "base_commit": "abc123",
  "observed_commit": "def456",
  "created_at": 1787440000,
  "confidence": 0.94,
  "files": ["src/AuthService.ts"],
  "node_ids": ["symbol:src/AuthService.ts:validateToken"],
  "tests": ["tests/auth.test.ts"],
  "source_message_ids": ["msg_17", "msg_21"],
  "content_sha256": "...",
  "stale": false
}
```

Valores iniciales:

- `kind`: `episodic`, `decision`, `fact`, `procedure`, `outcome`, `correction`, `handoff`.
- `scope`: `private`, `project`, `team`.
- `status`: `proposed`, `observed`, `verified`, `contested`, `superseded`, `deleted`.
- `visibility`: por defecto `project`; `private` nunca sale a otro agente.

### 4.3 SQLite

- Activar `PRAGMA journal_mode=WAL`, `foreign_keys=ON` y `busy_timeout`.
- Usar transacciones cortas e IDs ULID/UUID para escritores concurrentes.
- Crear FTS5 sobre título, contenido, tarea, archivos y aliases.
- Guardar vectores como BLOB/lista compacta en el backend integrado.
- Habilitar `sqlite-vec` mediante extra opcional `[memory-vector]` cuando exista.
- Versionar el esquema con `schema_migrations`; nunca alterar `history.db` en sitio.

## 5. Ingestión y ciclo de memoria

### 5.1 Sesión explícita

1. El cliente llama `memory_session_start` con agente, tarea, rama y capacidades.
2. Los mensajes se envían mediante `memory_append` o un adaptador/hook autorizado.
3. `memory_checkpoint` extrae una decisión, resultado o handoff importante.
4. `memory_session_end` resume la sesión y registra pruebas/commit/pendientes.
5. Un compactador deduplica recuerdos equivalentes y genera embeddings.

Los clientes sin hooks pueden usar MCP manualmente; los que tengan hooks pueden
capturar `user`, `assistant` y resultados de herramientas. Nunca capturar mensajes
`system`, secretos, variables de entorno ni cadenas detectadas por el redactor.

### 5.2 Extracción de recuerdos

La primera versión debe ser determinista:

- mensajes marcados explícitamente como decisión/corrección;
- commits, diffs, comandos y resultados de pruebas observados;
- `memory_checkpoint` iniciado por el agente;
- respuesta final y handoff de la sesión.

Una fase posterior puede usar Qwen local o API para proponer memorias. Esas
propuestas nacen con estado `proposed`; solo evidencia observable o confirmación
del usuario permite `verified`.

### 5.3 Saneamiento

Antes de persistir:

- redactar patrones de tokens, claves privadas, cookies y credenciales;
- permitir reglas `.graphtyn/memory-policy.json` por proyecto;
- aplicar límites de tamaño y tipos MIME;
- almacenar hash del original saneado para deduplicación;
- rechazar rutas fuera del proyecto salvo autorización explícita.

## 6. Embeddings e indexación incremental

Reutilizar `semantic_index.py` mediante una interfaz común `EmbeddingProvider`:

- `feature-hash-v2`: fallback determinista, multilingüe y cero dependencias;
- `ollama:<modelo>`: vector semántico local, recomendado para conversación;
- proveedor API opcional solo con consentimiento explícito;
- índice separado por proveedor/modelo/dimensión para evitar mezclar espacios.

Texto a embeber por memoria:

```text
[kind] [title] [content] [task] [files] [symbols] [aliases] [agent]
```

Recalcular únicamente cuando cambie `content_sha256` o el modelo. Las memorias
corregidas crean nueva versión y desactivan el vector anterior.

## 7. Retrieval híbrido

### 7.1 Pipeline

1. Resolver `project_id`, rama, commit y agente solicitante.
2. Clasificar la consulta: recuerdo, decisión, handoff, procedimiento o historial.
3. Obtener candidatos paralelos:
   - FTS5/BM25;
   - similitud vectorial;
   - filtros de metadatos;
   - símbolos del grafo mencionados o semánticamente recuperados.
4. Fusionar por Reciprocal Rank Fusion.
5. Expandir uno o dos saltos por `memory_links` y vecinos direccionales del grafo.
6. Reordenar por evidencia, vigencia, rama, recencia, feedback y diversidad MMR.
7. Empaquetar bajo presupuesto con citas y atribución.

Puntuación inicial auditable:

```text
0.27 vector + 0.23 BM25 + 0.18 graph + 0.12 branch/revision
+ 0.10 evidence + 0.06 recency + 0.04 feedback - stale_penalty
```

Los pesos son configuración y deben calibrarse con benchmarks, no tratarse como
constantes definitivas. Si falta un embedding, BM25+grafo continúa funcionando.

### 7.2 Expansión por vecinos

Los vecinos se usan después de encontrar candidatos:

- memoria → sesión creadora;
- memoria → archivos/símbolos/pruebas/commit;
- símbolo → consumidor/implementación/test;
- memoria → corrección/superseded/contradicción;
- sesión → handoff de otra sesión.

No expandir comunidades completas ni convertir proximidad en causalidad.

### 7.3 Respuesta

`memory_context` devuelve:

- respuesta resumida opcional;
- memorias ordenadas con score desglosado;
- atribución `agent_id/session_id`;
- evidencia y vigencia;
- rama/commit y advertencias de divergencia;
- vecinos usados y razón de inclusión;
- `context_id`, tokens estimados y `do_not_expand`.

## 8. Contrato MCP v2

| Tool | Uso |
|---|---|
| `memory_session_start` | Abre sesión atribuida a agente/proyecto/tarea. |
| `memory_append` | Añade mensaje o evento saneado e idempotente. |
| `memory_checkpoint` | Guarda decisión, resultado, corrección o handoff. |
| `memory_compact` | Propone memorias desde mensajes saneados con determinismo, Qwen o API autorizada. |
| `memory_session_end` | Cierra, resume y registra estado/pruebas/commit. |
| `memory_search` | Recuperación híbrida con filtros y scores. |
| `memory_context` | Paquete listo para agente con vecinos y presupuesto. |
| `memory_get` | Evidencia completa de una memoria concreta. |
| `memory_correct` | Crea nueva versión y relación `supersedes`. |
| `memory_feedback` | Marca resultado útil/irrelevante/incorrecto. |
| `memory_forget` | Tombstone o borrado físico autorizado. |
| `memory_export` | Exporta proyecto/sesión en JSONL saneado. |
| `memory_import` | Importa transcript con adaptador y deduplicación. |

El perfil MCP predeterminado debe exponer `graph_query_intent` y
`memory_context`; las tools de escritura se habilitan con
`GRAPHTYN_MEMORY_CAPTURE=1` o configuración equivalente.

Ejemplo de recuperación:

```json
{
  "query": "¿recuerdas el cambio de autenticación?",
  "scope": ["decision", "outcome", "handoff"],
  "branch_policy": "current_then_related",
  "limit": 8,
  "token_budget": 1800,
  "include_transcript": "only_if_needed"
}
```

## 9. CLI, HTTP y dashboard

### CLI

```text
graphtyn memory session start/end
graphtyn memory append/checkpoint
graphtyn memory search/context/get
graphtyn memory correct/forget
graphtyn memory import/export
graphtyn memory status/doctor/reindex
```

### HTTP

- `/api/memory/sessions`
- `/api/memory/search`
- `/api/memory/context`
- `/api/memory/{id}`
- `/api/memory/correct`
- `/api/memory/forget`
- autenticación Bearer existente más permisos `read/write/admin`.

### Dashboard

Crear vista **Memoria compartida** separada del grafo de código:

- sesiones por agente, tarea, rama y fecha;
- buscador semántico con explicación del ranking;
- memoria → símbolos/archivos/pruebas como subgrafo;
- indicadores verified/proposed/contested/stale/private;
- comparación entre recuerdo y commit actual;
- acciones corregir, invalidar, olvidar y exportar;
- métricas de cobertura, duplicación, stale ratio y retrieval feedback.

## 10. Migración y compatibilidad

1. Mantener `graph_history_*` durante dos versiones como aliases de lectura.
2. Importar `history.db` como eventos `legacy_observation`, conservando IDs.
3. Importar `.graphtyn/memory/*.json` como `outcome`/`correction` v2.
4. No eliminar archivos antiguos automáticamente; escribir marcador de migración.
5. `memory doctor` valida conteos, hashes, FTS, vectores y huérfanos.
6. Permitir rollback: v2 puede desactivarse sin afectar `index.json`.

## 11. Fases de implementación

### Fase 0 — contratos y amenazas

- ADR de privacidad, scopes, atribución y retención.
- JSON Schema/Pydantic de eventos y memorias.
- corpus de pruebas con secretos falsos, ramas y contradicciones.

**Salida:** contratos congelados y pruebas de esquema fallando primero.

### Fase 1 — almacén unificado

- `SharedMemoryStore`, migraciones SQLite, WAL, FTS5 e idempotencia.
- importar historial/resultados existentes.
- CRUD, corrección, tombstones y auditoría.

**Aceptación:** dos procesos escriben 1,000 eventos sin pérdida; reimportar no duplica.

### Fase 2 — MCP/CLI de captura

- sesiones, append, checkpoint, end, get y search lexical.
- identidad de agentes y política de captura opt-in.
- adapters documentados para AGY, OpenCode, OpenClaw, Codex, Claude y Hermes.

**Aceptación:** AGY registra una sesión y OpenCode la recupera con atribución exacta.

### Fase 3 — embeddings incrementales

- interfaz de providers, fallback hashing y Ollama.
- cache por hash/modelo, reindex y `memory doctor`.

**Aceptación:** paráfrasis bilingües recuperan el mismo recuerdo; segunda pasada
reutiliza 100% de vectores no modificados.

### Fase 4 — retrieval híbrido + grafo

- FTS/vector/RRF, filtros por rama, expansión vecinal y MMR.
- vigencia por SHA/commit y scores explicables.
- `memory_context` con presupuesto y delta por `context_id`.

**Aceptación:** preguntas indirectas recuperan decisión, autor y evidencia sin
mezclar una memoria homónima de otro proyecto o rama.

### Fase 5 — captura y resumen asistidos

- redactor de secretos y políticas.
- compactación determinista; Qwen/API opcional para propuestas.
- contradicciones, supersession y confirmación del usuario.

**Aceptación:** ningún secreto del corpus aparece en DB, logs, vectores o export.

### Fase 6 — dashboard y operación

- vista Memoria compartida, administración, feedback y métricas.
- backup/export/import, reparación y límites de retención.

**Aceptación:** búsqueda, corrección y olvido funcionan desde UI y MCP con la misma DB.

### Fase 7 — evaluación competitiva y endurecimiento

- repetición, concurrencia, corrupción simulada y pruebas de permisos.
- benchmarks de memoria larga y suite multiagente propia.
- documentación de límites y resultados negativos.

## 12. Estrategia de pruebas

### Unitarias

- migraciones, deduplicación, redacción, scopes, fingerprints y scoring;
- embeddings por provider/dimensión y cache incremental;
- branch policy, recencia, stale penalty, supersession y MMR.

### Integración

- dos servidores MCP contra un proyecto y SQLite común;
- stdio + HTTP leen la misma memoria;
- procesos concurrentes, reinicio abrupto y recuperación WAL;
- migración desde `history.db` y memoria v1.

### End-to-end

Escenario mínimo reproducible:

1. AGY implementa cambio X y registra pruebas.
2. OpenCode implementa Y en otra rama.
3. OpenClaw pregunta por X con una paráfrasis.
4. Debe responder autor, tarea, rama, archivos, pruebas y vigencia.
5. OpenCode corrige un detalle; la versión anterior queda superseded.
6. Codex pregunta de nuevo y obtiene solo la versión vigente con historial accesible.

### Seguridad

- inyección de prompts dentro de memorias;
- secretos en mensajes/resultados de herramientas;
- traversal de rutas y acceso cross-project;
- memoria privada consultada por otro agente;
- borrado físico verificando FTS, vector, backups temporales y audit policy.

## 13. Métricas y benchmarks

Medir por proyecto y tipo de pregunta:

- Recall@5/10 y MRR de la memoria correcta.
- precisión de atribución de agente/sesión/rama.
- exactitud QA con evidencia.
- tasa de recuerdos stale o contradictorios devueltos.
- tokens, latencia p50/p95 y número de tools.
- porcentaje de retrievals resueltos sin transcript completo.
- reducción frente a reinyectar conversaciones completas.
- tasa de secretos filtrados: objetivo obligatorio 0.

Suite propia inicial: 30 escenarios × 3 formulaciones × 3 agentes, con ground truth
versionado. Ejecutar lexical, vector, grafo e híbrido como ablaciones; no publicar
solo el mejor resultado.

## 14. Criterios de salida para v1

- Un proyecto posee una única memoria compartida collision-safe.
- Tres clientes distintos escriben/leen simultáneamente por MCP.
- La respuesta distingue «lo hizo AGY» de «lo hizo OpenCode».
- Recuperación híbrida encuentra paráfrasis y explica por qué incluyó cada memoria.
- Rama/commit divergente produce advertencia visible.
- Correcciones desplazan recuerdos obsoletos sin perder auditoría.
- Captura desactivada por defecto y redacción validada.
- Borrado elimina contenido e índices derivados según política.
- Instalación base continúa sin vector DB externo.
- Benchmarks y límites quedan documentados con artefactos reproducibles.

## 15. Orden recomendado inmediato

Implementar primero Fases 0–2 sin LLM: store v2, atribución, migración y herramientas
MCP. Esto entrega valor multiagente verificable rápidamente. Después añadir
embeddings y retrieval híbrido sobre datos reales; hacerlo antes ocultaría defectos
de identidad, permisos y procedencia bajo similitud vectorial.

## 16. Avance implementado

El primer corte funcional incluye:

- `SharedMemoryStore` y `memory-v2.db` con WAL, FTS5, atribución y auditoría;
- sesiones, checkpoints, handoff de cierre y búsqueda entre sesiones;
- scopes `private`, `project` y `team` con aislamiento de `private`;
- deduplicación idempotente de checkpoints;
- migración repetible de `history.db` y `.graphtyn/memory/*.json`;
- comandos CLI y tools MCP para el ciclo principal;
- pruebas de recuperación cross-agent, privacidad, WAL, idempotencia y migración.
- embeddings incrementales con `feature-hash-v2` y Ollama opcional;
- búsqueda híbrida FTS5/vector mediante RRF, bonus de rama y score explicable;
- detección stale basada en fingerprints de archivos de evidencia;
- `memory_context` acotado por tokens y con `context_id` estable.
- expansión de un salto hacia consumidores/dependencias directos con razón y confianza;
- exclusión explícita de comunidades completas durante expansión;
- vigencia Git `current`/`ancestor`/`diverged` y advertencias entre ramas;
- truncado seguro de memorias extensas para respetar el presupuesto.
- captura opt-in de mensajes `user`/`assistant`/`tool`, nunca `system`;
- redacción de secretos en texto y metadatos, límites y deduplicación;
- handoff determinista al cerrar una sesión capturada;
- correcciones versionadas con `supersedes` y exclusión de la versión anterior;
- tombstone o borrado físico autorizado, incluyendo FTS y embeddings derivados;
- contenido recuperado marcado como dato no confiable contra prompt injection.
- API HTTP de estado, sesiones, búsqueda, contexto, corrección y olvido;
- autenticación Bearer opcional con token específico o token MCP reutilizado;
- dashboard de memoria separado del grafo, responsivo y con errores visibles;
- búsqueda, atribución, sesiones, corrección y olvido sobre la misma base MCP/CLI.
- `memory doctor` para integridad SQLite, claves foráneas, FTS y embeddings;
- benchmark reproducible con Recall@5/10, MRR, atribución, tokens y latencia;
- prueba concurrente de 100 checkpoints con ocho escritores;
- detección y reparación incremental de embeddings faltantes;
- corpus bilingüe versionado y guardrails automáticos de calidad/coste.
- extracción determinista y Qwen/Ollama sobre mensajes previamente saneados;
- API externa deshabilitada salvo consentimiento explícito;
- propuestas con confianza máxima 0.85, estado `proposed` y mensajes fuente válidos;
- perfil MCP `memory` para escribir sin cargar el catálogo completo.

Todavía pendientes: políticas avanzadas de retención y ampliar el corpus estadístico
multiagente. Por ello esta entrega no se etiqueta todavía como RAG conversacional v1.
