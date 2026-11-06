# Llamadas sobre `self` a métodos heredados: validación

Fecha: 2026-11-06. 16 sesiones de Codex: 4 tareas nuevas × 2 versiones de Graphtyn × 2
repeticiones. Unos 440.000 tokens.

**Veredicto: NEUTRAL en las respuestas; POSITIVE en el grafo.**

- **Respuestas:** la rama corregida acertó 32/52 hechos y `main` 29/52. Por parejas gana en 2,
  pierde en 2 y gasta un 1,8 % más de tokens. No hay mejora medible.
- **Consumidores directos:** las dos versiones nombraron todos los consumidores directos.
  `main` ya los daba en el paquete como referencias de texto sin verificar.
- **Grafo:** la corrección los convierte en relaciones `EXTRACTED`, con el método consumidor
  como entidad del paquete. Eso no cambió lo que respondió Codex en estas tareas.

## Diseño

- **Corrección medida** (rama `fix/inherited-self-calls`, `9d01d55`):
  - las clases de Python registran sus bases; antes el grafo no tenía ninguna relación
    `hereda` en Python, porque el parser no leía el campo `superclasses`;
  - lo mismo en TypeScript y JavaScript, cuyo `extends` está en `class_heritage`;
  - una llamada sobre `self`, `cls`, `this` o `$this` busca el método en la propia clase y
    luego en sus bases, de la más cercana a la más lejana;
  - `super()` y `super(Clase, self)` se saltan la propia clase.
- **Versiones comparadas:** `main` (`1192669`) y la rama corregida, cada una desde un worktree
  congelado. MCP lean y regla de parada `targeted`.
- **Tareas:** 4 de impacto en Flask (pallets/flask `d086db85`), con 26 hechos, escritas leyendo
  el código y congeladas en `f142e58` antes de ejecutar. En todas, el consumidor llama con
  `self` a un método que su clase hereda:
  - `get_cookie_name` y `should_set_cookie`, de `SessionInterface`, llamados desde
    `SecureCookieSessionInterface`;
  - `_get_exc_class_and_code`, de `Scaffold`, llamado desde `App`;
  - `inject_url_defaults`, de `App`, llamado desde `Flask`.
- **Cliente:** Codex 0.153.2 con `gpt-5.6-luna` y `--ignore-user-config`. Cada sesión usa una
  copia del repositorio y un `GRAPHTYN_HOME` propio. El orden de las versiones se alterna entre
  repeticiones.
- **Calificación:** dos jueces de modelos distintos (Gemini y GPT), sin herramientas; cuenta un
  hecho solo si coinciden. Kappa entre jueces: 0,90.

## Resultado

| Versión | Hechos (jueces) | Tokens: media | Tokens: mediana | Herramientas |
|---|---:|---:|---:|---:|
| `main` | 29/52 (56 %) | 27.146 | 27.086 | 1,0 |
| Corregida | 32/52 (62 %) | 27.650 | 27.558 | 1,0 |

| Tarea | `main` | Corregida | Consumidores en el paquete: `main` / corregida |
|---|---:|---:|---|
| `get_cookie_name` | 8/14 | 14/14 | 2 como texto / 2 enlazados |
| `_get_exc_class_and_code` | 7/14 | 6/14 | 1 enlazado y 1 como texto / 2 enlazados |
| `inject_url_defaults` | 7/10 | 5/10 | 2 como texto / 1 enlazado y 1 como texto |
| `should_set_cookie` | 7/14 | 7/14 | 1 como texto / 1 enlazado |

- **`get_cookie_name`:** es la única tarea con una diferencia clara. Con `save_session` como
  entidad del paquete, la versión corregida explicó que el nombre se usa tanto para borrar como
  para poner la cookie (`delete_cookie`, `set_cookie`). `main` no lo explicó en ninguna de las
  dos repeticiones.
- **Resto de tareas:** las diferencias son de 1 o 2 hechos en ambos sentidos, del mismo
  tamaño que la variación entre sesiones medida en la validación anterior.

## Límites

- **Rúbrica mal ajustada a la pregunta:** en `_get_exc_class_and_code` y `should_set_cookie`,
  tres de los siete hechos son consecuencias indirectas (`handle_*`, `process_response`, los
  errores que se lanzan). Las preguntas pedían solo los consumidores directos, y ninguna
  versión los mencionó. Ese fallo de diseño afecta igual a las dos versiones.
- **Pocas repeticiones:** n=2 por celda, en 4 tareas de un solo repositorio y un solo cliente.
- **Otros lenguajes sin medir:** TypeScript y JavaScript tienen pruebas unitarias pero no
  tienen corpus de benchmark.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/inherited_self_calls_2026-11-06 \
  --run-root <ejecuciones> --variant codex-main --variant codex-fix
python benchmarks/inherited_self_calls_2026-11-06/analyze.py --run-root <ejecuciones>
```

`runs.json`, `results.json` y `judge_grades.json` guardan los datos por sesión. Las sesiones
crudas no están en el repositorio porque incluyen copias de los corpus.
