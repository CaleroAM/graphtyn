# Validación de `0.12.0`

Fecha: 2026-11-02. Esta versión hace que las gramáticas de Tree-sitter se
instalen por defecto, corrige el dashboard abierto desde la red y el grafo que
bloqueaba la página al cambiar de proyecto, y añade el panel de actividad de
agentes, la ayuda, el modo anónimo y el proyecto de ejemplo. El detalle está en
`docs/CHANGELOG.md`.

## Validación reproducible

Entorno observado: Linux 6.18.35 x86_64. La suite local se ejecutó sobre `fa554d3`,
preparado como `0.11.1`. Después sólo cambiaron el número de versión y la
documentación; el wheel y Docker se repitieron con `0.12.0`, y el CI repite la
suite en 3.10–3.13 sobre el commit final.

| Comprobación | Resultado |
|---|---|
| Suite completa, Python 3.10.20, 3.11.15, 3.12.13 y 3.13.13 (entornos `uv` limpios con `.[dev]`, `GRAPHTYN_HOME` aislado) | 770 pasaron, 3 omitidas en cada versión |
| Pruebas adversariales de fugas (`tests/test_security_leaks.py`) | pasan, dentro de la suite |
| Puerta de mantenibilidad (`tools/check_maintainability.py`) | pasa: 32 hotspots heredados, sin crecimiento |
| `uv build` | `graphtyn-0.12.0-py3-none-any.whl` y `graphtyn-0.12.0.tar.gz` |
| Contenido del wheel | dashboard, librerías en `web/vendor/`, proyecto de ejemplo, las dos skills, `api/agent_activity.py`, `core/query_log.py` |
| Wheel en entorno vacío (Python 3.13), sin extras | `--version` 0.12.0; `setup` en vista previa; `reindex` y `report` funcionan sobre el proyecto de ejemplo |
| MCP stdio desde ese wheel | `serverInfo.version` 0.12.0; `graph_query_intent` devuelve 10 entidades y 3 etapas, y la consulta queda registrada con el nombre del cliente |
| `pip-audit` sobre el entorno del wheel | sin vulnerabilidades conocidas (el propio paquete no existe en PyPI y no se audita) |
| Docker | la imagen construye; `/health` responde `{"status":"ok","service":"Graphtyn","version":"0.12.0"}`; el proceso corre como usuario 10001; no faltan gramáticas |
| Smoke de Chromium (`tests/smoke_frontend.py`) | 3 de 3 sin errores JS |

Comprobaciones del dashboard hechas en los PR de esta versión, con un servidor
aislado y un navegador real:

| Recorrido | Resultado |
|---|---|
| Ayuda, atajos, modo anónimo y proyecto de ejemplo (#27) | 8 de 8 |
| Actividad con un proceso MCP real y el hook de Codex con el panel abierto (#28) | 29 de 29 |
| Interruptor del registro, por la red y con token (#29) | 8 de 8 |
| Índice con y sin `tree-sitter` en un entorno limpio (#30) | 14 relaciones `llama` con él; 0 sin él, con aviso |

## Límites de las afirmaciones

- **Actividad:** se probó con un proceso MCP real al que se le dio un nombre de
  cliente, no con Claude Code, Codex u OpenCode reales. El nombre que muestre cada
  cliente puede variar.
- **Lo que no se ve:** el panel sólo cuenta lo que pasa por Graphtyn. No sabe qué
  archivos lee o busca el agente después. «Suficiente» es la señal `do_not_expand`
  de Graphtyn, no prueba de que el agente dejara de buscar.
- **`graphtyn query-intent`:** las consultas por CLI no se registran.
- **Motivos de cada entidad:** se calculan después de la selección. Explican qué
  relaciona la entidad con la pregunta, no el ranking interno.
- **Etiquetas sobre el lienzo:** sólo en la vista 2D.
- **Hook con rutas reales:** el defecto se midió en sesiones archivadas, pero el
  efecto de corregirlo no se midió con sesiones nuevas.
- **Tree-sitter:** se comprobó que existen wheels para Linux (glibc y musl), macOS
  y Windows, incluido ARM, en Python 3.10–3.14. La instalación y ejecución real
  sólo se probó en Linux x86_64 y en el job de Windows de CI; macOS y ARM, no.
- **`install.ps1`:** no se ejecutó en local; lo cubre el job de Windows de CI.
- **Sin benchmarks nuevos:** esta versión no aporta mediciones nuevas de ahorro de
  tokens. Siguen valiendo los límites de `docs/release-validation-0.11.0.md`.

## Requisitos antes de etiquetar

La etiqueta `v0.12.0` sólo se publica después de que el CI pase sobre el commit
final, incluidos los jobs `browser` y `docker`. Hay que descargar los artefactos de
la release y verificar `SHA256SUMS`. Al publicar, se actualizan el enlace de
instalación y la versión del README.
