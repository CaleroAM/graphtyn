# Antigravity + Gemini 3.7 Flash: repositorios reales

Fecha: 2026-08-25. Modelo observado en la telemetría de Antigravity:
`gemini-3.7-flash-high`. Repositorios fijados: Starlette
`398e5a3430eb1ddd33e1d48d766efe41426e231f` y go-chi
`735ae2b87f8c733d616e809ae86e0985c1bc3350`. El competidor fue
Gra…ify `0.9.49`. Cada tarea se calificó contra hechos atómicos definidos antes
de ejecutar el agente.

## Matriz original aleatorizada

| Variante | Calidad media | Tokens medios | Tiempo medio | Éxito del agente |
|---|---:|---:|---:|---:|
| Sin grafo | 100.00% | 137,742 | 64.55 s | 3/4 |
| Gra…ify | 78.75% | 107,192 | 41.53 s | 4/4 |
| Graphtyn, antes del arreglo | 56.25% | 60,317 | 29.82 s | 4/4 |

La calidad original de Graphtyn no fue competitiva: falló la selección de la
entrada ASGI de Starlette y parte del flujo de parámetros URL de go-chi. La
lectura directa alcanzó todos los hechos, aunque una celda terminó con estado
`ERROR` después de producir una respuesta completa. Los resultados crudos están
en `results.json`; no se sustituyeron al corregir el sistema.

## Repetición dirigida posterior

Se corrigieron la expansión de intención, el anclaje de entrypoints y la
priorización de `FindRoute`. Sólo se repitieron las dos celdas afectadas de
Graphtyn; las otras dos se conservaron porque ya tenían calidad 100%.

| Variante reconstruida | Calidad media | Tokens medios | Tiempo medio |
|---|---:|---:|---:|
| Graphtyn posterior | 100.00% | 41,306 | 17.35 s |

En esta reconstrucción dirigida, Graphtyn usa 61.46% menos tokens que Gra…ify y
70.01% menos que la lectura directa, con cobertura total de los hechos. No es
una nueva matriz aleatorizada ni prueba significancia estadística: es evidencia
de regresión para los dos defectos encontrados. Una afirmación competitiva
general exige más repositorios, tareas y repeticiones pareadas.

Artefactos: `results.json`, `postfix_graphtyn.json`,
`postfix_v2_graphtyn.json`, `../antigravity_real_tasks.json` y
`../run_antigravity_comparison.py`.

## Integración de agentes y memoria

La instalación `graphtyn agent-install antigravity` generó `GEMINI.md` y una
sesión nueva de Antigravity descubrió y ejecutó `graphtyn query-intent` sin que
el prompt nombrara el comando. La primera validación también detectó que el
agente reabría archivos completos aunque `source_evidence` ya cubría la tarea;
por ello AGENTS.md, la skill y la plantilla instalada ahora contienen un contrato
explícito de parada (`do_not_expand`).

Se reutilizaron por SSH las sesiones existentes de OpenClaw:

- Orchestrator/nexus, sesión `ec29e901-ad12-4d13-b333-44f5b5a32641`: llamó memoria tres
  veces y respetó evidencia propuesta, pero su resumen posterior mezcló agente y
  revisión; se clasifica como parcialmente correcto, no como evidencia fiable.
- Agent Beta/career, sesión `dcf8c37e-8d7f-422b-97d0-8b5c40786783`: llamó
  `memory_context` una vez, sin fallos, y devolvió correctamente métricas,
  revisiones, artefactos, modelo y limitaciones de benchmarks verificados. Uso
  observado: 24,598 tokens totales (3,542 entrada, 1,216 salida, 40,024 cache
  read y 263 razonamiento, según los campos del proveedor).

Al ingerir esta corrida se detectó que la CLI local y el servidor remoto podían
usar almacenes distintos si no compartían `GRAPHTYN_HOME`. Tras ingerir en el
almacén autoritativo `<HOME>/.graphtyn`, se repitió la consulta en la misma
sesión de Agent Beta: una llamada a `memory_context`, cero fallos, respuesta correcta con
las dos matrices, commits, artefactos y limitaciones. La segunda llamada tardó
8.18 s y reportó 30,189 tokens totales, de los cuales 52,098 fueron cache reads;
el campo total es el reportado por OpenClaw/proveedor y no es la suma simple de
todos los contadores expuestos.

Esto valida recuperación y atribución entre agentes, pero también demuestra que
la política de claims debe seguir siendo obligatoria: recuperar un nodo correcto
no garantiza que cualquier modelo lo resuma sin errores.
