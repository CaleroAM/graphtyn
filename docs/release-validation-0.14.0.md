# Validación de `0.14.0`

Fecha: 2026-11-17. Versión menor sobre `0.13.1`:
- **`graphtyn scope`:** limita qué rutas de un proyecto indexa Graphtyn, pensado para un home del que
  solo interesa la configuración. Los secretos nunca entran.
- **Paquetes de impacto:** los tests ya no desplazan a los consumidores de producción, y un paquete
  que depende de usos textuales ya no se declara completo.
- **Captura continua en reposo:** un ciclo sin cambios pasa de unos 31 s de CPU a unos 1,8 s, y el
  servidor y el watcher bajan su propia prioridad.

El detalle está en `docs/CHANGELOG.md`.

## Validación reproducible

Entorno observado: Linux 6.18.35 x86_64. Todo se ejecutó sobre `d74d818`, el commit de la versión,
exportado con `git archive` y con un `GRAPHTYN_HOME` aislado. Después solo cambió la documentación, y
el CI repite la suite en 3.10–3.13 sobre el commit final.

| Comprobación | Resultado |
|---|---|
| Suite completa en entornos `uv` limpios con `-e .[dev]`, Python 3.10.20, 3.11.15, 3.12.13 y 3.13.13 | 1013 pasaron y 3 omitidas en cada versión. El único fallo fue `test_release_documents_and_workflows_exist`, porque este documento aún no estaba en el commit |
| Puerta de mantenibilidad (`tools/check_maintainability.py`) | pasa: 32 hotspots heredados, sin crecimiento |
| Gate de recuperación (`tools/check_retrieval_coverage.py`, 10 corpus públicos fijados) | pasa: 138 tareas, cobertura media 80,3 % (80,2 % en `0.13.1`) |
| `uv build` | `graphtyn-0.14.0-py3-none-any.whl` y `graphtyn-0.14.0.tar.gz` |
| Wheel en entorno vacío (Python 3.13), sin extras | `--version` 0.14.0; el dashboard y las skills están en el paquete; `setup` en vista previa no cambia el proyecto; `reindex` (12 nodos, 18 conectores) y `report` funcionan sobre un proyecto de prueba de tres módulos |
| MCP stdio desde ese wheel | `serverInfo.version` 0.14.0, 16 herramientas; `graph_query_intent` con una pregunta de impacto devuelve intención `impact`, `do_not_expand=true` y el consumidor correcto con su línea (`app/service.py:5`) |
| `pip-audit` sobre las 45 dependencias del entorno del wheel | sin vulnerabilidades conocidas |
| Docker | la imagen construye; `/health` responde `{"status":"ok","service":"Graphtyn","version":"0.14.0"}`; el proceso corre como usuario 10001; las 14 gramáticas cargan |
| Smoke de Chromium (`tests/smoke_frontend.py`, servidor desde el wheel) | dashboard, vistas y estilos sin errores JS |

## Mediciones de esta versión

| Cambio | Resultado | Informe |
|---|---|---|
| Consumidores de producción en paquetes de impacto | 8 tareas nuevas en requests, axios, commons-lang y echo (72 sesiones de Codex): de 102 a 112 hechos de 117; sin grafo, 115. La mediana de tokens sube de 31k a 47k, un 29 % por debajo de no usar grafo | `benchmarks/impact_fix_validation_2026-11-15/report.md` |
| Comparación con Graphify 0.9.106 | Graphtyn es el que menos tokens gasta, pero pierde calidad. Con Claude saca 146/157 hechos, frente a 155 sin grafo; con Codex, 90/162 frente a 137. Las dos causas de recuperación que encontró son las que corrige esta versión | `benchmarks/graphify_head_to_head_2026-11-15/report.md` |
| `graphtyn scope` en un home real | Sin alcance, el índice tenía 289.010 nodos y 1,9 GB, sin ningún archivo de configuración. Con un alcance de configuración: 591 archivos, 2.709 nodos y 4,7 MB, indexado en 0,9 s | CHANGELOG |
| Captura continua en reposo | Ciclo sin cambios en un almacén real (147 sesiones): de unos 31 s de CPU a unos 1,8 s, con las mismas sesiones descubiertas. Un test de regresión falla si un ciclo sin datos nuevos lanza un proceso o escribe un archivo | CHANGELOG |

## Límites de las afirmaciones

- **Calidad frente a no usar grafo:** la corrección de impacto se validó con tareas nuevas, pero aún
  queda por debajo de no usar grafo (112 frente a 115 de 117), y la comparación con Graphify sigue
  siendo negativa en calidad.
- **Mediciones de un solo equipo:** las de `scope` y de la captura en reposo vienen de un único
  equipo real.
- **Plataformas:** macOS, ARM, Windows e `install.ps1` solo los cubren los jobs de CI; no se probaron
  en local.

## Requisitos antes de etiquetar

La etiqueta `v0.14.0` solo se publica después de que el CI pase sobre el commit final, incluidos
los jobs `browser` y `docker`. Después hay que descargar los artefactos de la release, verificar
`SHA256SUMS` y apuntar el README a la versión publicada.
