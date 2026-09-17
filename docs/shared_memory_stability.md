# Estabilidad de memoria compartida

> Registro `PARTIAL` hasta repetir la matriz con más proyectos y clientes.

## Telemetría de costos

Cada ingestión y recuperación se registra en `memory_telemetry`. La auditoría
separa procesamiento local (`local_input_tokens`, `local_output_tokens` y
`embedding_characters`) del contexto que el cliente puede enviar al modelo remoto
(`remote_context_tokens`). `raw_history_tokens_avoided` compara ese paquete con
los mensajes fuente de las memorias recuperadas. Son estimaciones `UTF-8 / 4`, no
tokens facturados por un proveedor.

**Suite:** `stable-30x3x3`  
**Fecha:** 2026-08-22  
**Diseño:** 30 escenarios × 3 formulaciones × 3 agentes solicitantes

La suite genera 270 consultas positivas entre Codex, AGY y OpenClaw, más 15
consultas negativas. Las memorias se atribuyen rotativamente a AGY, OpenCode,
Codex y OpenClaw. Incluye ramas `main`/feature, consultas español/inglés y aliases

## Matriz viva de clientes

Además de la suite sintética, el 22 de agosto de 2026 se ejecutó una matriz E2E
contra el mismo daemon persistente y autenticado. OpenClaw escribió y una sesión
nueva de OpenClaw, OpenCode (`x-preview-f-free`), AGY y Codex recuperaron la misma
memoria con atribución. OpenCode y AGY también escribieron en sentido inverso y
otros clientes recuperaron sus checkpoints. Evidencia estructurada:
[`benchmarks/shared_memory_live_matrix_2026-08-22.json`](../benchmarks/shared_memory_live_matrix_2026-08-22.json).
estables equivalentes a task IDs o símbolos del proyecto.

## Resultado observado · 22 de agosto de 2026

| Métrica | Resultado |
|---|---:|
| Consultas positivas | 270 |
| Consultas negativas | 15 |
| Recall@5 / Recall@10 | 100% / 100% |
| MRR | 0.9889 |
| Atribución | 100% |
| Exactitud negativa | 100% |
| Tokens estimados por consulta | 292.65 |
| Latencia media / p95 | 8.16 / 13.33 ms |
| Fallos | 0 |

La primera ejecución obtuvo Recall@5 de 71.11% porque las consultas usaban aliases
compuestos que no existían en las memorias. El contrato se corrigió para persistir
el alias estable junto al título, como Graphtyn hace con símbolos/task IDs; las
consultas no fueron modificadas. Esta medición de tokens es histórica: el cálculo
actual contabiliza la respuesta estructurada completa, incluidos metadatos y
referencias.

## Reejecución · 13 de septiembre de 2026

Se repitió la matriz completa después de ampliar el contexto con episodios,
mensajes fuente y relaciones. La ejecución actual mide todos los campos que el
cliente recibe:

| Métrica | Resultado |
|---|---:|
| Consultas positivas / negativas | 270 / 15 |
| Recall@5 / Recall@10 | 100% / 100% |
| MRR | 0,9889 |
| Atribución / exactitud negativa | 100% / 100% |
| Tokens estimados por consulta | 516,93 |
| Latencia media / p95 | 37,11 / 47,75 ms |
| Fallos | 0 |

Los 90 casos por solicitante también alcanzaron Recall@5 de 100% para AGY,
Codex y OpenClaw. El presupuesto completo promedio quedó bajo el límite actual
de 750 tokens; este límite cuenta estructura y referencias además del texto de
memoria. El benchmark es sintético y no sustituye la evaluación de conversaciones
reales.

## Guardrails

La prueba automatizada exige Recall@5 y MRR ≥ 0.98, atribución y negativos al 100%,
promedio ≤ 750 tokens de respuesta completa y cero fallos. También verifica resultados por agente para
evitar que un promedio oculte un cliente peor.

```bash
graphtyn memory benchmark --suite stability \
  --output benchmarks/shared_memory_stability_result.json --path .
```

Esta suite sintética es un gate de regresión estable, no sustituye una evaluación
de conversaciones humanas ni demuestra calidad competitiva por sí sola.
