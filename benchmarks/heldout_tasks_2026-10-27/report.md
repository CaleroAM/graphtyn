# Tareas no vistas (held-out) — 27 oct 2026

## Por qué

Las cuatro correcciones de selección de fuente del 27 oct se diseñaron mirando
las mismas tres tareas con las que se midieron (Redis `processCommand`,
`fmt::format`, `ActiveRecord#save`). Este run comprueba si los resultados se
sostienen con preguntas nuevas. Las seis tareas, dos por repositorio y en los
mismos commits, se escribieron leyendo la fuente directamente, sin consultar
Graphtyn. Sus rúbricas literales se congelaron en el commit `a4d5aa8`, antes de
cualquier sesión.

Clientes y brazos:

| Cliente | Modelo | Brazos | Repeticiones |
|---|---|---|---:|
| Claude Code | `claude-sonnet-5-5` | MCP lean, hook | 2 |
| Codex | `gpt-5.6-luna` | sin grafo, MCP lean, hook | 1 |
| OpenCode | `opencode/deepseek-v4.1-flash-free` | MCP lean, hook | 1 |

54 de 54 sesiones completas.

## 1. Cobertura del paquete, sin agentes

Hechos de la rúbrica presentes en el paquete de `graph_query_intent`, con el
código anterior a las correcciones (`2fde7ee`) y con el actual:

| Tarea | Antes | Ahora | `do_not_expand` ahora |
|---|---:|---:|---|
| Redis `processCommand` (original) | 6/8 | 8/8 | true |
| fmt `format` (original) | 8/8 | 8/8 | true |
| Rails `save` (original) | 8/8 | 8/8 | true |
| **Redis expiración** | 5/8 | 5/8 | **true** |
| **Redis PSYNC** | 5/8 | 6/8 | **true** |
| fmt `print` | 8/8 | 8/8 | true |
| **fmt entero con especificaciones** | 3/7 | 3/7 | **true** |
| Rails `destroy` | 2/8 | 3/8 | false |
| Rails carga de relación | 1/8 | 1/8 | false |

- **Sin regresiones:** las correcciones no quitaron ningún hecho que antes
  estuviera cubierto, y en PSYNC añadieron uno.
- **Sin generalización:** la recuperación no se sostiene fuera de las tareas
  originales. Lo grave son las tres filas en negrita: el paquete se declara
  completo aunque le faltan partes de lo pedido.

## 2. Sesiones con agentes

Tokens medios por sesión y rúbrica literal (/8; fmt entero /7):

| Tarea | Claude lean | Claude hook | Codex sin grafo | Codex lean | Codex hook | OpenCode lean | OpenCode hook |
|---|---|---|---|---|---|---|---|
| Redis expiración | 145k · 8,8 | 32k · 7,6 | 101k · 7 | 28k · **4** | 11k · **4** | 98k · 8 | 14k · 7 |
| Redis PSYNC | 154k · 8,8 | 89k · 7,8 | 257k · 6 | 30k · 4 | 12k · 5 | 46k · 8 | 16k · 7 |
| fmt `print` | 61k · 7,7 | 33k · 7,7 | 215k · 6 | 30k · 5 | 12k · 6 | 28k · 7 | 15k · 7 |
| fmt entero | 57k · **3,3** | 30k · **3,4** | 139k · **7** | 27k · **3** | 10k · **3** | 25k · **3** | 215k · 7 |
| Rails `destroy` | 225k · 8,8 | 163k · 8,8 | 344k · 6 | 263k · 6 | 13k · 5 | 521k · 8 | 733k · 8 |
| Rails relación | 270k · 8,8 | 266k · 8,8 | 179k · 8 | 99k · 8 | 102k · 7 | 631k · 8 | 258k · 8 |

### Lectura

- **Paquete completo de verdad (fmt `print`):** el patrón de las tareas
  originales se repite. El hook ronda los 33k tokens en Claude y los 12k en
  Codex, sin herramientas, con la misma nota que el MCP lean y frente a 215k de
  Codex sin grafo.
- **Paquete incompleto declarado completo (Redis expiración, Redis PSYNC, fmt
  entero):** los agentes obedecen la regla de parada y responden con lo que
  hay.
  - En fmt entero, todos los brazos con Graphtyn sacan 3/7 salvo uno, frente a
    7/7 de Codex sin grafo. La excepción es OpenCode con hook, que ignoró la
    regla, buscó (16 herramientas) y llegó a 7/7 con 215k tokens.
  - En Redis expiración, Codex con Graphtyn saca 4/8 frente a 7/8 sin grafo.
  - Claude con MCP lean compensó en Redis porque siguió consultando (3–6
    herramientas, 145–154k tokens). Con el hook, que no busca, perdió hechos.
  - **El ahorro de tokens en estos casos viene, en parte, de responder menos.**
- **Paquete que no se declara completo (Rails `destroy`, Rails relación):** los
  agentes buscan por su cuenta. La calidad se mantiene (8/8 en Claude), pero el
  ahorro desaparece: Claude gasta 160–270k tokens y OpenCode 258–733k, más que
  Codex sin grafo. Codex con hook respondió `destroy` sin buscar y bajó a 5/8.

## Conclusión

Las cifras de ahorro de los informes del 26 y 27 oct son correctas para las
tareas medidas, pero no se pueden presentar como generales. El fallo de fondo
es la calibración de `do_not_expand`. Cuando la recuperación no encuentra parte
de lo pedido, el paquete no debe declararse completo. Con el hook el riesgo es
mayor, porque su cabecera prohíbe buscar.

Mientras no se corrija:

- el hook sigue siendo opcional y no se recomienda por defecto;
- el README y `docs/BENCHMARKS.md` no deben afirmar «misma calidad» en general;
- cualquier corrección de `do_not_expand` debe validarse con otro conjunto de
  tareas no vistas, porque este ya se ha mirado.

## Limitaciones

- **Repeticiones:** n=2 en Claude y n=1 en Codex y OpenCode.
- **Rúbrica:** es literal. En esta ronda no hubo adjudicación ciega; los hechos
  que faltan en fmt entero (`parse_format_specs`, `on_format_specs`,
  `handle_dynamic_spec`, `arg_formatter`) son omisiones de contenido, no
  paráfrasis, porque tampoco aparecen en el paquete.
- **Codex:** usa `gpt-5.6-luna`.
- **Eventos crudos:**
  `/home/calero/Documentos/docker/graphtyn-benchmark-runs-heldout-2026-10-27/`.
