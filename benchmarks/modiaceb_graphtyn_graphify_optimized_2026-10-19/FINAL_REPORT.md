# modIAceb: baseline vs Graphtyn vs Graphify (2026-10-19)

## Alcance

Una repetición por celda sobre el commit congelado `70dc1e8b732ebb08d93e39219a2016f4ef2d8bf8`, con OpenCode 1.18.13 y `opencode/deepseek-v4.1-flash-free`. Se compararon una pregunta de arquitectura (C1) y una edición real. El coste reportado por el proveedor fue 0 en todas las celdas; por ello los tokens sirven como consumo técnico, no como ahorro monetario observado.

Graphify 0.9.92 requirió transporte HTTP local. Los intentos iniciales se conservan: dos usaron Graphtyn indebidamente y tres se detuvieron porque OpenCode no expuso el MCP local. Solo `graphify_retry5` cuenta como Graphify: cada evento contiene una llamada `graphify_query_graph`. No se repitieron las celdas válidas de baseline o Graphtyn.

## Resultados válidos

| Tarea | Brazo | Total | Entrada sin caché | Caché | Salida | Razonamiento | Tiempo | Calidad |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | Baseline | 212,571 | 38,045 | 168,320 | 3,221 | 2,985 | 54.939 s | 6/6 |
| C1 | Graphtyn | 74,154 | 24,247 | 46,592 | 2,326 | 989 | 34.323 s | 6/6 |
| C1 | Graphify | 174,657 | 44,007 | 126,848 | 2,891 | 911 | 39.251 s | 6/6 |
| Edición | Baseline | 2,423,404 | 163,591 | 2,237,184 | 9,219 | 13,410 | 257.928 s | 8/8 |
| Edición | Graphtyn | 2,294,024 | 57,544 | 2,220,032 | 16,448 | 0 | 456.814 s | 8/8 |
| Edición | Graphify | 2,652,156 | 315,061 | 2,310,784 | 10,293 | 16,018 | 629.210 s | 8/8 |

Frente a baseline, Graphtyn redujo el total 65.1% en C1 y 5.3% en edición. Graphify redujo 17.8% en C1 y aumentó 9.4% en edición. Frente a Graphify, Graphtyn usó 57.5% menos total en C1 y 13.5% menos en edición. En edición, Graphtyn tardó 77.1% más que baseline y Graphify 143.9% más.

La diferencia más favorable de Graphtyn está en entrada sin caché: -36.3% en C1 y -64.8% en edición contra baseline. En la edición, casi todo el total fue contexto cacheado para los tres brazos; por tanto, “tokens totales” no equivale directamente a coste facturable y debe publicarse junto a cada componente.

## Calidad independiente

Los tres parches se aplicaron sobre copias limpias del mismo commit. La suite común `test_model_artifact.py + test_model_publication.py` pasó: baseline 24, Graphtyn 21 y Graphify 23 pruebas. Las cantidades difieren porque cada parche agregó distinto número de casos. `git diff --check` pasó en los tres. Graphify pasó Ruff; baseline y Graphtyn conservaron dos `E741` preexistentes en `scripts/comprobar_instalacion.py`, sin afectar la tarea.

Los tres cumplen los ocho criterios: resolución y fallback, uso efectivo en lectura/hash/caché/error, API+worker, verificador de instalación, respaldo, tres escenarios de prueba, pruebas sin binarios y diff acotado. Graphify además aisló la variable en `conftest.py` y limpió tres nombres `E741` en el archivo ya modificado.

## Conclusión

En esta muestra mínima, Graphtyn sí vale más que Graphify para estas dos tareas: igual calidad, menor consumo total y menor tiempo en C1; en edición también menor consumo que Graphify, aunque ambos fueron más lentos que baseline. No demuestra que Graphtyn siempre ahorre: solo hay un repositorio, dos tareas, un modelo gratuito y una repetición. La ventaja grande se observó en consulta; en edición fue pequeña frente a baseline.
