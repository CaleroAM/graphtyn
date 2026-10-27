# Claude Code / Sonnet con tres repeticiones — 25–26 oct 2026

## Resultado

Tres repeticiones contrabalanceadas (AB, BA, AB) por corpus con Claude Code
2.1.310 y `claude-sonnet-5-5`, sobre los mismos commits, tareas y rúbricas que
`real_claude_agents_2026-10-25`, después de todas las mejoras de esa fecha:
*rationale*, comunidades, vocabulario genérico, citas listas, builtins de Ruby,
paquetes Kotlin/Swift/Scala e índice más rápido. Las 18 sesiones válidas
terminaron; cada brazo Graphtyn hizo una sola llamada a `graph_query_intent`, con
`missing=[]` y sin lecturas adicionales ni herramientas prohibidas.

| Corpus | Calidad base → Graphtyn (r1, r2, r3) | Δ tokens media (rango) | Tokens base | Tokens Graphtyn | Δ coste media (rango) | Δ sesión media | Índice frío |
|---|---|---:|---:|---:|---:|---:|---:|
| Redis | 8,8,8 → 8,8,8 | **−65,1 %** (−62,5 a −69,8) | 166.601–208.690 | 62.544–63.123 | −41,7 % (−40,3 a −42,8) | −34,7 % | 15,0–15,4 s |
| fmt | 8,8,8 → 8,8,8 | **−78,1 %** (−72,9 a −81,8) | 232.972–344.531 | 62.622–63.245 | −40,8 % (−73,7 a +8,1) | −50,7 % | 1,2–3,5 s |
| Rails | 6,7,7 → 7,8,8 | **−70,5 %** (−67,8 a −72,7) | 195.226–228.903 | 62.568–62.930 | −42,0 % (−35,6 a −46,8) | −37,3 % | 23,6–25,3 s |

Graphtyn redujo los tokens en las 9 parejas. La desviación estándar del delta
fue de 2,5 a 4,7 puntos. El brazo Graphtyn fue muy estable (±300 tokens), mientras
que la lectura directa varió hasta un 48 % entre repeticiones del mismo corpus.

En Rails la calidad no fue igual entre brazos, así que el analizador no marca esas
parejas como comparables. Graphtyn obtuvo una calidad igual o mayor en las tres
repeticiones: la base omitió `create_branch` en las tres y `failure_semantics` en
r1; Graphtyn sólo omitió `create_branch` en r1.

## Incidencias

- **Sesiones rechazadas.** Durante la primera ejecución se agotó el límite de uso
  de la cuenta: 9 sesiones (fmt r2 base, fmt r3, las 6 de Rails) terminaron sin
  llamar a la API (`duration_api_ms=0`, mensaje sintético, 0 tokens). Se
  conservan en `failed_attempts/` dentro del directorio de ejecución y se
  repitieron después con el mismo código. El runner ahora se detiene ante una
  sesión con error y uso cero en lugar de consumir las celdas restantes.
- **Caché fría en el reintento.** fmt r2 base y fmt r3 se ejecutaron unas dos
  horas después que el resto. Con la caché de prompt fría escribieron 43.771 y
  33.782 tokens de caché frente a unos 10.000–22.000; por eso fmt r3 Graphtyn
  costó 0,170 USD (+8,1 % frente a su base) aunque usó los mismos tokens. El
  coste depende de la temperatura de la caché; los tokens no.

## Limitaciones

n=3 por corpus; calificación automática congelada sin adjudicación manual;
`~/.claude/CLAUDE.md` del usuario no aislado; el orden de fmt r2 cambió porque
sólo se repitió su brazo base. Los eventos crudos están en
`/home/calero/Documentos/docker/graphtyn-benchmark-runs-claude-reps-2026-10-25/`.
