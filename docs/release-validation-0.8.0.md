# Validación de `0.8.0`

Fecha: 2026-09-11. Estado: candidato preparado en la rama de trabajo; no
publicado.

## Cobertura de cambios

- El almacén de memoria detecta dos bases locales/centrales divergentes y
  rechaza elegir una silenciosamente. Los cerebros registrados filtran datos
  históricos por los identificadores exactos de sus agentes.
- La API remota exige token separado del token MCP y aplica roles y ámbitos de
  proyecto. Las escrituras de registro usan reemplazo atómico.
- El acceso concurrente coordina conexiones, backup SQLite y restauración; la
  restauración se rechaza mientras otro cliente usa el almacén.
- La importación de historial conserva el ámbito de agentes y el registro de
  Cerebro no infiere propietarios a partir del nombre de una carpeta.
- Un tema que una episodios de agentes distintos se oculta en un cerebro
  registrado, aunque esa asociación exista en datos históricos; temas nuevos no
  continúan episodios ajenos. La memoria de proyecto mantiene relaciones
  multiagente compartidas.
- Se corrigen referencias de mensajes de temas y ventanas para verificar el
  agente de cada mensaje, y el procesamiento por lotes mantiene cursores en la
  misma transacción que sus resultados.
- El watcher persistente espera el intervalo configurado entre sincronizaciones;
  los fallos de transporte de Chromium ya no pueden pasar silenciosamente en CI.

## Evidencia local

- Suite completa: **312 pasaron, 2 omitidas**, Python 3.13.13, Linux. Las
  omisiones corresponden a dependencias/entorno opcionales; no se ejecutó aquí
  la matriz remota de Python 3.10–3.12 ni Windows.
- Wheel y sdist se construyeron. El wheel se instaló en un entorno virtual
  limpio; `graphtyn --version` devolvió `0.8.0` y el dashboard está incluido.
- Docker construyó la imagen `0.8.0`; ejecutó como UID `10001` y respondió
  `{"service":"Graphtyn","status":"ok","version":"0.8.0"}` en `/health`.
- `pip-audit` no encontró vulnerabilidades conocidas en las dependencias
  auditables. Omitió el paquete Graphtyn porque esta versión candidata no está
  publicada en PyPI.
- El smoke de Chromium **no se pudo ejecutar** en este host: Playwright requiere
  `libstdc++.so.6` y Chromium requiere `libglib-2.0.so.0`, que no están
  disponibles en el entorno. El script reporta `SKIP`; el job de navegador de
  CI debe pasar en el SHA candidato antes de etiquetar.
- Benchmark reproducible de memoria compartida, con 30 recuerdos sintéticos,
  270 consultas positivas y 15 negativas: Recall@5/10 **1.000**, MRR **0.9889**,
  atribución **1.000**, precisión negativa **1.000**, 643.24 tokens estimados
  por consulta en promedio, latencia media **49.081 ms** y p95 **61.391 ms**.
  La corrida tomó **16.195 s** y alcanzó **156,164 KiB (152.5 MiB)** de RSS
  máximo del proceso. Los tokens son una estimación por caracteres UTF-8/4.
- `git diff --check` y `py_compile` de los módulos modificados pasan.

El benchmark mide recuperación de recuerdos estructurados, no la calidad de
segmentación/recall de temas conversacionales. Sus cifras no representan una
medición con historiales reales ni corpus de varios GB.

La corrida sintética se reproduce con
`graphtyn memory benchmark --suite stability --output resultado.json --path .`.

## Pendiente antes de publicación estable

- CI del SHA exacto en Linux/Python 3.10–3.13, Windows, navegador, auditoría de
  dependencias y Docker.
- Ejecutar Chromium en un entorno compatible y revisar sus resultados.
- Validar actualización/restauración en instalaciones reales y carga sostenida
  con almacenes grandes; no se declara probado el uso multi-GB.
- Revisar el artefacto final y sus hashes. El tag, la release y la publicación
  no se crean hasta que todos los controles requeridos de CI estén verdes.

El benchmark generado durante esta validación se guardó en `/tmp` y no contiene
datos de usuario; el repositorio no incluye conversaciones privadas.
