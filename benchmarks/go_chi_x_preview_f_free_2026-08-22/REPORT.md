# Benchmark real de OpenCode: go-chi

Fecha: 2026-08-22. Repositorio público: `go-chi/chi`, revisión fija
`735ae2b87f8c733d616e809ae86e0985c1bc3350`. Es un router HTTP de producción
escrito en Go (78 archivos Go rastreados), elegido para probar flujo de control,
middleware, estado por petición y semántica de errores fuera de los proyectos de
desarrollo de Graphtyn.

## Protocolo

- Modelo idéntico: `opencode/x-preview-f-free`.
- Cuatro preguntas idénticas, cada una con seis hechos atómicos verificables.
- Una ejecución por tarea y variante: 12 ejecuciones en total.
- OpenCode puro pudo usar lectura y búsqueda local.
- En las variantes con grafo se desactivaron lectura, grep, glob y shell; el agente
  solo pudo consultar el MCP correspondiente.
- Gra…ify se indexó con `update --no-cluster`; Graphtyn con `reindex --mode fast`.
- Las respuestas se puntuaron contra el ground truth versionado en
  `benchmarks/go_chi_agent_tasks.json`: cubierto = 1, parcial = 0.5, ausente = 0;
  las contradicciones descuentan puntuación.

## Resultado agregado

| Variante | Calidad ajustada | Errores factuales | Tokens totales | Tiempo | Consultas |
|---|---:|---:|---:|---:|---:|
| OpenCode puro | 95.84% | 0 | 65,965 | 581.2 s | 41 |
| Gra…ify | 31.25% | 1 | 60,492 | 428.0 s | 58 |
| Graphtyn | 72.92% | 0 | 42,061 | 383.3 s | 5 |

Los tokens son el campo acumulado `usage.total_tokens` informado por OpenCode y
el proveedor; incluyen el contexto procesado durante las rondas y no equivalen a
`input_tokens + output_tokens` de la respuesta final.

## Comparaciones pareadas

- Graphtyn frente a OpenCode puro: 36.24% menos tokens (10,515 frente a 16,491
  por tarea), 34.05% menos tiempo y 22.92 puntos porcentuales menos de calidad.
- Graphtyn frente a Gra…ify: 30.47% menos tokens, 10.46% menos tiempo, 41.67
  puntos más de calidad y cero errores factuales frente a uno.
- Graphtyn ganó en calidad a Gra…ify en las cuatro tareas. OpenCode puro ganó en
  calidad a Graphtyn en las cuatro.

## Resultado por tarea

| Tarea | Puro calidad/tokens | Gra…ify calidad/tokens | Graphtyn calidad/tokens |
|---|---:|---:|---:|
| Ciclo de `Mux.ServeHTTP` | 91.67% / 21,207 | 25.00% / 12,805 | 58.33% / 14,729 |
| Orden de middleware | 100% / 13,110 | 16.67% / 14,957 | 83.33% / 8,975 |
| Seguridad del contexto | 91.67% / 19,532 | 33.33% / 15,179 | 66.67% / 9,581 |
| Semántica de fallos | 100% / 12,116 | 50.00% / 17,551 | 83.33% / 8,776 |

## Auditoría y lectura honesta

Las 12 ejecuciones terminaron con `SUCCESS` y sin reintentos. La revisión manual
confirma el principal motivo de la diferencia: Gra…ify expuso símbolos y enlaces,
pero omitió varias operaciones internas de cuerpos de función. En la tarea de
orden de middleware, además, su respuesta contradijo el hecho prohibido sobre el
orden de ejecución. Graphtyn recuperó operaciones del flujo con una o dos llamadas
MCP por tarea, pero todavía dejó detalles parciales, sobre todo en el ciclo de
`ServeHTTP`. OpenCode puro leyó directamente los archivos y obtuvo la mejor
cobertura, a costa de mucho más contexto y más llamadas.

Esto es evidencia útil, no una afirmación estadística definitiva: son cuatro
tareas y una repetición por celda. Con cuatro pares, la prueba de signos da
`p=0.125`; hacen falta más repositorios y al menos cinco repeticiones por variante
para estimar varianza y significancia. El índice se construyó antes de preguntar y
su costo local no consume tokens del modelo remoto.

## Reproducción

Los prompts, respuestas, telemetría y calificaciones completas están en esta
carpeta. Los archivos sin sufijo `_graded` son la captura cruda; los que terminan
en `_graded.json` incorporan la evaluación determinista. No se deben comparar
solo longitudes de respuesta: la métrica principal es cobertura factual ajustada,
acompañada de errores, tokens y latencia.
