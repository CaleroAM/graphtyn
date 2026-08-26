# Pruebas y benchmarks

La regresión ejecuta `pytest -q --ignore=tests/test_api.py`. En el entorno de
agosto de 2026, `fastapi.testclient.TestClient` se bloquea incluso con una app
FastAPI mínima; la API se valida además levantando Uvicorn temporalmente y
consultando salud, OpenAPI y rutas v1 autenticadas. CI no debe omitir esa prueba.

`tests/test_security_leaks.py` es la barrera adversarial de privacidad. Comprueba
texto y metadatos anidados, Bearer/JWT/AWS, credenciales en URL, prompts del
sistema, rutas absolutas, temporales, vectores, stderr remoto, permisos de API,
salida CLI de tokens, traversal de backups/adaptadores y ausencia de identidades
de una máquina concreta. También inspecciona bytes crudos de SQLite/configuración,
no solamente las respuestas de alto nivel.

## Estados de evidencia

- **FULL**: mismo corpus, tarea, modelo, presupuesto y rúbrica; corrida completa.
- **PARTIAL**: resultado útil, pero falta una celda o control comparable.
- **HISTORICAL**: evidencia de otra versión; útil para regresión.
- **VENDOR**: cifra publicada por un proveedor, no medida por Graphtyn.
- **PENDING**: protocolo definido, ejecución incompleta.

Una corrida parcial o una cifra del proveedor nunca debe presentarse como una
comparación concluyente.

## Pirámide de validación

1. Unitarias de parser, resolución, impacto, memoria, presupuesto y seguridad.
2. Contratos de CLI, MCP, HTTP y dashboard.
3. Repositorios reales multilenguaje con ground truth atómico.
4. Comparación pareada: agente solo, Gra…ify y Graphtyn con el mismo modelo.
5. Matriz de 36 tareas/108 celdas antes de afirmar superioridad general.

## Métricas

- calidad y cobertura de hechos críticos;
- tokens de entrada/salida, latencia y llamadas de herramienta;
- Recall@k, MRR, nDCG y atribución correcta;
- abstenciones, contradicciones y contaminación entre proyectos;
- índice inicial/incremental, tamaño y errores.

La estimación `bytes UTF-8 / 4` compara payloads, pero no equivale a facturación.
Los resultados están en [`BENCHMARKS.md`](../BENCHMARKS.md).

## Reproducción mínima

```bash
python -m pytest -q
graphtyn benchmark-suite validate --protocol benchmarks/statistical_protocol_36_tasks.json
graphtyn memory doctor --path .
graphtyn memory benchmark --path .
graphtyn report --path .
```

Las pruebas con agentes externos deben fijar commit, modelo, prompt, límites,
temperatura y herramientas. Sin esos controles se publican como observación.
