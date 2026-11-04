# Changelog

Este proyecto usa [Semantic Versioning](https://semver.org/) y versiones
compatibles con PEP 440.

## [Sin publicar]

### Añadido

- `graphtyn antigravity-context` (`install|uninstall|status|hook`): hook de primer
  turno para Antigravity en `.agents/hooks.json` (`PreInvocation`). Lee el mensaje
  de la transcripción e inyecta una vez por turno. Opcional, requiere `--consent`.
  No ahorra tokens de forma general: ver
  `benchmarks/antigravity_hook_2026-11-03/report.md`.

### Corregido

- Decir «en este proyecto» o «in this repository» ya no convierte una pregunta
  sobre código en un `overview`. Antes, «¿Qué hace la función X en este proyecto?»
  devolvía el resumen del repositorio, a menudo sin esa función; y «en este
  repositorio» activaba `persistence`. Esas frases tampoco influyen ya en qué
  código se selecciona. Las preguntas sobre el proyecto entero siguen siendo
  `overview`.
- `impact` ya no afirma que un símbolo no tiene consumidores cuando el grafo sí
  los tiene. Con varias sobrecargas (`vformat_to` en fmt tiene 9), estas agotaban
  el presupuesto de nodos antes de recorrer a los consumidores, y el paquete
  declaraba cero y evidencia suficiente. Ahora ocupan como mucho la mitad del
  presupuesto, y `direct_consumers` cuenta sobre todo el grafo y lista con
  `archivo:línea` los que no entran.
- «¿Quién llama a X?», «¿Dónde se usa X?» y «¿Qué se rompe si cambio X?» pasan a
  `impact`, también si la frase incluye «si cambia X».
- La clasificación reconoce el alcance, las preguntas sobre el proyecto y las de
  consumidores también en portugués, francés, alemán e italiano.
- `impact` añade `direct_consumers.text_references`: usos que el índice no resuelve,
  como las llamadas con plantilla de C++, hallados con una búsqueda de texto acotada
  y marcados como pistas sin verificar. Si no caben todos, el paquete ya no le dice
  al agente que pare.
- «¿Qué hace X?» sobre un símbolo nombrado devuelve su cuerpo entero y quién lo
  llama. Antes elegía líneas según las palabras de la pregunta (`con` coincidía con
  `config_`), dejaba 69 de las 233 líneas de `activeExpireCycle` y declaraba la
  evidencia completa. Un cuerpo que no cabe se informa como `source_body:<símbolo>`
  en `missing`.
- Los extractos empiezan en el comentario de la declaración, no dentro de la función
  anterior.
- Medición con agentes en Antigravity (80 sesiones): calidad igual o mejor en dos
  conjuntos con un 59 % y un 30 % menos de tokens, con excepciones que recoge
  `benchmarks/intent_impact_2026-11-04/report.md`.
- El README ya no dice que Antigravity carece de hooks, ni indica `agy mcp list`
  para verificar la entrada de proyecto: ese comando sólo muestra los servidores
  globales.

## [0.12.0] - 2026-11-02

Validación de la versión: `docs/release-validation-0.12.0.md`.

### Añadido

- Panel «Actividad» del dashboard: qué preguntan los agentes en este proyecto
  (por MCP, MCP HTTP o hook), con su cliente y hora, qué entidades y etapas
  recibieron y por qué entró cada entidad. «Ver en el grafo» deja sólo ese
  paquete y «Seguir en vivo» lo hace con cada consulta nueva. Incluye un resumen
  de 7 días; sólo cuenta lo que pasa por Graphtyn, no lo que el agente lee después.
  Las preguntas se guardan en el `history.db` local y se borran a los 30 días; el
  panel permite apagar el registro por proyecto, y MCP y los hooks lo respetan.
- Ayuda del dashboard (botón `?` o tecla `?`): qué muestra cada vista, cómo leer
  colores y líneas, y atajos (`/` busca, `A` modo anónimo, `Esc` cierra).
- Modo anónimo (`A`): difumina proyectos, archivos, comunidades y paneles, y el
  grafo usa nombres genéricos, para compartir pantalla sin revelar código.
- Proyecto de ejemplo: «Probar con un proyecto de ejemplo» (bienvenida, ayuda y
  dashboard vacío) copia una tienda pequeña a `GRAPHTYN_HOME/demo-projects/` y
  la registra, para explorar el dashboard sin usar código propio.

### Cambiado

- El dashboard explica lo que muestra: una leyenda con el color de cada tipo
  de nodo (archivo, clase, función, documento; en Semántico también
  subsistema y arquitectura), una línea por vista que se puede ocultar, y un
  mensaje en Topología cuando aún no hay agentes en lugar de un nodo suelto.
  El selector «Memoria» sólo aparece en su vista, el panel de comunidades está
  en español y deja de repetir el número de nodos.

### Corregido

- Las gramáticas de Tree-sitter se instalan por defecto (unos 4 MB, con wheels
  para Linux, macOS y Windows). Antes eran un extra opcional que el comando de
  instalación del README y `install.ps1` no pedían: esas instalaciones usaban en
  silencio el parser de respaldo, sin relaciones de llamada exactas. El extra
  `.[treesitter]` sigue aceptándose. Si una gramática no puede cargarse, lo avisan
  «Calidad y contexto» y `graphtyn reindex` en local.
- Dashboard abierto desde la red (no loopback): Code AST, Semántico,
  Topología, Reindexar y el registro de proyectos enviaban la petición sin el
  token guardado, y el servidor la rechazaba aunque el token fuera válido.
  Ahora todas las rutas protegidas lo envían, y el aviso indica dónde
  escribirlo (Acciones → Administrar memoria → Token HTTP).
- El indicador «MCP Activo» era un texto fijo en verde. Ahora consulta
  `/api/service`: muestra si el servicio responde y si su `/mcp` por HTTP
  acepta clientes. Si el servicio deja de responder con la página abierta, lo
  avisa y recarga el grafo cuando vuelve.
- El dashboard ya no carga d3, force-graph ni 3d-force-graph desde
  cdn.jsdelivr.net: el paquete incluye versiones fijas (`graphtyn/web/vendor/`,
  verificadas contra la integridad publicada en npm). Sin conexión, o cuando el
  CDN fallaba, el grafo no se dibujaba. El smoke test de navegador informa
  ahora, cuando falla, de los errores de consola, los tiempos de la API, el
  estado del grafo y el final del log del servidor.
- Dashboard: al cambiar de proyecto o recargar el grafo, la instancia anterior
  de ForceGraph se destruye. Antes solo se quitaba su canvas del DOM y su
  simulación seguía redibujando fuera de pantalla; con un grafo grande dibujado
  antes del cambio, la página quedaba bloqueada decenas de segundos. Esta era la
  causa principal del fallo intermitente del smoke test de navegador en CI.
- La API (`graphtyn.api.main`) y los gestores de trabajos resuelven
  `GRAPHTYN_HOME` al usarlo y no al importarse: un `GRAPHTYN_HOME` fijado
  después de importar se respeta, e importar el módulo ya no crea
  `~/.graphtyn`. Por eso los tests escribían en el directorio real del usuario,
  incluido `registered_projects.json`.
- El contexto que inyecta el hook (Claude y Codex) muestra `call_outline` con
  rutas reales (`ldo.c:1083`) en vez de alias `F5:1083`: el mapa `files` no se
  incluye en ese texto, así que el agente no podía resolver el alias y buscaba
  la etapa a mano. En las sesiones de test3 y test4, entre el 19 % y el 26 % de
  las búsquedas posteriores al hook perseguían una etapa que el outline ya
  nombraba (10-19 % con MCP, que sí trae el mapa).
- Ruby: las llamadas conservan el sufijo `!`/`?` del método (`route!`,
  `valid?`), y `self.x`, `dup.x` y `clone.x` se resuelven como llamadas a la
  propia clase. Antes `dispatch!` aparecía llamando a `route` (otro método) y
  `call!` no tenía llamadas entrantes. Rails gana 3.917 relaciones y Sinatra 45;
  la cobertura del banco de tareas no cambia de forma apreciable (de 91 tareas,
  una gana un hecho y otra pierde uno neto).

## [0.11.0] - 2026-11-01

### Añadido

- `GRAPHTYN_FLOW_POLICY` (`KEY=VALUE,...`) ajusta la política de los paquetes
  de flujo sin tocar el código; una clave desconocida se avisa por stderr y se
  ignora. `coverage.py --policy` y `run_variants.py` la usan para comparar
  políticas.
- `call_outline` incluye, con la marca `S`, funciones que comparten con una
  etapa un campo de estado poco usado (`server.ready_keys`): flujos que pasan
  por estado compartido y no por llamadas. Redis BLPOP en desarrollo: 5 → 7/8.
- Banco de tareas: cuarto conjunto de prueba (jq y Sinatra, más tareas
  `impact`, `tests`, `bindings` y `persistence`), `run_variants.py`,
  `judge_answers.py` (juez semántico) y `paired_ci.py`. `analyze_variants.py`
  calcula el coste en USD con los precios de lista de cada modelo.
- `AGENTS.md`, la skill y la política del instalador explican `call_outline`.

- Peticiones de flujo (`graph_query_intent`, hook): la mitad del presupuesto de
  entidades se reserva para las etapas a las que llama el punto de entrada,
  aunque no compartan palabras con la petición; las utilidades llamadas desde
  todas partes no cuentan. `call_outline` lista hasta 12 etapas más como
  `[caller, callee, F:línea, E|I]`, sin su código. Un comando escrito en
  mayúsculas (`BLPOP`) incluye su función (`blpopCommand`). El presupuesto por
  defecto sigue en 10 entidades. Cobertura del paquete: desarrollo 56,2 → 62,8 %,
  test2 60,8 → 66,6 %, test3 (nuevo, con Lua) 35,9 → 48,8 %, sin más tokens.
  En 300 sesiones reales, el coste ponderado baja un 19–21 % frente a no usar
  Graphtyn, con la misma calidad.
- Tercer conjunto de prueba (`benchmarks/task_bank_2026-10-28/test3/`, 15 tareas
  con Lua como corpus nuevo) y `analyze_variants.py`, que separa los tokens por
  tipo (lectura y escritura de caché, entrada sin caché, salida) y los pondera
  por precio.

- Job `retrieval` de CI (`tools/check_retrieval_coverage.py`): mide la cobertura
  de los paquetes en 22 tareas sobre fmt y Flask fijados. Falla si la media
  baja, si una tarea pierde dos hechos o si aparece una falsa completitud.
- Ruby: `include`/`prepend`/`extend` se resuelven por la búsqueda léxica de
  constantes, y las llamadas sin receptor y `super` por la cadena de ancestros
  de cada clase que incluye el módulo (`graphtyn/core/ruby_mro.py`). En Rails,
  los `include` ambiguos pasan de 1.166 a 54 y aparecen 527 relaciones `super`.
- La puntuación de candidatos es una tabla de rasgos con nombre
  (`graphtyn/core/ranking_weights.py`), con pesos ajustados por
  `tools/learn_ranking_weights.py` sobre el conjunto de desarrollo.
- Banco de 30 tareas con división desarrollo/prueba
  (`benchmarks/task_bank_2026-10-28/`), medido por la cobertura del paquete sin
  agentes. Las 15 tareas de prueba se congelaron antes de cambiar la
  recuperación.
- `graph_query_intent` deja de declarar completo un paquete cuya evidencia es
  escasa para una petición de varias partes (menos de 250 tokens por parte):
  devuelve `missing=["request_parts"]` y pide buscar sólo las partes que la
  evidencia no aborda. El hook usa la misma indicación.
- Tampoco lo declara completo cuando la petición nombra un identificador
  (`BLPOP`, `TRYAGAIN`) que la evidencia no contiene:
  `missing=["named_identifiers"]` y `evidence_sufficiency` lista los que faltan.
- Segundo conjunto de tareas no vistas (`benchmarks/heldout_v2_2026-10-27/`):
  con la regla de parada dirigida la calidad se recupera, pero el ahorro en
  tareas nuevas es moderado. En cuatro de seis, el paquete cubre 0–1 hechos de la
  rúbrica, así que la recuperación sigue siendo el cuello de botella.
- Benchmark de tareas no vistas (`benchmarks/heldout_tasks_2026-10-27/`): seis
  tareas nuevas con rúbricas congeladas antes de ejecutar. Muestra que el ahorro
  del hook y del MCP lean no generaliza cuando el paquete se declara completo
  (`do_not_expand=true`) sin cubrir lo pedido.
- `graphtyn agent-install copilot` registra además el servidor MCP del proyecto
  en `.vscode/mcp.json` (`servers`, `type: stdio`, `cwd: ${workspaceFolder}`)
  para el modo agente de Copilot en VS Code. Está cubierto por tests pero no se
  verificó con un cliente Copilot real.
- `graphtyn integrations remove` retira también las skills que `agent-install`
  escribió para ese cliente y que nadie editó después (según el hash registrado);
  las editadas se conservan y se informan en `preserved_skills`.
- La skill publicada se divide en `skills/graphtyn` (contexto e impacto de
  código, con el flujo de cambios en `references/change-workflow.md`) y
  `skills/graphtyn-memory` (memoria compartida, brains y OpenClaw), cada una con
  una descripción acotada que remite a la otra. La skill de código reconoce el
  bloque `<graphtyn-context>` de los hooks; la de memoria lleva la política
  gestionada vigente, verificada por tests. `graphtyn agent-install` instala las
  dos desde los datos del paquete, registra el hash de cada archivo escrito para
  actualizar sólo los no editados y migra la skill combinada anterior con copia
  en `.graphtyn/legacy-skills/`.
- `graphtyn codex-context` y `graphtyn opencode-context` (`install|uninstall|status|hook`):
  el hook de primer turno para Codex (`.codex/hooks.json`, `UserPromptSubmit`
  con `additionalContextLimit`) y OpenCode (plugin `chat.message` en
  `.opencode/plugins/graphtyn-context.js`). Opcionales, requieren `--consent`.
- `graphtyn mcp --response-detail lean|debug` fija el detalle por defecto de
  `graph_query_intent`.
- El arnés comparativo añade el brazo `graphtyn_full` (mismo MCP con
  `response_detail=debug`) y el brazo `graphtyn_hook` para Codex y OpenCode.
  Medición en cuatro clientes y tres corpus (84 sesiones) con adjudicación
  conceptual ciega: `benchmarks/real_multi_client_hook_2026-10-27/`.
- `graphtyn claude-context install|uninstall|status|hook`: hook opcional
  `UserPromptSubmit` de Claude Code que ejecuta `graph_query_intent` antes del
  primer turno y añade el paquete como `<graphtyn-context>`, repartido en dos
  hooks paralelos de ≤ 9.800 caracteres (límite por hook de Claude Code); sólo
  para mensajes de código, sin construir índices y con límite de tiempo.
- `graph_query_intent` devuelve por defecto un paquete `lean`: sin diagnósticos
  (`planner`, `timing_ms`, `validation` correcta…), sin entidades desconectadas
  de los fragmentos de fuente cuando éstos ya cubren la petición y sin repetir
  firmas u operaciones ya impresas. `response_detail="debug"` conserva el
  paquete completo.
- El arnés comparativo añade un brazo `graphify` para Claude Code (`--arm graphify
  --graphify-bin`): construye el grafo de sólo código de una instalación aislada
  de Graphify fuera del tiempo medido y expone su `graphify-mcp` oficial. También
  admite `--repetition` para reintentos auditados y se detiene ante una sesión
  rechazada sin uso.
- Integración nativa con Claude Code: skill `.claude/skills/graphtyn`, registro
  reversible del MCP en el ámbito `local` mediante `claude mcp add` además de
  `.mcp.json`, y alias de identidad `claude` ↔ `claude-code` en la memoria.
- El arnés comparativo admite Claude Code como cuarto cliente: MCP aislado con
  `--strict-mcp-config`, herramientas de edición deshabilitadas, uso normalizado
  con lectura y escritura de caché por separado, traza por llamada de modelo y
  prueba de conexión y llamadas al servidor Graphtyn.
- Nodos de *rationale*: comentarios `WHY:`/`NOTE:`/`RATIONALE:`/`DECISION:`/
  `HACK:`/`IMPORTANT:` y citas ADR/RFC se adjuntan al símbolo que documentan y
  aparecen en `explain` y en los paquetes MCP (`why`).
- Comunidades, *god nodes*, conexiones sorprendentes y preguntas sugeridas en
  `GRAPHTYN_REPORT.md` y en el `overview` MCP (`structure`).
- `graphtyn export-html`: grafo autocontenido y sin red para compartir.
- `graphtyn prs`: triaje de varias ramas o PR con conflictos simulados por
  `git merge-tree`, símbolos compartidos, acoplamiento llamador/llamado y orden
  de merge sugerido.
- `.graphtynignore` con sintaxis de `.gitignore` para indexación y watcher.
- Códigos de salida en `query`, `path` y `explain` (0 respuesta, 3 ambiguo,
  4 sin coincidencia); los tres usan el índice cacheado en lugar de reescanear.
- Hooks Git gestionados para `post-commit`, `post-checkout` y `post-merge` que
  conservan el contenido del usuario.
- Paquetes Tree-sitter para Kotlin, Swift y Scala.
- Campo `citations` con referencias `archivo:línea` reales listas para citar,
  añadido sólo con el presupuesto sobrante tras acotar la evidencia.
- `--repetitions` en el arnés comparativo, con orden de brazos alternado.
- Captura nativa de memoria en Claude Code mediante un hook `Stop`
  (`graphtyn memory claude-capture install --consent`, o `setup --memory on`):
  sincroniza el transcript del turno en segundo plano con el mismo cursor
  idempotente del watcher; `memory_status` lo informa en `client_capture_hooks`.
- Instrucciones de instalación por cliente y para agentes en el README, con la
  explicación de un servidor MCP y una entrada por cliente.
- Contrato declarativo de paquetes Tree-sitter y metadatos del índice que
  indican qué lenguajes se procesaron realmente.
- Extracción precisa para C y C++: encabezados, includes, tipos, funciones,
  métodos, campos, llamadas, espacios de nombres y herencia.
- Benchmark local determinista para la cobertura y latencia del paquete C/C++.
- Benchmark exploratorio sobre Redis y fmt con OpenCode, Codex y Antigravity,
  incluyendo eventos crudos, caché, calidad, tiempos de índice y sesiones fallidas.
- Paquete Ruby con clases, módulos, métodos, llamadas, `require`, herencia y
  relaciones explícitas para `include`, `prepend` y `extend`.
- Benchmark determinista del parser y grafo Ruby, más validación de escala sobre
  un commit fijado de Ruby on Rails.
- Benchmark Rails con OpenCode, Codex y Antigravity que conserva por cliente los
  tokens, caché, calidad, tiempos de índice y artefactos crudos.
- Perfil MCP `query` que expone sólo `graph_query_intent`, con precarga opcional
  del índice para separar arranque, recuperación y tiempo de sesión.
- Repetición aislada Codex/Rails que conserva el primer intento incompleto y una
  segunda pareja comparable tras corregir la cobertura de evidencia.

### Corregido

- Clasificación de intenciones: cuentan las formas flexionadas («afectado»,
  «consumidores», «persiste») y una pasiva refleja («cuando se añade una ruta»)
  ya no se toma por una petición de edición. Las peticiones de impacto y de
  registro de extensiones se clasifican bien y sus paquetes son más pequeños.
- El código de dependencias incluidas (`deps/`, `vendor/`, `third_party/`…) no
  ancla un paquete salvo que la petición nombre la dependencia, y el handler de
  un comando en mayúsculas se conserva fuera de los archivos de anclaje.
- Un tipo sólo cuenta como nombrado si la petición lo escribe con su mayúscula
  (`record.reload` no nombra la clase `Record`); entre homónimos, el
  propietario que describe la petición (`autosave` → `AutosaveAssociation`)
  pesa más en la clase que en su espacio de nombres.
- La completitud exige identificadores completos: `lua_pcallk` ya no demuestra
  que se encontró `lua_pcall`; un nombre en mayúsculas sólo tiene que empezar
  una palabra (`BLPOP` → `blpopCommand`).

- Los fragmentos de `source_evidence` que empatan conservan el orden de
  selección del paquete (el punto de entrada primero), no el de sus rutas.
- Recuperación para `flow`:
  - un glosario de programación español→inglés (`evicción`→`evict`) y la
    puntuación de términos poco frecuentes dentro de nombres de función;
  - los marcadores de operaciones web (`save`, `send`…) sólo cuentan si la
    petición los nombra;
  - los campos de struct ya no anclan el paquete;
  - como mucho dos homónimos;
  - las funciones llamadas por el punto de entrada entran en el paquete.
  En el banco de tareas, la cobertura de prueba pasa del 20 % al 37,5 %.
- «registra» ya no clasifica una petición como `bindings` sin vocabulario de
  inyección de dependencias.
- Entre homónimos de un método nombrado se prefiere el dueño o la firma que
  describe la petición (`update(attributes)` → `Persistence#update`).
- Las palabras españolas en prosa y los nombres de directorio ya no puntúan
  como términos.
- La cadena de llamadas sigue hasta tres saltos por métodos hermanos.

- Regla de parada dirigida: un paquete con `do_not_expand=true` ya no prohíbe
  buscar. El hook, la guía del paquete, la skill y `AGENTS.md` piden responder
  con la evidencia sin releerla y consultar sólo la parte de la petición que no
  cubre, porque la recuperación por grafo puede omitir parte de una petición con
  varias preguntas (benchmark de tareas no vistas). El arnés conserva la regla
  estricta anterior (`--stop-rule strict`) para reproducir las ejecuciones previas.
- Ruby: una llamada sin paréntesis ni receptor (`destroy_associations`,
  `persisted? && destroy_row`) se registra como llamada si no es un parámetro ni
  una variable local; sólo se resuelve dentro del mismo lenguaje y sin
  ambigüedad (+2.022 relaciones en Rails, 1.322 `EXTRACTED`).
- «Traza qué ocurre…» ya no se clasifica como `bindings` porque «registro»
  coincidía con el marcador de registro de servicios; los empates con `flow`
  se resuelven a favor de `flow`.
- Los tipos nombrados en la petición deben coincidir en mayúsculas (`array` en
  prosa no es la clase `Array`); los archivos `_test`/`_spec` cuentan como tests y
  el código vendorizado o minificado se penaliza; nombrar un paquete de primer
  nivel de un monorepo (`ActiveRecord`) acota los homónimos como un nombre
  cualificado.
- El filtro de los hooks de primer turno reconoce peticiones en portugués,
  francés, italiano y alemán además de español e inglés, y un identificador de
  código (`snake_case`, `camelCase`, `a::b`, un archivo fuente) basta por sí
  solo en cualquier idioma.
- `graphtyn integrations remove` ya no deja vacía la carpeta `skills` del cliente.
- Selección de fuente en modo `precision`: un tipo cuyo nombre exacto aparece en
  la petición (`format_string/fstring`) pasa a ser símbolo obligatorio; un
  homónimo de un símbolo ya resuelto en otro archivo ya no lo es; la extensión de
  una clase o struct se completa con sus llaves cuando el parser la cierra en el
  primer miembro (cabeceras con macros); y el recorte de cuerpos largos amortigua
  los términos frecuentes y resta peso a los comentarios, para que las ramas de
  rechazo de `processCommand` no pierdan frente a palabras raras de comentarios.
- El bloque `<graphtyn-context>` completo repite la regla de parada al final.
- El arnés comparativo cierra stdin de cada sesión: `codex exec` esperaba más
  entrada y agotaba el tiempo.
- `evidence_result` ya no recorta en sitio los fragmentos del paquete interno. La
  segunda llamada que guarda el contexto MCP acortaba la respuesta ya construida;
  el presupuesto efectivo de fragmentos en modo `precision` (el medido en los
  benchmarks) ahora es explícito.
- Las llamadas Ruby sin receptor a `require`, `include`, `raise` y otros
  métodos de `Kernel`/`Module` ya no se resuelven contra métodos homónimos del
  proyecto; en Rails desaparecen unas 32.000 relaciones falsas.
- El vocabulario de expansión de consultas es genérico; se eliminaron
  identificadores de productos y librerías concretas que sobreajustaban los
  benchmarks.
- `hook install` ya no sobrescribe un hook Git existente del usuario.
- La importación de transcripts de Claude Code ya no guarda salida de
  herramientas, bloques `<system-reminder>`, notificaciones de tareas ni turnos
  meta, ni duplica cada mensaje como repr de Python.
- Las obligaciones ligadas a un framework (por ejemplo `validation_gate` de
  Rails) se marcan como no aplicables cuando ningún nodo del grafo puede
  cumplirlas, en lugar de dejar el paquete incompleto en otros lenguajes.
- Los cuerpos largos se entregan como ventanas enfocadas en la petición con
  números de línea reales, los símbolos camelCase nombrados cuentan como
  explícitos y el recorte final del payload conserva inicio y final. En Redis el
  paquete pasa de 3/8 a 8/8 hechos de la rúbrica con tamaño similar.
- La guía de los paquetes pide citar `archivo:línea` reales, no alias.
- Indexación: se eliminaron cuatro recorridos cuadráticos con un grafo idéntico;
  reindexado en frío de Rails 259,7 → 62 s, fmt 33,1 → 5 s y Redis 24,0 → 18 s.
- Retirar la última entrada Graphtyn de `.mcp.json` conserva `mcpServers: {}`,
  que Claude Code exige para considerar válido el archivo.
- La contabilidad de Codex ya no suma `cached_input_tokens` sobre
  `input_tokens`: la caché es un subconjunto de la entrada y el razonamiento un
  subconjunto de la salida en el esquema de uso de OpenAI.
- Las obligaciones de memoria requieren palabras completas, por lo que
  “aporta” ya no solicita evidencia de un puerto.
- Una petición explícita de panorama conserva `overview` al evaluar posibles
  mejoras; las preguntas operativas enumeradas siguen usando `flow`.
- Los símbolos Tree-sitter con nombres válidos como `Base` ya no se eliminan
  como ruido léxico.
- Los encabezados `.h` con sintaxis C++ seleccionan la gramática C++ en vez de
  quedar degradados por la gramática C; los encabezados C conservan su parser.
- Los selectores cualificados consideran namespaces y rutas de paquete, evitan
  métodos homónimos de pruebas y conservan los símbolos tardíos de solicitudes
  con varias etapas. La evidencia de precisión admite cuerpos de tipos nombrados.
- Las relaciones ambiguas de llamada, herencia y mixin dejan de expandirse contra
  cientos de candidatos homónimos. Las consultas CLI reutilizan el índice
  persistido en lugar de reconstruir el repositorio antes de recuperar contexto.
- La evidencia de precisión verifica por separado cada obligación y cada símbolo
  nombrado. Si el presupuesto elimina un fragmento requerido, reabre `missing` y
  desactiva `do_not_expand` en vez de declarar cobertura completa.
- Las rutas complejas distinguen validación, callbacks de guardado/creación,
  entrada y rollback transaccionales, adaptador y semántica de fallo; nombres de
  proyecto o palabras como “commit” ya no desplazan esos símbolos.

## [0.10.7] - 2026-10-20

### Añadido

- La memoria de proyecto mantiene índices FTS5 y embeddings persistentes para
  mensajes fuente, con una migración compatible para almacenes existentes.
- La regresión aislada de recuperación publica Recall@6, cobertura de
  obligaciones, filtrado de mensajes de evaluación, latencia y tamaño máximo
  del contexto sin llamar modelos, servicios externos ni almacenes activos.
- `graph_query_intent` entrega un `implementation_context` acotado con archivos
  iniciales, consumidores directos, efectos laterales, pruebas, comandos
  extraídos y un presupuesto explícito de exploración para tareas de edición.
- El servicio persistente acepta interfaz, puerto, archivo de tokens y
  configuración local de Ollama. Exponerlo fuera de loopback requiere un
  archivo de autenticación válido.
- Los arneses comparativos cubren OpenCode, Codex y Antigravity, conservan el
  desglose de entrada, caché, salida y razonamiento informado por cada cliente,
  y separan recuperación, sesión completa y coste monetario.

### Cambiado

- La recuperación de mensajes combina candidatos léxicos y semánticos acotados,
  aplica ranking recíproco, diversifica por sesión y devuelve fragmentos
  adaptativos con una referencia para ampliar sólo el mensaje necesario.
- Cada resultado distingue obligaciones solicitadas, cubiertas y faltantes, y
  clasifica la evidencia como observada, histórica o propuesta. Los mensajes de
  bootstrap, evaluación y ecos de recuperaciones previas quedan fuera del
  ranking histórico.
- La conexión predeterminada de OpenClaw expone únicamente
  `memory_project_context`, `memory_message_window` y `memory_status`. La captura
  continúa a cargo del watcher autorizado y no de herramientas de escritura en
  el contexto del agente.
- Los embeddings locales de Ollama admiten lotes, reutilizan consultas recientes
  y conservan un fallback compatible cuando el endpoint por lotes no está
  disponible. La reindexación incluye recuerdos y mensajes.
- El índice incluye manifiestos y configuración YAML, TOML, INI, CFG, Docker y
  workflows. El planificador pondera identificadores dentro de operaciones,
  reserva evidencia para configuración, pruebas y verificadores, y reclasifica
  peticiones operativas de `overview` a `flow`.
- `evidence-v1` limita el JSON serializado completo, deduplica expansiones por
  identidad estable de archivo/símbolo y publica tiempos de carga, recuperación,
  cobertura y render junto con el estado de caché del índice.
- La skill de Graphtyn trata `implementation_context` como contrato de acción:
  lee `read_first` en orden, evita exploración amplia cuando la cobertura está
  completa y no instala dependencias durante una edición sin petición explícita.

### Corregido

- Pytest limita el descubrimiento a `tests/`, evitando que checkouts temporales
  guardados bajo artefactos de benchmark se mezclen con la suite de Graphtyn.
- `do_not_expand` y `sufficient_evidence` ya no pueden indicar que la
  recuperación está completa cuando falta una obligación solicitada.
- `project_doctor` prioriza un watcher actual y saludable frente a registros
  antiguos obsoletos o degradados del mismo almacén.
- El benchmark de OpenCode exige declarar si `step_finish` es por paso o
  acumulado, conserva las muestras crudas y suma los reintentos en lugar de
  seleccionar el contador máximo sin conocer su semántica.
- `validate-answer` deja de interpretar los dígitos de identificadores técnicos
  como `SHA-256` o `UTF-8` como afirmaciones numéricas independientes y distingue
  una fuente existente pero no indexada de una cita inexistente.

La validación y sus límites están en
[`release-validation-0.10.7.md`](release-validation-0.10.7.md).

## [0.10.6] - 2026-10-11

### Corregido

- El watcher reconcilia de forma síncrona los cambios ocurridos mientras
  Graphtyn estaba apagado antes de servir el índice. Si falta su manifiesto,
  reconstruye el grafo en lugar de aceptar una fotografía antigua.
- El dashboard recarga el proyecto cuando cambia la versión del watcher,
  incluido el reinicio de su contador después de reiniciar el servicio.
- La vista detallada de memoria carga las relaciones entre temas y entidades
  en una consulta por lote, evitando una conexión por cada combinación y los
  bloqueos observados en proyectos con cientos de temas.

## [0.10.5] - 2026-10-10

### Añadido

- El perfil mixto de RF07 evalúa decisiones en español, paráfrasis sin
  identificadores sintéticos y preguntas naturales sin respuesta, con métricas
  separadas por tipo.
- `memory project-evaluation` comprueba en un checkout real la recuperación,
  procedencia de archivos/nodos y abstención; sus fallos se conservan como
  regresiones reproducibles.

### Corregido

- La puntuación híbrida prioriza vocabulario coincidente y tokens identificadores
  exactos frente a memorias recientes que sólo comparten palabras genéricas.
- `query-intent` mantiene coherentes `missing`, `do_not_expand` y
  `stopping.sufficient_evidence` después de adjuntar evidencia de fuente.

## [0.10.4] - 2026-09-21

### Añadido

- Resolución canónica de alias de agente (`antigravity` ↔ `agy`, `openclaw`, `codex`, `cursor`, etc.) en permisos de proyectos, filtros de importación de historial y llamadas MCP.
- Asignación automática del ámbito de memoria del proyecto al ejecutar `agent-install` para el cliente seleccionado.
- Auto-consolidación transparente de bases de datos de memoria (`memory-v2.db`) entre el almacenamiento local y central con respaldo preventivo, resolviendo conflictos de duplicación.
- Soporte explícito del parámetro `path` y etiquetado con metadatos de `project_context` y `workspace` en las herramientas MCP de grafo (`graph_neighborhood`, `graph_blast_radius`, `graph_search_concepts`, etc.).
- Metadatos de `runtime` en el reporte del CLI `agent-install` e `integrations` clarificando el alcance global del binario frente a configuraciones locales de proyecto.

### Corregido

- Los proyectos compartidos con agentes asignados ya no se tratan erróneamente como restringidos (`restricted`), permitiendo el acceso multi-agente legítimo sin bloqueos de autorización ni fugas hacia proyectos externos.
- El servidor MCP auto-registra al agente solicitante activo del workspace en proyectos registrados, previniendo caídas a servidores MCP globales con contexto de otros proyectos.
- `graphtyn setup` inicializa el almacenamiento de memoria de proyecto por defecto (`memory-ready`).

## [0.10.3] - 2026-09-19

### Añadido

- Integraciones MCP aisladas por proyecto para Codex, OpenCode, Claude, Cursor
  y Antigravity, con identidad persistente y migración controlada de
  configuraciones antiguas.
- Recuperación de memoria compartida por proyecto con continuidad entre
  agentes, enrutamiento exacto de workspaces y soporte ampliado para
  OpenClaw.

### Corregido

- La concurrencia de checkpoints SQLite y la lectura de trabajos persistentes
  quedan protegidas también en Windows.
- Las rutas `file:///C:/...` de Antigravity se normalizan correctamente y la
  indexación conserva rutas Unicode y separadores portables.
- El CI de Windows valida las rutas actuales de integración MCP y cubre el
  onboarding, el dashboard y la instalación del wheel.

## [0.10.2] - 2026-09-13

### Añadido

- `memory_context` ofrece `mode=continuity` en MCP, API y CLI para combinar
  recuerdos temáticos con actualizaciones recientes atribuidas a agente, sesión
  y mensaje fuente. El presupuesto cuenta la respuesta completa.
- El estado del almacén muestra la última recuperación de contexto sin guardar
  ni exponer la consulta del agente.
- La sincronización por proyecto descubre historiales locales de Codex y Claude,
  además de OpenCode y Antigravity; sólo importa rutas de workspace exactas y
  mantiene las sesiones ambiguas pendientes.
- El instalador mantiene una política de memoria versionada e idempotente para
  los agentes, preserva instrucciones propias y distingue cerebro privado,
  memoria de proyecto, recuperación y captura automática.
- La guía del agente evita repetir consultas cuando una ventana de evidencia no
  está disponible; `memory_context` se consulta una vez y sólo se amplía una
  referencia concreta cuando hace falta.

### Corregido

- MCP stdio y HTTP resuelven el alcance compartido de proyecto con la política
  común del almacén: atribuir una fuente a un agente ya no oculta el contexto de
  otros agentes del mismo proyecto.
- Las importaciones Codex excluyen su envoltura `<environment_context>` aunque
  el formato la represente con el rol `user`.
- Una importación histórica sin fecha fuente ya no usa la hora de importación
  como si fuera la fecha de actividad original; esas entradas no se anuncian
  como actividad reciente.
- Los registros `MODEL/GENERIC` de Antigravity sólo se clasifican como respuesta
  si identifican explícitamente autoría del agente; resultados de herramientas
  conservan el tipo `tool`.

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
