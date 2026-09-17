# Validación de recuperación y captura entre proyectos

Fecha de la prueba: 13 de septiembre de 2026, hora de Ciudad de México.

## Resultado de extremo a extremo

Se probó una conversación real de OpenClaw con el agente `openclaw/nexus` (Evi),
ejecutado con `vertexai/gemini-2.5-pro`. La sesión de Gateway terminó correctamente
y contiene cuatro mensajes activos: una consulta y respuesta sobre
TourMuseosPuebla, seguidas por una consulta y respuesta sobre OpenClaw. El agente
consultó la memoria compartida de cada proyecto por separado.

La captura nativa por SSH importó los cuatro mensajes en dos destinos:

| Proyecto | Mensajes de la prueba | Atribución | Método de asociación |
| --- | ---: | --- | --- |
| TourMuseosPuebla | 2 | `openclaw/nexus` | `explicit_project_name` |
| OpenClaw | 2 | `openclaw/nexus` | `explicit_project_name` |

Ambos pares conservan la misma referencia de sesión OpenClaw y el identificador
de cada mensaje original. Los identificadores de TourMuseosPuebla no aparecen en
el almacén de OpenClaw ni viceversa; no hay duplicados de esos identificadores.
Cada ventana de mensaje de prueba se mantuvo dentro de su sesión de proyecto.
La captura es asíncrona, así que el mensaje puede tardar hasta el siguiente ciclo
de sincronización en aparecer en el almacén.

El almacén de TourMuseosPuebla tenía 3.591 mensajes y 7 sesiones al medir; el de
OpenClaw tenía 1.121 mensajes y 34 sesiones. La sesión sintética de validación
permanece en el historial de OpenClaw como evidencia reproducible.

## Recuperación medida

Se ejecutaron 12 búsquedas locales repetidas por proyecto sobre los almacenes
capturados. El objetivo fue encontrar una referencia histórica conocida en cada
caso; el tiempo mide `search_messages` en SQLite, no la llamada al modelo ni el
viaje completo por MCP.

| Almacén | Mensajes consultables | Coincidencias léxicas | Referencia objetivo | Posición en top 3 | p50 / máximo |
| --- | ---: | ---: | --- | ---: | ---: |
| TourMuseosPuebla | 3.591 | 213 | `ee3541a8-620d-4a6c-8b0b-dc07283ddc2e` | 3 | 170,73 / 173,36 ms |
| OpenClaw | 1.025 | 93 | `msg_01a0996d-5d7f-79a3-9fd1-b1ff0aefc6c8` | 2 | 22,21 / 23,43 ms |

Los valores son la mediana y el máximo observado en 12 ejecuciones; no se publica
p95 porque una muestra de 12 repeticiones no lo estima con solidez. El proceso
Python de la medición alcanzó 31.508 KiB de RSS máximo; es el máximo del proceso
completo, no memoria incremental atribuible sólo al buscador. En estos dos
ejemplos controlados, ambas referencias conocidas aparecieron en el top 3. Esto
no constituye una estimación general de precisión o recall.

La primera medición detectó que varios mensajes recientes de una sola sesión
podían ocupar todo el top 3. `search_messages` ahora devuelve como máximo un
resultado por sesión; la ventana de mensajes permite ampliar el intercambio
completo sin llenar el resumen con duplicados de contexto. Una prueba unitaria
reproduce esa competencia entre una conversación reciente y referencias
históricas de otras sesiones.

## Verificaciones

- La suite completa `pytest -q`: **399 pasaron, 2 omitidas** en 133,05 s.
- La reejecución `memory benchmark --suite stability`: 285 consultas; Recall@5
  100%, MRR 0,9889, atribución y negativos 100%, 516,93 tokens medios y p95 de
  47,75 ms (37,11 ms de media). No hubo fallos; el desglose por AGY, Codex y
  OpenClaw también pasó.
- Captura de historial: **1.105 mensajes** con interrupción, apertura de una
  instancia nueva del almacén, reanudación, relectura idempotente y continuación
  de una línea final incompleta. Se comprobaron 1.105 IDs de fuente únicos y
  1.106 mensajes después de añadir el último registro.
- MCP de Codex: se añadió un perfil local `graphtyn_project` con `--path`
  explícito, conservando el servidor genérico para otros proyectos. `codex mcp
  list` confirmó ambos perfiles y una llamada MCP directa a `memory_status`
  devolvió la ruta del repositorio Graphtyn. Codex debe recargar su configuración
  para exponer el nuevo perfil en la sesión interactiva.
- Pruebas de ruteo: los nombres de dos proyectos separados generan segmentos
  atribuidos por sesión; referencias ambiguas a varios proyectos y chats sin
  proyecto se quedan pendientes, y una mención incidental de Graphtyn como
  herramienta no desplaza el proyecto explícito.
- `py_compile` de `graphtyn/core/shared_memory.py`: correcto.
- `git diff --check` en Graphtyn: correcto.
- La captura nativa y el dashboard de Graphtyn estaban activos durante la
  verificación.
- La política de recuperación aparece en las instrucciones del repo y la skill
  de Graphtyn, en la plantilla de agentes especialistas de OpenClaw y en sus
  espacios de agente. También se añadió al `AGENTS.md` del workspace OpenClaw
  predeterminado para cubrir conversaciones sin carpeta de proyecto abierta.

## Alcance pendiente

La prueba E2E usó nombres exactos de proyectos; el enrutamiento ambiguo se cubrió
con pruebas de integración aisladas que verifican que no se elige un destino sin
evidencia suficiente. Las dos búsquedas reales siguen siendo casos controlados,
no una estimación general de precisión o recall. No se ejecutó una fuente de
varios GB en esta validación; la captura usa lectura por lotes, y la suite cubre
una sesión de más de mil mensajes, reanudación y un registro individual mayor
que el límite. La búsqueda léxica puede devolver candidatos secundarios: el
agente debe leer atribución, cobertura y ventana antes de afirmar una decisión.
El estado de captura no demuestra por sí solo que el agente haya consultado la
memoria al responder.
