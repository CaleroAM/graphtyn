# modIAceb después de optimizar edición: baseline vs Graphtyn vs Graphify

## Alcance

Una repetición por celda sobre el commit congelado `70dc1e8b732ebb08d93e39219a2016f4ef2d8bf8`, OpenCode 1.18.13 y `opencode/deepseek-v4.1-flash-free`. Se preservaron los resultados anteriores. El coste reportado por el proveedor fue cero en las seis celdas.

## Resultados válidos

| Tarea | Brazo | Total | Entrada sin caché | Caché | Salida | Razonamiento | Tiempo | Calidad |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | Baseline | 330,486 | 45,395 | 277,120 | 4,267 | 3,704 | 48.368 s | 6/6 |
| C1 | Graphtyn | 94,439 | 23,580 | 67,328 | 2,798 | 733 | 29.978 s | 6/6 |
| C1 | Graphify | 344,478 | 52,000 | 286,336 | 3,726 | 2,416 | 90.853 s | 6/6 |
| Edición | Baseline | 2,325,475 | 79,673 | 2,221,824 | 23,978 | 0 | 652.320 s | 8/8 |
| Edición | Graphtyn | 2,494,477 | 59,631 | 2,413,056 | 21,790 | 0 | 444.486 s | 8/8 |
| Edición | Graphify | 2,579,481 | 127,247 | 2,431,744 | 10,242 | 10,248 | 414.945 s | 8/8 |

En C1, Graphtyn redujo el total 71.4% y el tiempo 38.0% frente a baseline; frente a Graphify redujo 72.6% y 67.0%. En edición, Graphtyn aumentó el total 7.3% frente a baseline, aunque tardó 31.9% menos. Frente a Graphify usó 3.3% menos tokens, pero tardó 7.1% más.

## Calidad independiente

Los tres parches se aplicaron sobre copias limpias del mismo commit. La suite común `test_model_artifact.py + test_model_publication.py` pasó: baseline 24, Graphtyn 23 y Graphify 22 pruebas. `git diff --check` y la sintaxis de scripts shell pasaron. Baseline dejó Ruff limpio; Graphtyn y Graphify conservaron dos `E741` preexistentes en `scripts/comprobar_instalacion.py`.

Los tres parches cumplen los ocho criterios congelados. Las cantidades de pruebas difieren porque cada parche añadió casos distintos.

## Diagnóstico del flujo Graphtyn

La llamada MCP fue real y devolvió `implementation_context`, `do_not_expand=true`, comandos extraídos de CI y la política de no aprovisionar dependencias. Sin embargo, `source_evidence` reemplazó la guía superior. El agente hizo una búsqueda de 100 coincidencias, 51 llamadas y 43 pasos, buscó entornos globalmente e instaló paquetes offline. El brief también eligió varias pruebas poco relacionadas y omitió archivos requeridos en `read_first`.

Por tanto, la optimización mejoró las llamadas frente a la corrida anterior (57 a 51) y redujo el tiempo, pero no redujo los tokens totales frente al baseline emparejado. El resultado no demuestra un efecto universal: es una repetición, un repositorio y un modelo gratuito.

## Evidencia trazable

- C1 baseline, Graphtyn y Graphify: `results.json:2`, `results.json:23` y `results.json:44`.
- Edición Graphify, Graphtyn y baseline: `results.json:65`, `results.json:94` y `results.json:121`.
- Calificaciones congeladas: `grades.json:3` y `grades.json:8`.
- Verificación independiente: `verification/baseline_pytest.txt:2`, `verification/graphtyn_pytest.txt:2` y `verification/graphify_pytest.txt:2`.
- Decisiones posteriores al brief de Graphtyn: `runs/edit_manifest_graphtyn/events.jsonl:2`, `:13`, `:76`, `:115` y `:124`.
