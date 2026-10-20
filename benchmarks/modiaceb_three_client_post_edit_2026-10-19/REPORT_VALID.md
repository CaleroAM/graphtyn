# C1 en OpenCode, Codex y Antigravity después de las optimizaciones

## Resultados válidos

| Cliente | Brazo | Entrada | Caché | Salida | Razonamiento | Total reportado | Tiempo | Calidad |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| OpenCode | Baseline | 41,109 | 400,384 | 3,236 | 2,775 | 447,504 | 47.242 s | 6/6 |
| OpenCode | Graphtyn | 32,408 | 120,960 | 3,502 | 2,194 | 159,064 | 41.558 s | 6/6 |
| Codex | Baseline | 104,461 | 83,840 | 1,813 | no reportado | 106,274 | 59.521 s | 6/6 |
| Codex | Graphtyn | 109,916 | 82,432 | 1,881 | no reportado | 111,797 | 49.951 s | 6/6 |
| Antigravity | Baseline | 119,853 | 1,034,754 | 28,096 | 17,339 | 147,949 | 247.223 s | 6/6 |
| Antigravity | Graphtyn | 86,214 | 498,547 | 15,499 | 6,956 | 101,713 | 139.960 s | 6/6 |

Los deltas del total reportado son -64.5% para OpenCode, +5.2% para Codex y -31.3% para Antigravity. Los tiempos cambian -12.0%, -16.1% y -43.4%, respectivamente.

Los seis brazos produjeron respuesta completa. Los tres tratamientos ejecutaron `graph_query_intent`; Antigravity registró explícitamente `graphtyn_benchmark`.

## Contabilidad y desviaciones

Los totales sólo deben compararse dentro de cada cliente. OpenCode suma eventos `step_finish` por paso e incluye caché y razonamiento en el total. Codex usa `turn.completed`; su total reportado es entrada más salida y deja la caché separada. Antigravity también reporta `total_tokens = input_tokens + output_tokens` y separa `cache_read_tokens`; el razonamiento no debe sumarse otra vez porque forma parte de la salida reportada. Incluyendo caché como consumo técnico derivado, Codex pasa de 190,114 a 194,229 (+2.2%) y Antigravity de 1,182,703 a 600,260 (-49.2%). Estas sumas derivadas no son cifras facturadas por los proveedores.

OpenCode realizó primero una llamada MCP fallida por un `expected_project` incorrecto y luego reintentó correctamente. Codex recibió `missing=["relevant_anchor"]` y completó mediante lectura local. Estas desviaciones se conservaron y no se repitieron las sesiones.

## Conclusión

Con calidad equivalente, Graphtyn redujo consumo reportado en OpenCode y Antigravity, pero lo aumentó 5.2% en Codex. Esto confirma que la ventaja depende del cliente y del comportamiento posterior a la recuperación; no sustenta una afirmación universal de ahorro.

## Evidencia trazable

- OpenCode baseline y Graphtyn: `results.json:2` y `results.json:26`.
- Codex Graphtyn y baseline: `results.json:50` y `results.json:74`.
- Antigravity baseline y Graphtyn: `results.json:98` y `results.json:122`.
- Calificación local no independiente: `GRADES_VALID.json:2`.
