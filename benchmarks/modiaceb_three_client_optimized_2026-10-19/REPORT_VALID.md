# Repetición mínima C1: tres clientes

Fecha: 2026-10-19. Repositorio evaluado: modIAceb `70dc1e8b732ebb08d93e39219a2016f4ef2d8bf8`.
Graphtyn declaró versión `0.10.6` sobre un árbol de trabajo modificado; el diff de las cuatro correcciones centrales tuvo SHA-256 `de7b46c4bec61c2e3703255e2a4cad7858c82907c895d0804a7d11d9a285e5f5`.

## Resultado válido

| Cliente/modelo | Baseline total | Graphtyn total | Cambio | Baseline s | Graphtyn s | Calidad |
|---|---:|---:|---:|---:|---:|---:|
| OpenCode / `opencode/deepseek-v4.1-flash-free` | 283,591 | 349,947 | +23.4% | 49.5 | 64.6 | 6/6 vs 6/6 |
| Codex / `gpt-6-astra` | 101,178 | 154,403 | +52.6% | 41.8 | 53.3 | 6/6 vs 6/6 |
| Antigravity / `gemini-3.8-flash-high` | 138,307 | 115,878 | -16.2% | 240.5 | 226.7 | 6/6 vs 6/6 |

No se agregan los totales entre clientes: cambian modelo, cliente, política de caché y formato de herramientas. La única conclusión medida es por par. En esta tarea, con calidad manual equivalente, Graphtyn consumió más tokens reportados en OpenCode y Codex, y menos en Antigravity. Una tarea y una repetición no estiman varianza ni prueban un efecto general.

## Desglose

| Cliente | Brazo | Entrada | Caché reportada | Salida | Razonamiento | Total |
|---|---|---:|---:|---:|---:|---:|
| OpenCode | baseline | 62,853 | 215,552 | 3,143 | 2,043 | 283,591 |
| OpenCode | Graphtyn | 43,751 | 300,032 | 3,149 | 3,015 | 349,947 |
| Codex | baseline | 99,493 | 67,968 | 1,685 | 22 | 101,178 |
| Codex | Graphtyn | 152,602 | 120,704 | 1,801 | no informado | 154,403 |
| Antigravity | baseline | 113,525 | 896,255 | 24,782 | 13,139 | 138,307 |
| Antigravity | Graphtyn | 92,738 | 652,834 | 23,140 | 13,074 | 115,878 |

Los campos conservan la semántica del proveedor. En Codex, caché es subconjunto de entrada y no se suma otra vez. Antigravity informa una lectura de caché mayor que `total_tokens`; por ello se conserva separada y no se interpreta como consumo facturable. OpenCode informó coste `0` en ambos brazos; los otros clientes no informaron coste. No se infiere coste monetario desde tokens.

OpenCode redujo entrada no cacheada 30.4%, pero su caché y razonamiento elevaron el total 23.4%. Codex elevó entrada 53.4% y total 52.6%. Antigravity redujo entrada 18.3% y total 16.2%.

## Comparación con Graphtyn anterior y Graphify

Estas cifras son históricas y se presentan por protocolo. No deben promediarse con la repetición actual.

### Pregunta C1 con OpenCode

Esta es la comparación más cercana: misma pregunta C1, mismo commit de modIAceb y mismo modelo `opencode/deepseek-v4.1-flash-free`, con una repetición por condición.

| Condición | Calidad | Total | Entrada sin caché | Caché | Tiempo | Cambio frente al baseline histórico |
|---|---:|---:|---:|---:|---:|---:|
| Baseline histórico | 6/6 | 540,504 | 75,265 | 459,904 | 109.409 s | referencia |
| Graphtyn anterior | 6/6 | 662,919 | 74,350 | 578,432 | 150.466 s | +22.65% |
| Graphify 0.9.92 | 6/6 | 437,058 | 75,612 | 355,200 | 67.386 s | -19.14% |
| Graphtyn corregido, repetición actual | 6/6 | 349,947 | 43,751 | 300,032 | 64.550 s | protocolo nuevo; no usar el baseline histórico |

En la comparación histórica directa, Graphify consumió 34.07% menos tokens que Graphtyn anterior. Frente al Graphtyn anterior, la repetición actual de Graphtyn reportó 47.21% menos tokens y 57.10% menos tiempo, pero no es un A/B entre versiones: cambió el arnés, el presupuesto de salida, la recuperación y la sesión del proveedor. La comparación causal válida de la versión actual sigue siendo contra su propio baseline actual: 349,947 frente a 283,591, es decir, +23.4%.

### Tarea de edición con OpenCode

| Condición | Calidad | Pruebas verificadas | Total | Entrada sin caché | Caché | Tiempo | Cambio frente al baseline |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 8/8 | 16 pasaron | 1,679,938 | 116,684 | 1,546,112 | 192.449 s | referencia |
| Graphtyn anterior | 8/8 | 16 pasaron | 2,535,043 | 213,199 | 2,297,984 | 277.267 s | +50.90% |
| Graphify 0.9.92 | 8/8 | 17 pasaron | 2,998,493 | 246,146 | 2,729,856 | 377.325 s | +78.49% |

En esta tarea Graphify consumió 18.28% más tokens que Graphtyn anterior. Ambos consumieron más que el baseline porque la consulta del grafo se añadió a la lectura, edición y validación local en vez de sustituirlas.

### Piloto original de Codex en modIAceb

El piloto del 17–18 de octubre usó `gpt-6-astra`, esfuerzo `xhigh`, tres preguntas de código, dos repeticiones y un flujo obligatorio de memoria, grafo y validación. Sus medias por sesión fueron:

| Condición de código | Sesiones | Calidad acumulada | Total medio | Entrada sin caché media | Tiempo medio |
|---|---:|---:|---:|---:|---:|
| Sin Graphtyn | 6 | 36/36 | 135,113 | 43,044 | 66.8 s |
| Con Graphtyn anterior | 6 | 36/36 | 295,886 | 51,311 | 132.5 s |

Graphtyn anterior usó 2.19 veces los tokens totales y 1.99 veces el tiempo en esas preguntas de código. En las dos tareas de memoria, en cambio, mejoró cobertura de 8/12 a 11/12 y redujo el total medio de 96,730 a 93,550 tokens. Ese piloto no fue una réplica del benchmark publicado y tuvo interrupciones por cuota, evaluación no independiente y desviaciones conservadas.

Graphify también publica internamente una reducción `87.1x`, calculada al comparar un corpus estimado de 140,800 tokens con unos 1,617 tokens recuperados por consulta. Esa medida describe corpus frente a subgrafo recuperado; no representa el consumo total de una sesión de agente y no contradice que su tarea de edición usara 2,998,493 tokens.

## Uso efectivo de Graphtyn

Los tres tratamientos invocaron `graph_query_intent`: OpenCode mediante la herramienta MCP nombrada, Codex mediante un evento `mcp_tool_call` completado y Antigravity mediante `call_mcp_tool`. La salida serializada observada fue de 7,138 bytes en OpenCode y 17,584 bytes en Codex. El stream de Antigravity omite el cuerpo de salida, así que sus bytes no pueden reconstruirse y se dejan desconocidos.

La recuperación todavía eligió `overview` y devolvió contexto arquitectónico genérico antes de que los agentes leyeran el código necesario. Esto explica parte del sobrecoste: para C1, Graphtyn añadió contexto sin reemplazar suficiente exploración local. El resultado de Antigravity muestra que el ahorro sí puede aparecer cuando el cliente usa ese contexto para reducir su exploración posterior.

### Corrección posterior al benchmark

Después de conservar los resultados anteriores, el planificador se ajustó sin ejecutar nuevas sesiones de modelos. Una reproducción local de la misma C1, incluso solicitando explícitamente `intent=overview`, ahora se reclasifica como `flow`, identifica siete obligaciones concretas, recupera Docker, el cargador y los dos generadores, y termina con `missing=[]` y `do_not_expand=true`.

El paquete serializado bajó de 3,997 a 2,815 tokens estimados, una reducción determinista de 29.6%, y los archivos seleccionados bajaron a cinco. Esta cifra mide solamente contexto recuperado; no predice todavía la reducción del total de sesión. Los totales A/B de la tabla permanecen sin cambios hasta una nueva ejecución autorizada.

## Intentos preservados y excluidos

- En el directorio principal, las dos primeras celdas de Antigravity quedaron sin respuesta porque `--sandbox` negó lectura local y MCP. Sus tokens (16,228 y 20,572) son consumo real del intento, pero no pertenecen al A/B de calidad comparable.
- `modiaceb_three_client_optimized_2026-10-19_codex_retry1` hizo visible el MCP, pero la política `never` rechazó la llamada. Se preserva y se excluye.
- La primera celda Codex Graphtyn del directorio principal usó el CLI local porque el MCP no estaba cargado. Se preserva y se excluye del par final.
- El par Codex válido está en `modiaceb_three_client_optimized_2026-10-19_codex_retry2`; el par Antigravity válido está en `modiaceb_three_client_optimized_2026-10-19_antigravity_retry1`.

## Límites y siguiente prueba

La calidad fue evaluada por el mismo agente que ejecutó y consolidó la prueba, no por un evaluador ciego e independiente. Cada respuesta cubrió las seis obligaciones congeladas, pero esta puntuación manual no detecta diferencias finas de concisión o utilidad.

Antes de publicar una cifra de ahorro conviene ejecutar C1-C3, dos repeticiones, con orden AB/BA y evaluación ciega. Deben reportarse medianas e intervalos por cliente/modelo, intentos fallidos, bytes recuperados, entrada no cacheada, caché, salida, razonamiento, total de sesión, tiempo y coste monetario informado. Los resultados históricos deben permanecer sin cambios.
