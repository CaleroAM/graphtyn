# Validación de `0.13.0`

Fecha: 2026-11-10. Esta versión mejora sobre todo el grafo de llamadas:
- **Despacho a implementaciones:** una llamada a un método de interfaz, trait o abstracto llega a
  sus implementaciones, con un máximo de 8 por llamada.
- **JavaScript:** los métodos asignados a un objeto, sus cadenas de alias y los getters definidos
  con `defineGetter` o `Object.defineProperty` son símbolos de ese objeto.
- **TypeScript:** se registran las llamadas a miembros `#privados`.
- **Java, C# y PHP:** los métodos de un enum tienen al enum como dueño.
- **Genéricos:** un campo de tipo genérico toma el tipo de su cota.

También corrige los nombres de la pregunta que no son símbolos y el índice semántico que mezclaba
espacios de embeddings, y acelera el paso que pone en blanco los literales. El detalle está en
`docs/CHANGELOG.md`.

## Validación reproducible

Entorno observado: Linux 6.18.35 x86_64. Todo se ejecutó sobre `33ec07d`, el commit de la versión, con un
`GRAPHTYN_HOME` aislado. Después solo cambió la documentación, y el CI repite la suite en 3.10–3.13
sobre el commit final.

| Comprobación | Resultado |
|---|---|
| Suite completa en entornos `uv` limpios con `.[dev]`, Python 3.10.20, 3.11.15, 3.12.13 y 3.13.13 | 979 pasaron y 2 omitidas en cada versión |
| Puerta de mantenibilidad (`tools/check_maintainability.py`) | pasa: 32 hotspots heredados, sin crecimiento |
| Gate de recuperación (`tools/check_retrieval_coverage.py`, 10 corpus públicos fijados) | pasa: 138 tareas, cobertura media 80,3 % |
| `uv build` | `graphtyn-0.13.0-py3-none-any.whl` y `graphtyn-0.13.0.tar.gz` |
| Contenido del wheel | dashboard, librerías en `web/vendor/`, proyecto de ejemplo, las skills, `core/declaration_facts.py` y `core/relation_resolution.py` |
| Wheel en entorno vacío (Python 3.13), sin extras | `--version` 0.13.0; `setup` en vista previa; `reindex` (48 nodos, 66 conectores) y `report` funcionan sobre el proyecto de ejemplo |
| MCP stdio desde ese wheel | `serverInfo.version` 0.13.0; `graph_query_intent` devuelve 10 entidades, intención `flow` y `do_not_expand=true` |
| `pip-audit` sobre las 45 dependencias del entorno del wheel | sin vulnerabilidades conocidas |
| Docker | la imagen construye; `/health` responde `{"status":"ok","service":"Graphtyn","version":"0.13.0"}`; el proceso corre como usuario 10001; las 14 gramáticas cargan |
| Smoke de Chromium (`tests/smoke_frontend.py`, servidor desde el wheel) | dashboard, vistas y estilos sin errores JS |

## Mediciones de esta versión

Todas usan Codex con `gpt-5.6-luna` y la mayoría de tres jueces (Gemini, GPT y Claude) con las
citas resueltas.

| Cambio | Resultado | Informe |
|---|---|---|
| Despacho a implementaciones | 32/39 hechos frente a 30/39 de `main`. IC 95 % de [−6 %, +12 %], sin significación, con un 6 % menos de tokens | `benchmarks/interface_dispatch_2026-11-10/report.md` |
| Métodos asignados de JavaScript | Con las tareas congeladas, la rama propuesta empeoraba (14/30 frente a 24/30). Tras corregir las dos causas queda en 23/30 con un 33 % menos de tokens, pero las tareas ya no son independientes | `benchmarks/js_assigned_methods_2026-11-10/report.md` |
| Identificadores que no son símbolos | En las preguntas reales de proyectos locales, las afectadas por el hueco pasan de 32 a 9. Solo se registraron cifras agregadas | CHANGELOG |
| Embeddings locales (`nomic-embed-text`) | La cobertura es idéntica al hash en 72 tareas de 8 corpus (83,2 %) | CHANGELOG |

## Límites de las afirmaciones

- **Sin mejora demostrada en sesiones:** ninguna medición con cliente de esta versión es
  significativa. Las tareas son pocas, con una repetición cada una.
- **Tareas de desarrollo:** las mejoras finales de los métodos asignados se midieron con las mismas
  tareas que sirvieron para encontrar sus fallos.
- **Despacho inferido:** todas sus aristas son `INFERRED` y conviene verificarlas en el código.
  Go apenas tiene interfaces en los corpus de prueba, así que su despacho está poco ejercitado.
- **Cliente único:** las sesiones se hicieron solo con Codex, no con Claude Code ni con Antigravity.
- **Plataformas:** macOS, ARM y `install.ps1` solo los cubren los jobs de CI; no se probaron en
  local.

## Requisitos antes de etiquetar

La etiqueta `v0.13.0` solo se publica después de que el CI pase sobre el commit final, incluidos
los jobs `browser` y `docker`. Después hay que descargar los artefactos de la release, verificar
`SHA256SUMS` y apuntar el README a la versión publicada.
