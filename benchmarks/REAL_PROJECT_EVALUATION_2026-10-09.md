# Evaluación de proyecto real — 2026-10-09

Se ejecutó `graphtyn memory project-evaluation --path .` sobre el checkout de
Graphtyn. Las tres sondas pasaron: dos preguntas naturales recuperaron la
decisión esperada con archivos y nodos resolubles, y la pregunta sobre un
protocolo orbital inexistente devolvió cero memorias.

El resultado reproducible está en
[`real_project_evaluation_2026-10-09.json`](real_project_evaluation_2026-10-09.json).
El evaluador no considera suficiente una coincidencia textual: comprueba que
cada archivo esté dentro del proyecto, exista en disco y que cada `node_id`
resuelva en el grafo actual. Los negativos de procedencia y abstención están
permanentes en [`tests/test_project_evaluation.py`](../tests/test_project_evaluation.py).
