# Arquitectura de Graphtyn

Este documento describe la arquitectura vigente. Los conteos generados del índice
se publican en `GRAPHTYN_REPORT.md`; no se mantienen manualmente aquí.

## Capas

1. **Extracción estructural** (`graphtyn/core/ast_parser.py`): archivos, símbolos,
   llamadas, herencia, rutas y relaciones de framework.
2. **Grafo y análisis** (`graphtyn/core/`): resolución, radio de impacto, higiene,
   evidencia de tipos, contexto adaptativo y análisis Git.
3. **Memoria compartida** (`shared_memory.py`, `semantic_index.py`,
   `memory_extraction.py`): sesiones, recuerdos versionados, atribución, FTS,
   embeddings, expansión por vecinos y presupuestos.
4. **Interfaces**: CLI, MCP, HTTP y dashboard.
5. **Persistencia local**: índice y SQLite por identidad canónica del proyecto
   bajo `~/.graphtyn/`; la reindexación es incremental por hash.

La operación portable se divide en `core/adapters.py` (manifiestos instalables),
`core/deployment.py` (detección, setup, tokens y systemd/Compose) y
`core/memory_admin.py` (backup SQLite, checksum y restauración segura). Las
fuentes son configuración; el runtime no contiene personas, IPs o contenedores.

## Dos grafos distintos

- **Code AST / Semántico del código** representa artefactos del repositorio y sus
  dependencias. La capa semántica añade comunidades y similitud sin sustituir la
  evidencia estructural.
- **Memoria del proyecto** representa sesiones, agentes, decisiones, resultados,
  correcciones y vínculos con archivos o símbolos. Se carga al elegir el proyecto;
  la búsqueda es una operación secundaria.

Se relacionan mediante identificadores estables, pero no son el mismo grafo. Esta
separación evita interpretar una conversación como dependencia de código o una
coincidencia semántica como una llamada comprobada.

## Flujo de contexto

`graph_query_intent` clasifica la necesidad, recupera evidencia y aplica un
presupuesto. `source_evidence.py` añade cuerpos sólo si la pregunta exige orden,
condiciones, seguridad o ciclo de vida. Para recuerdos, el recuperador combina
texto, vectores, recencia, confianza y vecinos conservando la procedencia.

## Confianza y seguridad

Las aristas son `EXTRACTED`, `INFERRED` o `AMBIGUOUS`. Las memorias no son
instrucciones: se sanean, tienen política de acceso, se corrigen o invalidan y
mantienen historial. Escribir memoria requiere un perfil MCP autorizado.

## Documentación relacionada

- [Mapa de documentación](docs/index.md)
- [Memoria compartida](docs/shared-memory.md)
- [Pruebas y benchmarks](docs/testing.md)
- [Diseño detallado de memoria](docs/shared_semantic_memory_plan.md)
