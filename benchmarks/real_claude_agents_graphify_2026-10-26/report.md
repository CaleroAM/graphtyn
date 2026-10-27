# Claude Code / Sonnet: lectura directa vs Graphtyn vs Graphify — 26 oct 2026

## Resultado

Tercer brazo Graphify añadido a la réplica de tres repeticiones
(`real_claude_agents_reps_2026-10-25`): mismo Claude Code 2.1.310,
`claude-sonnet-5-5`, commits, tareas y rúbricas congeladas. Graphify 0.9.96 se
instaló en un venv aislado fuera del repositorio
(`~/.cache/graphtyn-bench/graphify-latest`); no se instaló skill, hook ni
instrucción de proyecto, y nunca se registró bajo el nombre Graphtyn. Antes de
cada sesión se construyó su grafo de sólo código con
`GRAPHIFY_BACKEND=none graphify update <workspace>` (sin LLM, fuera del tiempo
medido) y se expuso con el `graphify-mcp` oficial y sus 10 herramientas como
único servidor (`--strict-mcp-config`). Las 9 sesiones Graphify terminaron;
todas llamaron una vez a `query_graph` y después verificaron en fuente con
Bash/Read. Ninguna usó herramientas prohibidas.

Tokens totales por sesión (entrada + lectura y escritura de caché + salida):

| Corpus | Rep. | Lectura directa | Graphtyn | Graphify | Calidad (base / Graphtyn / Graphify) |
|---|---|---:|---:|---:|---|
| Redis | r1 | 166.601 | 62.544 | 196.652 | 8 / 8 / 8 |
| | r2 | 170.359 | 62.900 | 190.734 | 8 / 8 / 8 |
| | r3 | 208.690 | 63.123 | 107.110 | 8 / 8 / 8 |
| fmt | r1 | 310.168 | 62.933 | 343.123 | 8 / 8 / 8 |
| | r2 | 344.531 | 62.622 | 236.317 | 8 / 8 / 8 |
| | r3 | 232.972 | 63.245 | 228.559 | 8 / 8 / 8 |
| Rails | r1 | 228.903 | 62.568 | 251.447 | 6 / 7 / 8 |
| | r2 | 195.226 | 62.930 | 258.187 | 7 / 8 / 8 |
| | r3 | 217.576 | 62.701 | 249.769 | 7 / 8 / 6 |

| Corpus | Media base | Media Graphtyn | Media Graphify | Graphify vs base | Graphtyn vs Graphify | Coste medio USD (base / Graphtyn / Graphify) | Grafo Graphify |
|---|---:|---:|---:|---:|---:|---|---:|
| Redis | 181.883 | 62.856 | 164.832 | −6,2 % (−48,7 a +18,0) | **−58,8 %** (−68,2 a −41,1) | 0,124 / 0,072 / 0,150 | 18,9 s |
| fmt | 295.890 | 62.933 | 269.333 | −7,6 % (−31,4 a +10,6) | **−75,8 %** (−81,7 a −72,3) | 0,202 / 0,106 / 0,156 | 4,8 s |
| Rails | 213.902 | 62.733 | 253.134 | +19,0 % (+9,9 a +32,3) | **−75,2 %** (−75,6 a −74,9) | 0,126 / 0,073 / 0,121 | 106,4 s |
| **Total 9 rep.** | **230.558** | **62.841** | **229.100** | −0,6 % | −72,6 % | 1,356 / 0,752 / 1,284 (suma) | |

Graphify no redujo de forma consistente el consumo frente a la lectura directa:
ahorró en 3 de 9 parejas y gastó más en las otras 6. `query_graph` devolvió un
subgrafo truncado (~2.000 tokens) que no bastaba para citar archivo:línea, así
que el agente siguió leyendo fuente con Bash y Read (2–6 comandos por sesión).
Graphtyn usó menos tokens que Graphify en las 9 repeticiones.

En calidad, Graphify igualó en Redis y fmt (8/8). En Rails obtuvo 8/8 en r1 y
r2, la mejor nota de esas repeticiones, pero 6/8 en r3 (omitió `create_branch`
y `failure_semantics`).

## Incidencias y limitaciones

- **Brazos no contemporáneos.** Base y Graphtyn se midieron el 25–26 oct; Graphify
  el 26 oct por la tarde. La métrica principal son los tokens; el coste depende
  del estado de la caché de prompt y no es estrictamente comparable.
- **Construcción del grafo.** Graphify tardó 106 s en Rails frente a 24–25 s del
  índice Graphtyn; en Redis 19 s frente a 15 s; en fmt 5 s frente a 1–4 s. Ese
  tiempo queda fuera de la sesión en ambos casos.
- **Configuración de Graphify.** Grafo sólo de código (sin extracción semántica
  con LLM) y servidor MCP sin skill de Graphify. Con su skill o un grafo semántico
  el comportamiento podría variar.
- n=3 por corpus; calificación automática congelada sin adjudicación manual;
  `~/.claude/CLAUDE.md` del usuario no aislado. Eventos crudos en
  `/home/calero/Documentos/docker/graphtyn-benchmark-runs-claude-graphify-2026-10-26/`.
