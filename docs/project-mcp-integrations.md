# MCP por proyecto

Cada proyecto registrado recibe un ID persistente en `.graphtyn/graphtyn.json`.
El alias MCP se deriva del nombre actual de la carpeta y del ID, por ejemplo
`graphtyn_e50e_a1b2c3d4`; así los repos con el mismo nombre no comparten el
mismo servidor. Si la carpeta cambia de nombre, el ID se conserva y el alias se
actualiza al volver a instalar el cliente.

Registra el proyecto en el dashboard o ejecuta `graphtyn memory projects
--path .`. Después configura únicamente los clientes que vas a usar:

```bash
graphtyn agent-install codex --path .
graphtyn agent-install antigravity --path .
graphtyn agent-install opencode --path .
graphtyn agent-install claude --path .
graphtyn integrations status --path .
graphtyn integrations verify --path .
```

Los archivos de proyecto conservan sus otros servidores MCP. Si un archivo no
es JSON válido o el alias ya pertenece a otro servidor, Graphtyn lo deja intacto
y marca ese cliente como `needs_review`. Las entradas agregadas se pueden quitar
sin afectar las demás con `graphtyn integrations remove --path . --agent codex`;
omitir `--agent` retira todas las entradas compatibles que instaló Graphtyn.

Codex usa `.codex/config.toml`; requiere que el proyecto sea confiable para
cargar su MCP local. Graphtyn escribe la ruta absoluta del proyecto como `cwd`
para que el MCP arranque en el workspace correcto aunque Codex se abra desde
otra ruta. Esta ruta depende de cada máquina: regenera la configuración local y
revísala antes de compartirla o comitearla. Antigravity usa
`.agents/mcp_config.json`. OpenCode, Claude Code y Cursor reciben una entrada de
stdio en la configuración local del proyecto. Las entradas usan el comando
`graphtyn` del PATH y una ruta relativa al workspace. Si un cliente de
escritorio no hereda el PATH de la terminal, instala Graphtyn en un PATH visible
para ese cliente y recárgalo.

`graphtyn integrations status --path .` informa el ID, el alias, la presencia y
el destino de cada archivo MCP. `graphtyn integrations verify --path .` inicia
el servidor por stdio y comprueba el handshake MCP y la disponibilidad de
`memory_context`; el dashboard ofrece la misma prueba con «Probar servidor MCP
del proyecto». Esta prueba valida el servidor local, no que el cliente lo haya
cargado: recarga el cliente si sus herramientas no aparecen. El dashboard
informa por separado la configuración, la prueba MCP y el estado real de captura.

La API del dashboard devuelve los mismos datos en
`GET /api/memory/status?path=<proyecto>` dentro de `project_integrations`.
`POST /api/memory/integrations/verify` acepta `{"path":"<proyecto>"}` y
requiere el mismo permiso de escritura que las operaciones de memoria. Sólo
inicia el servidor stdio para probarlo; no lee ni importa historiales.

OpenClaw usa un servidor compartido por instalación. Como una conversación de
OpenClaw puede tratar varios proyectos, sus agentes consultan cada memoria con
`memory_project_context` y el ID/nombre explícito del proyecto. `agent-install
openclaw` instala instrucciones, pero no crea una conexión MCP fija a un solo
repositorio ni cambia `openclaw.json`.

La instalación MCP no inicia la captura ni importa sesiones pasadas. Para
captura continua, ejecuta `graphtyn memory sync --path . --watch --consent` y
confirma con `graphtyn memory status --path .`. La importación histórica tiene
un flujo explícito y separado en `graphtyn memory bootstrap` o
`graphtyn setup --apply --memory on --import-history --consent-history`.
