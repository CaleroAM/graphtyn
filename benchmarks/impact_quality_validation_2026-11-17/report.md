# Validación de calidad con pocos tokens en paquetes de impacto

Fecha: 2026-11-17. 72 sesiones con Codex: 8 tareas × 3 brazos × 3 repeticiones. En total, 2.357.469
tokens.

**Veredicto: NO cumple el criterio preregistrado, por una tarea.**

- **Hechos:** cumple. `a41fcb6` saca 64/120, frente a 57–58/120 de `main` y 53/120 de `c213b37`.
- **Tokens:** cumple. La mediana de `a41fcb6` es 28,3k, frente a 33,9k de `main`.
- **Ninguna tarea más de un hecho por debajo de `main`:** no cumple. En winston
  `ExceptionHandler.getAllInfo`, `a41fcb6` saca 5/12 y `main` 8/12.

## Diseño

- **Brazos:**
  - `main` en `7ab006a`, con el PR #68 fusionado;
  - `c213b37`, la versión que recortaba tokens;
  - `a41fcb6`, en la rama `exp/impact-quality-lowtoken`: `c213b37` más el trabajo offline de Fable
    (sigue el resultado asignado, incluye la sentencia que abre la llamada, indexa CommonJS y
    `.mjs/.cjs`, y descarta como objetivos las palabras de la ruta).
- **No hay brazo sin grafo:** esta validación compara versiones de Graphtyn entre sí.
- **Repositorios nuevos en commit fijo:**
  - [winstonjs/winston](https://github.com/winstonjs/winston) `ff0b79de` (JavaScript CommonJS);
  - [marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow) `777ff660`
    (Python);
  - [Seldaek/monolog](https://github.com/Seldaek/monolog) `09b95283` (PHP, peticiones
    `Clase::metodo`);
  - [sirupsen/logrus](https://github.com/sirupsen/logrus) `6ef0748d` (Go).
- **Sustitución:** nodemailer se descartó antes de escribir tareas porque ya no es CommonJS.
- **Rúbricas:**
  - 40 hechos, escritos con grep sin Graphtyn y sin ver paquetes de ninguna rama;
  - congelados en `358350e` antes de la primera sesión;
  - incluyen qué hace cada consumidor con el resultado y los consumidores indirectos.
- **Cliente:** Codex `gpt-5.6-luna`. El orden de los tres brazos rota en cada repetición.
- **Calificación:** mayoría de tres jueces (Gemini, GPT y Claude como desempate). Kappa entre jueces:
  0,88.
- **Una sesión con un juez distinto:** Gemini agotó el tiempo cinco veces seguidas en la respuesta
  de `main` r1 de marshmallow `callable_or_raise`, incluso con 300 s. Esa sesión se calificó con GPT
  y Claude, que discrepan en un hecho, y por eso `main` aparece como 57–58.

## Resultado

| Brazo | Hechos | Tokens: mediana | Tokens: media |
|---|---:|---:|---:|
| Graphtyn `main` (PR #68) | 57–58/120 | 33.934 | 38.758 |
| Graphtyn `c213b37` | 53/120 | 28.231 | 30.994 |
| Graphtyn `a41fcb6` | **64/120** | **28.256** | **28.476** |

Por parejas (misma tarea y repetición; `main` sin la sesión calificada aparte):

| Comparación | Gasta menos en | Cambio mediano de tokens | Sesiones mejor / peor |
|---|---:|---:|---|
| `a41fcb6` frente a `main` | 16 de 23 | −1,4 % | 7 / 3 |
| `a41fcb6` frente a `c213b37` | 10 de 24 | 0,0 % | 9 / 2 |
| `c213b37` frente a `main` | 12 de 23 | −0,2 % | 1 / 3 |

| Tarea | `main` | `c213b37` | `a41fcb6` |
|---|---|---|---|
| logrus `getPackageName` | 4/9 · 28k | 3/9 · 28k | 6/9 · 28k |
| logrus `prefixFieldClashes` | 6/15 · 30k | 6/15 · 30k | 7/15 · 30k |
| marshmallow `callable_or_raise` | 7–8/18 · 38k | 7/18 · 27k | 8/18 · 28k |
| marshmallow `is_aware` | 6/18 · 38k | 6/18 · 28k | 6/18 · 28k |
| monolog `Utils::canonicalizePath` | 6/15 · 41k | 7/15 · 53k | 6/15 · 29k |
| monolog `Utils::unwrapFormatter` | 15/15 · 29k | 15/15 · 30k | 14/15 · 29k |
| winston `ExceptionHandler.getAllInfo` | **8/12** · 78k | 4/12 · 28k | **5/12** · 28k |
| winston `getLevelValue` | 5/18 · 28k | 5/18 · 28k | **12/18** · 28k |

## Qué falla

**Winston `getAllInfo`.** `main` leyó código (78k de mediana) y encontró
`this.logger.log(info)` en `exception-handler.js:220`. El paquete de `a41fcb6` trae
`const info = this.getAllInfo(err);` sin el uso posterior y se declara completo, así que Codex no lee.
La búsqueda de usos lejanos se detiene en la siguiente definición, y entre las dos líneas hay una
función anidada (`function gracefulExit()`). Además, el paquete cita como usos textuales las
declaraciones de `index.d.ts`, incluida la de `RejectionHandler`, otra clase.

**Todos los brazos dejan fuera la mitad de los hechos.** Los tres responden sin leer (unos 28k
tokens) porque el paquete dice `do_not_expand: true`.

- **marshmallow `is_aware`:** el paquete no incluye `AwareDateTime._deserialize`
  (`fields.py:1409`, `if not utils.is_aware(ret):`), que es un consumidor directo, y ninguna sesión
  lo nombra. De `NaiveDateTime` solo trae la primera línea de la rama, sin el `raise` ni la
  conversión.
- **Efectos lejanos:** los hechos que dependen de lo que el consumidor hace con un campo en otro
  método se pierden en todos los brazos:
  - marshmallow guarda el callable y lo invoca en `_serialize`;
  - monolog abre `$this->url` en `write` y usa `$this->filename` para rotar;
  - logrus, en `DataKey`, recoge las claves después de la llamada.

No hay brazo sin grafo, así que esta validación no dice cuántos de esos hechos encontraría Codex
leyendo por su cuenta. En la validación del 2026-11-16, sin grafo sacó 103/108.

## Límites

- **Muestra:** n=3 por celda, en 8 tareas de impacto.
- **Cliente y rúbricas:** solo Codex, y las rúbricas son mías.
- **Datos ya vistos:** las correcciones que sugieren estos fallos necesitan otra validación con
  tareas nuevas.

## Reproducir

```bash
bash <ejecuciones>/lane.sh codex gpt-5.6-luna 4500000
python benchmarks/judge_grades.py --tasks-root benchmarks/impact_quality_validation_2026-11-17 \
  --run-root <ejecuciones> --variant codex/main --variant codex/tokens --variant codex/final \
  --tiebreak --repos <repositorios>
python benchmarks/impact_quality_validation_2026-11-17/analyze.py
```
