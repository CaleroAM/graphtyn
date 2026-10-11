# Validación de `0.10.6`

Fecha: 2026-10-11. Esta versión corrige la vigencia automática del índice del
dashboard y el costo de la vista detallada de memoria.

## Validación local

- Suite completa en Linux: **549 pruebas pasaron y 2 se omitieron**.
- Comprobación de mantenibilidad: **29 hotspots heredados sin crecimiento**.
- `git diff --check`: pasó.
- Las regresiones cubren cambios realizados con Graphtyn apagado y la
  reconstrucción de un índice existente cuando falta el manifiesto del watcher.
- El dashboard persistente se reinició con `--watch`; `modIAceb` expuso 2.415
  nodos y 4.963 relaciones después de la reconciliación.
- La vista detallada de memoria respondió desde el servicio activo sin el
  bloqueo anterior.
- `graphtyn --version`: `0.10.6`.

## Paquete y CI

- Wheel: `graphtyn-0.10.6-py3-none-any.whl`, instalado y ejecutado en un entorno
  virtual vacío.
- Sdist: `graphtyn-0.10.6.tar.gz`.
- Los metadatos de ambos artefactos coinciden con `0.10.6`.
- La publicación queda condicionada a CI verde para el commit fusionado y para
  el tag exacto `v0.10.6`, incluidos Linux, Windows, seguridad, navegador y
  construcción de contenedor.

## Límites

La reconciliación automática se ejecuta al comenzar a vigilar un proyecto. Su
duración depende del tamaño del repositorio y puede retrasar la primera consulta
para garantizar que no se entregue un índice obsoleto. La memoria compartida
mantiene un watcher y una política de captura independientes del índice de
código.
