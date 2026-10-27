# Claude Code / Sonnet tras las correcciones — 25 oct 2026

## Resultado

Repetición de `benchmarks/real_claude_agents_2026-10-25` con el mismo cliente
(Claude Code 2.1.310), modelo (`claude-sonnet-5-5`), commits, tareas, rúbricas y
orden, después de las correcciones registradas en
`../real_claude_agents_2026-10-25/post_fix_verification.json`. Las seis sesiones
terminaron con calidad 8/8 en ambos brazos; cada brazo Graphtyn hizo una sola
llamada a `graph_query_intent` con `missing=[]` y `do_not_expand=true` y ninguna
lectura adicional.

| Corpus | Calidad base → Graphtyn | Total informado base → Graphtyn | Delta | Coste USD base → Graphtyn | Delta coste | Sesión base → Graphtyn | Índice frío | Citas válidas base → Graphtyn |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Redis | 8/8 → 8/8 | 206.119 → 63.373 | **−69,25 %** | 0,2057 → 0,1689 | −17,90 % | 26,333 → 24,171 s | 18,993 s | 47 → 35 |
| fmt | 8/8 → 8/8 | 360.509 → 62.719 | **−82,60 %** | 0,1900 → 0,0786 | −58,62 % | 57,711 → 23,974 s | 3,850 s | 69 → 24 |
| Rails | 8/8 → 8/8 | 259.795 → 62.245 | **−76,04 %** | 0,1366 → 0,0723 | −47,06 % | 43,630 → 26,470 s | 61,532 s | 16 → 13 |

## Antes y después de las correcciones (brazo Graphtyn)

| Corpus | Tokens Graphtyn | Coste Graphtyn | Paquete | Lecturas extra | Citas válidas | Índice frío |
|---|---:|---:|---|---:|---:|---:|
| Redis | 104.063 → 63.373 (−39,1 %) | 0,1994 → 0,1689 | `missing=[validation_gate]`, truncado → completo | 1 → 0 | 2 → 35 | 24,0 → 19,0 s |
| fmt | 63.092 → 62.719 | 0,0778 → 0,0786 | completo en ambas | 0 → 0 | 28 → 24 | 33,1 → 3,9 s |
| Rails | 62.091 → 62.245 | 0,0711 → 0,0723 | completo en ambas | 0 → 0 | 16 → 13 | 259,7 → 61,5 s |

La mejora atribuible es la de Redis, donde el paquete dejó de quedar incompleto,
y la del índice frío en los tres corpus. fmt y Rails ya estaban completos y no
cambiaron de forma material. Las citas mejoraron mucho sólo en Redis; en fmt y
Rails el brazo Graphtyn sigue citando menos que la lectura directa.

Los brazos base variaron entre corridas sin cambios de código (Redis
173.411 → 206.119, Rails 225.214 → 259.795): con una repetición por celda, esa
variación es del mismo orden que algunas diferencias y los deltas deben leerse
como indicativos.

## Por qué el coste baja menos que los tokens

Cada sesión de Claude Code escribe en caché unos 34.000–41.000 tokens del prompt
del sistema y las definiciones de herramientas. Graphtyn no reduce esa parte,
que es la más cara por token; en Redis el tratamiento escribió 34.239 tokens de
caché frente a 39.351 de la base. Por eso el ahorro de coste (−17,90 % a
−58,62 %) es menor que el de tokens.

## Limitaciones

Una repetición por celda, calificación automática congelada sin adjudicación
manual, `~/.claude/CLAUDE.md` del usuario no aislado y sin `--claude-bare`. Los
eventos crudos están en
`/home/calero/Documentos/docker/graphtyn-benchmark-runs-claude-postfix-2026-10-25/`.
