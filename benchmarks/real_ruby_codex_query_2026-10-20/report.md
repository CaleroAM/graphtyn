# Codex/Rails · perfil `query`, iteración 1

Fecha: 2026-10-20. Repositorio: `rails/rails` en `3f0b675158e8284241bb1213c00375bc1fb9c52f`. Cliente/modelo: Codex CLI 0.153.2, `gpt-6-astra`. Una repetición por brazo.

| Brazo | Calidad rúbrica | Tarea completa | Tokens totales | Entrada (caché incluida) | Salida | Sesión |
|---|---:|---:|---:|---:|---:|---:|
| Lectura directa | 8/8 | sí | 192.172 | 189.171 | 3.001 | 94,515 s |
| Graphtyn | 8/8 | **no** | 47.919 | 46.944 | 975 | 37,709 s |

La diferencia bruta de tokens es −75,07 %, pero **no es una comparación válida de igual calidad**. La respuesta de Graphtyn declaró que le faltaban `Transactions#save`, callbacks de creación y la semántica de abortos/excepciones. El paquete había dicho `missing=[]` y `do_not_expand=true`; esa falsa completitud impidió que el agente leyera lo faltante. Por eso `results.json` deja los deltas comparables en `null`, aunque conserva todos los contadores.

El índice tardó 177,762 s fuera de la sesión; primer uso = 215,471 s. Los costes monetarios no fueron expuestos. En Codex, `cached_input_tokens` es un subconjunto de `input_tokens` y `reasoning_tokens` es un subconjunto de la salida; no se suman otra vez. La CLI sólo publicó el agregado de sesión, de modo que no pueden reconstruirse llamadas de modelo individuales.

Los eventos y respuestas crudos permanecen en `/home/calero/Documentos/docker/graphtyn-benchmark-runs-ruby-codex-query-2026-10-20/`. La adjudicación es manual y no independiente. Esta ejecución se conserva como evidencia del defecto y no se reemplazó al repetir.
