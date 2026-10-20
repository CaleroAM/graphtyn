# Validación de `0.10.7`

Fecha: 2026-10-20. Esta versión mejora la recuperación de memoria compartida,
el contexto de implementación para ediciones, la contabilidad de benchmarks y
la integración de lectura de OpenClaw.

## Alcance

Esta entrega añade índices FTS5 y embeddings persistentes de mensajes, búsqueda
híbrida acotada, diversificación por sesión y fragmentos adaptativos. La salida
declara las obligaciones solicitadas, cubiertas y faltantes; sólo permite
`do_not_expand=true` cuando la evidencia devuelta cubre lo pedido.

La procedencia distingue conversaciones, bootstrap, evaluaciones y contenido
derivado de recuperaciones. El ranking excluye bootstrap, evaluación y ecos de
contexto para evitar que una respuesta anterior se convierta en su propia fuente.
Las propuestas permanecen recuperables, pero no satisfacen por sí solas una
pregunta sobre una acción ejecutada.

La integración predeterminada de OpenClaw expone tres herramientas de lectura:
`memory_project_context`, `memory_message_window` y `memory_status`.
`memory_project_context` evita adjuntar el grafo de código cuando la petición es
de continuidad histórica. La captura permanece en el watcher configurado y
autorizado.

Los embeddings locales de Ollama aceptan lotes de hasta 64 textos, reutilizan
consultas recientes y vuelven al endpoint individual compatible si el endpoint
por lotes no responde. `memory reindex` actualiza embeddings de recuerdos y de
mensajes. En almacenes cifrados no se persisten índices de texto ni vectores de
mensajes; la recuperación usa un recorrido descifrado y acotado.

## Trazabilidad de la implementación

| Comportamiento publicado | Fuente |
|---|---|
| Esquema de embeddings y FTS5 de mensajes | `graphtyn/core/memory_schema.py:60`, `graphtyn/core/memory_schema.py:223` |
| Procedencia y exclusión de contexto inyectado | `graphtyn/core/shared_memory.py:90` |
| Obligaciones y clasificación de evidencia | `graphtyn/core/shared_memory.py:163` |
| Recuperación híbrida, fragmentos y diversificación | `graphtyn/core/shared_memory.py:1710` |
| Invariante final de cobertura y `do_not_expand` | `graphtyn/core/shared_memory.py:2135` |
| Batches y caché de Ollama | `graphtyn/core/semantic_index.py:129` |
| Fallback acotado para almacenes cifrados | `graphtyn/core/shared_memory.py:698` |
| Filtro de tres herramientas de OpenClaw | `graphtyn/core/openclaw_integration.py:269` |
| Contexto de proyecto sin grafo adjunto | `graphtyn/mcp_server.py:1190` |
| Prioridad del watcher activo en el diagnóstico | `graphtyn/core/shared_memory.py:3558` |

## Validación reproducible

Entorno observado:

- Linux 6.18.35 x86_64.
- Python 3.13.13.
- Intel Core i5-12500H.
- `graphtyn --version`: 0.10.7.

Se ejecutó la suite completa:

```bash
.venv/bin/pytest -q
```

Resultado: **591 pruebas pasaron, 3 se omitieron, en 208.59 segundos**.

También se ejecutaron por separado los contratos de seguridad y publicación:

```bash
.venv/bin/pytest -q tests/test_security_leaks.py tests/test_release_contracts.py
```

Resultado: **20 pruebas pasaron en 1.38 segundos**.

La puerta de mantenibilidad pasa con 34 hotspots registrados y sin crecimiento
respecto del baseline revisado. Esta versión añade cinco hotspots en las rutas de
planificación, recuperación y transporte MCP; se aceptan como deuda explícita por
ahora porque separar esas responsabilidades justo antes de publicar arriesgaría
los contratos funcionales ya validados. El baseline impide que crezcan sin otra
revisión y `docs/MAINTAINABILITY.md` identifica las extracciones prioritarias.

Los paquetes se construyeron con `python -m build`. El wheel se instaló en un
entorno virtual vacío y allí pasaron `graphtyn --version`, la comprobación de
recursos empaquetados, `setup` en modo de vista previa, `reindex`, `report` y la
inicialización MCP por stdio. `pip-audit` no encontró vulnerabilidades conocidas
en las dependencias instaladas del wheel; omitió el propio paquete porque esta
versión todavía no existe en PyPI. La imagen Docker construyó, ejecutó como el
usuario sin privilegios `graphtyn` y `/health` respondió con la versión 0.10.7.

El smoke local de Chromium no pudo iniciarse porque el ejecutable disponible no
encontró `libstdc++.so.6`. No se considera un pase: el job `browser` de GitHub
Actions instala Chromium con sus dependencias y debe finalizar correctamente en
el SHA exacto antes de crear la etiqueta.

La regresión aislada se ejecutó así:

```bash
PYTHONPATH=. .venv/bin/python benchmarks/run_memory_retrieval_benchmark.py \
  --repetitions 5 \
  --output benchmarks/memory_retrieval_2026-10-19/result.json
```

| Métrica | Resultado |
|---|---:|
| Consultas | 10 |
| Recall@6 | 1.00 |
| Obligaciones con evidencia suficiente | 1.00 |
| Fuga de mensajes de evaluación | 0.00 |
| Latencia mediana | 1.977 ms |
| Latencia p95 | 2.328 ms |
| Máximo contexto recuperado | 273 caracteres |
| Límite por consulta | 3.840 caracteres |

El resumen reproducible está en
`benchmarks/memory_retrieval_2026-10-19/REPORT.md:1`; el mismo directorio incluye
el JSON íntegro con las observaciones por consulta. El benchmark crea un
almacén temporal, usa `feature-hash-v2`, no activa modelos externos y no modifica
un almacén real; esas garantías forman parte de su implementación en
`graphtyn/core/memory_retrieval_benchmark.py:36`.

## Validación operativa observada

En la instalación de OpenClaw usada durante la integración se reindexaron 692
recuerdos y 5.640 mensajes. El almacén terminó sin embeddings huérfanos y el
watcher activo quedó saludable. Una inspección MCP desde el cliente devolvió las
tres herramientas permitidas y filtró las otras 35. Una consulta histórica con
varias obligaciones recuperó dos mensajes fuente, dejó cero obligaciones
pendientes y evitó adjuntar el grafo de código.

Estas cifras describen esa instalación y no forman parte del benchmark aislado.
No se publican rutas, direcciones, tokens, nombres de personas ni endpoints del
despliegue. La inspección estática de integraciones de `project_doctor` todavía
puede marcar como degradada una configuración MCP global y dinámica de OpenClaw,
aunque la prueba directa de `tools/list` sea correcta; la señal debe interpretarse
junto con la prueba del cliente.

## Límites de las afirmaciones

- La regresión acredita recuperación y tamaño del contexto devuelto para dos
  casos deterministas. No acredita calidad general sobre repositorios ni
  conversaciones arbitrarias.
- Los caracteres devueltos son un límite de contexto, no tokens facturados. No
  se midieron tokens de entrada, salida, razonamiento, caché, reintentos ni costo
  monetario de un proveedor.
- No se ejecutó en esta validación una comparación pareada con Codex, OpenCode o
  Antigravity. Por ello no demuestra que Graphtyn reduzca el consumo total de una
  sesión de agente.
- La latencia corresponde al equipo descrito, con `feature-hash-v2`, y no es un
  SLA ni una medición del endpoint local de Ollama.
- Los resultados históricos de otros benchmarks no se modificaron ni se
  seleccionaron según su resultado.

## Requisitos antes de etiquetar

La etiqueta `v0.10.7` sólo se publicará después de que CI pase sobre el commit
final, construir wheel y sdist, instalarlos en un entorno vacío y comprobar que
sus metadatos coinciden con la etiqueta. Una afirmación
pública de ahorro de tokens o dinero requiere además una comparación pareada
entre agentes, con las mismas tareas, modelos, instrucciones, acceso a archivos,
calidad mínima y contabilización end-to-end.
