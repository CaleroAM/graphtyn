# Claude Code / Sonnet: paquete MCP lean y hook de primer turno — 26 oct 2026

## Qué se midió

Dos cambios de Graphtyn sobre las mismas tareas, commits, rúbricas congeladas,
Claude Code 2.1.310 y `claude-sonnet-5-5` que
`real_claude_agents_reps_2026-10-25`:

- **MCP lean**: `graph_query_intent` devuelve por defecto un paquete sin
  diagnósticos, sin entidades desconectadas de los fragmentos de fuente y sin
  repetir líneas ya impresas. El agente sigue llamando a la herramienta.
- **Hook**: `graphtyn claude-context` registra dos hooks `UserPromptSubmit` que
  ejecutan la misma consulta antes del primer turno e inyectan el paquete como
  `<graphtyn-context>`, partido en dos bloques porque Claude Code persiste en
  disco el contexto de un hook que supera 10.000 caracteres. El servidor MCP
  sigue disponible en ese brazo.

Los dos brazos nuevos se ejecutaron juntos (3 repeticiones por corpus). Base,
Graphtyn anterior y Graphify son las sesiones de los días 25–26, mismas
condiciones salvo el momento de ejecución.

## Resultado: tokens totales por sesión

| Corpus | Rep. | Lectura directa | Graphify | Graphtyn anterior | **MCP lean** | **Hook** | Calidad (base / Graphify / anterior / lean / hook) |
|---|---|---:|---:|---:|---:|---:|---|
| Redis | r1 | 166.601 | 196.652 | 62.544 | 60.561 | **33.610** | 8 / 8 / 8 / 7 / 8 |
| | r2 | 170.359 | 190.734 | 62.900 | 60.519 | **33.767** | 8 / 8 / 8 / 7 / 8 |
| | r3 | 208.690 | 107.110 | 63.123 | 60.781 | **34.052** | 8 / 8 / 8 / 8 / 7 |
| fmt | r1 | 310.168 | 343.123 | 62.933 | 60.536 | **32.740** | 8 / 8 / 8 / 8 / 8 |
| | r2 | 344.531 | 236.317 | 62.622 | 60.388 | 134.115 | 8 / 8 / 8 / 8 / 8 |
| | r3 | 232.972 | 228.559 | 63.245 | 59.994 | 98.645 | 8 / 8 / 8 / 8 / 8 |
| Rails | r1 | 228.903 | 251.447 | 62.568 | 60.811 | **32.905** | 6 / 8 / 7 / 7 / 6 |
| | r2 | 195.226 | 258.187 | 62.930 | 60.970 | **32.951** | 7 / 8 / 8 / 8 / 8 |
| | r3 | 217.576 | 249.769 | 62.701 | 60.998 | **32.926** | 7 / 6 / 8 / 8 / 6 |

| Corpus | Media lean | Media hook | Hook vs lean | Hook vs lectura directa | Hook vs Graphify | Lean vs anterior |
|---|---:|---:|---:|---:|---:|---:|
| Redis | 60.620 | 33.810 | **−44,2 %** | −81,2 % | −77,8 % | −3,6 % |
| fmt | 60.306 | 88.500 | +46,9 % (−45,9 a +122,1) | −69,4 % | −63,5 % | −4,2 % |
| Rails | 60.926 | 32.927 | **−46,0 %** | −84,5 % | −87,0 % | −2,9 % |

### Lectura

- **MCP lean** redujo 2.200–2.600 tokens por sesión (−3 a −4 %), sin cambiar el
  número de llamadas. Es el cambio aplicable a todos los clientes MCP.
- **Hook**: en 7 de 9 sesiones el agente respondió en **una sola llamada al
  modelo, sin herramientas**, con ~33.000 tokens (−44 a −46 % frente a lean y
  −81 a −85 % frente a lectura directa). En fmt r2 y r3 el modelo verificó en
  fuente piezas que el paquete no mostraba (`basic_fstring`, `vargs`) con 3–4
  comandos, y gastó 98.645 y 134.115 tokens. Con el MCP el mismo paquete no
  provocó esas lecturas: el contexto inyectado por un hook pesa menos para el
  modelo que el resultado de una herramienta que pidió.
- **Calidad**: los fallos del hook en Rails r1 y r3 (`create_branch`,
  `failure_semantics`) no son evidencia perdida. El contexto inyectado contiene
  `new_record? ? _create_record` y `ActiveRecord::Rollback unless status`. Las
  respuestas los parafrasearon («devuelve `false`», «un `:abort` cancela la
  acción»), y la rúbrica congelada exige esos textos literales. En Redis, el
  fallo de `operational_rejections` (lean r1–r2, hook r3) es la rama de evicción,
  que cae en un tramo omitido del fragmento enfocado en todos los brazos
  Graphtyn. Las notas se informan sin adjudicación manual.

## Incidencias

Conservadas en `failed_attempts/` del directorio de ejecución:

1. **Instrucciones en el mensaje.** Con las instrucciones del brazo dentro del
   mensaje del usuario, el hook recuperó con ese texto («artefactos del
   benchmark»…) y obtuvo `src/redis-benchmark.c`. En uso real esas instrucciones
   viven en `CLAUDE.md` o en la skill. El brazo hook las recibe ahora por
   `--append-system-prompt` y el mensaje es sólo la pregunta.
2. **Límite de 10.000 caracteres por hook.** Con un solo bloque recortado a
   9.800 caracteres se omitió el centro de `processCommand`, y el agente lo
   leyó (68.005 tokens). Una prueba directa confirmó que el límite es por hook,
   así que el paquete se reparte en dos hooks paralelos.
3. **Cabecera v1.** Decía «answer from it directly» sin prohibir búsquedas; fmt
   r1–r2 verificaron en fuente. La v2 aplica la misma regla de parada que el
   brazo MCP recibía en su mensaje. Las 5 sesiones v1 se repitieron.
4. **Bug corregido.** `evidence_result` recortaba en sitio los fragmentos del
   paquete interno. La segunda llamada del handler MCP, que guarda el contexto,
   acortaba así la respuesta ya construida. Ahora el presupuesto efectivo de
   fragmentos es explícito y produce los mismos paquetes medidos.

## Limitaciones

n=3 por corpus; calificación automática literal; brazos de comparación no
contemporáneos; el coste en USD depende del estado de la caché de prompt (el
brazo hook tiene un prompt de sistema distinto y escribió caché en su primera
llamada) y por eso la métrica principal son los tokens. Eventos crudos:
`/home/calero/Documentos/docker/graphtyn-benchmark-runs-claude-lean-hook-2026-10-26/`.
