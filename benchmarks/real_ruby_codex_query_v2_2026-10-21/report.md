# Codex/Rails · cobertura estricta, iteración 2

Fecha: 2026-10-21. Repositorio: `rails/rails` en `3f0b675158e8284241bb1213c00375bc1fb9c52f`. Cliente/modelo: Codex CLI 0.153.2, `gpt-6-astra`. Una pareja A/B fresca; no reutiliza resultados de la iteración anterior.

| Métrica | Lectura directa | Graphtyn | Cambio |
|---|---:|---:|---:|
| Calidad | 8/8, completa | 8/8, completa | comparable |
| Tokens totales | 137.077 | 50.326 | **−63,29 %** |
| Entrada, caché incluida | 133.525 | 49.042 | −63,27 % |
| Entrada cacheada (subconjunto) | 103.296 | 21.888 | −78,81 % |
| Salida | 3.552 | 1.284 | −63,85 % |
| Razonamiento (subconjunto) | 31 | 13 | −58,06 % |
| Tiempo de sesión | 96,006 s | 48,268 s | **−49,72 %** |
| Primer uso con índice | 96,006 s | 221,871 s | **+131,10 %** |

Graphtyn expuso sólo `graph_query_intent`, precargó el índice y devolvió un paquete de 4.533 tokens, nueve fragmentos/7.470 caracteres, diez entidades, `missing=[]`, `do_not_expand=true` y cobertura explícita de validación, ambos callbacks, entrada y rollback transaccionales, adaptador, resultado fallido y aborto. Codex realizó una llamada MCP y ninguna lectura de repositorio por shell en ese brazo.

El índice inicial tardó 173,603 s y queda fuera del tiempo de sesión. Por ello el resultado acredita ahorro de sesión caliente para esta tarea, mientras que el primer uso fue más lento. No acredita ahorro universal, significancia estadística ni menor coste monetario: hay una repetición, el precio no fue informado y el baseline varió frente a la iteración anterior. La adjudicación 8/8 y completitud fue manual, no independiente.

En Codex, la entrada cacheada ya está incluida en `input_tokens` y el razonamiento en `output_tokens`. Ambos totales son `input + output`; no se duplican subconjuntos. Sólo existe uso agregado por sesión, así que no se pueden reconstruir tokens por llamada de modelo ni reintentos que la CLI no haya emitido explícitamente.

Los eventos y respuestas crudos permanecen en `/home/calero/Documentos/docker/graphtyn-benchmark-runs-ruby-codex-query-v2-2026-10-21/`. La iteración incompleta anterior sigue publicada en `../real_ruby_codex_query_2026-10-20/`.
