# RF07 — benchmark de memoria compartida (2026-10-09)

**Resultado:** APROBADO

Cinco repeticiones independientes por escala, con 90 consultas positivas y 10 negativas por modo y repetición.
Cada repetición mide carga inicial, actualización incremental, recuperación normal, degradación sin embeddings y aislamiento.

Las consultas son sintéticas y contienen identificadores/anclas exactos del fixture.
Estos resultados no acreditan la misma calidad para preguntas generales o paráfrasis
abiertas. El smoke visual quedó omitido porque Chromium no encontró `libstdc++.so.6`.

| Registros | Recall@5 | p95 normal ms | p95 degradado ms | Carga reg/s | Incremental reg/s | SQLite MB | RSS pico MB | Fugas |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 1.00 | 136.568 | 87.653 | 4665.01 | 470.76 | 3.60 | 46.64 | 0 |
| 10,000 | 1.00 | 148.645 | 92.982 | 5353.94 | 2375.92 | 31.85 | 55.80 | 0 |
| 50,000 | 1.00 | 198.901 | 197.881 | 5451.36 | 3006.28 | 158.15 | 90.19 | 0 |

## Crecimiento 1k → 50k

- `normal_latency_p95_1000_to_50000`: 1.4564
- `degraded_latency_p95_1000_to_50000`: 2.2575
- `initial_throughput_retention`: 1.1686
- `incremental_throughput_retention`: 6.386
- `database_bytes_per_record_growth`: 1.137

## Veredicto

- ✓ `all_scale_guardrails`
- ✓ `five_repetitions_each`
- ✓ `latency_p95_growth`
- ✓ `initial_throughput_retention`
- ✓ `incremental_throughput_retention`
- ✓ `database_bytes_per_record_growth`

Commit base: `3d754e96a60fc3d1caaa1dec9423678065c49645`; worktree con cambios: `True`.

Los tiempos de carga corresponden al fixture transaccional controlado del benchmark; no representan la latencia de llamadas individuales a `checkpoint`.
