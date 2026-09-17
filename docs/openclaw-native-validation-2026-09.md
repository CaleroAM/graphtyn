# Validación de la integración nativa con OpenClaw — 13 de septiembre de 2026

## Entorno y alcance

Se validó Graphtyn en el host Linux y OpenClaw en la VM Docker accesible por SSH
(`root@192.168.122.79`). La instalación detectada fue
`openclaw-cb62d8e6ebece7f5`, con 12 identidades: 11 cerebros activos y `main`
desactivado por política local. El dashboard y el capturador nativo usan el
mismo almacén efectivo, `/home/calero/.graphtyn`.

Este resultado cubre ese despliegue concreto; no certifica instalaciones en
otros hosts, contenedores o proveedores de agentes.

## Cambios verificados

- Los cerebros de agentes ya no exploran por defecto las bases locales de
  OpenCode, Codex, Claude o Antigravity. Sólo examinan fuentes asociadas al
  cerebro o seleccionadas explícitamente. Los proyectos mantienen su
  autodetección local y el enrutamiento requiere evidencia de proyecto.
- `discover` refleja las relaciones efectivas del registro Graphtyn y devuelve
  aparte `config_relation_status` y `config_parent_id`, que describen el
  `openclaw.json`. El estado efectivo de la instalación es 8 relaciones
  confirmadas, 4 raíces y 0 pendientes.
- Cada cerebro conserva el inicio y fin del ciclo, la última sincronización
  correcta, contadores de ciclos y un resumen compacto sin contenido de
  mensajes. Exclusiones y errores quedan contabilizados por separado. El
  dashboard muestra el resultado del último ciclo y la fecha de la última
  sincronización correcta. Las alertas antiguas no ocultan el estado del watcher
  más reciente.

## Resultado en el entorno activo

Se reiniciaron el dashboard y el servicio nativo después de guardar una copia
SQLite de **20 de 20 almacenes** que podían ser alcanzados por cerebro, familia
o proyecto. Las copias se hicieron con `sqlite3.Connection.backup()`; todas
pasaron `PRAGMA integrity_check`. El manifiesto está en:

`/home/calero/.graphtyn/backups/openclaw-sync-schema10-20260913-221159/manifest.json`

La migración versionada 10 se aplicó a los 12 almacenes de agentes y 4 almacenes
familiares. El primer ciclo nativo terminó en los 11 cerebros activos:

| Medida agregada por cerebro | Resultado |
|---|---:|
| Sesiones descubiertas | 16 |
| Sesiones nuevas | 0 |
| Sesiones reutilizadas | 16 |
| Sesiones excluidas | 37 |
| Errores de sincronización | 0 |

Las 37 exclusiones se debieron a `before_capture_baseline`: son historiales
anteriores al cursor de captura incremental, no fallos ni conversaciones
perdidas durante esta sincronización. Una importación histórica requiere la
acción explícita documentada con `--import-history`.

Como referencia, los ciclos anteriores recorrían 3.316 candidatos agregados y
registraban 3.300 exclusiones por identidad en cada pasada, también sin errores
reales. Los contadores son por almacén, no sesiones únicas globales. La primera
pasada con el cambio encontró 16 sesiones y 37 exclusiones en total; el filtro
redujo el recorrido de fuentes predeterminadas ajenas a cada cerebro.

Las cuentas de sesiones y mensajes de los 12 cerebros no cambiaron frente a las
copias previas. El servicio nativo, el dashboard y los sincronizadores de
OpenCode/Antigravity siguen activos; los antiguos servicios manuales de Eve y
Evi están inactivos. El log del ciclo quedó en 2.331 caracteres, con cantidades
y motivos, sin imprimir contenido de conversaciones. El endpoint `/health`
respondió `ok` en la versión 0.10.2.

## Prueba de enrutamiento y búsqueda

Se comprobó una sesión E2E ya existente de `openclaw/nexus`: sus cuatro mensajes
quedaron registrados como enrutados, dos al proyecto TourMuseosPuebla y dos al
proyecto OpenClaw. La tabla de estado de enrutamiento conserva la atribución
`openclaw/nexus` y el resultado por proyecto. Las sesiones ambiguas o sin un
nombre de proyecto inequívoco permanecen sin asignación automática.

La búsqueda privada de los registros E2E existentes devolvió dos resultados
atribuidos a `openclaw/nexus` y uno a `openclaw/career`; no mezcló resultados
entre ambos almacenes.

La vista OpenClaw también se abrió con Playwright sobre el dashboard activo y
datos leídos de los almacenes reales: mostró 12 agentes, el último ciclo, la
última sincronización correcta y 0 relaciones pendientes, sin errores JavaScript.
La llamada de red del navegador se sustituyó por una respuesta construida con
`agent_status` para evitar cambiar credenciales del dashboard durante la prueba.

## Pruebas y límites

- `.venv/bin/pytest -q`: **403 aprobadas, 2 omitidas**.
- `python -m compileall -q graphtyn`: correcto.
- `git diff --check`: correcto.
- Las pruebas cubren la migración desde un esquema anterior, resultados
  persistidos por ciclo, fuentes privadas de cerebros y diferencias entre la
  relación de Graphtyn y la configuración OpenClaw.
- Esta copia tiene un almacén local y otro central para el proyecto OpenClaw.
  Por protección, el CLI sin `GRAPHTYN_HOME` rehúsa elegir entre ambos. Para
  operar sobre el mismo almacén que el dashboard y el watcher, debe usarse el
  valor configurado por el servicio (`/home/calero/.graphtyn`).
- Las pruebas de historial son incrementales; no importan automáticamente los
  historiales anteriores al cursor. Las conversaciones cuyo proyecto no está
  identificado con evidencia explícita continúan en el cerebro del agente o en
  revisión pendiente.

## Cierre de aceptación en la instalación activa — 14 de septiembre de 2026

Antes del backfill se creó otra copia con `sqlite3.Connection.backup()` de 19
almacenes SQLite (19/19 con `integrity_check=ok`):

`/home/calero/.graphtyn/backups/openclaw-pre-history-backfill-20260914-044014/manifest.json`

La conciliación de las 11 fuentes habilitadas encontró 53 sesiones candidatas
en total: 37 no estaban en los cerebros y 16 ya existían. Se ejecutó el mismo
flujo de `sync_memory_workspace` con extracción determinista y cursor histórico
temporal, sin modificar los cursores persistentes. Resultado final: 37 sesiones
añadidas, 16 reutilizadas, 0 ambiguas y 0 errores. Se importaron además 16
segmentos a memorias de proyecto; no hubo segmentos rechazados ni fallidos.

La única sesión inicialmente ambigua pertenecía a `openclaw/nexus` y llevaba
como workspace `/home/node/.openclaw/workspace/nexus`. Esa ruta identifica el
workspace privado del agente, no un proyecto. Graphtyn ahora la conserva como
procedencia, la guarda en el cerebro de Nexus y la deja sin asignación de
proyecto hasta que un mensaje nombre uno. Una prueba de regresión cubre esta
regla.

Para probar captura automática se creó una conversación nueva de OpenClaw en
`nexus`, con dos mensajes. El watcher la capturó en su ciclo normal, atribuyó
ambos mensajes a `openclaw/nexus` y los enrutó al proyecto OpenClaw por su mención
explícita. Después de reiniciar el watcher, el nuevo ciclo informó 0 sesiones
nuevas, 12 reutilizadas y 0 errores. Los conteos de sesiones y mensajes del
cerebro de Nexus y del proyecto OpenClaw no cambiaron; siguen existiendo una
sola sesión de prueba y sus dos mensajes en cada almacén correspondiente.

Los 63 archivos `trajectory-path.json` observados en Career apuntan a trazas que
no están presentes en la fuente activa. La base canónica sí contiene 25 ventanas
de sesión; 24 tienen mensajes conversacionales indexados, y las 24 fueron
encontradas por Graphtyn: 23 importadas y una ya existente, con 1.189 mensajes
de usuario/asistente contabilizados. La ventana restante no tiene mensajes
conversacionales indexables. Los punteros ausentes no representaron sesiones
perdidas de esa base; quedan como advertencias de metadatos sin traza.

Validación posterior al ajuste: `.venv/bin/pytest -q` — **404 aprobadas, 2
omitidas**; `compileall`, `git diff --check`, `/health` y ambos servicios
systemd correctos. Esto cierra la aceptación de captura, recuperación histórica,
atribución, enrutamiento e idempotencia para esta instalación host + VM Docker.
No certifica automáticamente otras topologías de OpenClaw ni fuentes históricas
que no estén presentes en la instalación conectada.
