# Changelog

Este proyecto usa [Semantic Versioning](https://semver.org/) y versiones
compatibles con PEP 440.

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
