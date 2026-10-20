# Benchmark de memoria compartida v1

> La suite v1 continúa siendo una regresión pequeña. Su extensión RF07 tiene
> evidencia `FULL` para el protocolo local de 1k/10k/50k documentado, sin
> extrapolar a rendimiento empresarial ni embeddings remotos.

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

## Extensión de escala RF07

El comando de escala acepta repeticiones y consultas deterministas:

```bash
graphtyn memory benchmark --suite scale --records 50000 \
  --query-count 90 --repetitions 5 \
  --output benchmarks/rf07_2026-10-09/scale_50000.json --path .
python benchmarks/summarize_shared_memory_rf07.py benchmarks/rf07_2026-10-09
```

La recuperación directa de mensajes tiene además una regresión aislada que no
usa un almacén real ni llama modelos o servicios externos:

```bash
PYTHONPATH=. python benchmarks/run_memory_retrieval_benchmark.py --repetitions 5 \
  --output benchmarks/memory_retrieval_2026-10-19/result.json
```

Publica Recall@6, cobertura de obligaciones, filtrado de mensajes de evaluación,
latencia y un límite de caracteres devueltos. Este límite mide tamaño de contexto;
no representa tokens facturados por un proveedor. El corpus mínimo sirve como
regresión determinista y no sustituye una comparación pareada entre agentes.

La ejecución publicada del 19 de octubre de 2026 realizó 10 consultas: Recall@6
1.00, cobertura suficiente de obligaciones 1.00, fuga de evaluación 0.00,
mediana 1.977 ms, p95 2.328 ms y máximo 273 caracteres frente al límite de
3.840. El resultado completo está en
[`memory_retrieval_2026-10-19/result.json`](../benchmarks/memory_retrieval_2026-10-19/result.json)
y su resumen reproducible en
[`memory_retrieval_2026-10-19/REPORT.md`](../benchmarks/memory_retrieval_2026-10-19/REPORT.md).
El entorno y los límites de interpretación de la publicación están en
[`release-validation-0.10.7.md`](release-validation-0.10.7.md).

El mismo comando se ejecutó para 1.000 y 10.000 registros. El informe consolidado,
entorno, umbrales, muestras por consulta y resultados de las cinco repeticiones están
en [`benchmarks/rf07_2026-10-09/REPORT.md`](../benchmarks/rf07_2026-10-09/REPORT.md).
Las consultas RF07 son sintéticas y contienen identificadores/anclas exactos del
fixture. Miden regresión, escala y degradación de ese protocolo; no acreditan la
misma calidad ante preguntas generales, paráfrasis abiertas o conversaciones reales.

Para complementar esa medición sin alterar el protocolo sintético, use
`--query-profile mixed`:

```bash
graphtyn memory benchmark --suite scale --records 1000 \
  --query-count 90 --query-profile mixed --repetitions 1 --path .
```

El perfil mixto conserva la consulta con identificador exacto como control y
añade preguntas en español y paráfrasis de decisiones que no contienen
`scaleanchor`, además de negativos naturales sin palabras del fixture. El
resultado separa recall/MRR y precisión negativa en `by_query_kind`; estas
sondas complementan RF07 y no sustituyen su ejecución en 1.000, 10.000 y
50.000 registros.

Para ejercitar la procedencia sobre un proyecto real, el comando siguiente
crea un almacén temporal, enlaza cada respuesta con archivos y nodos del
checkout actual y registra cualquier fallo reproducible:

```bash
graphtyn memory project-evaluation --path . \
  --output benchmarks/real_project_evaluation.json
```

Un caso positivo sólo pasa si la memoria esperada aparece y sus archivos y
`node_ids` siguen resolviendo en el proyecto. Las preguntas negativas deben
devolver cero memorias. Los errores se serializan en `errors` para convertirlos
en regresiones permanentes.
