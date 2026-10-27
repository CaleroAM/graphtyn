# Mantenibilidad de Graphtyn

Graphtyn aplica un presupuesto estructural a su código Python. El comando

```bash
python tools/check_maintainability.py
```

rechaza módulos nuevos de más de 1.200 líneas, clases de más de 800 y funciones
de más de 120. La deuda anterior está registrada en
`tools/maintainability_baseline.json`: puede reducirse o desaparecer, pero el
CI falla si crece. El baseline no es una excepción permanente; actualizarlo
requiere revisar por qué no es posible extraer una responsabilidad.

Las fronteras extraídas en esta revisión son:

- `graphtyn/mcp_catalog.py`: catálogo declarativo y perfiles de herramientas.
- `graphtyn/cli_parser.py`: construcción del parser dividida por familias de comandos.
- `graphtyn/cli_memory.py`: ejecución de comandos de memoria, sincronización y watcher.
- `graphtyn/api/semantic_graph.py`: proyección semántica y selección acotada de relaciones.
- `graphtyn/core/memory_schema.py`: DDL y migraciones aditivas de SQLite.
- `graphtyn/core/memory_retrieval.py`: selección vectorial acotada para el proveedor local.
- `graphtyn/core/memory_scale_benchmark.py`: protocolo reproducible de escala RF07.
- `graphtyn/core/answer_validation.py`: etapas separadas para citas, candidatos,
  relaciones y política de confianza.

El transporte MCP HTTP mantiene la ruta pública en `api.main`, pero separa
autenticación, contexto de proyecto, memoria de agentes, operaciones de memoria y
consultas de grafo. Así cada política se prueba sin recorrer un único bloque de
despacho.

Los próximos recortes deben priorizar recuperación en `SharedMemoryStore`,
consolidación de memorias y los módulos heredados que aún figuran en el baseline. Los cambios de recuperación
deben conservar atribución, alcance y procedencia; optimizar una consulta no
puede ampliar la visibilidad de una memoria.

La revisión de `0.10.7` registra 34 hotspots. Cinco aparecen por primera vez en
esta entrega: el módulo y el contexto de implementación de `change_analyst`, la
búsqueda de mensajes en `SharedMemoryStore`, el adjunto de evidencia fuente y el
módulo MCP. Además crecieron rutas ya registradas de intención, contexto de
memoria y despacho MCP. Las siguientes extracciones deben separar el armado de
planes de edición, el ranking y recorte de mensajes, y los handlers MCP por
familia. Este baseline documenta la deuda y prohíbe crecimiento adicional; no
afirma que esas responsabilidades ya estén separadas.

La revisión de `0.11.0` registra 33 hotspots, ninguno nuevo. Sale del baseline
`attach_source_evidence`, dividido en recopilación, ranking, selección de
fragmentos y registro de cobertura. El paquete `lean` pasó a
`graphtyn/core/lean_package.py`, fuera de `mcp_server.py`. Crecen con
justificación explícita:

- **Paquetes de lenguaje:** `tree_sitter_backend.parse_file` y `visit` (C/C++,
  Ruby, Kotlin, Swift y Scala comparten un único recorrido) y
  `ASTParser.scan_directory` (registro de paquetes, rationale e ignore rules).
- **Planificación de intenciones:** `change_analyst.query_intent` y el módulo
  (precisión por símbolo nombrado y capas de Rails).
- **Servidor MCP:** el módulo, `evidence_result` (copia de fragmentos y
  presupuesto explícito) y `run_mcp_server` (`--response-detail`).
- **Memoria:** `history_import` y `SharedMemoryStore`, por la identidad
  `claude`/`claude-code` y la captura de Claude Code.

Después de esa revisión se hicieron dos extracciones:

- **Recorrido de tree-sitter:** las tablas de tipos de nodo pasaron a
  constantes de módulo, y las ramas de miembros, símbolos y llamadas a
  `_member_facts`, `_symbol_fact` y `_call_facts`. `visit` sale del baseline y
  `parse_file` baja de 409 a 224 líneas. Los grafos de Redis, fmt y Rails
  resultan idénticos nodo a nodo.
- **Consultas MCP incrementales:** el cálculo de deltas de `extends_context_id`
  vive en `graphtyn/core/intent_delta.py`. `mcp_server.py` baja a 1.371 líneas y
  `run_mcp_server` a 423.

Queda pendiente repartir los handlers de memoria del MCP por familia.

Después crecen, con revisión, `ASTParser.scan_directory` (+3 líneas: las
llamadas Ruby sin paréntesis sólo se resuelven dentro del mismo lenguaje y sin
ambigüedad) y el módulo `change_analyst` (+5: el desempate de intención a favor
de `flow`). Las señales de ruta y paquete pasaron a `path_signals.py`, y el
recorrido de tree-sitter se reparte en funciones auxiliares de ese módulo.

## Escala

SQLite con WAL es el backend local soportado. RF07 midió cinco repeticiones en
1.000, 10.000 y 50.000 registros: Recall@5/MRR/nDCG@10 de 1,0, p95 normal de
136,568/148,645/198,901 ms, cero errores y cero fugas, con RSS pico de 90,19 MB.
Los artefactos están en `benchmarks/rf07_2026-10-09/`.

El proveedor local `feature-hash` ya no recorre toda la tabla cuando la política
posterior exige solapamiento léxico: puntúa el conjunto acotado de candidatos FTS y
recientes. Los embeddings semánticos remotos todavía requieren búsqueda lineal y el
historial de mensajes conserva otro recorrido lineal; RF07 no acredita esos casos ni
un servicio multiusuario concurrente.

## Actualización controlada del baseline

Después de reducir un hotspot, se registra el nuevo límite con:

```bash
python tools/check_maintainability.py --update-baseline
git diff -- tools/maintainability_baseline.json
python tools/check_maintainability.py
```

El diff debe mostrar límites iguales o menores. Si aparece un hotspot nuevo o
un límite mayor, el cambio necesita una justificación arquitectónica explícita.
