# Validación de la corrección de paquetes de impacto con tareas y repositorios nuevos

Fecha: 2026-11-15. 72 sesiones con Codex: 8 tareas × 3 brazos × 3 repeticiones, unos 3,9 millones
de tokens.

**Veredicto: POSITIVE en calidad, NEGATIVE en tokens frente a antes del arreglo.**

- **Calidad:** con el arreglo, Graphtyn pasa de 102 a 112 hechos de 117. Sin grafo se llega a 115.
- **Tokens:** la mediana sube de 31k a 47k tokens por sesión. Sigue un 29 % por debajo de no usar
  grafo (68k).
- **De dónde sale la mejora:** de dos sitios.
  - En parte, de paquetes mejores: los tests ya no ocupan las filas de consumidores.
  - En parte, de que el paquete ya no se declara completo y Codex lee las líneas indicadas. Eso
    explica la subida de tokens.

## Diseño

- **Corrección evaluada:** rama `fix/impact-test-crowding` (commit `7ae4c27`).
  - Los usos desde tests se cuentan por archivo en `test_consumers` y no ocupan las filas de
    consumidores.
  - Un paquete con usos textuales de producción devuelve `missing=["verify_text_references"]` en vez
    de `do_not_expand=true`.
  - El escáner de usos atribuye cada uso al símbolo más interno que contiene la línea y descarta
    rutas de paquete, comentarios de bloque y nombres entre comillas.
- **Diagnóstico:** el fallo se vio en jsoup y koa en la comparación del mismo día
  (`benchmarks/graphify_head_to_head_2026-11-15`). La corrección se escribió con tests sintéticos y se
  comprobó en esos dos paquetes. No se repitieron aquellas tareas.
- **Repositorios públicos nuevos en commits fijos:**
  - [psf/requests](https://github.com/psf/requests) `3c7baaa0` (Python);
  - [axios/axios](https://github.com/axios/axios) `85ffbafa` (JavaScript);
  - [apache/commons-lang](https://github.com/apache/commons-lang) `8fb59087` (Java);
  - [labstack/echo](https://github.com/labstack/echo) `f275a6b1` (Go).
- **Independencia:** ninguno de los cuatro se había usado en benchmarks, en el gate ni para ajustar
  Graphtyn.
- **Tareas:** 8 de impacto, dos por repositorio, con 39 hechos.
  - Cada objetivo tiene entre 2 y 6 consumidores de producción.
  - Las rúbricas se escribieron leyendo el código, sin Graphtyn, y se congelaron en git (commit
    `077f91f`) antes de escribir el commit del arreglo y de ejecutar.
- **Brazos:**
  - **Sin grafo:** búsqueda y lectura normales.
  - **Antes:** Graphtyn `f566ac4`, el binario de la comparación del 15-11. `main` (`2ce9146`) no
    cambia la recuperación.
  - **Después:** la rama del arreglo, instalada desde un archivo congelado del commit `7ae4c27`.
  - En los dos brazos de Graphtyn: MCP lean y regla de parada `targeted`.
- **Cliente:** Codex 0.153.2 con `gpt-5.6-luna` y `--ignore-user-config`. El orden de los brazos
  «sin grafo» y «antes» se alterna entre repeticiones; «después» se ejecuta justo a continuación.
- **Calificación:** tres jueces sin herramientas por hecho: Gemini, GPT y Claude como desempate.
  - **Medida principal:** la mayoría de tres.
  - **Acuerdo entre jueces:** kappa 0,841.

## Resultado

| Brazo | Hechos | Tokens: mediana | Tokens: media |
|---|---:|---:|---:|
| Sin grafo | **115/117 (98 %)** | 68.384 | 76.151 |
| Graphtyn antes | 102/117 (87 %) | **31.044** | **33.890** |
| Graphtyn después | 112/117 (96 %) | 46.626 | 51.772 |

Por parejas (misma tarea y repetición):

| Comparación | Gasta menos en | Cambio mediano de tokens | Hechos | Sesiones mejor / peor |
|---|---:|---:|---|---|
| Después frente a antes | 5 de 24 | +46,0 % | 112 frente a 102 | 9 / 2 |
| Después frente a sin grafo | 18 de 24 | −28,7 % | 112 frente a 115 | 2 / 5 |
| Antes frente a sin grafo | 23 de 24 | −53,1 % | 102 frente a 115 | 2 / 11 |

## Por tarea

Hechos sumados de las tres repeticiones y mediana de tokens.

| Tarea | Sin grafo | Antes | Después |
|---|---|---|---|
| axios `mergeConfig` | 18/18 · 81k | 17/18 · 31k | 18/18 · 59k |
| axios `settle` | 15/15 · 53k | **9/15** · 30k | 14/15 · 54k |
| echo `Context.NoContent` | 15/15 · 95k | **11/15** · 33k | 15/15 · 63k |
| echo `Context.Redirect` | 15/15 · 69k | 12/15 · 31k | 13/15 · 45k |
| commons-lang `getShortClassName` | 12/12 · 106k | 12/12 · 41k | 11/12 · 40k |
| commons-lang `identityToString` | 15/15 · 93k | 15/15 · 41k | 15/15 · 40k |
| requests `get_auth_from_url` | 14/15 · 54k | 14/15 · 29k | 15/15 · 58k |
| requests `super_len` | 11/12 · 62k | 12/12 · 30k | 11/12 · 42k |

## Qué cambió en los paquetes

- **axios `settle`:**
  - **Antes:** el paquete se declaraba completo y mezclaba 17 filas de test entre los consumidores.
    Codex nombró los adaptadores, pero no qué hacen con `settle`: el `data:` URI con 405 y 200, y la
    respuesta en stream o en búfer. Le faltaron esos dos hechos en las tres repeticiones.
  - **Después:** los tests quedan contados por archivo. El paquete pidió verificar tres
    `text_references`, Codex leyó esos rangos de `http.js` y obtuvo 14/15.
  - **Pero:** esas tres filas eran las líneas `import settle`, no usos. La mejora vino de que Codex
    leyera, no de que el paquete contuviera más.
- **echo `Context.NoContent`:** antes faltaba `optionsMethodHandler` en las tres repeticiones; después
  aparece siempre.
- **commons-lang y requests `super_len`:** el resultado no cambia. Estos paquetes ya eran correctos
  antes.

## Lo que queda por corregir

Se observó en estas sesiones y no se corrigió para no ajustar Graphtyn a estas tareas.

1. **Las importaciones activan la verificación sin necesidad.**
   - `import settle from '../core/settle.js'` y los nombres dentro de `from .utils import (...)`
     cuentan como usos textuales de producción.
   - Eso retira la completitud de paquetes que ya eran completos, como requests
     `get_auth_from_url`, y explica parte de la subida de tokens.
2. **El nombre del repositorio se toma como símbolo.**
   - En echo, la palabra «echo» de la petición añade el struct `Echo` como objetivo.
   - `text_references` se llena de métodos `(e *Echo)` sin relación.
3. **Métodos homónimos sin su receptor.**
   - `ToMiddleware slash.go:138` no dice que es `RemoveTrailingSlashConfig`.
   - Codex omitió `RemoveTrailingSlash` en 2 de 3 sesiones (antes, en 3 de 3).

Tras la ejecución se corrigió un error de la propia rama: las menciones en documentos (filas sin
ruta) se contaban como tests en `test_consumers`. No afecta a ningún hecho de la rúbrica.

## Límites

- **Muestra pequeña:** n=3 por celda, en 8 tareas de impacto y 4 repositorios. No incluye tareas de
  flujo, que el arreglo no toca.
- **Solo Codex:** el arreglo no se midió con Claude Code.
- **Rúbricas mías:** las escribí yo, y los jueces son modelos.
- **Orden de los brazos:** el brazo «después» se ejecutó siempre tras los otros dos, no alternado.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/impact_fix_validation_2026-11-15 \
  --run-root <ejecuciones> --variant codex/before --variant codex/after --tiebreak --repos <repositorios>
python benchmarks/impact_fix_validation_2026-11-15/analyze.py
```

`judge_grades.json` y `judge_cache.json` guardan las notas por sesión.
