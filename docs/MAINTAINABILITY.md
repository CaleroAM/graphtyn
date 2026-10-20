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
