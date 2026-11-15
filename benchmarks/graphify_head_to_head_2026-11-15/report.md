# Sin grafo, Graphtyn y Graphify con la 0.13: repositorios y tareas nuevos

Fecha: 2026-11-15. 144 sesiones completas: 8 tareas × 3 brazos × 2 clientes × 3 repeticiones.
Unos 16,9 millones de tokens.

**Veredicto: NEGATIVE en calidad para Graphtyn; POSITIVE en tokens.**

- **Tokens:** Graphtyn es el brazo que menos gasta con los dos clientes.
- **Calidad con Claude Code:** Graphtyn queda un poco por debajo de no usar grafo y de Graphify.
- **Calidad con Codex:** Graphtyn pierde mucho, con 90 de 162 hechos frente a 136–137 de los otros
  dos brazos.
- **Causa:** casi toda la pérdida sale de dos fallos de recuperación, descritos abajo. Codex se fía
  del paquete y deja de buscar.
- **Graphify:** con los dos clientes gastó más que no usar ningún grafo, sin ganar calidad. Es lo
  mismo que en las mediciones del 26 de octubre y del 6 de noviembre.

## Diseño

- **Repositorios públicos nuevos en commits fijos:**
  - [pallets/click](https://github.com/pallets/click) `e38188e9` (Python);
  - [gin-gonic/gin](https://github.com/gin-gonic/gin) `0f09c3a9` (Go);
  - [koajs/koa](https://github.com/koajs/koa) `7c6bfe77` (JavaScript);
  - [jhy/jsoup](https://github.com/jhy/jsoup) `d90d5752` (Java).
- **Independencia:** ninguno de los cuatro está en el gate de recuperación ni se usó nunca para
  ajustar Graphtyn.
- **Tareas:** 8 nuevas, una de impacto y una de flujo por repositorio, con 54 hechos.
  - Las rúbricas se escribieron leyendo el código, sin usar Graphtyn ni Graphify.
  - Se congelaron en git antes de ejecutar (commit `7e3589e`).
- **Brazos:**
  - **Sin grafo:** búsqueda y lectura normales.
  - **Graphtyn:** `main` en `f566ac4` (0.13.1 más #64–#66, que no tocan la recuperación), MCP lean y
    regla de parada `targeted`.
  - **Graphify:** 0.9.106 con `graphifyy[mcp]`, su `graphify-mcp` oficial y un grafo de solo código
    construido sin LLM (`GRAPHIFY_BACKEND=none`) fuera del tiempo medido. Es la versión más reciente
    con al menos 5 días publicada; la 0.9.109 salió el día anterior.
- **Aislamiento:**
  - **Graphify:** en `~/.cache/graphtyn-bench/graphify-0.9.106`, fuera del repositorio, sin skill,
    hook ni instrucciones, y nunca registrado como `graphtyn`.
  - **Sesiones:** cada una usa una copia del repositorio y un `GRAPHTYN_HOME` propio.
  - **Tamaño de los grafos:** parecido en las dos herramientas. Por ejemplo, en jsoup Graphify tiene
    6.031 nodos y Graphtyn 6.960.
- **Clientes:** Claude Code 2.1.325 con `claude-sonnet-5-5`, y Codex 0.153.2 con `gpt-5.6-luna` y
  `--ignore-user-config`. El orden de los brazos se alterna entre repeticiones.
- **Calificación:** tres jueces sin herramientas ni acceso al código: Gemini, GPT y Claude como
  desempate.
  - **Medida principal:** la mayoría de tres, la regla calibrada contra las notas del mantenedor
    (kappa 0,95 y ningún hecho dado por bueno de más; `benchmarks/judge_calibration_2026-11-08`).
  - **Medidas secundarias:** el consenso de Gemini y GPT, y la rúbrica literal. El consenso da casi
    lo mismo (±1 hecho por brazo).
  - **Acuerdo entre jueces:** kappa 0,915.

## Resultado

Hechos por mayoría de jueces. Las medias son por sesión. En Claude, los tokens incluyen lecturas y
escrituras de caché, y el coste es el que informa el cliente.

| Cliente | Brazo | Hechos | Tokens: media | Tokens: mediana | Coste USD | Herramientas |
|---|---|---:|---:|---:|---:|---:|
| Claude | Sin grafo | **155/162 (96 %)** | 110.610 | 102.232 | **0,066** | 2,9 |
| Claude | Graphtyn | 146/157 (93 %) | **102.021** | **93.121** | 0,074 | 2,5 |
| Claude | Graphify | 150/162 (93 %) | 124.032 | 103.380 | 0,080 | 3,6 |
| Codex | Sin grafo | **137/162 (85 %)** | 119.200 | 99.213 | — | 5,0 |
| Codex | Graphtyn | 90/162 (56 %) | **41.882** | **30.999** | — | 1,6 |
| Codex | Graphify | 136/162 (84 %) | 204.320 | 176.603 | — | 6,5 |

Para Claude con Graphtyn se califican 23 de 24 sesiones. En la que falta (impacto de `make_context`,
repetición 3), el juez Gemini no devolvió un veredicto válido en tres intentos. La respuesta es
válida y queda guardada con las demás.

Por parejas (misma tarea y repetición):

| Cliente | Comparación | Gasta menos en | Cambio mediano de tokens | Hechos |
|---|---|---:|---:|---|
| Claude | Graphtyn frente a Graphify | 21 de 24 | −29,7 % | 146 frente a 150 |
| Claude | Graphtyn frente a sin grafo | 16 de 24 | −27,4 % | 146 frente a 155 |
| Claude | Graphify frente a sin grafo | 6 de 24 | +18,4 % | 150 frente a 155 |
| Codex | Graphtyn frente a Graphify | 24 de 24 | −79,8 % | 90 frente a 136 |
| Codex | Graphtyn frente a sin grafo | 24 de 24 | −66,3 % | 90 frente a 137 |
| Codex | Graphify frente a sin grafo | 3 de 24 | +60,3 % | 136 frente a 137 |

Con Claude, Graphtyn gasta menos tokens pero el coste medio informado es mayor que sin grafo (0,074
frente a 0,066 USD). Parte de sus tokens son escrituras de caché, que cuestan más que las lecturas.

## Por tarea

Hechos sumados de las tres repeticiones.

| Tarea | Claude: sin grafo / Graphtyn / Graphify | Codex: sin grafo / Graphtyn / Graphify |
|---|---|---|
| click `make_context`, impacto | 15/15 · 10/10 · 15/15 | 15/15 · 10/15 · 14/15 |
| click, argumentos hasta el callback, flujo | 18/24 · **22/24** · 14/24 | 9/24 · 6/24 · 8/24 |
| gin `Context.Next`, impacto | 17/18 · 15/18 · 16/18 | 16/18 · 13/18 · 15/18 |
| gin, petición desde `ServeHTTP`, flujo | 24/24 · 24/24 · 24/24 | 22/24 · 22/24 · 24/24 |
| koa `ctx.onerror`, impacto | 15/15 · **9/15** · 15/15 | 12/15 · 5/15 · 12/15 |
| koa, petición desde `callback()`, flujo | 27/27 · 27/27 · 27/27 | 27/27 · 18/27 · 27/27 |
| jsoup `Element.select`, impacto | 15/15 · 15/15 · 15/15 | 15/15 · **0/15** · 15/15 |
| jsoup, `Jsoup.parse`, flujo | 24/24 · 24/24 · 24/24 | 21/24 · 16/24 · 21/24 |

## Los fallos de Graphtyn

1. **Los tests desplazan a los consumidores de producción.**
   - En jsoup `Element.select`, el paquete se llenó con métodos de `CompiledQueryTest`, `CssTest`,
     `HasEvaluatorTest` y `QueryCompatTest`, porque los tests llaman a `select` cientos de veces.
     Ninguno de los cinco consumidores de producción (`DataUtil.detectCharset`,
     `FormElement.formData`, `uniqueIdSelector`, `cssSelectorComponent` y los ejemplos) entró en el
     presupuesto.
   - Codex dio esa lista como respuesta en las tres repeticiones (0/15). Claude leyó el código y
     llegó a 15/15.
   - En una repetición del flujo de Koa ocurrió lo mismo: Codex trazó la petición a partir de tests
     (`__tests__/application/*.test.js`) y obtuvo 0/9 en esa sesión.
2. **Completitud falsa con un receptor sin tipo.**
   - En Koa, las llamadas `ctx.onerror(err)` usan un parámetro `ctx` sin tipo. El grafo no las
     resolvió y las dejó como 11 referencias de texto («`indexed: 0`»).
   - Aun así, el paquete se declaró completo (`missing=[]`, `do_not_expand=true`). Faltaron
     `handleRequest`, con su `.catch(onerror)`, y el callback de `Stream.pipeline` en `respond`.
   - Claude se fió en 2 de las 3 repeticiones (9/15); Codex, en las tres (5/15).
   - Es la misma familia de fallo que «processMultibulkBuffer» en la comparación del 6 de
     noviembre.
3. **Acoplamiento por estado compartido.** En gin, ninguna respuesta de Graphtyn mencionó que
   `Abort` y `IsAborted` dependen de que `Next` use el campo `index` (`abortIndex`). Con Claude, los
   otros dos brazos lo nombraron en las tres sesiones. Con Codex casi nadie lo hizo: 1 de 3 sin grafo
   y 0 de 3 con Graphify.
4. **Click, flujo de argumentos:** con Codex, Graphtyn obtuvo 6/24. El paquete llegó hasta
   `make_context` y `invoke`, y omitió `parse_args` y el procesado de parámetros.

No se corrigieron ni se repitieron sobre estas tareas: hacerlo convertiría la prueba en ajuste. La
validación de cualquier corrección tiene que hacerse con tareas nuevas.

## Comparación con la medición del 6 de noviembre

En aquella prueba, con redis, fmt, rails y flask, Graphtyn ganó en calidad con Claude: 118/118
frente a 116 sin grafo y 114 con Graphify. Aquí no. Las dos coinciden en lo demás:
- Graphtyn es el más barato en tokens.
- Graphify gasta más que no usar grafo.
- Con Codex, la calidad de Graphtyn depende de que el paquete no se declare completo cuando no lo
  está.

Con repositorios y tareas nuevos, el resultado favorable de Claude no se sostiene. Eso indica que
parte de aquella ventaja venía del tipo de repositorio o de tarea.

## Límites

- **Muestra pequeña:** n=3 por celda, en 8 tareas y 4 repositorios.
- **Rúbricas mías:** las escribí yo; los jueces son modelos y pueden compartir sesgos.
- **Claude como desempate:** también es uno de los clientes evaluados. Solo decide los hechos en
  los que Gemini y GPT discrepan, y el consenso sin él da casi lo mismo.
- **Coste:** solo Claude informa el coste; en Codex se comparan tokens.
- **Sesiones repetidas:** 5 celdas de Claude, de la repetición 3, chocaron con el límite de uso de
  la cuenta. Se apartaron (`claude-refused/`) y se repitieron con el mismo código y la misma
  configuración.
- **Graphify sin capa semántica:** su grafo es solo de código y sin LLM, como en las mediciones
  anteriores.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/graphify_head_to_head_2026-11-15 \
  --run-root <ejecuciones> --variant claude --variant codex --tiebreak --repos <repositorios>
python benchmarks/graphify_head_to_head_2026-11-15/analyze.py --run-root <ejecuciones>
```

`runs.json`, `results.json`, `judge_grades.json` y `judge_cache.json` guardan los datos por sesión.
Las sesiones crudas no están en el repositorio porque incluyen copias de los corpus.
