# Validación final: 20 tareas nuevas, jueces calibrados

Fecha: 2026-11-08 y 2026-11-09. 64 sesiones: 40 de Codex (20 tareas × 2 versiones), y 12 de
Claude Code y 12 de Antigravity (6 tareas × 2 versiones). Una repetición. Unos 2,9 millones de
tokens.

**Veredicto: POSITIVE en Codex; NEUTRAL en Claude y Antigravity.**

- **Codex:** la rama acierta 110/146 hechos y `main` 97/146. La diferencia es de +9,1 %, con
  IC 95 % de [+3,9 %, +16,2 %] por tareas. Mejora en 9 de 20 tareas, no empeora en ninguna y
  gasta los mismos tokens (×1,005).
- **Claude Code y Antigravity:** misma calidad. Claude gasta un 13 % menos (×0,87, IC
  [0,75, 1,02]), pero con 6 tareas ese ahorro no se distingue del ruido.

## Qué se comparó

- **`main`:** `741d371`, después de #46.
- **Rama `feat/impact-completeness`:** `50fb076`, con las herramientas de #47 y estos cambios:
  - **paquete de impacto completo:** línea de cada llamada, efectos y llamadas del propio símbolo,
    consumidores de segundo nivel, pruebas relacionadas y `answer_checks` sacados del paquete;
  - **precisión del grafo:** cadenas y comentarios fuera de la búsqueda de declaraciones, imports de
    JavaScript y TypeScript, métodos de objeto literal, bases de Rust solo traits, constantes de Ruby;
  - **huecos de extracción:** `impl Trait for Type` en Rust, parámetros y literales con tipo en Go,
    interfaces de Go por conjunto de métodos y atributos con tipo en Python.

## Diseño

- **Tareas:** 20 nuevas, una de impacto y una de flujo en cada corpus fijado: Flask, Redis, fmt,
  Rails, gson, Slim, cobra, ripgrep, express y ky. Ninguna había sido nombrada en una tarea
  anterior. Suman 146 hechos, con las rúbricas escritas leyendo el código y congeladas en
  `50fb076` antes de ejecutar.
- **Clientes:**
  - Codex 0.153.2 con `gpt-5.6-luna`, en las 20 tareas;
  - Claude Code con `claude-sonnet-5-5` y Antigravity con `gemini-3.8-flash-high`, en 6 tareas
    (3 de impacto y 3 de flujo).
- **Orden y aislamiento:** el orden de las versiones se alterna por tarea. Cada sesión usa una copia
  del corpus y un `GRAPHTYN_HOME` propio, y cada versión se ejecuta desde un worktree congelado.
- **Calificación:** Gemini y GPT reciben las citas `archivo:línea` resueltas, y Claude desempata
  donde discrepan. La regla es la mayoría de los tres. Kappa entre Gemini y GPT: 0,96. Los
  intervalos salen de remuestrear tareas (`benchmarks/paired_stats.py`).

## Resultado

| Cliente | Tareas | `main` | Rama | Diferencia | IC 95 % | Tokens |
|---|---:|---:|---:|---:|---|---:|
| Codex | 20 | 97/146 | **110/146** | **+9,1 %** | **[+3,9 %, +16,2 %]** | ×1,005 |
| Antigravity | 6 | 39/44 | 40/44 | +2,8 % | [0 %, +8,3 %] | ×0,98 |
| Claude Code | 6 | 41/44 | 41/44 | 0 % | [0 %, 0 %] | ×0,87 |

Codex, por tarea (proporción de hechos):

| Tarea | `main` | Rama |
|---|---:|---:|
| Slim `registerBodyParser`, impacto | 0,25 | **0,88** |
| Flask `get_debug_flag`, impacto | 0,83 | 1,00 |
| ripgrep `print_stats`, impacto | 0,50 | 0,67 |
| gson `getIndent`, impacto | 0,33 | 0,50 |
| fmt `get_arg_checked`, impacto | 0,67 | 0,83 |
| fmt `do_format_decimal`, flujo | 0,67 | 0,83 |
| cobra `genMan`, flujo | 0,89 | 1,00 |
| Rails `valid_authenticity_token?`, flujo | 0,88 | 1,00 |
| ripgrep `sink_slow_multi_line_only_matching`, flujo | 0,88 | 1,00 |
| Las otras 11 tareas | igual | igual |

- **La mejora no viene de encontrar más:** sin cliente, los paquetes de las dos versiones traen los
  mismos hechos en total (116/146). Viene de lo que el agente transmite: con la línea de cada
  llamada, los efectos del símbolo y `answer_checks`, Codex nombra más de lo que ya tenía delante.
  En Slim, por ejemplo, `main` solo encontró como consumidor una prueba. La rama nombró
  `__construct` y `registerDefaultBodyParsers`, y los tipos que registra este último (JSON,
  formularios, XML), que el paquete traía en la línea de cada llamada.
- **Coste:** los tokens de Codex no cambian.

## Lo que sigue flojo

En tres tareas, las dos versiones aciertan lo mismo, y poco:

- **express `res.sendFile` (2/9 en Codex):** los dos paquetes traen solo 2 de los 9 hechos, y
  ninguno el cuerpo del método, definido por asignación (`res.sendFile = function sendFile(...)`).
- **Rails `reject_new_record?` (1/6):** las dos versiones encuentran solo uno de sus dos
  consumidores, `assign_nested_attributes_for_collection_association`.
- **ky `calculateRetryTimingDelay` (2/8):** su único consumidor es el método privado
  `#calculateRetryDelay`. Los hechos que faltan están en el cuerpo del propio objetivo (segundos,
  fechas), y el paquete de impacto solo trae de él los `return`.

## Hallazgo posterior

Al terminar las sesiones, el paquete de `getIndent` (gson) mostró que «List the direct consumers»
convertía `list` en símbolo. Ya está corregido en `e76c838`. No cuenta como evidencia de esta
validación, porque sus paquetes salieron del commit congelado.

## Límites

- **Una repetición:** n=1. La variación entre sesiones se cubre con más tareas, no con
  repeticiones.
- **Claude y Antigravity:** solo 6 tareas cada uno; detectan una regresión grande, no una mejora
  pequeña.
- **Sesiones repetidas:** 6 sesiones de Claude fueron rechazadas por el límite de uso de 5 horas
  sin llegar a usar el modelo. Se guardaron aparte y se repitieron con el mismo código cuando el
  límite se reinició.
- **Rúbricas mías:** las escribí yo, y los jueces son modelos.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/final_validation_2026-11-08 --run-root <ejecuciones> \
  --variant codex-main --variant codex-fix --variant claude-main --variant claude-fix \
  --variant antigravity-main --variant antigravity-fix --tiebreak --repos <corpus fijados>
python benchmarks/paired_stats.py benchmarks/final_validation_2026-11-08/judge_grades.json \
  --base codex-main --new codex-fix --rule majority
```
