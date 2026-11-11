# Despacho a implementaciones: validación con Codex

Fecha: 2026-11-10. 18 sesiones de Codex: 6 tareas nuevas, `main` frente a dos versiones de la
rama, una repetición. Unos 560.000 tokens.

**Veredicto: NEUTRAL a POSITIVE, sin significación.** Tras la corrección, la rama acierta 32/39
hechos frente a 30/39 de `main`. La diferencia es de +4,4 %, con un IC 95 % por tareas de
[−6 %, +12 %], y la rama gasta un 6 % menos de tokens.

## Diseño

- **Tareas:** 6 preguntas de impacto sobre métodos de interfaz, trait o abstractos, con 39 hechos.
  Las escribí leyendo el código y las congelé en `897a60e` antes de ejecutar.
  - gson: `FieldNamingStrategy.translateName`.
  - ripgrep: `Sink::matched` y `Matcher::find_at`.
  - Flask: `SessionInterface.save_session` y `View.dispatch_request`.
  - Slim: `CallableResolverInterface::resolve`.
- **Versiones:**
  - `main`: `bf3eaab`.
  - Rama: `12e5335`, la primera ronda.
  - Rama corregida: `71973c1`, la segunda ronda.

  Cada versión se ejecutó desde un worktree congelado.
- **Cliente:** Codex con `gpt-5.6-luna`, MCP lean y regla de parada `targeted`. Cada sesión
  tiene su propia copia del repositorio y su propio `GRAPHTYN_HOME`.
- **Calificación:** mayoría de tres jueces (Gemini, GPT y Claude), con las citas resueltas por
  el arnés. Kappa entre jueces: 0,85.

## Comprobación previa sin cliente

Antes de lanzar sesiones comparé qué hechos de la rúbrica aparecían en el paquete. En la
primera versión de la rama, `Sink::matched` bajaba de 6/7 a 1/7. Al ser ya símbolo el método
del trait, sus 18 homónimos competían por las anclas y ganaba `Gitignore::matched`. Lo
corregí en `12e5335`:
- el dueño nombrado en la pregunta elige las anclas;
- las referencias de texto ponen primero las llamadas;
- un campo genérico (`sink: S` con `S: Sink`) toma el tipo de su cota.

Como esa tarea sirvió para encontrar el fallo, no cuenta como evidencia independiente.

## Resultado

| Tarea | `main` | Rama (`12e5335`) | Rama corregida (`71973c1`) |
|---|---:|---:|---:|
| gson `translateName` | 5/6 | 2/6 | 5/6 |
| ripgrep `Sink::matched` | 4/7 | 5/7 | 5/7 |
| ripgrep `find_at` | 6/7 | 7/7 | 7/7 |
| Flask `save_session` | 6/6 | 6/6 | 5/6 |
| Flask `dispatch_request` | 5/6 | 5/6 | 5/6 |
| Slim `resolve` | 4/7 | 5/7 | 5/7 |
| **Total** | **30/39** | **30/39** | **32/39** |
| Tokens | 196.213 | 181.376 | 182.730 |

- **Rama `12e5335`:** diferencia de −1,2 %, con un IC 95 % de [−23 %, +12 %]. En gson perdió 3
  hechos porque el alcance por dueño descartaba los homónimos sin arista `implementa`. Los siete
  cuerpos de constante de `FieldNamingPolicy` no tenían dueño y desaparecieron incluso de
  `omitted_homonyms`.
- **Rama corregida `71973c1`:**
  - los homónimos de fuera del dueño se siguen informando;
  - los métodos de un enum de Java, C# o PHP, incluidos los cuerpos de sus constantes,
    tienen al enum como dueño, así que implementan la interfaz;
  - gson vuelve a 5/6 y gasta 29.706 tokens frente a los 42.711 de `main`.
- **Flask `save_session` (6/6 → 5/6):** la sesión de la rama no mencionó `is_null_session`. El
  paquete sin cliente tiene los mismos 6/6 hechos en las dos versiones, así que lo atribuyo a la
  variación entre sesiones.

## Límites

- **Pocas sesiones:** una repetición, seis tareas y un solo cliente.
- **Tareas no independientes:** dos de las seis tareas (`Sink::matched` y `translateName`)
  sirvieron para encontrar fallos que luego se corrigieron.
- **Rúbricas mías:** las escribí yo, y los jueces son modelos.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/interface_dispatch_2026-11-10 --run-root <ejecuciones> \
  --variant codex-main --variant codex-fix --variant codex-fix2 --tiebreak --repos <corpus fijados>
python benchmarks/paired_stats.py benchmarks/interface_dispatch_2026-11-10/judge_grades.json \
  --base codex-main --new codex-fix2 --rule majority
```
