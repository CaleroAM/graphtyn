# Validación de `0.10.0`

## Alcance

- Sincronización de todos los espacios con errores de almacén informados sin
  detener los destinos válidos, y administración CLI de la política de dueño.
- Importación OpenClaw desde raíces configuradas y seguimiento seguro de
  `trajectory-path.json` a la transcripción canónica local.
- Secciones Markdown/RST indexables con referencias de origen, búsqueda de
  documentos por ruta explícita y redacción de patrones comunes de credenciales.
- Estado de memoria por MCP stdio y controles acotados en búsqueda y contexto.
- Corrección del alcance de dueño en las candidatas de relación y referencias
  de mensajes en episodios.

## Evidencia

- Suite completa en Python 3.13/Linux: **355 pruebas pasadas y 2 omitidas**.
- `python -m build` creó `graphtyn-0.10.0.tar.gz` y
  `graphtyn-0.10.0-py3-none-any.whl`.
- El wheel se instaló en un entorno virtual limpio; `graphtyn --version` y las
  versiones del paquete y API devolvieron `0.10.0`; `pip check` no reportó
  dependencias rotas.
- El merge en `main`, commit
  [`96a4157`](https://github.com/CaleroAM/graphtyn/commit/96a4157a07b196de40891c5d6ac4f6602072f488),
  pasó todos los trabajos CI, incluida la matriz Python 3.10–3.13, Windows,
  navegador, paquete, seguridad y Docker
  ([ejecución](https://github.com/CaleroAM/graphtyn/actions/runs/34720900070)).
- La etiqueta `v0.10.0` apunta al commit `eef7142`; su CI y el workflow de
  publicación pasaron ([CI del tag](https://github.com/CaleroAM/graphtyn/actions/runs/34722164040),
  [release](https://github.com/CaleroAM/graphtyn/actions/runs/34722164037)).
- Se corrigió el `SHA256SUMS` publicado para usar nombres de asset descargados;
  la verificación pasó después de descargar los cuatro artefactos de nuevo.

La publicación se distribuye por GitHub Releases. PyPI permanece deshabilitado.
El workflow de release espera CI satisfactoria para el SHA exacto de la etiqueta
antes de construir y adjuntar artefactos.
