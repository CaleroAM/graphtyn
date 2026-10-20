# Regresión aislada de recuperación de mensajes

Fecha: 2026-10-19. El comando se ejecutó desde la raíz del repositorio:

```bash
PYTHONPATH=. .venv/bin/python benchmarks/run_memory_retrieval_benchmark.py \
  --repetitions 5 \
  --output benchmarks/memory_retrieval_2026-10-19/result.json
```

## Resultado

| Métrica | Resultado |
|---|---:|
| Casos | 2 |
| Repeticiones | 5 |
| Consultas | 10 |
| Recall@6 | 1.00 |
| Obligaciones con evidencia suficiente | 1.00 |
| Fuga de mensajes de evaluación | 0.00 |
| Latencia mediana | 1.977 ms |
| Latencia p95 | 2.328 ms |
| Máximo contexto recuperado | 273 caracteres |
| Límite por consulta | 3.840 caracteres |

Entorno: Linux 6.18.35 x86_64, Python 3.13.13 e Intel Core i5-12500H. El
artefacto completo es [`result.json`](result.json).

## Alcance

La prueba crea un almacén temporal, usa `feature-hash-v2`, no llama modelos ni
servicios externos y no modifica un almacén activo. Comprueba dos casos
deterministas, la cobertura de obligaciones, la exclusión de un eco de evaluación
y el tamaño del contexto recuperado.

Los caracteres no representan tokens facturados. La latencia depende del equipo
y no es un SLA. Este resultado no mide tokens end-to-end, costo monetario ni
calidad de edición de Codex, OpenCode o Antigravity; tampoco sustituye una
comparación pareada entre agentes.
