# Memoria compartida del proyecto

Graphtyn permite que Codex, AGY, OpenCode, OpenClaw y otros clientes MCP consulten
la misma memoria local aunque trabajen en sesiones diferentes.

## Qué guarda

- sesión, cliente y agente que originaron la información;
- mensajes autorizados, decisiones, resultados, correcciones y handoffs;
- referencias a archivos, símbolos, commits y pruebas;
- embeddings por hash y procedencia para recuperación auditable.

Una conversación no se vectoriza mágicamente: el cliente debe capturarla mediante
las herramientas de memoria, sincronización local o importar un transcript. La compactación del cliente
no elimina lo persistido. El embedding sólo se repite si cambia el contenido o el
modelo.

La memoria conversacional y el RAG documental son fuentes distintas. Para
documentación del repositorio, el parser crea nodos `documentation_section` con
archivo y líneas de origen; `graph_search_concepts` recupera sus fragmentos con
búsqueda léxica y embeddings locales. Si Ollama está configurado, se usa ese
modelo local; sin Ollama, el índice de características hash sigue funcionando,
sin enviar documentos a una API externa. La búsqueda documental opera sobre el
espacio indicado por `path`; no descubre ni combina otros proyectos por sí sola.

## Operación portable

Durante la instalación, `graphtyn setup --apply` pregunta si se desea activar la
memoria conversacional (`--memory on|off|ask`). Al activarla registra las fuentes
detectadas e importa historiales compatibles con el proyecto; no requiere indicar
el MCP en cada turno. Para instalaciones automatizadas usa `--memory on` o
`--memory off` (el valor `ask` no bloquea procesos sin terminal).

`graphtyn setup` detecta primero y sólo escribe con `--apply`. Los adaptadores se
gestionan con `graphtyn adapter`; las fuentes con `memory sources
add|test|remove|list`. `service install --kind systemd --enable` instala y activa
el dashboard persistente como servicio del usuario; Compose sólo genera el
artefacto para conservar control explícito sobre Docker.

El ciclo operativo completo no requiere privilegios root:

```bash
graphtyn service install --kind systemd --path /ruta/proyecto --enable
graphtyn service status
graphtyn service stop
graphtyn service start
graphtyn service restart
graphtyn service uninstall
```

El servicio escucha exclusivamente en `http://127.0.0.1:9210` y conserva la ruta
absoluta del ejecutable instalado para funcionar con pipx, virtualenv y NixOS.
La sincronización incremental se activa explícitamente con **Captura continua**
o `memory sync --watch --interval 10`. Registrar un proyecto por sí solo no
importa historiales: las conversaciones anteriores se previsualizan y requieren
consentimiento para evitar asignar sesiones ambiguas. Una vez activo, el watch
detecta sesiones nuevas y cambios de forma incremental; extrae temas en modo
determinista para no esperar al modelo local. El enriquecimiento por IA se puede
ejecutar aparte desde **Actualizar memoria** o pedir expresamente a la API del
watch con `enrich: true`.
Los tokens pueden residir en `GRAPHTYN_MEMORY_TOKENS_FILE` y rotarse por rol.

`graphtyn backup` usa la API de backup SQLite; `backup-verify` comprueba SHA-256
y `restore` previsualiza salvo `--apply`, conservando una copia recuperable.
Las bases se copian y verifican por bloques de 1 MiB. La restauración obtiene
un bloqueo exclusivo y se niega si hay operaciones activas de una instalación
Graphtyn actualizada; nunca reemplaza el archivo mientras SQLite tiene WAL abierto.
La compactación descarta intercambios casuales y la importación fusiona fragmentos
crecientes sin perder proveedor, agente, fecha o fuente.

## Recuperación

La consulta combina texto, similitud vectorial, recencia, confianza y expansión
acotada por vecinos. El paquete respeta un presupuesto y explica la procedencia.
Al cambiar de tema se ejecuta una recuperación nueva; no se arrastran todos los
nodos de la consulta anterior.

Al iniciar una sesión nueva en un proyecto, el agente debe llamar primero a
`memory_context` con el trabajo solicitado, su identidad real y
`mode: "continuity"`. Esto combina los recuerdos temáticos con hasta tres
actualizaciones recientes de cualquier agente que haya escrito en la memoria
compartida. Cada actualización incluye agente, proveedor, sesión, fecha, mensaje
fuente y el último intercambio usuario/agente disponible. Así, Codex puede
retomar lo que hizo OpenCode o AGY aunque su sesión no comparta el historial del
otro cliente. Las actualizaciones son evidencia histórica; se comprueban contra
el estado actual antes de afirmar que algo sigue vigente.

Los temas siguen separados por agente para conservar quién pidió o realizó cada
cambio. En un espacio de proyecto compartido, Graphtyn los conecta cuando la
evidencia identifica el mismo archivo dentro del repositorio o el mismo símbolo;
la extracción revisa mensajes de usuario, agente y herramienta, conserva la
referencia al mensaje fuente y normaliza las rutas al espacio del proyecto. Un
nombre de archivo sin ruta sólo se considera una coincidencia ambigua. También
se muestran como líneas ámbar punteadas las relaciones temáticas que aún esperan
revisión. Términos repetidos como el nombre del proyecto o del proveedor no crean
por sí solos una relación; los candidatos de baja especificidad se conservan
para auditoría, pero no saturan el grafo. Así, una coincidencia probable ayuda a
encontrar el otro tema, pero no se registra como hecho ni combina sus autores.

`memory_context` conserva sus campos existentes y agrega `related_topics` para
temas relacionados por evidencia explícita, con agentes, estado y tipo de
relación; `suggested_related_topics` contiene candidatos pendientes y marcados
como ambiguos. Los cerebros de agente mantienen su filtro de propietario y no
reciben relaciones de otros cerebros. La misma conducta sirve para cualquier
identidad de agente almacenada, sin una lista fija de proveedores.

En modo `continuity`, `source_messages` devuelve hasta tres mensajes históricos
de sesiones distintas, ordenados por coincidencia léxica y recencia. Esto evita
que varios turnos de una sola conversación ocupen todo el resumen breve. Para
leer la pregunta, respuesta y mensajes vecinos de una referencia, usa
`memory_message_window`; la ventana permanece dentro de esa misma sesión.

Cuando un agente de OpenClaw trabaja desde su cerebro y necesita recordar un
proyecto compartido, usa `memory_project_context` con el nombre, ID estable,
alias exacto o ruta registrada del proyecto. La herramienta resuelve un único
destino, combina recuerdos con actividad reciente atribuida, consulta sólo ese
almacén y aplica el alcance de lectura del token. Si
el nombre no coincide o pertenece a varios proyectos, devuelve el estado y los
candidatos sin elegir por similitud. `memory_agent_context` continúa limitado al
cerebro privado del agente y a memorias familiares publicadas explícitamente.

El modo continuity sólo etiqueta como reciente una fecha observada en la fuente
o una captura en vivo. Si una transcripción importada no trae fecha original,
Graphtyn conserva el mensaje como historial pero lo omite de la lista de
actividad reciente. Si hace falta detalle, el agente amplía una referencia con
`memory_message_window` una vez; una cobertura incompleta indica que la búsqueda
no garantiza recall total, no que haya que repetir la misma consulta.

El modo predeterminado `semantic` conserva la respuesta anterior y no agrega
actividad reciente. El modo `continuity` está disponible en MCP, API y CLI:

```bash
graphtyn memory context "¿qué se cambió recientemente en el panel?" \
  --agent codex --mode continuity --activity-limit 3 --path .
```

Una respuesta de contexto informa `retrieval_mode`, referencias y contabilidad
de tokens dentro del presupuesto. `memory status` y el Dashboard distinguen la
captura continua de la última consulta de contexto. Ver captura activa no prueba
por sí sola que un agente haya consultado la memoria.

Codex, CLI y Dashboard deben apuntar al mismo espacio. En particular, define en
`~/.codex/config.toml` `GRAPHTYN_HOME` con el directorio central ya configurado
para Graphtyn; no crees una base local adicional dentro del checkout. Confirma
la ruta efectiva mediante `memory status` antes de probar la recuperación.

El servidor MCP también debe quedar ligado al proyecto correcto. Si Codex puede
abrir varios repositorios o inicia el servidor desde un directorio distinto,
registra un servidor MCP con nombre propio y `--path` explícito:

```toml
[mcp_servers.graphtyn_project]
command = "graphtyn"
args = ["mcp", "--tool-profile", "full", "--path", "/ruta/al/proyecto"]

[mcp_servers.graphtyn_project.env]
GRAPHTYN_HOME = "/ruta/al/estado-compartido"
```

Conserva el mismo `GRAPHTYN_HOME` de los demás clientes. Después de reiniciar o
recargar Codex, verifica que `memory_status` indique la ruta de ese proyecto;
un servidor genérico sin `--path` puede heredar el directorio de trabajo del
cliente y consultar otro almacén.

La sincronización de un proyecto busca las fuentes locales de OpenCode, Codex,
Claude y Antigravity cuando existen. Importa automáticamente sólo sesiones cuya
ruta registrada coincide exactamente con el proyecto; una sesión sin metadatos
de workspace, como algunas transcripciones de AGY, permanece ambigua y debe
revisarse. OpenClaw remoto se conecta por la configuración explícita de su
instalación. El atributo de agente describe al autor y no vuelve privado un
proyecto compartido; los cerebros personales sí mantienen su alcance de
propietario.

Para que agentes compatibles sigan este flujo al comenzar una sesión, instala o
actualiza la política del proyecto conservando sus instrucciones existentes:

```bash
graphtyn agent-install codex --path .
graphtyn agent-install opencode --path .
```

La política administrada solicita contexto antes de usar Git como único registro
del trabajo anterior y evita volver a ingerir el transcript cuando el watcher ya
lo captura.

## Dashboard

`Memoria del proyecto` se carga al seleccionar el repositorio y muestra agentes,
sesiones, recuerdos y relaciones con código. El color atribuye autoría o
participación; no implica propiedad exclusiva del archivo. `Buscar en memoria`
filtra o recupera contexto dentro de esa vista.

El panel izquierdo mantiene catálogos separados para proyectos y cerebros.
Los proyectos tienen memoria temática ligada a su repositorio; cada cerebro es
un espacio de memoria de una identidad propietaria y sus alias explícitos. Las
sesiones de otros agentes se rechazan en descubrimiento y las filas importadas
por error se marcan `quarantined`, conservando auditoría y backup. La memoria
de un agente sigue disponible como consulta federada sobre los cerebros y
proyectos que tiene asociados, pero cada almacén aplica su filtro de identidad.
El registro no supone que todos los agentes se llamen Evi ni que el proveedor
sea la identidad: ambos datos se conservan por separado. Usa
`GET /api/agents` y `POST /api/agents/register` para administrar identidades.
Usa `GET /api/brains` o `POST /api/projects/register` con
`space_type: "agent_brain"` para administrar los espacios que aparecen bajo
`CEREBROS REGISTRADOS`.
La vista `Topología de agentes` sólo dibuja fuentes, espacios y relaciones que
están configuradas u observadas, con procedencia en sus metadatos.

## Operación

```bash
graphtyn memory status --path .
graphtyn memory doctor --path .
graphtyn memory search --path . --query "decisión de autenticación"
graphtyn memory context --path . --query "cambio de autenticación"
graphtyn memory benchmark --path .
graphtyn memory scope show --path /ruta/al/cerebro
graphtyn memory scope set --path /ruta/al/cerebro --space-type agent_brain --agent-id openclaw/main
```

`memory scope set` agrega propietarios explícitos por defecto; `--replace-agent-ids`
reemplaza la lista y `--clear-agent-ids` la vacía de forma deliberada. MCP stdio
y HTTP exponen `memory_status`; HTTP requiere pasar el path del espacio para que
la consulta no caiga en un almacén por defecto. `memory sync --all-spaces`
continúa con los demás espacios si detecta una base local/central duplicada y
deja ese conflicto asociado sólo al espacio afectado.

El contrato MCP, seguridad y modelo de datos están en
[`shared_semantic_memory_plan.md`](shared_semantic_memory_plan.md).

## Bootstrap histórico y API v1

`memory bootstrap` descubre primero y sólo importa con `--apply --consent`.
La vista previa es inmutable y admite `--session ID` repetible para limitarse a
conversaciones concretas. Los JSONL se procesan por streaming, con límite por
registro, por lo que los historiales multi-GB no se cargan completos en memoria.
Antigravity reconoce `USER_EXPLICIT`/`MODEL`, usa `brain/<id>` como identidad de
sesión y toma sólo `logs/transcript.jsonl`, evitando copias compactadas y ruido.
Admite historiales JSON/JSONL anidados y bases SQLite con columnas comunes de
sesión, rol y contenido. Cada adaptador normaliza hacia el mismo `ingest_turn`,
por lo que redacción, compactación, embeddings y deduplicación no se bifurcan.
OpenCode usa un esquema distinto: `session`, `message` y `part` almacenan los
roles y fragmentos en JSON. Graphtyn reconoce `opencode-stable.db`, conserva IDs
nativos y sólo toma partes de texto; reasoning, herramientas y salidas técnicas
quedan fuera. En una sincronización por proyecto puede descubrir esta base local
sin configurarla manualmente y sólo acepta sesiones cuyo `directory` coincide
exactamente con la ruta registrada. Las demás quedan ambiguas.
OpenClaw también puede guardar el transcript canónico en
`agent/openclaw-agent.sqlite`; Graphtyn lee `transcript_events` (incluidos sus
roles e IDs nativos) y no depende de la tabla FTS derivada. Esto permite importar
sesiones creadas después de la migración de OpenClaw sin confundir el índice de
búsqueda con la fuente de conversación.
En archivos JSONL, la detección revisa también `OPENCLAW_STATE_DIR`,
`OPENCLAW_HOME`, `OPENCLAW_CONFIG_PATH` y `*.trajectory-path.json`. Los punteros
se resuelven dentro de la fuente seleccionada; del trace sólo se lee
`session.started.data.sessionFile`, nunca mensajes, prompts ni resultados de
herramientas del registro técnico.
Las fechas originales se conservan separadas de la fecha de ingesta.
Cuando cambió la ruta del proyecto, `memory projects --path . --alias
/ruta/histórica` registra la equivalencia explícita antes de importar; una ruta
desconocida permanece ambigua y nunca se mezcla automáticamente.
Registrar una carpeta crea el espacio de memoria, pero no importa historiales
antiguos sin consentimiento: usa **Previsualizar** y después **Importar con
consentimiento**. Para sincronizar cambios nuevos, **Actualizar memoria** ejecuta
una pasada; **Activar captura continua** deja el watcher activo para ese espacio.
El estado del panel indica si la captura continua está activa. La previsualización
persiste sólo IDs, rutas y conteos; al autorizar la importación, Graphtyn vuelve a
leer la fuente y confirma que el historial no cambió desde la revisión.
Las conversaciones importadas aparecen en **Memoria de proyecto** como nodos
`memory_session` marcados como históricos. Cada nodo se conecta con el agente
que participó y con las memorias compactadas que produjo; el panel muestra hasta
100 sesiones recientes, incluidas las anteriores a Graphtyn.
El catálogo se pagina con `GET /api/memory/sessions?limit=100&offset=N` y admite
`query` por identificador, tarea o agente. Al seleccionar una sesión se puede
abrir su detalle y enfocar el mapa; el foco mantiene la sesión aislada y permite
cargar la siguiente página de temas sin cruzar conversaciones.
Cada nodo de memoria recibe una referencia pública persistente (`N-000001`) que
el dashboard muestra y permite copiar. `memory_node` o `memory node` resuelve
esa referencia dentro del almacén seleccionado.

Las coincidencias léxicas no crean aristas temáticas automáticamente. Las
candidatas se consultan con `memory_relation_candidates` o `memory relation-candidates`
y se aceptan o rechazan con trazabilidad mediante `memory_relation_review` o
`memory relation-review`. La vista de memoria sólo dibuja relaciones extraídas
o revisadas; el orden temporal permanece en los episodios.

Cuando `GRAPHTYN_MEMORY_SUMMARY_MODEL` o `OLLAMA_MODEL` apunta a un modelo
Ollama local, la captura termina rápido y un trabajador en segundo plano
propone títulos, resúmenes y clasificaciones de candidatas. El estado del
dashboard indica el modelo configurado y los enriquecimientos realizados. La
IA no fusiona temas ni marca pruebas como superadas: sus propuestas conservan
proveedor, evidencia y estado pendiente de revisión. `GRAPHTYN_MEMORY_AUTO_ENRICH=0`
desactiva ese trabajador.
Las fuentes admiten ruta local, `docker://contenedor/ruta`,
`ssh://usuario@host/ruta` y `ssh+docker://usuario@host:contenedor/ruta`. Se
registran con `graphtyn memory sources add`; Graphtyn transfiere por SSH/Docker
un tar comprimido y filtrado, procesa una copia temporal y la elimina incluso si
el adaptador falla. Las trazas `*.trajectory.jsonl`, imágenes y logs se excluyen.
Durante el descubrimiento tampoco se recorren archivos dentro de `skills`,
`templates`, `examples`, `fixtures`, `node_modules` o `.git`: aunque contengan
campos `role` y `content`, son recursos auxiliares y no conversaciones. La regla
es independiente del proveedor y funciona igual con una instalación que sólo
use OpenClaw, sólo Hermes o adaptadores adicionales.

Para sincronizar nuevas conversaciones por cerebro (la fuente debe estar
asociada explícitamente con `--workspace`):

```bash
graphtyn memory sync --path . --consent
graphtyn memory sync --path . --watch --interval 5 --consent
graphtyn memory sync --all-spaces --consent
```

El modo `--watch` conserva cursores y vuelve a procesar sólo datos nuevos. La
misma operación está disponible en el dashboard como “Actualizar memoria” o
“Actualizar todos los espacios”; “Activar captura continua” mantiene un
watcher persistente y su heartbeat aparece en `memory status`. MCP
`memory_ingest_turn` continúa disponible para checkpoints explícitos. Todos los
caminos deduplican, sanean secretos y generan embeddings locales.

Inicializa y registra un cerebro con propietario explícito:

```bash
graphtyn memory brain-init --brain-path /ruta/al/cerebro --name Evi \
  --agent-id openclaw/main --register
```

El registro se escribe atómicamente incluso cuando el cerebro es nuevo. Si aún
no se conoce el propietario, se puede omitir `--agent-id`: el espacio queda
pendiente y no acepta captura hasta asignarle una identidad. No uses un nombre
corto como `main` para representar `openclaw/main`; las identidades coinciden
completas y los alias deben registrarse explícitamente.

Asocia una fuente a un cerebro con `graphtyn memory sources add --workspace
/ruta/al/cerebro --agent-id openclaw/main`. `agent_id` es obligatorio para
sincronizar un cerebro; una fuente raíz que contiene varios agentes debe
apuntar a la subcarpeta de uno de ellos (por ejemplo `agents/main` o
`agents/career`). Las fuentes sin asociación o sin propietario se pueden
previsualizar, pero no se enrutan automáticamente a ningún espacio. CLI y dashboard deben usar el
mismo `GRAPHTYN_HOME`; compruébalo desde CLI con `graphtyn memory status
--path /ruta/al/espacio` y desde `GET /api/memory/status?path=...`. El campo
`db` debe ser idéntico. Sin `GRAPHTYN_HOME`, si aparecen una base local y otra
central, la operación se detiene con conflicto en vez de escoger una
silenciosamente. La variable explícita define el almacén central.

El propietario también se aplica a `memory_context`, `memory_search`, `memory_topics`,
`memory_topic`, `memory_node`, las ventanas de mensajes y ambos grafos. Una
consulta con un `N-xxxxxx` de otra identidad devuelve acceso denegado aunque el
identificador exista en el mismo archivo SQLite. Para reparar una importación
antigua sin borrar datos, usa el script auditable
`scripts/isolate_memory_agent.py`; marca sesiones y memorias como
`quarantined` y registra `agent_scope_quarantine`.

Para un agente remoto, el servicio debe publicar MCP con
`GRAPHTYN_MCP_TOKEN` y una interfaz alcanzable por el contenedor o VM. Ese token
protege sólo `/mcp`. Las llamadas HTTP de memoria usan
`GRAPHTYN_MEMORY_HTTP_TOKEN` (un token de administrador heredado) o
`GRAPHTYN_MEMORY_TOKENS` para asignar roles y rutas:

```bash
export GRAPHTYN_MEMORY_TOKENS='{"token-secreto":{"role":"writer","projects":["/srv/cerebro-evi"]}}'
```

No reutilices el token MCP como token REST. Las peticiones remotas al API REST
fallan cerradas si no hay autenticación de memoria; el dashboard de red debe
quedar detrás de un proxy con TLS y autenticación. Comprueba la conexión MCP
desde el runtime remoto con `tools/list` y confirma que aparece
`memory_ingest_turn`.

La identidad global combina remoto Git, rutas y alias para unir proyectos
renombrados. Las asociaciones con otro proyecto conocido se marcan ambiguas en
vez de importarse silenciosamente. `POST /api/v1/context` acepta
`scope.projects=["*"]` o `scope.paths` para recuperar entre proyectos y devolver
siempre el almacén de origen.

Los jobs `/api/v1/imports` son persistentes, cancelables y observables mediante
SSE. Los roles `reader`, `writer` y `admin` separan recuperación, captura y
administración. Exportación no incluye vectores y la retención protege estados
`verified` por defecto. El dashboard permite previsualizar e importar sin usar
la terminal.

Los tokens pueden limitarse a rutas concretas y tienen rate limit por identidad.
El almacén aplica permisos privados y soporta cifrado autenticado opcional con
`graphtyn[security]` más `GRAPHTYN_MEMORY_ENCRYPTION_KEY`. Cuando está activo no
se copia contenido cifrado a FTS; la búsqueda semántica continúa por embeddings.
# Memoria temática y captura incremental

El enriquecimiento local es incremental: cada tema conserva la huella de sus mensajes fuente, el modelo y la versión del prompt. Una segunda ejecución sin cambios hace cero llamadas; sólo los temas nuevos o modificados entran en la cola persistente. Los cambios de modelo o prompt se marcan `stale` y requieren `--force`. Un fallo transitorio se reintenta una vez y después queda `failed` para reintento manual. Las correcciones humanas quedan protegidas y cualquier propuesta posterior queda registrada sin sobrescribirlas.

El almacén conserva asuntos (`topics`), episodios (`topic_episodes`), referencias a mensajes (`topic_messages`) y cambios auditables (`topic_events`). También registra entidades concretas (`entities`) y sus vínculos con asuntos (`topic_entities`). La extracción determinista crea episodios con procedencia explícita; un modelo local puede enriquecer títulos y resúmenes si `GRAPHTYN_MEMORY_SUMMARY_MODEL` o `OLLAMA_MODEL` está configurado. La API externa sólo se usa con `provider=api` y sus variables de autorización.

La identidad se separa del asunto. Por ejemplo, `botón de Jugar`, `botón de Fichas`, `botón de Ajustes` y `botón de Volver` son cuatro entidades distintas. También se reconocen funcionalidades, módulos, reportes, pantallas, plataformas, referencias de archivo y símbolos Python explícitos como `reports.py`, `función calcular_reporte`, `clase ReportService` y `método listar_operadores`. En un CRM, `botón del reporte` y `funcionalidad del botón de operadores` quedan como asuntos independientes; una conversación posterior sobre `funcionalidad de operadores` puede continuar el segundo asunto aunque ya no mencione el botón. En un proyecto Python, una conversación sobre corregir `calcular_reporte` y otra sobre probarlo quedan vinculadas por `mismo símbolo`, aunque representen episodios de trabajo distintos. Los asuntos relacionados se conectan mediante relaciones explicadas como `mismo elemento`, `mismo símbolo`, `mismo concepto`, `mismo tipo`, `misma plataforma` o `tema de diseño`. Compartir una categoría general no fusiona trabajos.

La captura histórica se procesa por lotes con `memory stream` o `POST /api/memory/history/stream`. Cada lote confirma un cursor por fuente, sesión y posición; los IDs nativos evitan duplicados y una rotación sin IDs queda pendiente. `memory sync --watch` y el botón de captura continua ejecutan el sincronizador persistente y registran heartbeat; mostrar un comando no activa captura. El contenido histórico se trata como datos no confiables.

Interfaces equivalentes:

`memory topics-enrich [--session ID] [--force]` y `POST /api/memory/topics/enrich` permiten ejecutar o reprocesar explícitamente la cola. El detalle de cada tema expone `ai_status`, modelo, revisión de fuente, versión del prompt, fecha, error y referencias de mensajes; `memory status` agrega cobertura única y el estado de la cola.

- CLI `memory entities [consulta]`, `memory entity <id>`, `memory topics`, `memory topic`, `memory node N-000001`, `memory window`, `memory relation-candidates` y `memory relation-review`.
- MCP `memory_entities`, `memory_entity`, `memory_topics`, `memory_topic`, `memory_message_window`, `memory_topic_update`, `memory_node`, `memory_relation_candidates` y `memory_relation_review`.
- API `/api/memory/entities`, `/api/memory/entity`, `/api/memory/topics`, `/api/memory/topic`, `/api/memory/node`, `/api/memory/relation-candidates`, `/api/memory/relation-review`, `/api/memory/window` y `/api/memory/topic/update`.

Las ventanas usan 10 mensajes anteriores y 10 posteriores en la misma sesión, con presupuesto predeterminado de 3.000 tokens y cursores. `memory_context` mantiene 1.800 tokens por defecto, informa cobertura, pendientes, truncamiento y referencias; una respuesta encontrada no marca `do_not_expand` como completa.

El lienzo de “Memoria del proyecto” ofrece dos modos: `Simplificada` conecta temas, sesiones, agentes y relaciones temáticas; `Detallada` añade entidades y episodios de cada tema. El selector sólo aparece en esa vista y no altera Code AST, Semántico, Harness ni Cambios. Los mensajes se abren bajo demanda desde el episodio para conservar el rendimiento del navegador.
El grafo inicia con una página acotada y muestra el total procesado; “Cargar más
temas” amplía el proyecto o la sesión enfocada sin reemplazar lo ya visible.
En **Diseño del grafo**, mientras está activa esta vista, “Colores de memoria del
proyecto” permite editar por separado el núcleo y el halo de temas, sesiones,
agentes, episodios y entidades. Los colores se guardan localmente, se aplican en
2D/3D y en los estilos estándar, neuronal y holográfico, y no afectan las otras
vistas. La opción “Burbuja sigue al nodo” vincula ambos colores cuando se desea.
El selector de memoria incluye paletas listas para usar (Obsidian, Cyberpunk,
Dracula, Solarized, Nordic, Vaporwave, monocroma, Matrix y por comunidad) y
“Personalizada”, que conserva los colores elegidos manualmente. El apartado
“Halos / irradiación” permite apagar o encender la iluminación alrededor de
nodos, enlaces y pulsos. “Parpadeo de Vértices” se guarda junto con
esas preferencias y actualiza también el lienzo 2D cuando la simulación ya se
ha estabilizado. Las partículas direccionales usan un desfase, una velocidad y
una cantidad estables por enlace para que las señales salgan y lleguen de forma
irregular, sin sincronizar todo el grafo con un único ciclo.

Los estados de asunto son `abierto`, `en investigación`, `resuelto`, `reabierto` y `archivado`. La verificación es independiente (`sin verificar`, `declarado`, `prueba superada`, `prueba fallida`, `confirmado por usuario`). Las verificaciones requieren mensajes fuente compatibles y cada corrección, fusión o separación conserva un evento auditable.

Antes de migrar un almacén efectivo, compruébalo con `GET /api/memory/status` y crea un respaldo SQLite. La captura sólo se importa tras seleccionar explícitamente el proyecto y la sesión; sesiones ambiguas permanecen pendientes.

## Incorporar un legado al cerebro activo

`Legado histórico` y `Legado mixto` describen archivos de origen, no cerebros
que los agentes deban consultar en paralelo. Histórico identifica una memoria
anterior al flujo actual; mixto indica que el archivo puede incluir más de una
identidad. El dashboard los muestra aparte de los cerebros activos. El archivo
queda intacto como respaldo después de incorporar sus datos.

La consolidación se ejecuta para una identidad exacta y un único cerebro activo.
Primero valida en el dashboard que el destino pertenezca al agente y revisa la
vista previa. Desde CLI, la vista previa es el comportamiento predeterminado:

```bash
graphtyn memory consolidate \
  --source /ruta/al/archivo-legado \
  --target /ruta/al/cerebro-evi \
  --agent-id openclaw/nexus
```

Cuando los conteos y la atribución sean correctos, autoriza la copia:

```bash
graphtyn memory consolidate \
  --source /ruta/al/archivo-legado \
  --target /ruta/al/cerebro-evi \
  --agent-id openclaw/nexus \
  --apply --consent
```

`--source` debe estar registrado como `legacy`; `--target` debe ser un cerebro
activo registrado para esa misma identidad. Para migrar un legado mixto a varias
personas, repite el comando con el cerebro activo de cada persona. Graphtyn no
adivina propietarios ni fusiona Eve con Evi. En el dashboard, cada archivo e
identidad muestra su estado; **RESPALDADA** sólo significa que esa identidad
procedente de ese archivo ya se integró. No marca como integrados otros archivos
del mismo agente. La etiqueta **FUENTE ORIGINAL** indica que el archivo se
conserva para consulta y auditoría; por sí sola no significa que falte integrar
su contenido. **Revisar novedades** vuelve a contar los cambios y solicita
confirmación sólo si hay registros pendientes. Si ya existe una integración,
el dashboard usa el destino exacto guardado en su auditoría aunque el agente
tenga también un almacén familiar con la misma identidad.

La API equivalente es `POST /api/v1/memory/consolidations`. Envía
`source_path`, `target_path` y `agent_id` para obtener la vista previa. La
ejecución requiere `apply: true` y `consent: true`; responde con un `job.id` que
se consulta en `GET /api/v1/memory/consolidations/{job_id}`. Las dos rutas deben
estar dentro del alcance del token administrativo configurado.

Antes de escribir, Graphtyn crea una copia online de SQLite del legado y, si ya
existe, otra del cerebro destino. Conserva esas copias con checksum bajo
`legacy-backups/` dentro del almacén destino. Un ledger por conversación,
mensaje, recuerdo y tema hace que la operación sea incremental e idempotente;
si se interrumpe, vuelve a ejecutar el mismo comando o reanuda desde el
dashboard. La base original no se modifica.

Se copian mensajes de sesiones autorizadas, recuerdos explícitos y procedencia
de varios mensajes/sesiones. Los historiales en cuarentena quedan fuera. De una
sesión sin captura conversacional se conserva sólo el recuerdo explícito, sin
importar su transcripción. Los recuerdos que figuraban como verificados en el
archivo se incorporan como observaciones históricas: Graphtyn conserva su estado
anterior en la procedencia, pero no los presenta como una verificación actual.
Los temas y episodios consultables se reconstruyen desde los mensajes; el título,
estado, verificación y eventos anteriores también se conservan como evidencia
histórica. Las relaciones y revisiones se transfieren al grafo activo cuando
cada tema de origen corresponde a un único tema reconstruido para ese agente.
Si la correspondencia es ambigua, Graphtyn conserva la relación como un recuerdo
histórico que requiere revisión, sin crear una arista dudosa. El detalle de cada
elemento mantiene `capture_mode=historical_import` y referencias al archivo y a
sus IDs originales.

Al terminar, el agente consulta su cerebro activo junto con sus conversaciones
nuevas. Cuando la captura nativa está activa, los chats y sesiones nuevos se
guardan directamente en ese cerebro; no se agregan al archivo histórico. Los
archivos marcados LEGADO no entran a `memory sync --all-spaces` ni a captura
automática. Si el propio archivo histórico recibe elementos nuevos, usa
**Revisar novedades** o vuelve a ejecutar la consolidación: sólo se incorporan
los registros nuevos o cambiados. La publicación entre cerebros de una familia
sigue siendo explícita y no forma parte de esta migración.
