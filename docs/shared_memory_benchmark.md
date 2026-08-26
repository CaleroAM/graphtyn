# Benchmark de memoria compartida v1

> Evidencia `PARTIAL`; consulte [`testing.md`](testing.md). No demuestra todavía
> rendimiento empresarial a gran escala.

**Fecha:** 2026-08-22  
**Corpus:** `benchmarks/shared_memory_v1.json`  
**Protocolo:** `graphtyn-shared-memory-v1`

Este benchmark comprueba recuperación entre agentes, paráfrasis español/inglés,
atribución y coste del contexto. Siempre publica todas las consultas y fallos.

## Evolución observada

| Ejecución | Recall@5 | MRR | Atribución | Tokens estimados |
|---|---:|---:|---:|---:|
| Fallback inicial | 50% | 0.50 | 50% | 1,029 |
| Umbral vectorial permisivo | 100% | 0.875 | 100% | 2,047 |
| Híbrido con solapamiento semántico | 100% | 1.00 | 100% | 1,255 |

La segunda ejecución recuperó todos los recuerdos, pero añadió distractores y casi
duplicó el contexto. La tercera conserva el recall, coloca todas las respuestas
correctas en primer lugar y reduce 38.7% los tokens frente a esa ejecución.

Resultado final observado: latencia media aproximada 7.9 ms y cuatro consultas sin
fallos. La latencia depende de la máquina y no es un SLA.

## Reproducción

```bash
graphtyn memory benchmark \
  --dataset benchmarks/shared_memory_v1.json \
  --output benchmarks/shared_memory_v1_result.json \
  --path .
```

## Límites

Cuatro consultas son una prueba de regresión, no evidencia competitiva suficiente.
Antes de publicar una afirmación externa se requiere ampliar a por lo menos 30
escenarios, tres formulaciones y tres agentes, conservar negativos difíciles y
reportar intervalos de confianza. Los tokens usan la aproximación UTF-8/4 y no
representan facturación de un proveedor.
