# Validación de `0.13.1`

Fecha: 2026-11-14. Versión de correcciones sobre `0.13.0`:
- **Recorte del paquete:** una pregunta cuyo paquete no cabía en el presupuesto podía no terminar
  nunca (en Redis, cualquier pregunta que nombrara `set`). Ahora tarda 1,7 s.
- **Búsqueda semántica de respaldo:** sin `GRAPHTYN_EMBED_MODEL`, la primera consulta en Rails pasa
  de unos 50 s a 4 s, con resultados idénticos en las 138 tareas del gate.
- **Homónimos omitidos:** en una pregunta de impacto, cada definición omitida nombra su dueño
  (`OsFs.OpenFile`) y si implementa el método pedido, y `coverage.implementations` cuenta las del
  grafo entero.

El detalle está en `docs/CHANGELOG.md`.

## Validación reproducible

Entorno observado: Linux 6.18.35 x86_64. Todo se ejecutó sobre `10540c3`, el commit de la versión,
exportado con `git archive` y con un `GRAPHTYN_HOME` aislado. Después solo cambió la documentación, y
el CI repite la suite en 3.10–3.13 sobre el commit final.

| Comprobación | Resultado |
|---|---|
| Suite completa en entornos `uv` limpios con `.[dev]`, Python 3.10.20, 3.11.15, 3.12.13 y 3.13.13 | 983 pasaron y 2 omitidas en cada versión. El único fallo fue `test_release_documents_and_workflows_exist`, porque este documento aún no estaba en el commit; con él, `tests/test_release_contracts.py` pasa entero (11) en las cuatro versiones |
| Puerta de mantenibilidad (`tools/check_maintainability.py`) | pasa: 32 hotspots heredados, sin crecimiento |
| Gate de recuperación (`tools/check_retrieval_coverage.py`, 10 corpus públicos fijados) | pasa: 138 tareas, cobertura media 80,2 % (80,3 % en `0.13.0`). La única tarea por debajo del baseline es `RAILS_TOUCH_IMPACT`, con 5/6 hechos en vez de 6/6: está en el límite del presupuesto del paquete |
| `uv build` | `graphtyn-0.13.1-py3-none-any.whl` y `graphtyn-0.13.1.tar.gz` |
| Wheel en entorno vacío (Python 3.13), sin extras | `--version` 0.13.1; `setup` en vista previa; `reindex` (48 nodos, 66 conectores) y `report` funcionan sobre el proyecto de ejemplo |
| MCP stdio desde ese wheel | `serverInfo.version` 0.13.1; `graph_query_intent` devuelve 10 entidades, intención `flow` y `do_not_expand=true` |
| `pip-audit` sobre las 45 dependencias del entorno del wheel | sin vulnerabilidades conocidas |
| Docker | la imagen construye; `/health` responde `{"status":"ok","service":"Graphtyn","version":"0.13.1"}`; el proceso corre como usuario 10001; las 14 gramáticas cargan |
| Smoke de Chromium (`tests/smoke_frontend.py`, servidor desde el wheel) | dashboard, vistas y estilos sin errores JS |

## Mediciones de esta versión

| Cambio | Resultado | Informe |
|---|---|---|
| Homónimos con dueño y recuento del grafo entero | En la interfaz `Fs` de afero, Codex pasa de 12/17 hechos (`0.13.0`) a 17/17, con un 40 % menos de tokens que `0.12.0`. Son las mismas tareas que sirvieron para encontrar el fallo | `benchmarks/go_dispatch_2026-11-11/report.md` |
| Recorte del paquete | La pregunta de Redis que no terminaba tarda 1,7 s; el gate da el mismo resultado en las 138 tareas | CHANGELOG |
| Búsqueda semántica de respaldo | Primera consulta en Rails: de unos 50 s a 4 s; resultados idénticos en las 138 tareas | CHANGELOG |
| Calibración de los jueces | Sobre 12 respuestas (85 hechos) calificadas a mano por el mantenedor, la mayoría de jueces coincide en el 97,6 % (kappa 0,95), sin dar por cubierto ningún hecho que el humano rechazó. GPT solo coincide en el 90,6 % (kappa 0,79) | — |

## Límites de las afirmaciones

- **Tareas de desarrollo:** la mejora en afero se midió con las tareas que revelaron el fallo; no es
  evidencia independiente.
- **Calibración pequeña:** 12 respuestas de dos estudios y un solo calificador humano.
- **Plataformas:** macOS, ARM y `install.ps1` solo los cubren los jobs de CI; no se probaron en
  local.

## Requisitos antes de etiquetar

La etiqueta `v0.13.1` solo se publica después de que el CI pase sobre el commit final, incluidos
los jobs `browser` y `docker`. Después hay que descargar los artefactos de la release, verificar
`SHA256SUMS` y apuntar el README a la versión publicada.
