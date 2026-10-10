# Plan de correcciones de fiabilidad de Graphtyn

**Fecha:** 8 de octubre de 2026.

**Estado:** RF01–RF07 cerradas técnicamente. RF07 se ejecutó en la infraestructura
objetivo acordada con cinco repeticiones de 1k, 10k y 50k; RF08 espera únicamente
la firma humana sobre el cambio y sus límites.

**Alcance:** procedencia de evidencias, validación de afirmaciones, comparación de ejecuciones y evaluación de recuperación.

**Origen:** revisión posterior a los cambios del plan del 7 de octubre.

**Entrega de este documento:** informe y evidencia de cierre de las correcciones de fiabilidad.

## 1. Objetivo y relación con el plan anterior

Cerrar tres problemas reproducidos después de las primeras mejoras y disponer de
evidencia reproducible para revisar su integración:

1. Un registro de ejecución inventado puede promover métricas a `verified_measured`.
2. Ciertas citas inexistentes, cifras sin respaldo y afirmaciones compuestas reciben `supported`.
3. Las repeticiones de una misma tarea se emparejan incorrectamente en el benchmark.

Este documento complementa el [análisis del 7 de octubre](ANALISIS_Y_PLAN_MEJORAS_GRAPHTYN_2026-10-07.md)
y precisa el cierre de la [especificación G01](ESPECIFICACION_ESTADOS_VERSIONADOS_G01.md).
Reabre los casos incompletos de H01/G02 y H02/G03 y añade una corrección al
benchmark de agentes. Las mejoras de recuperación, impacto y diagnóstico ya
observadas deben conservarse y seguir cubiertas por regresiones.

Se considerará cerrado el bloque de correcciones cuando los fallos dejen de
reproducirse, los casos válidos sigan funcionando y los consumidores comuniquen
el mismo estado. La evaluación de rendimiento tiene su propio cierre; pasar
pruebas funcionales no demuestra una mejora de velocidad, coste o relevancia.

## 2. Línea base y límites de la evidencia

La revisión anterior de esta conversación examinó Graphtyn `0.10.4`, con HEAD
`3d754e96a60fc3d1caaa1dec9423678065c49645` y modificaciones locales sin commit.
Por tanto, el commit por sí solo no identifica el código examinado. RF01 deberá
congelar las huellas y la diferencia local antes de implementar.

En esa revisión pasaron **144 pruebas seleccionadas**, distribuidas en:

| Selección ejecutada | Resultado histórico de la revisión |
|---|---:|
| Regresiones H01–H06, `test_delivery_features.py` y `test_advanced_quality.py` | 40 aprobadas |
| `test_mcp_server.py`, `test_api.py`, `test_dashboard_contracts.py` y `test_memory_scope.py` | 97 aprobadas |
| Selección de evidencia, diagnóstico y watchers de `test_shared_memory.py` | 7 aprobadas; 45 no seleccionadas |

Los experimentos adicionales usaron grafos y bases temporales y detectaron los
fallos siguientes. Estos resultados son antecedentes, no pruebas nuevas
ejecutadas al redactar este archivo ni evidencia de cierre de las correcciones.
La consulta de memoria compartida realizada para este plan no recuperó la
revisión reciente; se utilizó la conversación y se cotejaron los puntos de código.

| Caso | Reproducción observada | Resultado requerido |
|---|---|---|
| E01 | JSON con `tests_passed=123456`, comando nunca ejecutado, commit ficticio y hashes de relleno: `verified_measured`. | Conservarlo como informe declarado/importado; ninguna métrica queda verificada. |
| V01 | `handler calls Service (missing.py).`, con un nodo sin `file`: `supported`. | Cita no resuelta; la afirmación no recibe `supported`. |
| V02 | `handler calls Service (nonexistent/src/handler.py:5).`: `supported`. | La ruta inexistente no se resuelve por compartir un sufijo. |
| V03 | `handler calls Service exactly 5 times (src/handler.py:5).`: `supported`. | El número de línea no respalda la frecuencia de llamadas. |
| V04 | `handler calls Service and sends passwords to public logs.`: `supported`. | La relación conocida no respalda la segunda afirmación. |
| B01 | Referencia `[100, 300]`, candidato `[80, 280]`, misma tarea y repeticiones 0/1: delta medio `-120`. | Dos pares correctos, deltas `[-20, -20]`, media `-20`. |

Para V01–V04, el grafo de reproducción contiene `handler` en `src/handler.py`
(líneas 1–15), `Service` en `src/service.py` (1–30), un nodo de proyecto sin
`file` y una relación `handler → Service`, etiqueta `llama`, confianza `EXTRACTED`,
ubicada en `src/handler.py:5`. El control positivo es
`handler calls Service (src/handler.py:5).`.

## 3. Organización del trabajo

Las responsabilidades indican áreas técnicas propuestas. Se asignará una persona
responsable y un revisor por tarea al iniciar. Las horas son esfuerzo individual
estimado, sujeto a ajustar tras RF01; no son fechas comprometidas.

| ID | Tarea | Prioridad | Área responsable | Dependencias | Horas | Estado |
|---|---|---|---|---|---:|---|
| RF01 | Fijar línea base y convertir reproducciones en regresiones | P0 | Calidad / core | — | 2 | Cerrada |
| RF02 | Acordar estados, compatibilidad y alcance de la verificación | P0 | Core / integración | RF01 | 3 | Cerrada |
| RF03 | Verificar procedencia mediante ejecutor local y corregir ingesta | P0 | Memoria / ejecución | RF02 | 12 | Cerrada |
| RF04 | Corregir citas, cifras y afirmaciones compuestas | P0 | Validación | RF02 | 7 | Cerrada técnicamente |
| RF05 | Corregir pares y cálculo del benchmark | P1 | Evaluación | RF01 | 5 | Cerrada |
| RF06 | Integrar estados, migración y pruebas entre superficies | P0 | Integración / calidad | RF03, RF04, RF05 | 4 | Cerrada técnicamente |
| RF07 | Medir recuperación, latencia y comportamiento degradado | P1 | Evaluación / memoria | RF05, RF06 | 6 | Cerrada técnicamente; artefactos RF07 versionados |
| RF08 | Documentar resultados y revisar el cierre | P1 | Mantenedor / revisor | RF06, RF07 | 2 | Abierta: pendiente de firma humana |

**Estimación inicial total: 37–62 horas**, más la reserva que se acuerde al fijar
responsables. RF03 y RF04 pueden avanzar en paralelo después de RF02; RF05 puede
avanzar desde RF01. Esta distribución no presupone agentes automáticos ni
disponibilidad de varias personas.

## 4. RF01 — Línea base y regresiones reproducibles

- [x] Registrar versión, HEAD, estado del árbol de trabajo, huellas de archivos relevantes y entorno de Python/dependencias.
- [x] Preservar los cambios locales existentes. Preparar una rama o checkout que contenga explícitamente la base revisada antes de implementar.
- [x] Incorporar E01, V01–V04 y B01 a pruebas automatizadas con datos temporales y `GRAPHTYN_HOME` aislado.
- [x] Confirmar que las aserciones expresan el comportamiento corregido y fallan con la implementación defectuosa.
- [x] Añadir controles positivos: cita válida, relación extraída válida, importación ordinaria sin promoción y comparación de una tarea sin repeticiones.
- [x] Guardar resultados de la línea base con comando, salida, código de salida y manifiesto del código examinado.

**Aceptación:** cada fallo puede reproducirse desde un checkout preparado, sin
depender de archivos en `/tmp`, de memorias reales ni de servicios externos.
No se aceptan `xfail` permanentes ni aserciones que normalicen el resultado incorrecto.

## 5. RF02 — Contrato de evidencia y veredictos

- [x] Separar `operation_ok`, resolución de referencias, respaldo de cada afirmación y estado de ejecución.
- [x] Documentar estos niveles conceptuales: informe importado, integridad comprobada, ejecución declarada, ejecución observada y métrica verificada.
- [x] Definir su representación versionada en campos existentes/nuevos. `execution_declared` es una propuesta de estado, no una API disponible por este plan.
- [x] Reservar `execution_observed` para evidencia obtenida por una fuente comprobada. Un JSON completo o un hash con formato válido no bastan.
- [x] Reservar `verified_measured` para las métricas vinculadas al resultado real de una ejecución; un proceso que termina con código 0 no verifica cualquier cifra del informe.
- [x] Definir cómo representar observaciones fallidas, canceladas, obsoletas, de otro proyecto y sin procedencia suficiente.
- [x] Definir veredicto por afirmación atómica y agregación conservadora. Si no se puede resolver una frase compuesta, devolver respaldo parcial o abstención con motivo.
- [x] Revisar consumidores de `ok`, `status`, `confidence`, `claim_policy` y `verification_level`; documentar migración y compatibilidad de formatos históricos.

**Aceptación:** tabla de estados con ejemplos positivos/negativos y pruebas de
contrato compartidas por motor, CLI, API, MCP y panel. Ningún consumidor interpreta
éxito técnico como veracidad factual o probabilidad estadística de acierto.

## 6. RF03 — Procedencia real e integración con ejecución

Puntos principales: [`shared_memory.py`](../graphtyn/core/shared_memory.py),
`_validated_execution_record`, `ingest_benchmark_evidence`, `_claim_policy`,
`evidence_status`, `_revision_status` y `attribution_graph`.

- [x] Implementar un recorrido local explícito para ejecutar una verificación y registrar su resultado; importar un informe nunca ejecutará los comandos que este declare.
- [x] Generar el identificador de ejecución desde el ejecutor, con proyecto, argumentos, directorio, tiempos, código de salida y estado terminal reales.
- [x] Guardar salida y artefactos con hashes calculados sobre los bytes conservados. Comprobar el contenido, no solamente la forma del hash.
- [x] Registrar antes de ejecutar el commit, cambios locales relevantes, archivos no versionados necesarios, datos, pruebas y entorno; detectar cambios durante la ejecución.
- [x] Vincular informe y ejecución mediante un registro local independiente del JSON importado. Validar proyecto, revisión y artefactos contra ese registro.
- [x] Extraer métricas de salidas estructuradas comprobables —por ejemplo, resultados de pruebas— y conservar la relación entre cada métrica y su fuente.
- [x] Si un informe mezcla métricas comprobadas y cifras declaradas, distinguirlas individualmente; no promover todo el informe por una sola métrica válida.
- [x] Cubrir timeout, fallo, cancelación, reintento e importación idempotente. Ningún caso fallido conserva una etiqueta de éxito anterior.
- [x] Detectar obsolescencia al cambiar código, datos, pruebas o entorno vinculados; conservar el resultado histórico con su revisión original.
- [x] Documentar el límite de confianza del ejecutor local y sus permisos. El diseño no supone resistencia a un administrador que controle tanto el registro como sus artefactos.

**Pruebas mínimas:** E01; log ausente o alterado; hash inventado; ejecución de otro
proyecto; revisión diferente; cambio local durante la ejecución; métrica adulterada
con ejecución auténtica; fallo/cancelación; repetición idempotente; ejecución real
exitosa con una métrica verificable. Adaptar la prueba existente que usa hashes
sintéticos y espera `verified_measured` para que no certifique procedencia ficticia.

**Aceptación:** el ejecutor registra un comando realmente ejecutado y su métrica
comprobable; el JSON inventado sigue siendo una declaración aun con todos sus
campos completos. Un adaptador de CI podrá reutilizar el contrato, con verificación
de origen propia; su implementación se puede planificar después del ejecutor local.

## 7. RF04 — Citas y afirmaciones respaldadas

Puntos principales: [`answer_validation.py`](../graphtyn/core/answer_validation.py),
`_resolve_citation`, `_unsupported_numbers`, `_relation_matches_claim` y `validate_answer`.

- [x] Excluir rutas vacías. Un nodo sin `file` no puede resolver cualquier cita.
- [x] Normalizar separadores y resolver rutas contra la identidad del proyecto/índice; evitar coincidencias bidireccionales arbitrarias por sufijo.
- [x] Definir el tratamiento de rutas absolutas, nombres abreviados, archivos homónimos y mayúsculas según la plataforma. Una abreviatura ambigua debe explicitar su ambigüedad.
- [x] Verificar líneas en el archivo efectivamente resuelto y tratar de forma explícita un índice ausente u obsoleto.
- [x] Excluir del análisis numérico únicamente los caracteres de la cita, utilizando sus posiciones. No excluir una cifra en toda la frase porque también aparezca como número de línea.
- [x] Vincular cada cantidad con la afirmación y su evidencia; encontrar el mismo número en un texto cercano tampoco prueba su significado.
- [x] Evaluar afirmaciones atómicas o limitar `supported` a las relaciones cuyo alcance completo se pueda verificar. Una cláusula sin evidencia impide el respaldo total de la frase.
- [x] Conservar dirección, negación, modalidad y distinción entre `EXTRACTED`, `INFERRED` y `AMBIGUOUS`.
- [x] Exponer razones estables y evidencia específica por afirmación. Mantener `operation_ok=true` cuando la operación se completó, aunque el contenido carezca de respaldo.

**Pruebas mínimas:** V01–V04; cita real; línea fuera de rango; dos `service.py` en
carpetas diferentes; ruta absoluta válida y ruta inexistente; separadores Windows;
cifra válida con evidencia explícita; relación negada/invertida; cláusula adicional
sin evidencia; evidencia ambigua; texto que el motor no puede resolver.

**Aceptación:** desaparecen los falsos positivos reproducidos y permanecen los
controles positivos. El motor documenta su alcance de trazabilidad, sin presentarse
como verificador universal de cualquier afirmación en lenguaje natural.

**Estado de cierre:** las regresiones cubren cantidades con significado distinto,
contenido residual con `then`, `which` o sin conector y relaciones compuestas con
certezas mixtas. El contrato se verificó en núcleo, CLI, API y MCP; RF04 queda
cerrada técnicamente mediante la integración de RF06.

## 8. RF05 — Comparaciones correctas y reproducibles

Punto principal: [`agent_benchmark.py`](../graphtyn/core/agent_benchmark.py),
`compare_agent_runs` y `_summary`.

- [x] Establecer una clave de pareja: tarea, repetición y semilla/configuración experimental cuando corresponda. El identificador del tratamiento pertenece a la variante, no a la clave compartida de la pareja.
- [x] Detectar duplicados y pares incompletos; informar cuáles se excluyen y por qué. No sobrescribir ejecuciones silenciosamente.
- [x] Mantener compatibilidad con una única ejecución inequívoca por tarea. Los datos históricos ambiguos deben solicitar identificación explícita o quedar fuera del cálculo pareado.
- [x] Comprobar modelo, repositorio, revisión del proyecto evaluado, instrucciones, entorno y presupuesto. Registrar por separado la versión de Graphtyn comparada.
- [x] Separar resúmenes globales descriptivos de resultados sobre pares comparables. No atribuir diferencias al tratamiento cuando cambian otras condiciones sin control.
- [x] Tratar métricas ausentes como ausentes; no sustituir calidad desconocida por cero ni informar un empate inventado.
- [x] Calcular B01 con deltas `[-20, -20]` y media `-20`, independientemente del orden de entrada.
- [x] Definir la unidad estadística: las repeticiones de una tarea no equivalen a tareas independientes. Agrupar por tarea al estimar incertidumbre cuando corresponda.
- [x] Revisar el coste de enumerar `2^n` permutaciones. Limitar el método exacto a muestras pequeñas y usar un método acotado y reproducible para muestras mayores, con semilla y método registrados.

**Pruebas mínimas:** B01; orden permutado; varias tareas y repeticiones; duplicados;
pares faltantes; archivos vacíos; datos sin identificadores; métricas ausentes;
condiciones incompatibles; signos de las diferencias; muestra pequeña contrastada
con cálculo manual; conjunto grande que respete un presupuesto de ejecución fijado.

**Aceptación:** resultados numéricos verificables, identificación auditable de cada
pareja y cálculo acotado. Los cambios en ahorro de tokens solo se publican junto
con calidad, errores, latencia y límites de comparabilidad.

## 9. RF06 — Integración, datos históricos y documentación

- [x] Propagar contratos a CLI, API, MCP, `memory_context`, `memory_evidence_status`, grafo de atribución y panel; comprobar etiquetas y razones mostradas.
- [x] Probar el recorrido real: ejecutar → registrar → importar → consultar → modificar una dependencia → observar obsolescencia.
- [x] Probar el recorrido negativo: importar informe inventado → consultar por memoria y panel → confirmar que ninguna superficie lo eleva a verificado.
- [x] Revisar evidencias históricas creadas con la promoción anterior. Preparar migración idempotente con vista previa, respaldo y trazabilidad, conservando el contenido original.
- [x] Degradar etiquetas históricas sin procedencia suficiente; permitir reverificación explícita. No borrar evidencia para ocultar el problema ni verificarla por heredar `status=verified`.
- [x] Actualizar G01 y las guías que afirman cierre de H01/H02, diferenciando diseño, implementación y evidencia de aceptación.
- [x] Verificar clientes que consumen el formato anterior y documentar la transición de versión necesaria.
- [x] Completar el cierre de integración del contrato semántico de RF04 y confirmar
  que las superficies consumidoras conservan `ambiguous` o `partially_supported`,
  junto con su razón y la certeza de cada relación requerida.

**Aceptación:** pruebas de integración y contratos aprobadas, estados consistentes
en todas las superficies afectadas y migración ensayada sobre una copia aislada.
Las pruebas de procedencia no deben depender exclusivamente del propio
`validate-answer`, que también está siendo corregido.

## 10. RF07 — Evaluación de recuperación y funcionamiento degradado

Ampliar las capacidades existentes de evaluación en
[`memory_benchmark.py`](../graphtyn/core/memory_benchmark.py) y
[`agent_benchmark.py`](../graphtyn/core/agent_benchmark.py).

- [x] Preparar un conjunto versionado de consultas con referencias relevantes revisadas y casos sin respuesta; separar desarrollo y evaluación.
- [x] Incluir memorias antiguas, términos importantes al final de consultas largas, distractores, correcciones históricas y aislamiento entre proyectos/agentes.
- [x] Evaluar 1 000, 10 000 y 50 000 registros en la infraestructura objetivo acordada, con cinco repeticiones independientes por tamaño y artefactos crudos conservados.
- [x] Medir Recall@k, MRR, respuestas sin evidencia, tamaño de contexto, latencia p50/p95 y memoria máxima en conjuntos de prueba controlados.
- [x] Registrar separadamente tokens medidos por proveedor y estimaciones; medir el coste de la tarea completa cuando se evalúe ahorro.
- [x] Ensayar servicio de embeddings no disponible, timeout y vectores incompatibles. La degradación debe ser explícita y no comparar vectores de espacios incompatibles.
- [x] Fijar presupuestos de tiempo/memoria y tolerancias de regresión antes de ejecutar la evaluación final, apoyándose en la línea base y el equipo objetivo.
- [x] Comparar las variantes con las mismas consultas y condiciones, empleando el emparejamiento corregido de RF05.

**Aceptación:** informe reproducible con resultados por escenario, fallos y límites;
cumplimiento de los umbrales fijados previamente y ausencia de fugas de alcance en
los casos de aislamiento. Una medición favorable en un tamaño no acredita los demás.
Un resultado insuficiente abre una corrección concreta; no se cambia el umbral
después de ver el resultado para declarar el cierre.

### Ejecución final de RF07 (9 de octubre de 2026)

Se ejecutó `graphtyn-shared-memory-rf07-v1` en el equipo objetivo `acer`, Linux
6.18.35, Python 3.13.13, SQLite 3.51.2, 16 CPU lógicos y 16,46 GB de RAM. Cada
escala tuvo cinco bases independientes; cada repetición cargó el corpus, actualizó
el 1 %, ejecutó 90 consultas positivas y 10 negativas en modo normal y repitió las
mismas consultas con embeddings no disponibles. También se comprobó aislamiento.
Las consultas son sintéticas y contienen identificadores/anclas exactos del fixture;
esta ejecución no acredita calidad equivalente para preguntas generales o paráfrasis
abiertas sin esas anclas.

| Registros | Recall@5 / MRR / nDCG@10 | p95 normal | p95 degradado | Carga inicial | Actualización incremental | SQLite | RSS pico | Fugas |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 000 | 1,0 / 1,0 / 1,0 | 136,568 ms | 87,653 ms | 4 665,01 reg/s | 470,76 reg/s | 3,60 MB | 46,64 MB | 0 |
| 10 000 | 1,0 / 1,0 / 1,0 | 148,645 ms | 92,982 ms | 5 353,94 reg/s | 2 375,92 reg/s | 31,85 MB | 55,80 MB | 0 |
| 50 000 | 1,0 / 1,0 / 1,0 | 198,901 ms | 197,881 ms | 5 451,36 reg/s | 3 006,28 reg/s | 158,15 MB | 90,19 MB | 0 |

Todos los guardrails pasaron. De 1k a 50k, p95 creció 1,4564× en modo normal y
2,2575× sin embeddings; los bytes por registro variaron 1,137×. El RSS máximo fue
0,5480 % de la RAM, sin errores ni contaminación. El informe y las muestras crudas
están en [`benchmarks/rf07_2026-10-09/`](../benchmarks/rf07_2026-10-09/REPORT.md).
La carga usa el fixture transaccional del benchmark y no equivale a latencia de
llamadas individuales a `checkpoint`.

## 11. Ejecución de verificaciones y evidencias de cierre

Estos comandos son la base seleccionada de verificación, para ejecutar después de
implementar. Las pruebas nuevas deberán incorporarse a las suites correspondientes.

```bash
.venv/bin/python -m pytest -q \
  tests/test_h01_h02_regressions.py \
  tests/test_h03_h04_regressions.py \
  tests/test_h05_h06_regressions.py \
  tests/test_delivery_features.py \
  tests/test_advanced_quality.py \
  tests/test_reliability_regressions_2026_10_08.py

.venv/bin/python -m pytest -q \
  tests/test_mcp_server.py \
  tests/test_api.py \
  tests/test_dashboard_contracts.py \
  tests/test_memory_scope.py \
  tests/test_shared_memory.py
```

La segunda selección amplía la revisión anterior al archivo completo de memoria;
el número esperado de pruebas ya no tiene por qué ser 144. La ruta `.venv/bin/python`
corresponde al entorno Linux revisado; adaptar el ejecutable al entorno de prueba.

Antes y después de cambios que afecten consumidores, ejecutar el análisis de
impacto conforme a `AGENTS.md`, revisar `GRAPHTYN_CHANGE_REPORT.md` y añadir las
verificaciones pertinentes. Si cambia el panel, comprobar también visualmente los
estados válidos, parciales, inválidos y obsoletos.

Cada cierre deberá adjuntar:

1. Identificación del código y entorno, incluyendo cambios locales cuando existan.
2. Comandos, tiempos, códigos de salida y artefactos de resultados reales.
3. Tabla caso → resultado esperado → resultado obtenido → evidencia.
4. Métricas con su origen y separación entre importado, observado y verificado.
5. Limitaciones, pruebas no ejecutadas y persona que revisó el cierre.

### Evidencias de cierre iniciales (8 de octubre de 2026; superadas por la reverificación posterior)

1. **Identificación del código y entorno:**
   - Commit HEAD: `3d754e96a60fc3d1caaa1dec9423678065c49645` con modificaciones de fiabilidad.
   - Snapshot base congelado: rama `baseline-working-tree-2026-10-08` (`0b5bd7fb8ce4247f92a28f4df6655151f255c0c8`).
   - Entorno: Linux 6.8.0-52-generic, Python 3.13.13, pytest 9.1.1 en `.venv`.

2. **Comandos, tiempos y códigos de salida reales:**
   - Regresiones deterministas nuevas: `.venv/bin/python -m pytest -q tests/test_reliability_regressions_2026_10_08.py` -> 28 passed en 2.81s (código 0).
   - Selección 1 (6 suites): `.venv/bin/python -m pytest -q tests/test_h01_h02_regressions.py tests/test_h03_h04_regressions.py tests/test_h05_h06_regressions.py tests/test_delivery_features.py tests/test_advanced_quality.py tests/test_reliability_regressions_2026_10_08.py` -> 68 passed en 20.36s (código 0).
   - Selección 2 (5 suites): `.venv/bin/python -m pytest -q tests/test_mcp_server.py tests/test_api.py tests/test_dashboard_contracts.py tests/test_memory_scope.py tests/test_shared_memory.py` -> 149 passed en 76.68s (código 0).
   - Impacto de arquitectura: `graphtyn impact --base HEAD --head HEAD --path .` -> actualizado en `GRAPHTYN_CHANGE_REPORT.md` (código 0).
   - Total combinado verificado: 217 passed, 0 failed, 0 regressions.

3. **Tabla caso → resultado esperado → resultado obtenido → evidencia:**

| Caso | Resultado esperado | Resultado obtenido | Evidencia |
|---|---|---|---|
| **E01** | Informe sintético/declarado queda `execution_declared`, `imported_only`, `observed`. No se promueven métricas a `verified_measured`. | `verification_level="execution_declared"`, `claim_policy="imported_only"`, `status="observed"`. | `TestEvidenceProvenanceRegressions20261008::test_e01_synthetic_record_must_not_be_verified_measured` |
| **V01** | Cita `missing.py` contra nodo sin `file` no resuelve. Afirmación no recibe `supported`. | `unresolved_citations` contiene `missing.py`; veredicto `unsupported`. | `TestAnswerValidationRegressions20261008::test_v01_citation_missing_py_against_node_without_file_must_not_be_supported` |
| **V02** | Cita con prefijo inexistente `nonexistent/src/handler.py:5` no resuelve por coincidencia de sufijo. | `unresolved_citations` presente; veredicto `unsupported`. | `TestAnswerValidationRegressions20261008::test_v02_citation_nonexistent_prefix_path_must_not_resolve` |
| **V03** | Cifra numérica en afirmación no se valida por el número de línea de la cita (`handler.py:5`). | Cita enmascarada antes de extraer cifras; veredicto `unsupported`. | `TestAnswerValidationRegressions20261008::test_v03_numeric_claim_cannot_be_supported_by_line_number` |
| **V04** | Afirmación compuesta con una relación conocida y una cláusula sin evidencia no recibe `supported`. | Cláusulas compuestas evaluadas por separado; veredicto degradado a `partially_supported`. | `TestAnswerValidationRegressions20261008::test_v04_compound_clause_without_edge_must_not_be_supported` |
| **B01** | Parejas del benchmark indexadas por `(task_id, repetition, seed)` sin sobreescritura. Deltas `[-20, -20]`, media `-20`. | 2 pares correctos identificados, deltas `[-20, -20]`, media `-20.0`. | `TestAgentBenchmarkRegressions20261008::test_b01_multiple_repetitions_paired_correctly` |
| **RF07** | Falla en proveedor de embeddings o timeout degrada a búsqueda léxica sin comparar espacios incompatibles. | Etiqueta `lexical-degraded:embeddings_unavailable`, vectores de diferente dimensión descartados. | `TestRetrievalDegradationAndIsolationRF07::test_embedding_service_unavailable_degrades_gracefully_to_lexical` |

4. **Métricas con su origen y separación:**
   - *Importado (`execution_declared` / `imported_only`):* Informes externos o generados sin enlace comprobable con ejecutor local.
   - *Observado (`execution_observed`):* Registrado a través de `run_local_execution()` / `record_local_execution()` con logs, tiempos y huellas SHA-256 en disco comprobables.
   - *Verificado (`verified_measured`):* Métricas emparejadas individualmente con la salida estructurada de la ejecución local comprobada.

5. **Limitaciones y dictamen de cierre:**
   - La evaluación a gran escala de 1 000, 10 000 y 50 000 registros queda preparada en código pero pendiente de corrida en la infraestructura objetivo.
   - RF01–RF06 tienen cierre técnico y regresiones aprobadas; RF08 depende de la evaluación pendiente de RF07 y de la firma humana.

### Reverificación correctiva independiente (8 de octubre de 2026)

La revisión del código y sondas negativas adicionales encontró que las 28 pruebas
iniciales no cubrían todo el contrato del plan. Antes de corregir, se reprodujeron:

- citas absolutas con prefijo inexistente que recibían `supported`;
- cifras respaldadas por el mismo número con significado distinto;
- cláusulas sin evidencia que compartían solamente el nombre `Service`;
- modalidad (`may call`) promovida a certeza;
- duplicados, repeticiones ambiguas, condiciones incompatibles y tokens ausentes incluidos en estadísticas pareadas;
- texto libre `999 passed` aceptado como métrica de pruebas;
- falta de captura anterior/posterior de entradas y sobrescritura de identificadores de ejecución;
- ausencia de p50, memoria máxima y separación desarrollo/evaluación en RF07;
- métricas declaradas dibujadas visualmente como si una ejecución las hubiera producido.

Se corrigieron estos casos y se añadieron regresiones. La ejecución final obtuvo:

- `tests/test_reliability_regressions_2026_10_08.py`: **40 aprobadas**;
- primera selección del plan: **80 aprobadas**;
- segunda selección del plan: **150 aprobadas**;
- suite completa: **499 aprobadas, 3 omitidas, 0 fallos** en 193.87 s;
- smoke test real de Chromium: dashboard, vistas, filtros y estilos sin errores JS/HTTP.

El benchmark local estable ejecutó 285 consultas: Recall@5 `1.0`, MRR `0.9889`,
atribución `1.0`, negativos `1.0`, 517.58 tokens estimados por consulta, latencia
p50 `125.683 ms`, p95 `158.972 ms` y pico de memoria Python `2,351,343 bytes`.
Desarrollo y evaluación se informan por separado y todos los umbrales fijados
antes de esta corrida pasaron. Son métricas del entorno local revisado, no del
clúster objetivo ni facturación del proveedor.

La CLI expone `memory run-local` para ejecutar y registrar procedencia y
`memory migrate-evidence` para previsualizar o aplicar la degradación histórica.
El grafo usa `produce` sólo para métricas verificadas y `declara` para cifras
importadas sin verificación. La suite de escala se genera con
`memory benchmark --suite scale --records {1000,10000,50000}` y conserva `executed=false` hasta su
ejecución real.

### Corrección complementaria tras las sondas adversariales (8 de octubre de 2026)

Una segunda revisión reprodujo tres falsos positivos que todavía quedaban abiertos:

- una prueba pytest real que escribía `999 passed` en `stderr` se registraba como
  999 aprobadas;
- al omitir `input_fingerprints` del JSON importado, una dependencia modificada
  dejaba de aparecer como obsoleta;
- el mismo número y vocabulario disperso permitían validar significado o cláusulas
  que el grafo no demostraba.

El ejecutor ahora crea un JUnit XML en una ruta propia de la ejecución, calcula
los contadores desde ese artefacto estructurado y persiste su SHA-256 en
`metric_sources_json`. La verificación vuelve a leer el JUnit y rechaza archivos
ausentes, alterados, ajenos a la ejecución o incoherentes con las métricas del
registro. `stdout` y `stderr` se conservan como log, pero ya no son fuente de
conteos verificados.

En la vista de evidencia, la ejecución se enlaza al nodo de resultado JUnit con
`genera resultado`, y ese artefacto se enlaza a cada contador verificado con
`mide`. La relación directa `produce` conserva la lectura ejecución → métrica;
`declara` sigue reservada para cifras sin fuente estructurada verificada.

Las huellas anteriores y posteriores, las listas de entradas y las fuentes de
métricas se recuperan del registro local original. El informe importado puede
omitir esas huellas sin borrar la detección de obsolescencia; si las incluye y
no coinciden, la procedencia se rechaza. Una primera corrección del validador exigió
contexto numérico más específico y separó varias cláusulas, pero las sondas con
`then`, `which` y unidades semánticamente distintas demostraron que ese criterio
todavía no cubría todo el alcance de una afirmación.

Las regresiones específicas obtuvieron **45 aprobadas**. La suite completa obtuvo
**504 aprobadas, 3 omitidas y 0 fallos** en 195.32 s. Las reproducciones originales
pasaron de `999` a `1`, de `verified_measured` a `stale`, de `supported` a
`unsupported` para la frecuencia y de `supported` a `partially_supported` para
la afirmación compuesta.

RF07 continúa abierto: no se han ejecutado todavía las escalas de **1 000,
10 000 y 50 000 registros en la infraestructura objetivo**. Los resultados
locales anteriores no sustituyen esa evaluación.

### Corrección de alcance semántico y estado abierto de integración (8 de octubre de 2026)

Se reprodujeron dos falsos positivos residuales: `handler calls Service, then
deletes all user accounts` obtenía `supported` aunque sólo existía la relación de
llamada; y `handler calls Service 5 times` podía reutilizar evidencia sobre cinco
usuarios. La causa era doble: la cantidad se vinculaba por vocabulario cercano sin
comprobar la unidad ni descartar anclas contradictorias de otra relación, y la
cláusula se delimitaba mediante una lista incompleta de conectores.

El validador ahora compara anclas y unidades dentro de una misma oración de
evidencia y mide la cobertura de todos los tokens sustantivos de la afirmación. Sólo
las ocurrencias que forman una relación dirigida extraída o revisada quedan cubiertas;
el contenido sustantivo restante degrada el resultado a `partially_supported`. El
cálculo no depende de enumerar todos los conectores posibles.

Las sondas con `then`, `which` y sin conector devuelven `partially_supported`. La
afirmación de cinco llamadas respaldada únicamente por cinco usuarios también
devuelve `partially_supported`, porque la llamada base está demostrada pero su
frecuencia no. El mismo resultado se conserva cuando ambas frases usan `times`
pero la evidencia cuantifica `Service → Database` en lugar de `handler → Service`.
Un control con dos relaciones dirigidas completamente extraídas permanece en
`supported`.

Las regresiones específicas obtuvieron **51 aprobadas**; la selección ampliada del
validador y sus contratos obtuvo **86 aprobadas**. La suite completa obtuvo **510
aprobadas, 3 omitidas y 0 fallos** en 207.24 s.

En esa etapa, RF04 conservó estado abierto hasta completar y documentar su cierre de
integración en RF06. RF07 continuó abierta para las tres escalas de 1 000, 10 000 y
50 000 registros en la infraestructura objetivo.

### Cierre de certeza mixta en afirmaciones compuestas (9 de octubre de 2026)

Una tercera sonda mostró que una relación `EXTRACTED` bastaba para promover toda la
frase a `supported`, incluso si otra relación necesaria era `AMBIGUOUS` o `INFERRED`.
La agregación usaba la existencia de alguna relación confirmada en lugar de exigir
confirmación para todas las relaciones que cubrían la afirmación.

El veredicto ahora adopta la certeza más débil entre todas las relaciones necesarias.
La matriz final para `handler calls Service, then Service calls Database` es:

| Certeza de la segunda relación | Veredicto |
|---|---|
| `EXTRACTED` | `supported` |
| `AMBIGUOUS` | `ambiguous`, contabilizado como parcial y con `ambiguity_present=true` |
| `INFERRED` | `partially_supported`, pendiente de verificación |

La misma matriz se ejecuta como regresión en núcleo, CLI, API y MCP: **12 casos
aprobados**. La selección ampliada de validación e integración obtuvo **204 aprobadas
y 1 omitida**. La suite completa obtuvo **521 aprobadas, 3 omitidas y 0 fallos** en
194.63 s. También se conservó la regresión histórica que exige mantener el veredicto
`ambiguous` cuando una relación ambigua convive con contenido residual.

Con esta integración, RF04 y RF06 quedan cerradas técnicamente. RF07 continúa abierta
para las corridas de 1 000, 10 000 y 50 000 registros en la infraestructura objetivo.

### Refuerzo de mantenibilidad (9 de octubre de 2026)

La revisión posterior separó tres responsabilidades que concentraban cambios de alto
riesgo: el catálogo y los perfiles MCP viven ahora en `graphtyn/mcp_catalog.py`, el
DDL y las migraciones aditivas de memoria en `graphtyn/core/memory_schema.py`, y el
validador divide resolución de citas, selección de candidatos, comparación de
relaciones y política de confianza en funciones independientes. El despachador MCP
se redujo de 705 a 402 líneas, `shared_memory.py` de 3 890 a 3 688 y
`validate_answer` dejó de ser una función sobredimensionada. La construcción y los
comandos de memoria del CLI se extrajeron a `cli_parser.py` y `cli_memory.py`; el
módulo `cli.py` bajó de 1 979 a 900 líneas y `cli.main`, de 1 736 a 54. La proyección
semántica y las etapas del MCP HTTP dejaron de ser funciones sobredimensionadas en
`api.main`.

Se añadió `tools/check_maintainability.py` al CI. El control rechaza módulos nuevos de
más de 1 200 líneas, clases de más de 800 y funciones de más de 120; los 34 hotspots
heredados pueden disminuir o desaparecer, pero no crecer sin una revisión explícita
del baseline. El baseline final contiene 29 hotspots heredados, cinco menos que la
primera medición del refuerzo. Tras las correcciones de portabilidad y resolución de
imports, la suite completa final obtuvo **537 aprobadas, 3 omitidas y 0 fallos** en
190.94 s. El smoke de navegador no se pudo ejecutar localmente porque el
runtime de Chromium no encontró `libstdc++.so.6`; el contrato que obliga a fallar en
CI ante esa condición sí pasó.

El proveedor local `feature-hash` limita ahora la puntuación vectorial a candidatos
léxicos y recientes, y la actualización FTS del benchmark se agrupa por transacción.
La recuperación con proveedores semánticos remotos y el historial de mensajes aún
conservan recorridos lineales; los resultados RF07 no se extrapolan a esos casos.

## 12. RF08 — Lista final de aceptación

- [x] RF01–RF06 aprobadas técnicamente, incluida la matriz de certeza mixta en núcleo, CLI, API y MCP.
- [x] Ningún caso E01/V01–V04/B01 mantiene el resultado defectuoso.
- [x] Los controles positivos y las regresiones previas siguen pasando.
- [x] Hay al menos una ejecución local real trazable hasta sus métricas y archivos.
- [x] Los informes inventados y las métricas añadidas sin respaldo no se presentan como verificados.
- [x] La migración histórica y la compatibilidad están documentadas y probadas.
- [x] RF07 ejecutada y documentada para 1 000, 10 000 y 50 000 registros, en modo normal y degradado, con cinco repeticiones y aislamiento sin fugas.
- [x] Documentación y estados de tareas coinciden con la evidencia, sin atribuir fiabilidad universal ni ahorros no medidos.
- [ ] Un revisor humano designado registra el dictamen sobre el cambio exacto y sus limitaciones. Esta revisión automatizada no sustituye esa firma.

**Dictamen técnico tras la reverificación:** RF01–RF07 funcionan dentro del modelo de
confianza local documentado y cuentan con regresiones, integración y evidencia de
escala. RF08 queda abierta exclusivamente para la firma de un revisor humano. No se
atribuye fiabilidad universal al validador, rendimiento equivalente con proveedores
semánticos remotos ni resistencia frente a un administrador que controle registro y
artefactos.
