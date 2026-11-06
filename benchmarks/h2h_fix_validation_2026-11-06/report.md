# Validación de las correcciones de la comparación con Graphify

Fecha: 2026-11-06. 24 sesiones de Codex: 6 tareas nuevas × 2 versiones de Graphtyn × 2
repeticiones. Unos 734.000 tokens.

**Veredicto: POSITIVE para nombrar los consumidores directos; sin efecto medible en el resto.**

- **Consumidores directos en Flask:** la rama corregida nombró 9 de 10 consumidores directos
  y `main` 5 de 10, con los mismos tokens.
- **Total de hechos:** 80/96 frente a 70/96. Sin embargo, la mitad de esa diferencia sale de
  los tres flujos, cuyo paquete es idéntico en las dos versiones, así que ahí es variación
  entre sesiones, no efecto de la corrección.
- **Cuerpo entero sin probar:** esta validación no pone a prueba la corrección de cuerpo
  entero, porque `main` ya daba todos los hechos en los tres flujos nuevos.

## Diseño

- **Correcciones medidas** (rama `fix/h2h-failures`, `8b9e234`):
  - las llamadas `self.x()` y `cls.x()` de Python se enlazan a la clase del propio método;
  - en una pregunta de impacto, «X en Flask» trata `Flask` como alcance y no como símbolo;
  - una función nombrada larga se da entera cuando las palabras de la pregunta no aparecen en
    su código.
- **Versiones comparadas:** `main` (`0b1d8a8`) y la rama corregida (`8b9e234`), cada una desde
  un worktree congelado. MCP lean y regla de parada `targeted`.
- **Tareas:** 6 nuevas con 48 hechos, escritas leyendo el código y congeladas en `7b1a99e` antes
  de ejecutar. Ninguna se usó para ajustar las correcciones.
  - Tres de impacto en Flask que dependen de llamadas sobre `self`:
    - `_find_error_handler`, nombrando el proyecto tras «en» y con el método heredado de la
      clase base `App`;
    - `finalize_request`, en inglés;
    - `request_context`, sin nombrar el proyecto.
  - Tres flujos sobre cuerpos nombrados largos: `processInlineBuffer` y `zsetAdd` de Redis, y
    `save_collection_association` de Rails.
- **Repositorios públicos en commits fijos:** pallets/flask `d086db85`, redis/redis `f2a17a8d`
  y rails/rails `3f0b6751`.
- **Cliente:** Codex 0.153.2 con `gpt-5.6-luna` y `--ignore-user-config`. Cada sesión usa una
  copia del repositorio y un `GRAPHTYN_HOME` propio. El orden de las versiones se alterna entre
  repeticiones.
- **Calificación:** dos jueces de modelos distintos (Gemini y GPT), sin herramientas; cuenta un
  hecho solo si coinciden. Kappa entre jueces: 0,81.

## Resultado

| Versión | Hechos (jueces) | Consumidores directos de Flask | Tokens: media | Tokens: mediana | Herramientas |
|---|---:|---:|---:|---:|---:|
| `main` | 70/96 (73 %) | 5/10 | 30.733 | 29.597 | 1,0 |
| Corregida | **80/96 (83 %)** | **9/10** | 30.470 | 29.130 | 1,0 |

Por parejas (misma tarea y repetición), la versión corregida acierta más hechos en 5 de 12,
menos en 1, y el cambio mediano de tokens es +0,1 %.

| Tarea | `main` | Corregida | Paquete |
|---|---:|---:|---|
| Flask `_find_error_handler`, impacto | 8/16 | 11/16 | Corregido: 3 consumidores exactos, frente a 489 referencias |
| Flask `finalize_request`, impacto | 8/14 | 10/14 | Corregido: 3 consumidores enlazados de 4, frente a 1 de 489 |
| Flask `request_context`, impacto | 6/10 | 6/10 | Los mismos 2 consumidores, ahora enlazados y no como texto |
| Redis `processInlineBuffer`, flujo | 16/18 | 18/18 | Idéntico |
| Redis `zsetAdd`, flujo | 16/20 | 18/20 | Idéntico |
| Rails `save_collection_association`, flujo | 16/18 | 17/18 | Idéntico |

- **`_find_error_handler`:** en la primera repetición, `main` respondió que no había
  consumidores directos, porque su paquete mezclaba los 3 reales con 486 usos de la clase
  `Flask`. La versión corregida listó `handle_http_exception`, `handle_user_exception` y
  `handle_exception` con su línea.
- **`finalize_request`:** en la segunda repetición, `main` no nombró a `full_dispatch_request`
  ni a `handle_exception`. La versión corregida los nombró en las dos.

## Lo que queda

- **Métodos heredados:** `_find_error_handler` está definido en la clase base `App`
  (`src/flask/sansio/app.py`) y se llama como `self._find_error_handler` desde `Flask`. Sus 3
  consumidores llegan como referencias de texto sin verificar, no como aristas del grafo:
  la resolución descarta un candidato cuya clase no coincide con el tipo del receptor sin
  mirar la herencia (`graphtyn/core/ast_parser.py:897`). Se vio al preparar las tareas y no
  se corrigió sobre ellas.
- **Pruebas y consumidores indirectos:** ninguna versión puso en el paquete los archivos de
  prueba, ni el consumidor indirecto `session_transaction` (`src/flask/testing.py:161`). En
  esos hechos las dos versiones fallan por igual.
- **Ruido:** con paquetes idénticos, los flujos variaron 5 hechos entre versiones. La mejora en
  los consumidores (4 de 10) es de un tamaño parecido a ese ruido, así que la apoya sobre todo
  el contenido de los paquetes, no el total.

## Límites

- **Pocas repeticiones:** n=2 por celda, en 6 tareas y un solo cliente.
- **Solo Codex:** Claude ya acertaba todo en la comparación original, así que no se midió aquí.
- **Rúbricas mías:** las escribí yo y los jueces son modelos.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/h2h_fix_validation_2026-11-06 \
  --run-root <ejecuciones> --variant codex-main --variant codex-fix
python benchmarks/h2h_fix_validation_2026-11-06/analyze.py --run-root <ejecuciones>
```

`runs.json`, `results.json` y `judge_grades.json` guardan los datos por sesión. Las sesiones
crudas no están en el repositorio porque incluyen copias de los corpus.
