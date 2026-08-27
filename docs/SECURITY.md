# Política de seguridad

## Versiones soportadas

La serie estable `0.6.x` recibe correcciones de seguridad.

## Reportar una vulnerabilidad

No publiques credenciales, historiales ni pruebas de explotación en un issue.
Cuando exista el repositorio público, usa **Security → Report a vulnerability**
para enviar un aviso privado. Hasta entonces, comunica el hallazgo por el canal
privado usado para recibir el código y proporciona versión, impacto, reproducción
mínima y mitigación propuesta. Se confirmará recepción antes de divulgar detalles.

## Modelo de seguridad

- El dashboard debe escuchar en `127.0.0.1`; no se recomienda exposición directa.
- MCP HTTP requiere token cuando sale de un proceso local confiable.
- Docker publica sólo loopback y ejecuta como usuario sin privilegios.
- Las memorias pueden contener información sensible: activa captura únicamente
  con consentimiento y protege backups como datos del proyecto.
- Exportar no sustituye una revisión de datos; los patrones desconocidos pueden
  no ser reconocidos por el saneador.

Para red compartida o producción empresarial añade proxy TLS, autenticación,
rate limiting, gestión de secretos y políticas de retención externas.
