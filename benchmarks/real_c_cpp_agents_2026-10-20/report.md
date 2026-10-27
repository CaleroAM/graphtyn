# Benchmark real C/C++ con tres clientes — 20 oct 2026

## Resultado

Esta prueba exploratoria confirma que el efecto de Graphtyn depende del repositorio,
del cliente y de la calidad de la recuperación. En Redis, las tres sesiones
terminadas conservaron 8/8 hechos y redujeron el total informado entre 22,48 % y
52,01 %. En fmt, Codex consumió 11,24 % más, Antigravity informó 12,55 % menos y
OpenCode agotó el timeout sin dejar eventos suficientes para reconstruir tokens.
No se deben promediar clientes ni interpretar estos datos como ahorro universal.

### Redis/Redis, C (`f2a17a8dca1566d2a0f078840fffef5661eab4b1`)

| Cliente / modelo | Calidad base → Graphtyn | Total informado base → Graphtyn | Delta | Volumen técnico con caché | Sesión base → Graphtyn | Índice frío |
|---|---:|---:|---:|---:|---:|---:|
| OpenCode 1.18.13 / `opencode/deepseek-v4.1-flash-free` | 8/8 → 8/8 | 388.682 → 186.533 | **−52,01 %** | 388.682 → 186.533 (−52,01 %) | 141,523 → 421,177 s (+197,60 %) | 142,264 s |
| Codex 0.153.2 / `gpt-6-astra` | 8/8 → 8/8 | 109.060 → 84.538 | **−22,48 %** | 109.060 → 84.538 (−22,48 %) | 53,758 → 43,275 s (−19,50 %) | 142,613 s |
| Antigravity 1.3.5 / `gemini-3.8-flash-high` | 8/8 → 8/8 | 158.966 → 79.555 | **−49,95 %** | 564.117 → 182.690 (−67,61 %) | 201,280 → 92,991 s (−53,80 %) | 126,560 s |

El tiempo de sesión no incluye la indexación. En una primera consulta que tenga que
crear el índice, base → Graphtyn sería 141,523 → 563,441 s en OpenCode, 53,758 →
185,888 s en Codex y 201,280 → 219,551 s en Antigravity. La indexación se puede
reutilizar entre tareas y por eso se conserva como coste separado.

### fmtlib/fmt, C++ (`0fc31633e7d53ac895ae0a688b83b7d44f0b0c1f`)

| Cliente / modelo | Calidad base → Graphtyn | Total informado base → Graphtyn | Delta | Volumen técnico con caché | Sesión base → Graphtyn | Índice frío |
|---|---:|---:|---:|---:|---:|---:|
| OpenCode 1.18.13 / `opencode/deepseek-v4.1-flash-free` | 8/8 → sin respuesta | 859.913 → desconocido | **no calculable** | 859.913 → desconocido | 238,236 → timeout a 915,139 s | 26,621 s |
| Codex 0.153.2 / `gpt-6-astra` | 8/8 → 8/8 | 111.793 → 124.364 | **+11,24 %** | 111.793 → 124.364 (+11,24 %) | 67,764 → 73,046 s (+7,79 %) | 25,462 s |
| Antigravity 1.3.5 / `gemini-3.8-flash-high` | 8/8 → 8/8 | 263.050 → 230.029 | **−12,55 %** | 1.806.694 → 1.794.304 (−0,69 %) | 345,213 → 247,676 s (−28,25 %) | 26,475 s |

La aparente reducción de Antigravity casi desaparece al incluir sus entradas en
caché. El resultado de OpenCode no equivale a cero: el proceso no produjo
`step_finish`, respuesta ni otro registro de uso antes del timeout, de modo que el
consumo de esa celda es desconocido.

## Qué se midió

Se clonaron fuera de `PROYECTOS/` los repositorios oficiales
[Redis](https://github.com/redis/redis) y [fmt](https://github.com/fmtlib/fmt) en
commits fijados. Cada corpus tuvo una tarea de trazado con ocho hechos, una sesión base y
otra con Graphtyn para OpenCode, Codex y Antigravity. El orden fue contrabalanceado,
el acceso directo a archivos estuvo permitido en ambos brazos y cada sesión de
tratamiento inició un proceso stdio aislado de la misma implementación MCP. Los
protocolos congelados están en `benchmarks/real_c_cpp_agents_2026-10-20/redis_protocol.json:1` y `benchmarks/real_c_cpp_agents_2026-10-20/fmt_protocol.json:1`; las
tareas y rúbricas están en `benchmarks/real_c_cpp_agents_2026-10-20/redis_tasks.json:1` y `benchmarks/real_c_cpp_agents_2026-10-20/fmt_tasks.json:1`.

La rúbrica automática fue congelada antes de ejecutar. Una revisión posterior,
hecha por el mismo investigador, corrigió dos falsos negativos del patrón de Redis:
ambas respuestas base sí contenían tres o más rechazos operativos. La decisión y
sus líneas se conservan en `benchmarks/real_c_cpp_agents_2026-10-20/manual_adjudication.json:1`. Esta evaluación no es
independiente y sólo hubo una repetición por celda.

El contador suma los `step_finish` de OpenCode porque el protocolo declara
semántica por paso; la implementación está en
`benchmarks/run_three_client_mcp_comparison.py:29-54`. Codex toma el último
`turn.completed` (`:56-70`) y Antigravity el `result.usage` (`:72-90`). En estas
corridas OpenCode produjo 15/10 registros en Redis y 32/0 en fmt; Codex y
Antigravity produjeron un registro final por sesión terminada. No aparecieron
eventos explícitos de reintento, pero reintentos no etiquetados no se pueden
reconstruir.

`total_tokens` no tiene la misma composición entre clientes. OpenCode incluye
entrada, caché, salida y razonamiento. En Codex, la caché ya está incluida en
`input_tokens` y el razonamiento en salida; Antigravity expone caché aparte, como registra
`benchmarks/run_three_client_mcp_comparison.py:99-123`. Por eso los deltas sólo son
válidos dentro de cada cliente. El “volumen técnico con caché” es una magnitud
diagnóstica, no facturación. OpenCode informó coste 0 con el modelo gratuito; los
otros dos clientes no informaron precio. No hay base para convertir tokens en
ahorro monetario.

## Diagnóstico de recuperación

En Redis, Graphtyn encontró `processCommand` en `src/server.c:4667`, pero también
seleccionó símbolos ajenos como `finishShutdown`, `genRedisInfoString` y `main`. El
paquete de Codex/OpenCode entregó 10.400 caracteres en tres fragmentos, unos 3.957
tokens, quedó truncado y marcó `missing=[]` y `do_not_expand=true`. El fragmento de
`processCommand` terminó en `src/server.c:4786`: no incluía la ACL que comienza en
`src/server.c:4787`, los rechazos operativos de `src/server.c:4855` en adelante ni
la ejecución final de `src/server.c:5043`. Los agentes completaron esas obligaciones
leyendo fuente. Es un falso positivo de suficiencia y una selección con ruido,
aunque el ancla principal era correcta.

En fmt, el problema fue más severo. El paquete registrado eligió tres funciones
`format` de `test/format-test.cc:739`, `:1979` y `:2325`, y aun así declaró
`missing=[]`, `complete_for=[flow, order_and_control_flow]` y
`do_not_expand=true`. El flujo solicitado vive en las APIs y plantillas de
`include/fmt/core.h:1643`, `:2697`, `:2748` y `:2831`, la API pública en
`include/fmt/format.h:4666` y el buffer/análisis en
`include/fmt/format-inl.h:1458-1473`. El paquete ocupó unos 2.568 tokens, pero sólo
544 caracteres correspondían a evidencia fuente y esa evidencia era irrelevante.
Los agentes que terminaron recuperaron la respuesta mediante lecturas directas;
esto explica por qué el soporte sintáctico C++ puede pasar pruebas estructurales sin
producir todavía una recuperación eficiente para sobrecargas y plantillas.

La consulta MCP registrada tardó aproximadamente 0,414–0,534 s en fmt y
2,138–2,294 s en Redis. El tiempo extremo de OpenCode con Redis no procede de una
consulta MCP de varios minutos; corresponde al comportamiento completo del agente.
Antigravity no conservó el cuerpo de la respuesta MCP, sólo su duración, por lo que
sus campos de contexto no se reconstruyen ni se infieren.

## Corrección posterior verificada sin modelos

La medición histórica anterior no se modificó. Después de diagnosticar fmt se
corrigieron cuatro causas: los `.h` con sintaxis C++ ahora usan la gramática C++;
cada símbolo conserva su namespace léxico; los selectores cualificados distinguen
funciones libres de métodos `formatter::format`; y las tareas largas conservan sus
símbolos finales y reservan un representante de producción por nombre. La evidencia
de precisión también puede incluir el cuerpo de un tipo nombrado como `fstring`.

Al reindexar el mismo commit de fmt, el índice pasó de 4.627 nodos/14.368 conectores
a 7.103/18.036. La misma consulta dejó de escoger los tres `format` de pruebas: sus
primeros nodos fueron la API pública `include/fmt/format.h:4666`, `runtime` en
`include/fmt/core.h:2695`, `detail::vformat_to` en
`include/fmt/format-inl.h:1468`, `format_to` en `include/fmt/core.h:2831`,
`fstring` en `include/fmt/core.h:2699` y `vformat` en
`include/fmt/format-inl.h:1458`. No hubo anclas de `test/` entre los diez nodos.
Los fragmentos exactos cubrieron la API pública, el cuerpo de `fstring` y la ruta
de `vformat`; las operaciones del nodo de `detail::vformat_to` conservaron el caso
rápido `{}` y la llamada a `parse_format_string`.

Esta verificación no ejecutó agentes ni produjo tokens nuevos. Su artefacto es
`benchmarks/real_c_cpp_agents_2026-10-20/post_fix_verification.json:1`; por tanto,
los deltas de las tablas siguen describiendo el código anterior a esta corrección y
se necesita otra A/B para medir su efecto de sesión.

## Correcciones prioritarias

1. Ampliar la regresión de resolución ya aplicada a más bibliotecas con namespaces,
   plantillas y sobrecargas; una consulta de API debe seguir penalizando `test/`
   salvo que pida pruebas.
2. Calcular `complete_for`, `missing` y `do_not_expand` desde evidencia que cubra
   cada obligación. Encontrar el símbolo de entrada no prueba el resto del flujo.
3. Seleccionar rangos por obligación y por ramas dirigidas, no un cuerpo fijo de
   120 líneas seguido de símbolos cercanos no conectados. Publicar qué obligación
   respalda cada fragmento.
4. Reutilizar un índice persistente y medir por separado consulta caliente,
   actualización incremental y creación fría. En Redis, crear el índice tardó
   entre 126,560 y 142,613 s: más que las dos sesiones Codex y que el tratamiento
   de Antigravity.
5. Hacer que el arnés escriba eventos a medida que llegan y preserve consumo parcial
   al cancelar un proceso. También debe capturar el resultado MCP de Antigravity;
   hoy esos datos faltan.

## Alcance de la conclusión

La prueba demuestra un beneficio grande y consistente para este flujo de Redis.
También demuestra una regresión de tokens en Codex/fmt, una ganancia marginal al
contar caché en Antigravity/fmt y una celda no medible de OpenCode/fmt. Dos
repositorios, dos tareas y una repetición no estiman un efecto general ni permiten
seleccionar únicamente resultados favorables.

Los datos normalizados están en `benchmarks/real_c_cpp_agents_2026-10-20/results.json:1`, el detalle por corrida y hashes
de los eventos en `benchmarks/real_c_cpp_agents_2026-10-20/grades_by_run.json:1`, y el analizador reproducible en
`benchmarks/real_c_cpp_agents_2026-10-20/analyze_results.py:1`. Los eventos, respuestas y workspaces se conservan bajo
`/home/calero/Documentos/docker/graphtyn-benchmark-runs-2026-10-20/`; los checkouts
fijados están bajo `/home/calero/Documentos/docker/graphtyn-benchmark-repos-2026-10-20/`.

La siguiente prueba mínima debe repetir cada celda completa al menos tres veces,
usar un segundo flujo por repositorio, separar índice frío y reutilizado, y exigir
calidad 8/8 antes de calcular deltas. Debe conservar las seis celdas, incluidos
timeouts y regresiones. El volumen estimado es de 36 sesiones adicionales (2
repositorios × 2 tareas × 3 clientes × 2 brazos × 3 repeticiones); el límite de
consumo se debe acordar antes de ejecutarla.
