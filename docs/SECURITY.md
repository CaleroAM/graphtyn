# Política de seguridad

## Versiones soportadas

El soporte de seguridad se aplica a la versión estable más reciente publicada
en [GitHub Releases](https://github.com/CaleroAM/graphtyn/releases/latest).
Actualiza Graphtyn antes de reportar un problema e incluye la salida de
`graphtyn --version` para identificar la versión afectada.

## Reportar una vulnerabilidad

No publiques credenciales, historiales ni pruebas de explotación en un issue.
En el repositorio público `CaleroAM/graphtyn`, usa **Security → Report a
vulnerability** para enviar un aviso privado. Si GitHub no muestra esa opción,
contacta directamente a los administradores por un canal privado sin incluir el
secreto en un issue. Incluye versión, impacto, reproducción mínima y mitigación
propuesta; coordina la divulgación antes de publicar detalles.

## Modelo de seguridad

- El dashboard debe escuchar en `127.0.0.1`; no se recomienda exposición directa.
- MCP HTTP requiere `GRAPHTYN_MCP_TOKEN` y credenciales Bearer cuando sale de un
  proceso local confiable. Ese secreto sólo autentica el transporte MCP.
- Las API de memoria remotas requieren `GRAPHTYN_MEMORY_HTTP_TOKEN` o
  `GRAPHTYN_MEMORY_TOKENS`; los tokens por rol pueden limitarse a rutas
  absolutas de proyectos. Las API rechazan acceso remoto sin configuración.
- Si hay un proxy inverso, termina TLS y autentica también el dashboard. El
  servicio sólo puede comprobar la dirección de su conexión inmediata, no
  confiar en `X-Forwarded-For`.
- Un cerebro registrado como `agent_brain` requiere identidades propietarias
  explícitas y exactas. Un espacio sin propietarios no permite escribir y sólo
  devuelve catálogos vacíos.
- Si coexisten una base local y una central para el mismo espacio, Graphtyn
  devuelve un conflicto; configura `GRAPHTYN_HOME` de forma consistente o
  resuelve la copia antes de importar, buscar o restaurar.
- La restauración de backup requiere que no haya operaciones activas en clientes
  Graphtyn actualizados. Se conserva una copia de seguridad y SQLite aplica la
  restauración con su API de backup, respetando WAL.
- Docker publica sólo loopback y ejecuta como usuario sin privilegios.
- Las memorias pueden contener información sensible: activa captura únicamente
  con consentimiento y protege backups como datos del proyecto.
- Exportar no sustituye una revisión de datos; los patrones desconocidos pueden
  no ser reconocidos por el saneador.

Para red compartida añade proxy TLS, autenticación, rate limiting, gestión de
secretos y políticas de retención externas. Graphtyn es self-hosted; no ofrece
aislamiento de tenants SaaS.
