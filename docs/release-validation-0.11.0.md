# Validación de `0.11.0`

Fecha: 2026-10-27. Esta versión añade paquetes de lenguaje (C/C++, Ruby,
Kotlin, Swift, Scala), la integración nativa con Claude Code, comunidades,
exportación HTML y triaje de PR, el paquete MCP `lean`, hooks de primer turno
para Claude Code, Codex y OpenCode, la separación de las skills `graphtyn` y
`graphtyn-memory`, y el registro MCP de Copilot en VS Code.

## Validación reproducible

Entorno observado: Linux 6.18.35 x86_64.

| Comprobación | Resultado |
|---|---|
| Suite completa, Python 3.13.13 (`.venv/bin/pytest -q`) | 693 pasaron, 3 omitidas |
| Suite completa, Python 3.10.20, 3.11.15 y 3.12.13 (entornos `uv` con `.[dev,treesitter]`) | 693 pasaron, 3 omitidas en cada versión |
| Puerta de mantenibilidad (`tools/check_maintainability.py`) | pasa: 33 hotspots, ninguno nuevo; revisión en `docs/MAINTAINABILITY.md` |
| `uv build` | `graphtyn-0.11.0-py3-none-any.whl` y `graphtyn-0.11.0.tar.gz` |
| Wheel en entorno vacío (Python 3.13) | `--version` 0.11.0; recursos empaquetados (dashboard y las dos skills); `setup` en vista previa; `reindex`; `report`; `query-intent`; MCP por stdio (`initialize` 0.11.0 y `tools/list` del perfil `query`); `codex-context hook`; `agent-install antigravity` instala las 5 rutas de skills y `integrations remove` las retira |
| `pip-audit` sobre las 29 dependencias instaladas del wheel | sin vulnerabilidades conocidas (el propio paquete no existe en PyPI) |
| Docker | la imagen construye; `--version` 0.11.0; `/health` responde `{"status":"ok","version":"0.11.0"}`; el proceso corre como `graphtyn` |
| Smoke de Chromium | **no ejecutado**: Playwright no encontró `libstdc++.so.6`. No es un pase; lo cubre el job `browser` de CI |

El CI comprueba además que el wheel contiene las skills empaquetadas.

## Evidencia de benchmarks

| Medición | Informe | Alcance |
|---|---|---|
| Hook y MCP lean en cuatro clientes | `benchmarks/real_multi_client_hook_2026-10-27/report.md` | Tres tareas, 84 sesiones. El hook baja la sesión a ~34k (Claude), ~12k (Codex) y 16–35k (OpenCode) |
| Tareas no vistas | `benchmarks/heldout_tasks_2026-10-27/report.md` | Seis tareas nuevas, 54 sesiones. **El ahorro no generaliza** cuando el paquete se declara completo sin cubrir lo pedido |

## Límites de las afirmaciones

- **Generalidad del ahorro:** las cifras de ahorro valen para las tareas
  medidas. Con tareas no vistas, en tres de seis el paquete declara
  `do_not_expand=true` sin cubrir lo pedido. Los agentes respondieron
  incompletos (fmt, entero con especificaciones: 3/7 con Graphtyn frente a 7/7
  sin grafo). La calibración de `do_not_expand` queda pendiente.
- **Hook opcional:** el hook de primer turno sigue siendo opcional (`--consent`)
  y no se recomienda por defecto.
- **Copilot:** el registro en `.vscode/mcp.json` está cubierto por tests, pero
  no se probó con un cliente Copilot real.
- **Hooks de Codex:** en uso real, los hooks de proyecto exigen confiar en la
  capa `.codex/` y aprobar el hook con `/hooks`.
- **Commits intermedios:** la suite se ejecutó sobre el commit final, no sobre
  cada commit intermedio de la rama.

## Cambios posteriores a esta validación

Después de la validación anterior se añadieron:

- el filtro multilingüe de los hooks;
- la limpieza de mantenibilidad;
- la regla de parada dirigida;
- las llamadas Ruby sin paréntesis y los filtros de candidatos;
- el segundo conjunto de tareas no vistas (`benchmarks/heldout_v2_2026-10-27/`);
- los cambios de recuperación y la regla de completitud por evidencia escasa,
  medidos con el banco de tareas (`benchmarks/task_bank_2026-10-28/`). Con ellos,
  la cobertura del conjunto de prueba pasa del 20 % al 37,5 %;
- una segunda ronda (completitud por identificadores y homónimos), medida en un
  segundo conjunto de prueba con Flask y en 75 sesiones reales de Claude y
  Codex (véase el informe del banco de tareas).
- la prueba de cobertura de CI, la composición de módulos Ruby y los pesos de
  ranking ajustados.
- una quinta ronda (cadena de llamadas reservada, `call_outline` y comandos en
  mayúsculas), medida en un tercer conjunto de prueba y en 300 sesiones reales.
- una sexta ronda (anclajes, homónimos, intenciones y estado compartido),
  medida en un cuarto conjunto de prueba y en 192 sesiones reales.
- validación local del commit candidato: wheel y sdist construidos, el wheel
  instalado en un entorno vacío responde a `--version` y `query-intent`, la
  imagen Docker responde `/health` como usuario 10001 y `pip-audit` no encuentra
  vulnerabilidades en las dependencias de Graphtyn.

La suite local pasa con 738 pruebas en Python 3.13 tras esos cambios. La matriz
3.10–3.12, el wheel, Docker y `pip-audit` deben repetirse sobre el commit que se
etiquete.

## Requisitos antes de etiquetar

La etiqueta `v0.11.0` sólo se publicará después de que el CI pase sobre el
commit final, incluidos los jobs `browser` y `docker`. Además hay que construir
wheel y sdist desde ese SHA, instalarlos en un entorno vacío y comprobar que sus
metadatos coinciden con la etiqueta. Una afirmación pública de ahorro de tokens
debe citar el alcance de las tareas medidas y el resultado de las tareas no
vistas.
