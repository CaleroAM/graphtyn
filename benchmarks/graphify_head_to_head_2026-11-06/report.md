# Sin grafo, Graphtyn y Graphify: comparación simultánea

Fecha: 2026-11-06. 96 sesiones completas: 8 tareas × 3 brazos × 2 clientes × 2 repeticiones.
Unos 11,2 millones de tokens.

**Veredicto: MIXED.**

- **Claude Code:** Graphtyn supera a Graphify en coste y en calidad.
- **Codex:** Graphtyn es con diferencia el más barato, pero pierde calidad frente a los otros
  dos brazos. Casi toda la pérdida sale de dos fallos concretos de Graphtyn, descritos abajo.

## Diseño

- **Repositorios públicos en commits fijos:**
  - [redis/redis](https://github.com/redis/redis) `f2a17a8d`;
  - [fmtlib/fmt](https://github.com/fmtlib/fmt) `0fc31633`;
  - [rails/rails](https://github.com/rails/rails) `3f0b6751`;
  - [pallets/flask](https://github.com/pallets/flask) `d086db85`.
- **Tareas:** 8 nuevas, dos por repositorio (una de impacto y una de flujo), con 59 hechos.
  Las rúbricas se escribieron leyendo el código y se congelaron antes de ejecutar (commit
  `3cda6ba`). Ninguna tarea se usó para ajustar Graphtyn.
- **Brazos:**
  - **Sin grafo:** búsqueda y lectura normales.
  - **Graphtyn:** `main` en `69c2085`, MCP lean y regla de parada `targeted`.
  - **Graphify:** 0.9.103 con `graphifyy[mcp]`, su `graphify-mcp` oficial y sus 10
    herramientas, sobre un grafo de solo código construido sin LLM (`GRAPHIFY_BACKEND=none`)
    fuera del tiempo medido.
- **Aislamiento:**
  - **Graphify:** instalado en `~/.cache/graphtyn-bench/graphify-0.9.103`, fuera de este
    repositorio, sin skill, hook ni instrucciones de proyecto, y nunca registrado como
    `graphtyn`.
  - **Sesiones:** cada sesión usa una copia del repositorio y un `GRAPHTYN_HOME` propio.
- **Clientes:** Claude Code 2.1.318 con `claude-sonnet-5-5`, y Codex 0.153.2 con
  `gpt-5.6-luna` y `--ignore-user-config`. El orden de los brazos se alterna entre
  repeticiones.
- **Calificación:** dos jueces de modelos distintos, Gemini y GPT, sin herramientas ni
  acceso al código, deciden cada hecho; cuenta solo si coinciden. El kappa entre jueces fue
  0,95. La rúbrica literal se conserva como medida secundaria; su kappa con el consenso es
  0,51.

## Resultado

Medias por sesión. En Claude los tokens incluyen lecturas y escrituras de caché, y el coste
es el que informa el cliente.

| Cliente | Brazo | Hechos (jueces) | Tokens: media | Tokens: mediana | Coste USD | Herramientas |
|---|---|---:|---:|---:|---:|---:|
| Claude | Sin grafo | 116/118 (98 %) | 116.769 | 87.411 | 0,088 | 3,0 |
| Claude | **Graphtyn** | **118/118 (100 %)** | **101.612** | **61.018** | **0,082** | 2,1 |
| Claude | Graphify | 114/118 (97 %) | 135.727 | 105.554 | 0,094 | 3,6 |
| Codex | Sin grafo | **105/118 (89 %)** | 103.795 | 99.531 | — | 4,6 |
| Codex | **Graphtyn** | 85/118 (72 %) | **46.667** | **34.006** | — | 1,7 |
| Codex | Graphify | 100/118 (85 %) | 194.408 | 201.914 | — | 6,9 |

Por parejas (misma tarea y repetición):

| Cliente | Comparación | Gasta menos en | Cambio mediano de tokens | Hechos |
|---|---|---:|---:|---|
| Claude | Graphtyn frente a Graphify | 15 de 16 | −38,7 % | 118 frente a 114 |
| Claude | Graphtyn frente a sin grafo | 10 de 16 | −26,6 % | 118 frente a 116 |
| Claude | Graphify frente a sin grafo | 3 de 16 | +18,5 % | 114 frente a 116 |
| Codex | Graphtyn frente a Graphify | 16 de 16 | −80,5 % | 85 frente a 100 |
| Codex | Graphtyn frente a sin grafo | 14 de 16 | −55,3 % | 85 frente a 105 |
| Codex | Graphify frente a sin grafo | 1 de 16 | +75,9 % | 100 frente a 105 |

Graphify gastó más que la versión sin grafo en los dos clientes, sin ganar calidad. Eso
coincide con la medición del 26 de octubre con Graphify 0.9.96.

## Por tarea

Hechos de las dos repeticiones y media de tokens.

| Tarea | Claude: sin grafo / Graphtyn / Graphify | Codex: sin grafo / Graphtyn / Graphify |
|---|---|---|
| Redis `lookupKeyWrite`, impacto | 16/16 103k · 16/16 59k · 16/16 105k | 16/16 104k · 16/16 30k · 16/16 166k |
| Redis `processMultibulkBuffer`, flujo | 16/16 156k · 16/16 170k · 16/16 187k | 14/16 170k · **9/16 54k** · 14/16 251k |
| fmt `count_digits`, impacto | 12/14 86k · 14/14 59k · 11/14 100k | 14/14 126k · 14/14 30k · 13/14 228k |
| fmt, comprobación en compilación | 16/16 217k · 16/16 255k · 15/16 259k | 14/16 163k · 14/16 113k · 14/16 259k |
| Rails `update_counters`, impacto | 10/10 121k · 10/10 59k · 10/10 106k | 10/10 71k · 9/10 37k · 9/10 247k |
| Rails `find_or_create_by`, flujo | 16/16 85k · 16/16 61k · 16/16 132k | 7/16 72k · 8/16 43k · 4/16 221k |
| Flask `ensure_sync`, impacto | 16/16 83k · 16/16 90k · 16/16 100k | 16/16 80k · **1/16 29k** · 16/16 83k |
| Flask `from_prefixed_env`, flujo | 14/14 82k · 14/14 61k · 14/14 97k | 14/14 44k · 14/14 38k · 14/14 100k |

## Los dos fallos de Graphtyn

- **«ensure_sync en Flask»:** `Flask` es una clase del repositorio, así que se tomó como
  símbolo pedido. La búsqueda de usos devolvió 505 referencias, casi todas de `Flask`, y el
  grafo solo resolvió 1 consumidor de `ensure_sync`, porque no enlaza las llamadas
  `self.ensure_sync(...)`. Codex se quedó con el paquete y listó líneas sin nombrar las
  funciones. Es la misma familia de fallo que «Active Record», cuando `record` se tomaba como
  símbolo.
- **«processMultibulkBuffer», falsa completitud:** el cuerpo tiene 230 líneas, y el paquete
  dio un extracto de 1.155 caracteres con partes omitidas, pero marcó
  `do_not_expand=true`. Faltaban 4 de los 8 hechos. Codex se fía de esa señal y para; Claude
  leyó más y llegó a 8/8.

Sin esas dos tareas, como diagnóstico posterior y no como resultado: Codex sin grafo 75/86 a
96.693 tokens, Graphtyn 75/86 a 48.377 y Graphify 70/86 a 203.656. No se corrigieron ni se
repitieron: hacerlo sobre estas tareas convertiría la prueba en ajuste.

## Límites

- **Pocas repeticiones:** n=2 por celda, en 8 tareas.
- **Rúbricas mías:** las escribí yo; los jueces son modelos y pueden compartir sesgos.
- **Coste:** solo Claude informa el coste; en Codex se comparan tokens.
- **Claude a veces gasta más con Graphtyn:** en tres tareas (las de flujo de fmt y Redis, y
  `ensure_sync` de Flask), Graphtyn gastó más que la versión sin grafo, porque Claude leyó el
  código igualmente.
- **Sesiones repetidas:** 4 sesiones de Claude las rechazó o cortó el límite de uso. Se
  guardaron aparte (`claude-refused/`, 52.913 tokens) y se repitieron con el mismo código.
- **Topes de tokens en Codex:** el tope que fijé era bajo, y un error de mi script hizo que
  algunas celdas arrancaran sin actualizar el total, así que 5 celdas se cortaron tras su
  primer brazo. Los 18 brazos que faltaban, entre los dos clientes, se ejecutaron después uno
  por uno, con lo que en esas celdas no se mantuvo el orden alternado.
- **Graphify sin capa semántica:** su grafo es solo de código y sin LLM, igual que el 26 de
  octubre. Su capa semántica sobre documentación necesitaría un proveedor configurado.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/graphify_head_to_head_2026-11-06 \
  --run-root <ejecuciones> --variant claude --variant codex
python benchmarks/graphify_head_to_head_2026-11-06/analyze.py --run-root <ejecuciones>
```

`runs.json`, `results.json` y `judge_grades.json` guardan los datos por sesión. Las sesiones
crudas no están en el repositorio porque incluyen copias de los corpus.
