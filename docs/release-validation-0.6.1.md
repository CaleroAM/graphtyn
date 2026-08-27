# Validación de `0.6.1`

Fecha: 2026-08-27.

Esta versión corrige fallos observados durante la instalación real de una
persona usuaria en Windows. Los archivos JSONL de origen se usaron únicamente
como evidencia diagnóstica y no se copiaron al repositorio ni a las pruebas.

## Regresiones cubiertas

- CLI y MCP fuerzan UTF-8 de forma tolerante en Windows.
- Las rutas versionadas y los identificadores del grafo usan `/` de forma
  canónica, aun cuando el sistema anfitrión use `\`.
- `graphtyn onboard` deja configuración, integración de agente, MCP e índice
  persistido en una sola ejecución.
- Antigravity recibe `SKILL.md`, manifiesto de plugin y perfil MCP explícito.
- Instalar todos los agentes no duplica `AGENTS.md` ni otros destinos comunes.

## Evidencia automatizada

- Suite Python completa en 3.10, 3.11, 3.12 y 3.13.
- Job Windows desde wheel: PowerShell, consola cp1252, ruta Unicode, repositorio
  C# anidado, onboarding, índice no vacío y configuración MCP.
- Construcción de wheel/sdist, auditoría de dependencias, navegador y Docker.

El tag `v0.6.1` sólo se crea después de que todos los controles de la rama y del
pull request estén verdes.
