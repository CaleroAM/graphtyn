# Validación de la reducción de tokens en paquetes de impacto

Fecha: 2026-11-16. 72 sesiones con Codex: 8 tareas × 3 brazos × 3 repeticiones. En total, 3.628.447
tokens.

**Veredicto: NO cumple el criterio preregistrado.**

- **Tokens:** cumple. La mediana baja un 32 % frente al arreglo (de 43k a 29k) y es menor que el
  límite de 36k.
- **Calidad:** no cumple. Saca 99/108 hechos, frente a 105/108 del arreglo y 103/108 sin grafo.
  Pierde 4 hechos en httpx `peek_filelike_length` y 2 en javapoet `characterLiteralWithoutSingleQuotes`.

## Diseño

- **Rama evaluada:** `c213b37`, sobre `fix/impact-test-crowding`, con las propuestas 1 a 8 del
  análisis de Fable:
  - las importaciones no cuentan como usos;
  - cada fila lleva la sentencia completa y la condición que la contiene;
  - los usos textuales cuyo propio código es concluyente quedan resueltos, y solo se piden
    `verify_lines` para los dudosos;
  - un símbolo calificado es la única ancla;
  - una llamada asignada a un archivo se atribuye a la función que la hace;
  - las filas indican el receptor.
- **Comparación:** brazo sin grafo y Graphtyn `7ae4c27`, el arreglo del PR #68.
- **Repositorios nuevos en commit fijo:**
  - [encode/httpx](https://github.com/encode/httpx) `7cff5f79` (Python);
  - [fastify/fastify](https://github.com/fastify/fastify) `46797238` (JavaScript);
  - [square/javapoet](https://github.com/square/javapoet) `b9017a95` (Java);
  - [spf13/viper](https://github.com/spf13/viper) `528f7416` (Go).
- **Sustitución:** caffeine se descartó antes de ejecutar porque su `AGENTS.md` obliga al agente a
  leer `.claude/`.
- **Rúbricas:** 36 hechos, escritos con grep sin Graphtyn y congelados en `5f21171` antes del commit
  de implementación.
- **Cliente:** Codex `gpt-5.6-luna`. El orden de los tres brazos rota en cada repetición.
- **Calificación:** mayoría de tres jueces (Gemini, GPT y Claude como desempate). Kappa entre jueces:
  0,79.
- **Criterio fijado antes de ejecutar:**
  - hechos ≥ los de `7ae4c27`;
  - mediana ≤ 36k;
  - ninguna tarea más de un hecho por debajo de `7ae4c27`.

## Resultado

| Brazo | Hechos | Tokens: mediana | Tokens: media |
|---|---:|---:|---:|
| Sin grafo | 103/108 | 62.498 | 62.323 |
| Graphtyn `7ae4c27` (PR #68) | **105/108** | 43.363 | 52.468 |
| Graphtyn `c213b37` | 99/108 | **29.512** | **36.394** |

Por parejas (misma tarea y repetición):

| Comparación | Gasta menos en | Cambio mediano de tokens | Sesiones mejor / peor |
|---|---:|---:|---|
| `c213b37` frente a `7ae4c27` | 18 de 24 | −28,4 % | 0 / 5 |
| `c213b37` frente a sin grafo | 21 de 24 | −47,4 % | 2 / 3 |
| `7ae4c27` frente a sin grafo | 15 de 24 | −13,1 % | — |

| Tarea | Sin grafo | `7ae4c27` | `c213b37` |
|---|---|---|---|
| fastify `buildErrorHandler` | 12/12 · 63k | 12/12 · 63k | 12/12 · 45k |
| fastify `createChildLogger` | 15/15 · 63k | 15/15 · 63k | 15/15 · 44k |
| httpx `peek_filelike_length` | 12/12 · 62k | 10/12 · 68k | **6/12** · 29k |
| httpx `primitive_value_to_str` | 15/15 · 109k | 15/15 · 43k | 15/15 · 29k |
| javapoet `characterLiteralWithoutSingleQuotes` | 8/12 · 44k | 11/12 · 56k | 9/12 · 30k |
| javapoet `emitModifiers` | 15/15 · 26k | 15/15 · 43k | 15/15 · 43k |
| viper `getConfigType` | 15/15 · 64k | 15/15 · 29k | 15/15 · 29k |
| viper `mergeWithEnvPrefix` | 11/12 · 68k | 12/12 · 29k | 12/12 · 29k |

## Por qué pierde hechos

Los hechos perdidos no son consumidores. Son lo que el consumidor hace con el resultado, cuando eso
está en las líneas siguientes a la llamada.

- **httpx `peek_filelike_length`:** la fila trae
  `content_length_or_none = peek_filelike_length(content)` y su condición. El
  `if content_length_or_none is None: headers = {"Transfer-Encoding": "chunked"}` está en la línea
  siguiente. Lo mismo ocurre con `MultipartStream.get_content_length`, que devuelve `None` en cuanto
  un campo lo hace. El paquete se declara completo y Codex responde sin leer, con 29k tokens. Con
  `7ae4c27`, Codex leyó esas líneas en 2 de 3 sesiones, con 68k tokens.
- **javapoet `$S`:** `CodeWriter.emit` llega al objetivo a través de `stringLiteralWithDoubleQuotes`.
  Es un consumidor indirecto, y el paquete no dice para qué sirve.

Ninguna tarea perdió consumidores directos: los 8 objetivos tienen todos sus consumidores en las 24
sesiones de `c213b37`.

## Límites

- **Muestra:** n=3 por celda, en 8 tareas de impacto.
- **Cliente y rúbricas:** solo Codex, y las rúbricas son mías.
- **Datos ya vistos:** estas tareas ya se han ejecutado y analizado. Una corrección basada en este
  fallo (añadir el uso del resultado asignado) necesita otra validación con tareas nuevas.

## Reproducir

```bash
bash <ejecuciones>/lane.sh codex gpt-5.6-luna 5500000
python benchmarks/judge_grades.py --tasks-root benchmarks/impact_tokens_validation_2026-11-16 \
  --run-root <ejecuciones> --variant codex/fix --variant codex/tokens --tiebreak --repos <repositorios>
python benchmarks/impact_tokens_validation_2026-11-16/analyze.py
```
