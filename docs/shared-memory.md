# Memoria compartida del proyecto

Graphtyn permite que Codex, AGY, OpenCode, OpenClaw y otros clientes MCP consulten
la misma memoria local aunque trabajen en sesiones diferentes.

## Qué guarda

- sesión, cliente y agente que originaron la información;
- mensajes autorizados, decisiones, resultados, correcciones y handoffs;
- referencias a archivos, símbolos, commits y pruebas;
- embeddings por hash y procedencia para recuperación auditable.

Una conversación no se vectoriza mágicamente: el cliente debe capturarla mediante
las herramientas de memoria o importar un transcript. La compactación del cliente
no elimina lo persistido. El embedding sólo se repite si cambia el contenido o el
modelo.

## Operación portable

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
Admite historiales JSON/JSONL anidados y bases SQLite con columnas comunes de
sesión, rol y contenido. Cada adaptador normaliza hacia el mismo `ingest_turn`,
por lo que redacción, compactación, embeddings y deduplicación no se bifurcan.
Las fechas originales se conservan separadas de la fecha de ingesta.
Cuando cambió la ruta del proyecto, `memory projects --path . --alias
/ruta/histórica` registra la equivalencia explícita antes de importar; una ruta
desconocida permanece ambigua y nunca se mezcla automáticamente.
Las conversaciones importadas aparecen en **Memoria de proyecto** como nodos
`memory_session` marcados como históricos. Cada nodo se conecta con el agente
que participó y con las memorias compactadas que produjo; el panel muestra hasta
100 sesiones recientes, incluidas las anteriores a Graphtyn.
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
