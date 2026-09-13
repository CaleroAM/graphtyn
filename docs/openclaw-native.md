# Conexión nativa con OpenClaw

Graphtyn detecta OpenClaw sin depender del nombre visible del agente. Cada cerebro se identifica por `instalación + openclaw/<id>`; Evi, Eve, Junio, Friday o cualquier otro nombre son sólo etiquetas.

## Descubrir y conectar

`graphtyn onboard` busca OpenClaw local y fuentes remotas ya registradas. Si
encuentra una sola instalación accesible, crea los almacenes privados, conserva
las relaciones ya confirmadas y activa la captura incremental; fija el cursor al
momento de conexión, así que no importa conversaciones anteriores. Si encuentra
varias, muestra sus IDs y espera una selección con
`--harness-installation <id>`. Usa `--no-harness-auto` para omitir esta detección.

En el mismo host:

```bash
graphtyn harness openclaw discover
graphtyn harness openclaw connect --installation openclaw-<id>
```

En VM o servidor, indica un destino SSH conocido. Graphtyn no escanea la red:

```bash
graphtyn harness openclaw discover \
  --ssh-target root@192.0.2.10 \
  --data-root /srv/openclaw/data

graphtyn harness openclaw connect --installation openclaw-<id> \
  --ssh-target root@192.0.2.10 \
  --data-root /srv/openclaw/data \
  --parent devops=nexus --parent design=nexus --independent nexus --independent career
```

El destino necesita una clave SSH no interactiva y permiso para leer `openclaw.json` y los directorios de agentes. `connect` sólo conserva un almacén anterior cuando todas sus fuentes lo atribuyen al mismo ID canónico; si el almacén heredado mezcla agentes, crea uno privado nuevo. Puedes fijar rutas con `--brain AGENTE=RUTA`. Las identidades nuevas reciben directorios aislados. Confirma las relaciones padre/hijo sólo cuando reflejen la jerarquía real.

Para que `onboard` detecte una instalación remota desde el primer uso, configura
`GRAPHTYN_OPENCLAW_SSH_TARGET` y `GRAPHTYN_OPENCLAW_DATA_ROOT` en el entorno,
además de `GRAPHTYN_MCP_URL` y `GRAPHTYN_MCP_TOKEN` si OpenClaw aún no tiene
registrado el servidor MCP. El autodetector nunca prueba hosts SSH arbitrarios.

`connect` asocia la fuente de historial a su agente, registra los cerebros y trata de iniciar un servicio `systemd --user` que sincroniza cada cinco minutos. Por defecto fija un cursor de inicio y procesa sólo conversaciones nuevas o modificadas después de conectarse. Para procesar historial anterior, activa esa decisión explícitamente con `--import-history`. La operación es incremental; volver a ejecutarla conserva los cursores y relaciones confirmadas.

La política de memoria se guarda por agente y por instalación. Todos los agentes
quedan habilitados por defecto, incluido uno llamado `main`; desactivar `main`
para una instalación no cambia el comportamiento de otros usuarios o
instalaciones. La identidad desactivada permanece registrada, pero Graphtyn
retira su fuente de historial, la omite en el sincronizador nativo y rechaza
escrituras al cerebro incluso si se intenta ingresar una conversación por MCP,
API o CLI. No borra datos que ya existan. Al volver a habilitarla, captura desde
ese momento y no importa historial anterior automáticamente.

```bash
graphtyn harness openclaw memory-policy --installation openclaw-<id> \
  --agent main --state disabled --reason "agente predeterminado sin memoria"
graphtyn harness openclaw list
```

El estado `memory_enabled` se muestra en el registro y su historial queda en
`memory_policy_events`. Para reanudar la captura, usa `--state enabled`; la
fuente se vuelve a registrar con un cursor nuevo.

Para usar MCP, `connect` conserva una entrada Graphtyn válida que ya exista en `openclaw.json`. Si configuras `GRAPHTYN_MCP_URL` y `GRAPHTYN_MCP_TOKEN`, también escribe la entrada MCP, haciendo una copia `openclaw.json.graphtyn-backup-<timestamp>` antes. El token no se imprime. Si no hay URL/token, fuentes y watcher pueden quedar configurados, pero `connect` informa que la consulta MCP sigue pendiente y devuelve estado incompleto.

```bash
export GRAPHTYN_MCP_URL='https://graphtyn.example/mcp'
# Carga GRAPHTYN_MCP_TOKEN desde el gestor de secretos del host.
graphtyn harness openclaw connect --installation openclaw-<id> \
  --ssh-target root@192.0.2.10 --data-root /srv/openclaw/data \
  --parent devops=nexus --parent design=nexus --independent nexus --independent career
```

Después de modificar `openclaw.json`, reinicia el gateway de OpenClaw con el método habitual de ese despliegue. Graphtyn no reinicia servicios del harness automáticamente.

## Cerebros, subagentes y memoria familiar

Por defecto cada `agents.entries.<id>` tiene un almacén privado. Graphtyn no convierte una similitud de nombre ni una etiqueta como “Evi DevOps” en parentesco. Sin relación confirmada, el agente queda `pending` y sólo consulta su almacén propio.

Usa estas operaciones para revisar y cambiar relaciones:

```bash
graphtyn harness openclaw list
graphtyn harness openclaw relate --installation <id> \
  --child devops --parent nexus --confirm
graphtyn harness openclaw relate --installation <id> \
  --child career --independent --confirm
```

La relación se registra como confirmación humana. En esta instalación, Evi aparece como `openclaw/nexus`; `main` es otra identidad. Usa los IDs de `agents.entries`, no los nombres visibles. Los agentes comparten recuerdos sólo cuando el autor publica el recuerdo concreto con `memory_agent_publish`. El autor puede revocar esa copia. `memory_agent_context` recupera el cerebro privado y las publicaciones explícitas de su familia; no fusiona los almacenes ni permite consultar rutas ajenas.

Por eso **Familia · Eve** y **Familia · Evi** pueden estar vacías aunque sus
cerebros privados tengan recuerdos. Esos nombres corresponden a las raíces de
agente de esta instalación; no son espacios globales ni nombres fijos del
producto. Cada instalación y cada agente raíz tiene su propia familia, nombrada
con la etiqueta visible de esa raíz. Otros usuarios pueden tener familias
distintas, con los nombres y miembros de sus propios agentes.

El legado histórico y las conversaciones privadas no se copian automáticamente
a la familia. El dashboard muestra los miembros de la familia seleccionada y
explica que un recuerdo aparecerá allí después de publicarse con
`memory_agent_publish`.

## Archivos `LEGADO`: histórico y mixto

`LEGADO` es una marca explícita del registro de espacios; no es un agente nuevo
ni una etiqueta que Graphtyn deduzca sólo por el nombre de una carpeta. Los
archivos se conservan y se pueden abrir desde **Cerebros registrados** para
consultar su grafo e historial. No representan los cerebros activos de OpenClaw.

- **Legado histórico · Cerebro Eve** conserva conversaciones previas a la
  conexión nativa. Sus registros usan tanto el alias antiguo `career` como el
  ID actual `openclaw/career`. El cerebro activo de Eve vive en su ruta privada
  nueva; el archivo conserva el contexto anterior para consulta.
- **Legado mixto · Cerebro Evi** conserva datos antiguos atribuidos a varias
  identidades y proveedores en un solo almacén. No se puede tratar el conjunto
  como si perteneciera a Evi: eso volvería a mezclar, por ejemplo, datos de
  `main`, `nexus`, `qa` y otras identidades. Sirve para inspección histórica,
  mientras la recuperación activa usa los almacenes separados por agente.

El dashboard y la API excluyen estos espacios de **Actualizar todos los
espacios** y de la captura continua global; pedir sincronización o captura
continua sobre un archivo `LEGADO` devuelve `409`. Así se mantienen disponibles
para consulta sin volver a introducir sus fuentes en el flujo actual. El nuevo
OpenClaw nativo captura en los cerebros privados registrados para cada ID.
Cuando una identidad de un archivo se integra, el dashboard la marca
**RESPALDADA** en ese archivo concreto. Los chats nuevos se sincronizan con el
cerebro privado activo de OpenClaw mientras la captura esté habilitada; no
actualizan el archivo legado. **Revisar novedades** comprueba si ese archivo
recibió datos nuevos y sólo vuelve a integrarlos después de confirmación.

En OpenClaw, usa el MCP `memory_agent_context` con el ID real, por ejemplo `openclaw/devops`. Si hay una única instalación conectada, `installation_id` se resuelve automáticamente. Para varias instalaciones, pásalo explícitamente. `memory_agent_status` informa relación, cobertura y estado de captura.

## Qué se modifica en OpenClaw

No hace falta modificar el código base de OpenClaw para capturar conversaciones o resolver cerebros. El único ajuste habitual es registrar Graphtyn como servidor MCP en `openclaw.json`; el conector lo puede hacer con backup si URL y token están en el entorno. Los agentes deben tener la política de Graphtyn para consultar su identidad, no usar rutas de otros agentes y evitar publicar sin autorización.

El fork local de OpenClaw incluye, además, un adaptador opcional para que el retrieval interno de Nexus use `memory_agent_context` por identidad (`NEXUS_MEMORY_BACKEND=graphtyn`, `GRAPHTYN_INSTALLATION_ID` y `GRAPHTYN_AGENT_IDS_JSON`). Esa extensión no es necesaria para OpenClaw estándar. El adaptador anterior `GRAPHTYN_BRAIN_MAP_JSON` sigue disponible para instalaciones manuales antiguas.

Para endurecer el aislamiento remoto, define credenciales MCP distintas por agente con el campo `agent_id` y limita `projects` al cerebro privado y, cuando aplique, al almacén familiar. `GRAPHTYN_OPENCLAW_REQUIRE_AGENT_TOKEN=1` exige credencial ligada al agente para las herramientas de memoria por agente. Un token administrador compartido no es aislamiento de autorización.

## Verificación y resolución de problemas

```bash
graphtyn harness openclaw list
systemctl --user status graphtyn-openclaw-<hash>.service
graphtyn memory status --path <ruta-del-cerebro>
```

El estado debe mostrar cada fuente bajo su dueño, captura activa y relaciones pendientes/confirmadas. Si `systemd --user` no está disponible, ejecuta el comando de observación que muestra Graphtyn:

```bash
graphtyn memory sync --installation openclaw-<id> --watch --interval 300 --consent
```

`--consent` autoriza la sincronización de las fuentes asociadas. El cursor por defecto evita importar el historial existente; la importación anterior requiere además `--import-history`. Para restaurar la configuración OpenClaw previa, copia el backup `openclaw.json.graphtyn-backup-*` sobre el config activo y reinicia el gateway.

Esta conexión es específica de OpenClaw. Hermes se conectará mediante su propio descubridor y adaptador; no se autodetecta todavía.

## Dashboard

Abre **Explorar → OpenClaw** para ver las instalaciones conectadas, cada identidad
`openclaw/<id>`, su tipo de relación, la ruta de su cerebro privado, el volumen de
sesiones/memorias y los errores de captura. La pantalla diferencia la última
captura almacenada del heartbeat del sincronizador periódico. Las relaciones
pendientes permanecen aisladas y se señalan para revisión.

**Sincronizar ahora** encola en segundo plano una sincronización incremental de
los cerebros de esa instalación. El dashboard muestra progreso y fallos por
cerebro; volver a ejecutar la sincronización no duplica conversaciones ya
capturadas. Esta acción no conecta una instalación nueva ni cambia
`openclaw.json`: para detectar y conectar una instalación usa los comandos CLI
de arriba. El endpoint de administración requiere un token con rol `admin` si
Graphtyn tiene autenticación de memoria configurada.
