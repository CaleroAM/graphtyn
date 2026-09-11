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
El watch incremental es opcional mediante `--watch --interval 10`, evitando que
una reindexación pesada retrase el grafo de memoria por defecto.
Los tokens pueden residir en `GRAPHTYN_MEMORY_TOKENS_FILE` y rotarse por rol.

`graphtyn backup` usa la API de backup SQLite; `backup-verify` comprueba SHA-256
y `restore` previsualiza salvo `--apply`, conservando una copia recuperable.
La compactación descarta intercambios casuales y la importación fusiona fragmentos
crecientes sin perder proveedor, agente, fecha o fuente.

## Recuperación

La consulta combina texto, similitud vectorial, recencia, confianza y expansión
acotada por vecinos. El paquete respeta un presupuesto y explica la procedencia.
Al cambiar de tema se ejecuta una recuperación nueva; no se arrastran todos los
nodos de la consulta anterior.

## Dashboard

`Memoria del proyecto` se carga al seleccionar el repositorio y muestra agentes,
sesiones, recuerdos y relaciones con código. El color atribuye autoría o
participación; no implica propiedad exclusiva del archivo. `Buscar en memoria`
filtra o recupera contexto dentro de esa vista.

## Operación

```bash
graphtyn memory status --path .
graphtyn memory doctor --path .
graphtyn memory search --path . --query "decisión de autenticación"
graphtyn memory context --path . --query "cambio de autenticación"
graphtyn memory benchmark --path .
```

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
OpenClaw también puede guardar el transcript canónico en
`agent/openclaw-agent.sqlite`; Graphtyn lee `transcript_events` (incluidos sus
roles e IDs nativos) y no depende de la tabla FTS derivada. Esto permite importar
sesiones creadas después de la migración de OpenClaw sin confundir el índice de
búsqueda con la fuente de conversación.
Las fechas originales se conservan separadas de la fecha de ingesta.
Cuando cambió la ruta del proyecto, `memory projects --path . --alias
/ruta/histórica` registra la equivalencia explícita antes de importar; una ruta
desconocida permanece ambigua y nunca se mezcla automáticamente.
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

Para sincronizar nuevas conversaciones sin depender de una llamada MCP manual:

```bash
graphtyn memory sync --path . --consent
graphtyn memory sync --path . --watch --interval 5 --consent
```

El modo `--watch` conserva cursores y vuelve a procesar sólo datos nuevos; MCP
`memory_ingest_turn` continúa disponible para checkpoints explícitos. Ambos
caminos deduplican, sanean secretos y generan embeddings locales.

Para un agente remoto, el servicio debe publicar MCP con
`GRAPHTYN_MCP_TOKEN` y una interfaz alcanzable por el contenedor o VM. Ese token
protege sólo `/mcp`; el dashboard local usa `GRAPHTYN_MEMORY_HTTP_TOKEN` si se
quiere proteger también su API. Comprueba la conexión desde el runtime remoto
con una llamada `tools/list` y confirma que aparece `memory_ingest_turn`.

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

La captura histórica se procesa por lotes con `memory stream` o `POST /api/memory/history/stream`. Cada lote confirma un cursor por fuente, sesión y posición; los IDs nativos evitan duplicados y una rotación sin IDs queda pendiente. `--watch` ejecuta el sincronizador persistente y registra heartbeat en `history_watchers`; mostrar un comando no activa captura. El contenido histórico se trata como datos no confiables.

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

Los estados de asunto son `abierto`, `en investigación`, `resuelto`, `reabierto` y `archivado`. La verificación es independiente (`sin verificar`, `declarado`, `prueba superada`, `prueba fallida`, `confirmado por usuario`). Las verificaciones requieren mensajes fuente compatibles y cada corrección, fusión o separación conserva un evento auditable.

Antes de migrar un almacén efectivo, compruébalo con `GET /api/memory/status` y crea un respaldo SQLite. La captura sólo se importa tras seleccionar explícitamente el proyecto y la sesión; sesiones ambiguas permanecen pendientes.
