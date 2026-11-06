# Alcance por miembro de workspace: tareas de reserva

Fecha: 2026-11-06. Solo medición de paquetes, sin sesiones de cliente.

**Veredicto: NEUTRAL en estas tareas.** Las dos versiones dan los mismos hechos.

## Qué se probó

El commit `afff470` hace que, en un workspace (`crates/globset`, `packages/x`), cada miembro
cuente como paquete. Si la pregunta nombra uno, ese paquete decide entre homónimos cualificados
de otros miembros y pesa más que un archivo llamado como el símbolo. El fallo se encontró en una
tarea congelada de `benchmarks/language_conformance_2026-11-06`: «`Parser::parse` en globset»,
donde ganaba `crates/core/flags/parse.rs`. Por eso esa tarea no sirve como evidencia
independiente.

Para tener una prueba independiente, escribí y congelé estas dos tareas (`e9b4434`) antes de
medir. Las dos piden el mismo método cualificado de ripgrep (`91f5d22e`), y cada una nombra un
crate distinto:

- `S_PCRE2_BUILD_MANY_FLOW`: `RegexMatcherBuilder::build_many` en `pcre2`;
- `S_REGEX_BUILD_MANY_FLOW`: el mismo método en el crate `regex`.

## Resultado

Hechos de la rúbrica presentes en el paquete:

| Tarea | `d38f930` (sin la corrección) | `afff470` (con ella) |
|---|---:|---:|
| `build_many` en pcre2 | 8/10 | 8/10 |
| `build_many` en regex | 9/9 | 9/9 |

Las dos versiones ya eligen el crate correcto. En estas tareas no hay un archivo llamado como
el método que desempate a favor del homónimo equivocado. No ejecuté las sesiones de Codex
previstas en el protocolo, porque con paquetes que traen los mismos hechos solo medirían
variación entre sesiones.

La evidencia a favor de la corrección es la tarea de globset (de 3 a 10 hechos de 12 en el
paquete) y la prueba unitaria
`test_a_named_workspace_member_picks_its_homonym_over_a_file_named_after_the_symbol`.
