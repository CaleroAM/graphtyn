# Receptores con ámbito (#56): validación con tres clientes

Fecha: 2026-11-11. 24 sesiones: 4 tareas nuevas, `main` frente a `feat/scoped-receiver-typing`, con
Codex, Claude Code y Antigravity, una repetición. Los jueces de este estudio y los del despacho en
Go (`benchmarks/go_dispatch_2026-11-11`) se calificaron juntos, y `judge_grades.json` incluye las
sesiones de ambos.

**Veredicto: NEUTRAL.** En total, `main` acierta 70 de 84 hechos y la rama 69. Ningún cliente
muestra una diferencia fuera del ruido.

## Diseño

- **Tareas:** 4 preguntas de impacto, congeladas en `8dedd8e` antes de ejecutar. Las elegí entre
  los símbolos cuyas aristas cambia la rama, en las dos direcciones:
  - `Flask.test_client` pierde llamadas desde pruebas: la fixture `app` de pytest deja de prestar
    su tipo.
  - cobra `Command.Name` pierde 17 llamadas por variables de `range`.
  - gson `LinkedTreeMap.put` gana 38 llamadas.
  - ripgrep `DirEntry::path` pierde 5.
- **Versiones:**
  - `main`: `56fc73b`.
  - Rama: `bf6cd29`.

  Cada versión se ejecutó desde un worktree congelado.
- **Clientes:**
  - Codex con `gpt-5.6-luna`.
  - Claude Code con `claude-sonnet-5-5`.
  - Antigravity con `gemini-3.8-flash-high`.

  Todos con MCP lean y regla de parada `targeted`.
- **Calificación:** mayoría de tres jueces con las citas resueltas. Kappa entre jueces: 0,855.

## Comprobación sin cliente

La rúbrica presente en el paquete es igual en las dos versiones, salvo en ripgrep, donde baja de 4/8
en `main` a 3/8 en la rama.

## Resultados (mayoría de tres jueces)

| Cliente | `main` | Rama | Tokens `main` → rama | Diferencia por tarea, IC 95 % |
|---|---|---|---|---|
| Codex | 21/28 | 22/28 | 126.424 → 129.692 | +3,1 %, [0 %, +9 %] |
| Claude Code | 25/28 | 24/28 | 252.010 → 253.436 | −3,1 %, [−9 %, 0 %] |
| Antigravity | 24/28 | 23/28 | 274.775 → 238.563 | −3,1 %, [−9 %, 0 %] |

Por tarea:
- **Flask, cobra y gson:** iguales en las dos versiones y casi en el máximo con los tres clientes.
  Estas tareas apenas discriminan.
- **ripgrep `DirEntry::path`:**
  - con Codex sube de 2/8 a 3/8;
  - con Claude Code y con Antigravity baja de 5/8 a 4/8.

## Lectura

La rama hace el grafo más preciso: las 16 aristas añadidas que comprobé son correctas, y quita
aristas falsas. A cambio pierde llamadas reales cuyo tipo venía prestado de otra declaración. En
estas sesiones ninguno de los dos efectos se nota en las respuestas:
- **Tareas saturadas:** en las tareas que pierden aristas, los clientes encuentran a los
  consumidores igual, por búsqueda o por las referencias de texto del paquete.
- **ripgrep:** es la única tarea donde cambia el paquete, y empeora en dos de tres clientes.

No hay motivo medido para fusionarla: no mejora las respuestas, el parseo es entre un 3 % y un 17 %
más lento, y el gate baja una décima.

## Límites

- **Muestra:** 4 tareas, una repetición. Tres de ellas quedan casi en el máximo con ambas versiones.
- **Antigravity:** su ahorro de tokens (×0,87) viene de una sola tarea (cobra) y no se repite en
  los otros clientes.
