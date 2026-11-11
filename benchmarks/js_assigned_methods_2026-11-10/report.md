# Métodos asignados de JavaScript y #privados de TypeScript: validación con Codex

Fecha: 2026-11-10. 13 sesiones de Codex sobre 4 tareas nuevas: `main` frente a tres versiones de la
rama, una repetición. 470.000 tokens en total.

**Veredicto: NEGATIVE en tareas independientes; NEUTRAL tras corregir, con un 33 % menos de tokens.**
- **Tareas congeladas:** la primera versión de la rama perdió frente a `main`, con 14/30 hechos
  contra 24/30.
- **Correcciones:** las dos causas se corrigieron. La versión final acierta 23/30 y gasta 136.000
  tokens, frente a los 202.000 de `main`.
- **Límite:** las cuatro tareas sirvieron para encontrar esas causas, así que el resultado final no
  es evidencia independiente.

## Diseño

- **Tareas:** 4 preguntas de impacto, con 30 hechos. Las escribí leyendo el código y las congelé en
  `d28f7b4` antes de ejecutar.
  - express: `req.get` y `res.set`.
  - ky: los privados `#raceWithTotalTimeout` y `#getResponseRequest`.

  Son distintas de las que se usaron al desarrollar la rama (`res.sendFile` y
  `calculateRetryTimingDelay`).
- **Versiones:**
  - `main`: `666b329`.
  - `fix`: `9d979b8`, la rama tal como se propuso.
  - `fix2`: `0a0fe48`, que añade las cadenas de alias y la recursión.
  - `fix3`: `da1db7c`, que añade los getters definidos.

  Cada versión se ejecutó desde un worktree congelado.
- **Cliente:** Codex con `gpt-5.6-luna`, MCP lean y regla de parada `targeted`. Cada sesión tiene su
  propia copia del repositorio y su propio `GRAPHTYN_HOME`.
- **Calificación:** mayoría de tres jueces (Gemini, GPT y Claude) con las citas resueltas. Kappa
  entre jueces: 0,95.

## Resultados (mayoría de tres jueces)

| Tarea | main | fix | fix2 | fix3 |
|---|---|---|---|---|
| express `req.get` | 4/6 (84.613 tok) | 3/6 | 2/6 | 4/6 (31.301 tok) |
| express `res.set` | 8/9 (60.263) | **0/9** | 8/9 (31.543) | — |
| ky `#getResponseRequest` | 7/8 (28.475) | 6/8 | 6/8 (28.932) | — |
| ky `#raceWithTotalTimeout` | 5/7 (28.922) | 5/7 | 5/7 (44.202) | — |
| **Total** | **24/30, 202.273 tok** | 14/30, 117.447 | 21/30, 135.104 | — |

Versión final (fix3 en `req.get`, fix2 en el resto): **23/30 con unos 136.000 tokens**. La diferencia
media por tarea es de −3,1 %: la única pérdida es un hecho en `#getResponseRequest`. Los tokens se
multiplican por 0,67, sobre todo porque `main` exploró mucho en express.

## Qué falló en la rama y cómo se corrigió

1. **Cadenas de alias.**
   - **Fallo:** en `res.set = res.header = function header(...)` solo se registraba `res.header`.
     Las llamadas `this.set(...)` de `res.send`, `res.json`, `res.type` y los demás no llegaban al
     método. El paquete mostraba como únicos consumidores tres archivos de prueba, y Codex respondió
     solo con ellos (0/9).
   - **Corrección:** cada nombre de la cadena es ahora el mismo método.
   - **Efecto secundario:** con `res.set` como símbolo, la recursión `this.set(...)` dentro de
     `app.set` se desviaba a `res.set`. Ahora esa recursión no se resuelve a un homónimo, solo en
     métodos asignados a un objeto. En ripgrep, aplicarla a todos los `self` quitaba 79 llamadas
     correctas de reenvío (`(*self).find_at(...)`).
2. **Getters definidos.**
   - **Fallo:** express define `req.host`, `req.protocol` y `req.xhr` con
     `defineGetter(req, 'host', function host() {...})`. Sus `this.get(...)` no tenían dueño. El
     paquete solo listaba `req.range`, y Codex concluyó que ningún getter dependía de `req.get`.
   - **Corrección:** ahora se reconocen `defineGetter(obj, 'x', function)` y
     `Object.defineProperty(obj, 'x', {get: ...})` sobre objetos del nivel superior.

Ambos fallos son del mismo tipo que en la validación del despacho: un paquete con
`do_not_expand=true` que parece completo, pero omite consumidores. El cliente se fía de él.

## Comprobaciones sin cliente

Rúbrica presente en el paquete:

| Tarea | main | fix | fix3 |
|---|---|---|---|
| express `req.get` | 3/6 | 4/6 | 6/6 |
| express `res.set` | 3/9 | 7/9 | 9/9 |
| ky `#raceWithTotalTimeout` | 6/7 | 7/7 | — |
| ky `#getResponseRequest` | 8/8 | 8/8 | — |

La comprobación sin cliente de `fix` ya daba 7/9 en `res.set`, pero los términos aparecían fuera de
los consumidores. Una rúbrica literal sobre el paquete no detecta que el cliente vaya a fiarse de una
lista de consumidores incompleta.

**Precisión del grafo** en las aristas que cambian entre `fix` y `fix3`:
- **Corpus sin cambios:** ky, Flask, gson, Slim y ripgrep no ganan ni pierden aristas.
- **express:** gana 71 aristas. En una muestra de 25 comprobé 24 contra el código y todas son
  correctas; la restante es de nivel de archivo, en `examples`, y no la comprobé.
- **Gate:** sigue pasando con una cobertura media del 80,3 %.

## Límites

- **Muestra pequeña:** 4 tareas y una repetición, así que no hay intervalo útil.
- **Sin evidencia independiente:** el resultado final de `fix2`/`fix3` no es independiente, porque
  las tareas sirvieron para encontrar los fallos.
- **Tokens:** el ahorro depende de una sola sesión de `main` de 84.613 tokens.
