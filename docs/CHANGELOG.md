# Changelog

Este proyecto usa [Semantic Versioning](https://semver.org/) y versiones
compatibles con PEP 440.

## [Unreleased]

Sin cambios registrados.

## [0.10.1] - 2026-09-12

### Corregido

- La captura de OpenClaw remoto reutiliza la configuración SSH explícita en el
  servicio persistente. Al reconectar, actualiza y reinicia el watcher para que
  aplique esa configuración, y devuelve errores si systemd no logra activarlo.
- `harness openclaw discover` y `connect` aceptan `--ssh-config` y validan el
  archivo antes de iniciar la conexión.
- El adaptador de OpenCode lee `opencode-stable.db` con su esquema SQLite/JSON
  actual y conserva los IDs nativos de mensaje. La sincronización de un proyecto
  detecta esa base local si aún no hay una fuente configurada y enruta sesiones
  sólo cuando su ruta de workspace coincide exactamente.
- La previsualización de conversaciones envía el proyecto seleccionado y deja
  visibles las sesiones ambiguas para que no se importen a otro proyecto.
- Los trabajos de previsualización guardan sólo referencias y conteos; al
  autorizar una importación vuelven a leer el origen y rechazan historiales que
  cambiaron después de la revisión.
- La captura continua extrae y persiste conversaciones sin esperar al modelo
  local; el enriquecimiento de temas por IA queda separado y es opt-in en el
  watcher.
- El aislamiento de importación reconoce rutas POSIX y Windows aunque Graphtyn
  se ejecute en otra plataforma, y conserva la asociación exacta del proyecto.

## [0.10.0] - 2026-09-12

### Añadido

- `memory scope show|set` permite gestionar la política de propietario de cada
  espacio sin sobrescribir sus demás metadatos.
- `memory sync --all-spaces` descubre espacios registrados y continúa con los
  almacenes válidos cuando otro presenta un conflicto, dejando el error visible.
- La importación OpenClaw reconoce raíces de runtime configuradas y sigue
  `trajectory-path.json` hasta la transcripción canónica, comprobando que la ruta
  permanezca dentro de la fuente seleccionada.
- El índice de código incluye secciones Markdown y RST con referencias de archivo
  y línea, y redacta patrones comunes de credenciales. La búsqueda semántica de
  documentos usa una ruta de proyecto explícita.
- MCP stdio incorpora `memory_status`; `memory_context` y `graph_search` exponen
  límites de recuperación acotados.

### Corregido

- Las candidatas de relación conservan el alcance del propietario además de los
  filtros de agentes autorizados.
- Las respuestas de episodios incluyen identificadores de mensajes fuente.
- `SHA256SUMS` usa nombres relativos a los assets descargados para que pueda
  verificarse directamente desde la carpeta de descarga.

## [0.9.0] - 2026-09-12

### Añadido

- Descubrimiento y conexión nativos con OpenClaw desde `onboard` y la CLI; cada
  instalación y agente conserva su identidad y almacén privado.
- Relaciones de familia confirmables entre cerebros y subagentes, captura
  incremental de conversaciones nuevas y revisión explícita del historial
  anterior.
- Migración y consolidación revisable de memorias heredadas hacia el cerebro
  activo, preservando el archivo de origen y distinguiendo datos respaldados de
  datos nuevos.
- Vista OpenClaw del dashboard para revisar instalaciones, cerebros, relaciones,
  estado de captura y errores de sincronización.

### Seguridad y compatibilidad

- Los agentes sin relación confirmada permanecen aislados; la similitud de
  nombres no asigna propiedad ni parentesco.
- La integración remota usa un destino SSH explícito y no explora la red.
- La conexión nativa es específica de OpenClaw; otros harness requieren su
  propio adaptador.

## [0.8.0] - 2026-09-11

### Incluye

- Referencias estables `N-xxxxxx` para nodos de memoria, resolución por CLI,
  MCP y API, y copia directa desde el dashboard.
- Candidatas léxicas separadas de las aristas del grafo, con aceptación o
  rechazo auditables y permisos validados para ambos temas.
- Enriquecimiento opcional con Ollama local en segundo plano y resaltado de
  sólo el nodo seleccionado, sus vecinos y sus conexiones.

### Seguridad y estabilidad

- Aislamiento de cerebros por identidad completa, aplicado dentro de SQLite a
  sesiones, mensajes, temas, grafos, estadísticas, exportaciones y retención.
- Temas mixtos heredados quedan fuera de la vista de un cerebro, y dos agentes
  no continúan el mismo asunto dentro de espacios aislados.
- Registro atómico de cerebros nuevos y bloqueo de captura en espacios aún sin
  propietario. Las identidades cortas no coinciden con IDs cualificados.
- Resolución común de SQLite para CLI, API y MCP; una pareja de almacenes local
  y central produce un conflicto visible en vez de bifurcar datos.
- Roles y rutas de proyectos se validan también en las API REST heredadas.
  El API de memoria rechaza conexiones remotas sin autenticación y MCP conserva
  su token independiente.
- Backup/verificación por streaming y restauración con la API de backup SQLite,
  copia de seguridad previa y bloqueo exclusivo mientras se protege un almacén.
- El workflow de release espera CI satisfactoria para el SHA exacto etiquetado.
- El watcher de memoria respeta el intervalo configurado; Chromium ausente hace
  fallar el smoke en CI en vez de contar como validación aprobada.
- Corregida la aserción del smoke del dashboard para distinguir los modos de
  memoria simplificado y detallado que realmente muestra la interfaz.

Publicada como versión estable desde el commit
[`346bc6b`](https://github.com/CaleroAM/graphtyn/commit/346bc6b949b63cfcf459e576741b862bbff782c4).
La validación de release y sus límites están en
[release-validation-0.8.0.md](release-validation-0.8.0.md); la evaluación
comparativa está en [competitive-validation-0.8.0.md](competitive-validation-0.8.0.md).

## [0.7.0] - 2026-09-10

Memoria temática multiagente con captura incremental y soporte para el
transcript SQLite actual de OpenClaw.

### Incluye

- Temas, episodios, entidades, estados, referencias a mensajes y evolución
  auditable por proyecto.
- Recuperación por temas, ventanas de mensajes, cobertura y filtros desde API,
  MCP, CLI y dashboard.
- Importación completa e incremental de historiales JSON/JSONL y SQLite,
  incluyendo `agent/openclaw-agent.sqlite` y `transcript_events`.
- Captura `memory_ingest_turn` idempotente, extracción determinista y soporte
  para agentes distintos de OpenClaw/Evi.
- Vistas de memoria simplificada y detallada con paginación, filtros y paneles
  de conversación.
- Protección de proyectos ambiguos, separación de autenticación MCP y API
  local, y cobertura de procesamiento visible.

### Validación

- Suite completa: 289 pruebas pasadas y 2 omitidas.
- Sesión real de OpenClaw importada y procesada sin duplicados: 1.224 mensajes
  descubiertos y procesados.

## [0.6.1] - 2026-08-27

Versión correctiva de instalación y primer uso, derivada de una sesión real en
Windows.

### Corregido

- Salida CLI y MCP en UTF-8 incluso cuando Windows inicia Python con `cp1252`.
- Rutas Git normalizadas para que proyectos con carpetas anidadas no produzcan
  índices vacíos en Windows.
- `graphtyn onboard` inicializa, integra agentes e MCP y construye un índice útil
  en una sola orden.
- La integración de Antigravity instala la skill y el manifiesto MCP con perfil
  seleccionable; `agent-install all` ya no duplica archivos compartidos.
- El instalador PowerShell ejecuta onboarding e indexación antes de registrar el
  dashboard.

### Validación

- CI en Windows crea e indexa un proyecto C# con ruta Unicode y consola cp1252.
- Pruebas contractuales cubren UTF-8, índice persistido, perfil MCP y deduplicación.

## [0.6.0] - 2026-08-25

Primera versión pública estable.

### Incluye

- Grafo AST determinista, Tree-sitter opcional y relaciones con procedencia.
- Análisis de impacto, contexto compacto, validación de evidencia y reportes.
- MCP stdio/HTTP e instalación de políticas para agentes de código.
- Memoria semántica compartida, atribuida por agente, con importación histórica.
- Dashboard 2D/3D reorganizado por tareas, calidad de índice y memoria visual.
- Despliegue local, systemd y Docker Compose.
- Dashboard persistente administrable mediante `graphtyn service install
  --enable`, `status`, `start`, `stop`, `restart` y `uninstall`.
- Sanitización de secretos, exportaciones portables y pruebas adversariales.

### Límites conocidos

- Despliegue local/single-user; no incluye SSO, TLS administrado ni aislamiento multi-tenant.
- La calidad depende del lenguaje y debe verificarse contra código fuente.
- Las relaciones `INFERRED` y `AMBIGUOUS` no constituyen evidencia estructural.
- Graphtyn aún no se distribuye mediante PyPI.
