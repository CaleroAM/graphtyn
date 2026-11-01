# Benchmark real con Claude Code / Sonnet: Redis, fmt y Rails — 25 oct 2026

## Resultado

Réplica con Claude Code 2.1.310 y `claude-sonnet-5-5` de las tareas congeladas
de Redis, fmt y Rails que ya se habían medido con OpenCode, Codex y Antigravity.
Las seis sesiones terminaron, la calidad fue 8/8 en ambos brazos de los tres
corpus y el servidor Graphtyn se conectó y fue llamado en cada brazo de
tratamiento. Graphtyn redujo el total informado entre 39,99 % y 83,19 %.

| Corpus / commit | Calidad base → Graphtyn | Total informado base → Graphtyn | Delta | Coste USD base → Graphtyn | Delta coste | Sesión base → Graphtyn | Índice frío |
|---|---:|---:|---:|---:|---:|---:|---:|
| Redis `f2a17a8` | 8/8 → 8/8 | 173.411 → 104.063 | **−39,99 %** | 0,2139 → 0,1994 | −6,76 % | 32,399 → 23,276 s | 24,004 s |
| fmt `0fc3163` | 8/8 → 8/8 | 375.381 → 63.092 | **−83,19 %** | 0,1987 → 0,0778 | −60,86 % | 53,863 → 19,613 s | 33,146 s |
| Rails `3f0b675` | 8/8 → 8/8 | 225.214 → 62.091 | **−72,43 %** | 0,1358 → 0,0711 | −47,62 % | 44,521 → 27,279 s | 259,746 s |

El coste es el `total_cost_usd` que informó Claude Code, no una estimación. La
indexación fría no forma parte del tiempo de sesión; en Rails supera el ahorro
de una sola sesión y sólo se amortiza si el índice se reutiliza.

## Qué se midió

- Protocolos: `redis_protocol.json`, `fmt_protocol.json` y `rails_protocol.json`
  de esta carpeta, derivados de los protocolos de 2026-10-20 cambiando sólo el
  cliente. Tareas y rúbricas copiadas sin cambios.
- Corpus: clones oficiales limpios fuera de `PROYECTOS/`, en los commits fijados.
- Orden: Redis y Rails base→Graphtyn; fmt Graphtyn→base.
- Cliente: `claude -p` con `--strict-mcp-config` (sin servidores del usuario ni
  de claude.ai), `--setting-sources project` sobre un workspace copiado sin
  `.claude/`, `.mcp.json` ni archivos de instrucciones, y sin Edit, Write,
  NotebookEdit, WebFetch, WebSearch, Task ni Agent. El tratamiento añadió un
  único servidor stdio `graphtyn mcp --tool-profile query --preload-index`.
- Contabilidad: `benchmarks/run_three_client_mcp_comparison.py`. Claude informa
  lectura y escritura de caché aparte de la entrada; el total suma entrada,
  ambas cachés y salida. La traza conserva un registro por id de mensaje.
- Calificación: `analyze_results.py`, rúbrica automática congelada, sin
  adjudicación manual.

## Diagnóstico

- **Redis:** el paquete de Graphtyn quedó truncado (`payload_truncated=true`),
  con `missing=["validation_gate"]` y `do_not_expand=false`; Claude leyó un
  archivo más. La escritura de caché subió 3,32 % y por eso el coste sólo bajó
  6,76 % pese a −39,99 % de tokens. Es el mismo hueco de recuperación de
  `processCommand` documentado con los otros clientes.
- **fmt y Rails:** `missing=[]` y `do_not_expand=true`; Claude respondió sólo con
  el paquete, sin lecturas adicionales.
- **Citas:** el brazo Graphtyn citó menos `archivo:línea` (Redis 10→2,
  fmt 72→28, Rails 38→21). Todas las citas resueltas eran líneas existentes. En
  Rails, 18 citas base y 5 Graphtyn usan nombres ambiguos (`validations.rb`) que
  el calificador no puede resolver; no prueban error.
- **Auditoría:** ninguna herramienta prohibida. Base: sólo Bash/Read.
  Tratamiento: una llamada `graph_query_intent` por sesión.

## Comparación con los otros clientes (mismas tareas)

| Corpus | OpenCode | Codex | Antigravity | Claude |
|---|---:|---:|---:|---:|
| Redis | −52,01 % | −22,48 % | −49,95 % | −39,99 % |
| fmt | sin respuesta | +11,24 % | −12,55 % | −83,19 % |
| Rails | −67,30 % | +86,52 % | −38,79 % | −72,43 % |

Los totales de cada proveedor tienen composición distinta; sólo los deltas
dentro de cada cliente son comparables. Las corridas previas se hicieron antes
de las correcciones posteriores de C/C++ y Ruby, así que parte de la diferencia
puede venir de Graphtyn y no del cliente.

## Limitaciones

Una repetición por celda; calificación automática no independiente; el
`~/.claude/CLAUDE.md` del usuario no se aisló (`--claude-bare` requiere
`ANTHROPIC_API_KEY`); `ENABLE_TOOL_SEARCH=false` y
`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` se fijaron en ambos brazos sin verificar su
efecto. Los eventos crudos están en
`/home/calero/Documentos/docker/graphtyn-benchmark-runs-claude-2026-10-25/`.

## Verificación posterior sin modelo

Después de esta corrida se corrigieron las causas del hueco de Redis y el coste
del índice frío. `post_fix_verification.json` registra la comprobación offline:
el paquete de Redis pasa de 3/8 a 8/8 hechos de la rúbrica con `missing=[]`,
fmt y Rails se mantienen en 8/8, y el reindexado en frío baja a 18 s, 5 s y
62 s con un grafo idéntico. No se ejecutaron sesiones nuevas de modelo, así que
estos cambios todavía no tienen un delta de tokens ni de calidad medido.
