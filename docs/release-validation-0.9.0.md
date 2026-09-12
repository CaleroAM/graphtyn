# Validación de `0.9.0`

## Alcance de la versión

- Conexión nativa con OpenClaw mediante descubrimiento local o de destinos SSH
  explícitos, creación/adopción controlada de cerebros por identidad y captura
  incremental.
- Relaciones explícitas entre agentes, publicación de recuerdos familiares y
  aislamiento por defecto cuando la relación sigue pendiente.
- Consolidación revisable de archivos heredados en cerebros activos, con
  procedencia y conservación del origen.
- Dashboard para conectar instalaciones y observar estado, cobertura y fallos
  de sincronización.

La integración incluida es específica de OpenClaw. No se declara integración
nativa con Hermes ni compatibilidad con configuraciones remotas que no se hayan
seleccionado explícitamente.

## Validación local

- Suite completa en Python 3.13.13/Linux: **340 pasaron, 2 omitidas**.
- `python -m build` generó el wheel universal y el sdist de `0.9.0`.
- `pyproject.toml`, `graphtyn.__version__` y la versión de la API coinciden en
  `0.9.0`; `git diff --check` pasó.

## Criterio de publicación

La CI debe pasar en el SHA exacto de la etiqueta `v0.9.0`. El workflow
[`release.yml`](../.github/workflows/release.yml) espera esa ejecución antes de
construir artefactos o crear la release. La matriz incluye Python 3.10–3.13,
Windows, navegador, paquete, seguridad y Docker.

La evidencia de CI, el SHA etiquetado y los artefactos se consultan desde la
[release `v0.9.0`](https://github.com/CaleroAM/graphtyn/releases/tag/v0.9.0) y
sus ejecuciones enlazadas. PyPI continúa deshabilitado; la distribución es por
GitHub Releases.
