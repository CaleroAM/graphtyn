# Validación de `0.10.1`

Fecha: 2026-09-12. Esta versión corrige la conexión y captura de instalaciones
OpenClaw remotas por SSH. La publicación queda condicionada a que GitHub Actions
complete satisfactoriamente la CI del commit exacto del tag.

## Cambio incluido

- `harness openclaw discover` y `connect` admiten `--ssh-config` y validan el
  archivo indicado.
- Los comandos SSH de descubrimiento e importación reutilizan esa configuración.
- El servicio persistente de captura conserva la ruta de configuración SSH,
  actualiza y reinicia el watcher al reconectar, y devuelve el error de systemd
  si no logra activarlo.
- OpenCode lee la base SQLite actual, prefiere `opencode-stable.db`, conserva IDs
  de mensajes y restringe la importación del proyecto a rutas `directory`
  coincidentes exactamente. La previsualización del dashboard incluye el path.
- Los trabajos de previsualización no persisten mensajes ni títulos derivados
  del prompt; la importación consentida vuelve a leer la fuente y valida el
  fingerprint revisado.

## Validación local

- Suite completa en Python 3.13/Linux: **366 pruebas pasadas y 2 omitidas**.
  El test del reindexado local se aisló de Ollama para que la verificación de
  fallback sea determinista.
- `python -m build` creó el sdist y wheel `0.10.1`. El wheel se instaló en una
  ubicación temporal; la versión importada fue `0.10.1` y el dashboard estaba
  incluido.
- La matriz Python 3.10–3.13, Windows, navegador, auditoría de seguridad y
  Docker quedan bajo el workflow CI; el workflow de release bloquea la creación
  de artefactos hasta que CI pase para el SHA exacto del tag.

## Prueba de memoria OpenClaw en el entorno de referencia

El 2026-09-12 se verificó Graphtyn en el host y OpenClaw en una VM Docker
accesible por SSH: discovery enumeró 12 agentes, con memoria habilitada para 11.
La prueba aislada de `openclaw/career` creó una sesión sintética de dos mensajes,
confirmó atribución, búsqueda y recuperación MCP, respuesta del dashboard y
ausencia de duplicados al leerla de nuevo. Se creó mediante `memory session-start`;
por tanto verifica el flujo MCP y la separación del cerebro, no la importación
automática de esa sesión desde los archivos de historial de OpenClaw.

## Prueba de OpenCode y aislamiento por proyecto

- Las 34 pruebas de `test_history_import.py` pasan. La fixture OpenCode verifica
  lectura del esquema JSON, exclusión de reasoning/herramientas, IDs estables,
  selección exacta del workspace, idempotencia y sincronización repetida.
- Se inspeccionó la base local en modo de sólo lectura: 199 sesiones, de las que
  4 (916 mensajes) tienen `directory=/home/calero/Documentos/openclaw`. La
  previsualización seleccionó esas 4 y dejó las otras 195 ambiguas. Tras la
  importación consentida, el estado mostró 4 sesiones, 916 mensajes procesados,
  36 memorias y 227 temas en el proyecto; la vista temática simplificada del
  dashboard devolvió 232 nodos y 454 relaciones (4 sesiones, 1 identidad y
  227 temas).
- La captura continua quedó activa para `/home/calero/Documentos/openclaw` con
  revisión cada 60 segundos. El watcher no ejecuta enriquecimiento por IA en
  cada ciclo, así los chats nuevos se persisten sin esperar cientos de llamadas
  al modelo local; el enriquecimiento sigue disponible como acción separada.
  Las otras 195 sesiones permanecen fuera del proyecto porque su asociación no
  coincide con la ruta seleccionada.

## Límites de la validación

Esta prueba de instalación no sustituye la matriz multiplataforma, las pruebas
de navegador ni la CI de GitHub. La release no afirma que cada instalación SSH,
política de familia o proveedor de agente haya sido probada. La captura
continua requiere que el servicio quede activo; el estado se comprueba con
`graphtyn harness openclaw list` y `graphtyn memory status`.
