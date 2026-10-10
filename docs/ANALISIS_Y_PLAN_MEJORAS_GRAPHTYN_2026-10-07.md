# Graphtyn: análisis de uso real y plan de mejora

**Fecha:** 7 de octubre de 2026.
**Estado:** diagnóstico y propuesta; correcciones de producto pendientes.
**Autor del análisis:** Codex, solicitado por el usuario.
**Versión instalada:** 0.10.4.
**HEAD observado:** `3d754e96a60fc3d1caaa1dec9423678065c49645`.

## 1. Conclusión

Graphtyn aporta continuidad entre sesiones, referencias de código y análisis de
dependencias. La prioridad es reforzar la calidad de esas evidencias antes de
aumentar el número de herramientas o incorporar otro modelo generativo.

La revisión de código y los experimentos aislados confirmaron problemas concretos:

1. El validador puede marcar `supported` cuando hay una cita inexistente, un ID de
   evidencia inexistente o únicamente una relación `AMBIGUOUS`.
2. La ingesta puede convertir un informe sintético sin ejecución en
   `verified_measured`, con `confidence=1.0`. Su huella demuestra integridad del
   archivo, pero no que se haya ejecutado el experimento que describe.
3. La búsqueda de memorias puede omitir una coincidencia exacta antigua cuando
   queda fuera de las 500 memorias más recientes, aunque siga almacenada e indexada.
4. La búsqueda de mensajes históricos descarta los términos posteriores a los
   primeros doce términos admitidos. Una consulta larga puede perder su tema.
5. Cambiar una frase de un README con cuarenta secciones produjo riesgo 100/100
   y 41 entradas de verificación. Además, consumidores homónimos de archivos
   distintos pueden colapsar en una sola entrada del plan.

Estos resultados no demuestran que todo Graphtyn falle ni una tasa global de
error. Sí justifican regresiones específicas y una revisión del significado de
sus etiquetas. Las 15 pruebas existentes seleccionadas pasaron: cubren
comportamientos útiles, pero no detectaban todos estos casos adversariales.

## 2. Alcance, procedencia y límites

Se revisaron las rutas de validación, impacto, memoria, evidencia, diagnóstico y
medición. Se consultó primero la memoria del proyecto donde surgieron las
observaciones y después se verificó el código en el repositorio de Graphtyn.
No se utilizó el historial conversacional como prueba del funcionamiento actual.

El checkout ya contenía modificaciones sin commit en CLI, MCP, memoria, API,
interfaz y pruebas. El análisis corresponde a **HEAD más ese árbol de trabajo**,
no exclusivamente al commit ni a una distribución publicada e inmutable.
Se preservaron esos cambios; no se modificó la implementación para obtener los
resultados. Los experimentos crearon repositorios y bases temporales, con
`GRAPHTYN_HOME` aislado y sin escribir memorias sintéticas en los proyectos reales.

Huellas SHA-256 de los archivos principales examinados:

| Archivo | SHA-256 |
|---|---|
| `graphtyn/core/answer_validation.py` | `97ae8522f465b0859555b2a11ffe1391ce376119666aa78bd4edd31e8a52a546` |
| `graphtyn/core/impact.py` | `8087b087b00787e74097b2173d10f267e91ace5d4d997cca7db82c20cb834247` |
| `graphtyn/core/shared_memory.py` | `c77708fbb7ce6973090b498064be33e7b8668d5f4253c5d1236d193e3b7d04ab` |
| `graphtyn/core/verification.py` | `10835c26e4a47f5296de0f7c43b47369a43aeb92818d6985d81da27a1639e3f9` |
| `graphtyn/cli.py` | `2329a91719a6a383409e78c1b3e93e1866797ee500d906df3ed2b05ac8316837` |

Las referencias de línea corresponden a esta revisión. El apéndice contiene un
reproductor independiente y resultados resumidos. No se ejecutó una comparación
completa con y sin Graphtyn, ni una auditoría exhaustiva de seguridad o de todos
los clientes MCP. No se atribuyen ahorros, superioridad ni porcentajes de
fiabilidad nuevos a partir de esta muestra.

## 3. Qué ya existe y conviene ampliar

La propuesta preliminar sobre herramientas nuevas debe ajustarse a lo encontrado:

| Capacidad existente | Evidencia de código | Mejora necesaria |
|---|---|---|
| Ingesta de evidencias de benchmarks | [`ingest_benchmark_evidence`](../graphtyn/core/shared_memory.py#L1860) | Distinguir archivo importado, integridad, ejecución observada y verificación de métricas; incorporar evidencia de pruebas/CI con procedencia. |
| Detección de archivos modificados mediante huellas | [`_fingerprints` y `_stale_files`](../graphtyn/core/shared_memory.py#L2504) | Declarar todas las dependencias relevantes de una ejecución, no solamente el informe resultante. |
| Revisión de rama y ascendencia de commit | [`_revision_status`](../graphtyn/core/shared_memory.py#L2596) | Completar el alcance con cambios locales, entorno, datos y caducidad de hechos externos. |
| Diagnóstico de memoria | [`doctor`](../graphtyn/core/shared_memory.py#L2446), CLI `memory doctor` | Unificar diagnóstico de SQLite/FTS/embeddings con conexión MCP, alcance del proyecto y salud de captura. |
| Estado de captura con heartbeat y `active` | [`status`](../graphtyn/core/shared_memory.py#L2109) | Explicar el estado efectivo y su causa; evitar que un estado histórico `watching` parezca actividad actual. |
| Plan de verificación | [`verification_plan`](../graphtyn/core/verification.py#L60) | Identidad por símbolo, agrupación por archivo, conservación de acciones y comandos verificables. |
| Presupuesto y telemetría de memoria | [`context`](../graphtyn/core/shared_memory.py#L1774) | Conservar evidencia pertinente al recortar; medir costos de la tarea completa. |
| Benchmarks de memoria y de agentes | [`memory_benchmark.py`](../graphtyn/core/memory_benchmark.py), [`agent_benchmark.py`](../graphtyn/core/agent_benchmark.py) | Ampliar escenarios adversariales, consultas reales y tamaños del historial. |

No hace falta duplicar estas capacidades con servicios paralelos. Los nombres de
herramientas que aparecen más adelante son propuestas de interfaz.

## 4. Hallazgos y correcciones propuestas

### H01 — El respaldo de una afirmación puede resultar aparente

**Prioridad P0. Estado: reproducido.**

En [`validate_answer`](../graphtyn/core/answer_validation.py#L64), los candidatos
se seleccionan por solapamiento de términos, coincidencia de ruta o IDs solicitados.
La línea 93 eleva el veredicto a `supported` si hay candidatos y cualquier cita,
cualquier lista de IDs solicitados o alguna relación entre candidatos.

Casos comprobados con un grafo mínimo:

- `Service sends payments (missing.py:999999).` resulta `supported`, aunque el
  grafo solo ubica `Service` en `src/service.py` y no prueba pagos.
- Una afirmación sobre `Service` con `evidence_ids=['missing-node']` también
  resulta `supported`; no exige que el ID pedido exista.
- `handler calls Service during request processing.` resulta `supported` aun
  cuando su única relación es `AMBIGUOUS`.
- Una afirmación larga sin ninguna coincidencia devuelve `ok=true` y
  `unsupported`. En este último caso `ok` indica finalización/formato, no respaldo:
  la implementación y su docstring lo distinguen, pero el contrato puede confundirse.

**Corrección:** separar `operation_ok`, `evidence_resolved` y
`claim_assessment`. Resolver cada ruta/ID y rango solicitado; conservar vínculos
exactos de afirmación a evidencia. La coincidencia léxica debe producir
`candidate_evidence`, no aprobación factual. Una relación ambigua debe conservar
su incertidumbre en el veredicto. Una afirmación sobre el estado actual de un PR
necesita una observación de GitHub/CI con fecha; un documento del repositorio no
la demuestra por similitud textual.

No se propone que un comprobador determinista demuestre toda afirmación en lenguaje
natural. Cuando no pueda comprobar sujeto, relación o valor, debe abstenerse y
explicar qué evidencia falta. Si se añade un verificador semántico, debe evaluarse
por separado y tampoco convertir una cita plausible en prueba automática.

**Aceptación:** ninguna cita o ID inexistente promueve `supported`; las relaciones
ambiguas no se publican como hechos confirmados; contradicciones, números,
negaciones y citas correctas pero irrelevantes tienen casos explícitos. CLI, API
y MCP deben conservar el mismo significado de los estados.

### H02 — Integridad de un informe no equivale a medición verificada

**Prioridad P0. Estado: reproducido.**

[`ingest_benchmark_evidence`](../graphtyn/core/shared_memory.py#L1902) comprueba
ubicación, lectura, formato y hash. Luego crea `status='verified'`,
`confidence=1.0` y `verification='artifact-hash+git-revision'`.
[`_claim_policy`](../graphtyn/core/shared_memory.py#L1975) puede traducir esto a
`verified_measured` porque el archivo se clasificó como benchmark.

Un `benchmarks/probe/summary.json` sintético que declaraba 123456 pruebas aprobadas
y advertía que no se había ejecutado ningún comando recibió esas etiquetas.
La ingesta fue real; las supuestas pruebas no existían. Esto revela una diferencia
entre la garantía ofrecida por el hash y el significado de la etiqueta.

La huella guardada cubría únicamente `summary.json`. Modificar el archivo de código
nombrado como sujeto dentro del JSON no marcó esa evidencia como obsoleta. No es
ausencia total de control de vigencia: los archivos enlazados sí tienen huellas.
El problema es el alcance incompleto de las dependencias del resultado.

**Corrección:** introducir niveles separados, por ejemplo `imported_report`,
`integrity_verified`, `execution_observed`, `metrics_recomputed` y
`human_reviewed`. Ninguno debe implicar automáticamente los demás.
Mantener imports de informes sin exigir su ejecución, pero con la etiqueta correcta.

Un registro de ejecución debe enlazar comando y argumentos, código de salida,
horarios, digest de log, identidad del ejecutor, proyecto, commit, cambios locales,
archivos de prueba, dependencias, datos y entorno. Los adaptadores de CI deben
conservar ejecución/job/commit y fecha. Los datos confidenciales deben sanearse
antes de persistir; consultar o importar evidencia no debe ejecutar órdenes de
un documento. Una huella o firma autentica contenido/procedencia, no verdad.

**Aceptación:** el informe sintético queda importado sin aprobar sus resultados;
una ejecución enlazada permite distinguir éxito, fallo, cancelación y evidencia
ausente. Cambiar una dependencia declarada invalida su aplicabilidad actual;
cambiar un archivo ajeno no debe invalidar todo indiscriminadamente. Los registros
históricos se conservan con su alcance original.

### H03 — Coincidencias antiguas se pierden en el conjunto de candidatos

**Prioridad P1. Estado: reproducido.**

[`search`](../graphtyn/core/shared_memory.py#L1337) consulta FTS, pero después
carga `visible_rows` con las 500 memorias más recientes y puntúa únicamente esas
filas ([bucle](../graphtyn/core/shared_memory.py#L1376)). Una coincidencia de FTS
fuera de ese conjunto no entra al resultado final.

Se guardó una decisión con el término único `xylophorino`: se recuperó inicialmente.
Tras crear 500 decisiones distintas, dejó de recuperarse. `get()` seguía encontrando
la memoria y FTS seguía reportando una coincidencia. No hubo pérdida de datos;
hubo pérdida de recuperación en `search`.

**Corrección:** construir la unión de candidatos léxicos y vectoriales autorizados
antes de aplicar ranking y límites finales. Conservar controles de proyecto,
propietario, privacidad, vigencia y estado en todas las rutas. Evitar resolverlo
únicamente aumentando 500: desplazaría el mismo defecto a otro tamaño.

**Aceptación:** recuperar la coincidencia exacta con 501, 1000 y un conjunto mayor
de memorias; incluir casos obsoletos, eliminados, privados y de otro proyecto para
comprobar que la ampliación de candidatos no vulnera el aislamiento. Medir latencia
y número de candidatos sin confundir tamaño de historial con relevancia.

### H04 — El prefijo de una consulta larga puede desplazar su intención

**Prioridad P1. Estado: reproducido.**

[`search_messages`](../graphtyn/core/shared_memory.py#L1474) conserva solo los
primeros doce términos admitidos. Exige uno o dos aciertos y puntúa coincidencias
por subcadena. El tema que aparece al final puede no participar en la búsqueda.

La consulta `fotometria incertidumbre calibracion` recuperó el mensaje correspondiente.
Anteponer doce verbos de tarea produjo cero coincidencias, sin cambiar el mensaje.
En uso real, las solicitudes completas suelen empezar con instrucciones similares.

**Corrección:** preservar la petición completa como procedencia, pero seleccionar
términos discriminantes, entidades e identificadores a lo largo de toda la consulta.
Usar tokenización coherente y ranking con contexto de sesión; evaluar umbrales de
abstención para evitar llenar el presupuesto con material irrelevante. La actividad
reciente puede seguir apareciendo, pero claramente identificada como actividad, no
como respuesta pertinente a cualquier pregunta.

`context` ya impone presupuesto, atribución y recortes. No se propone quitarlos;
se propone que la selección pertinente ocurra antes de gastar ese presupuesto.

**Aceptación:** conservar el resultado al mover la entidad al principio o final;
consultas cortas/largas, español/inglés, preguntas sin respuesta y entidades
parecidas deben formar parte de un conjunto reservado. No ajustar stopwords a
estos dos ejemplos únicamente.

### H05 — El riesgo mezcla conectividad documental con riesgo funcional

**Prioridad P1. Estado: reproducido.**

[`analyze_impact`](../graphtyn/core/impact.py#L135) recorre consumidores y también
descendientes de `contiene`. Su puntuación es:

```text
min(100, 5 × archivos + 12 × cambios de firma
         + 3 × nodos directos + nodos transitivos)
```

Cambiar una sola frase en un README con cuarenta subtítulos produjo un archivo
cambiado, cero símbolos modificados, 41 nodos directos y riesgo 100/100.
Se usó el parser real en un repositorio Git temporal, no un grafo inventado.

**Corrección:** separar alcance documental, impacto de contratos y riesgo de
ejecución. Mostrar factores, tipos de relación, ambigüedad y qué parte corresponde
a contención. Agrupar secciones del mismo archivo y mostrar rangos afectados.
No imponer riesgo bajo a toda documentación: contratos, instrucciones de despliegue
y procedimientos de recuperación pueden tener consecuencias reales.

**Aceptación:** cambios editoriales no saturan el riesgo solo por tener muchas
secciones; una ruptura de firma pública o contrato sigue destacando. Validar un
corpus con clasificación humana y publicar desacuerdos. El score debe presentarse
como heurística de revisión, no como probabilidad de defecto.

### H06 — El plan de verificación pierde acciones e identidades

**Prioridad P1. Estado: reproducido y verificado en fuente.**

El motor de impacto construye acciones como `run_adjacent_tests`; la
[CLI](../graphtyn/cli.py#L1198) reemplaza ese campo por la salida de
[`verification_plan`](../graphtyn/core/verification.py#L60), una lista de nombres
de símbolos y consumidores. En el caso del README se emitieron 41 entradas.

Además, `seen` deduplica por nombre. Dos consumidores llamados `validate` en
`a.py` y `b.py` produjeron una sola entrada. No debe confundirse agrupar un mismo
objeto con omitir dos objetos distintos.

**Corrección:** unificar el esquema entre motor, CLI, API y MCP; identificar por
ID estable y ruta, conservar acciones y agrupar comprobaciones equivalentes.
Cada comprobación debe indicar motivo, objetivos, comando si está identificado,
condiciones, costo estimado y resultado esperado. Si no hay comando conocido,
debe declararse revisión manual o cobertura desconocida, sin inventar pruebas.
El plan no debe ejecutar comandos por sí solo. La reutilización de resultados
requiere la evidencia vigente descrita en H02.

**Aceptación:** conservar ambos `validate`, no repetir decenas de secciones de un
README y no perder las acciones del motor. Añadir pruebas de contrato entre
superficies, además de comprobar que el Markdown contiene los encabezados.

### H07 — El diagnóstico existe; falta una explicación operativa unificada

**Prioridad P2. Estado: control correcto con mejora de presentación.**

El ensayo del watcher conservó `status='watching'` y calculó `active=false` cuando
su heartbeat era antiguo. El código ya detecta esa caducidad y tiene una prueba
que la comprueba. No sería correcto reportarlo como ausencia de detección.

[`doctor`](../graphtyn/core/shared_memory.py#L2446) verifica SQLite, claves,
FTS y embeddings. Se propone ampliar la experiencia de diagnóstico con un estado
efectivo (`stale`, `stopped`, `healthy`, `degraded`), causa, edad del heartbeat,
último ciclo satisfactorio, cliente y proyecto. Configuración correcta, proceso
vivo, captura exitosa y recuperación de memoria deben ser señales distintas.

**Aceptación:** casos de heartbeat caducado, permiso denegado, proyecto equivocado,
almacén sano sin captura, captura sana sin consulta y MCP desconectado producen
diagnósticos diferenciados. La herramienta ofrece instrucciones; no reinicia
procesos ni cambia configuración durante un diagnóstico de lectura.

### H08 — Medir utilidad completa y controlar el volumen del grafo

**Prioridad P2. Estado: mejora propuesta sobre capacidades existentes.**

El presupuesto de memoria ya contempla la respuesta estructurada. En cambio,
[`_overview_package`](../graphtyn/core/change_analyst.py#L95) limita nodos y conserva
sus campos; `matched` y `nodes` pueden serializar nodos repetidos. El límite de
entidades no garantiza por sí solo una respuesta pequeña. Conviene proyectar
campos compactos, aplicar presupuesto de bytes/tokens y devolver detalle por ID.

La [telemetría documentada](shared_memory_stability.md) reconoce que UTF-8/4 es
una estimación. `raw_history_tokens_avoided` compara contexto con mensajes fuente;
no es una medición del ahorro neto de completar la tarea con Graphtyn.
Ya existen [comparaciones pareadas de agentes](../graphtyn/core/agent_benchmark.py),
por lo que corresponde ampliarlas, no crear otro contador de ahorro equivalente.

**Aceptación:** tareas equivalentes con mismos modelos, repositorios y condiciones
comparan éxito, afirmaciones sin respaldo, tiempo, llamadas, tokens disponibles del
proveedor y costo. Separar estimaciones y mediciones. Publicar fallos y variantes
rechazadas; no concluir mejora por reducir texto si se pierde evidencia necesaria.

## 5. Herramientas: ampliar primero, añadir lo indispensable

| Propuesta | Decisión | Contrato mínimo |
|---|---|---|
| `validate-answer` / evaluación de afirmaciones | Corregir la herramienta actual; compatibilidad mediante esquema versionado. | Operación, cita resuelta y soporte factual son campos distintos; abstención explícita. |
| `evidence_record` | Ampliar la ingesta existente con un registro tipado y adaptadores de pruebas/CI. | Procedencia, alcance, estado de verificación, digests y referencias a ejecución; sin ejecutar instrucciones importadas. |
| `evidence_status` | Vista sobre el registro anterior, no una segunda base de evidencia. | Vigencia respecto a dependencias, motivo de invalidez y alcance histórico. |
| `project_doctor` | Vista unificada que reutilice `memory doctor`, estado MCP y estado de captura. | Diagnóstico de lectura, proyecto explícito, causas y remedios concretos. |
| `verification_plan` | Consolidar la función y las superficies existentes. | IDs estables, acciones, comandos conocidos, revisión manual y resultados enlazados. |
| Explicación de recuperación | Añadir modo de diagnóstico a `context/search`, sin inflar la respuesta habitual. | Componentes de ranking, candidatos descartados y cobertura, respetando permisos. |

No añadir inicialmente otro vector store, otro LLM, aprendizaje autónomo de
políticas ni un ejecutor general de comandos. Primero corregir candidatos,
semántica de estados y cobertura de pruebas. Un reranker posterior solo se justifica
si mejora el conjunto reservado y compensa su latencia/costo.

## 6. Secuencia ejecutable

Los esfuerzos son estimaciones iniciales de una persona familiarizada con el código,
no compromisos de calendario. Deben revisarse al diseñar la migración de contratos.

| ID | Prioridad | Responsable sugerido | Dependencias | Acción y entrega | Esfuerzo | Cierre |
|---|---|---|---|---|---|---|
| G01 | P0 | Calidad + mantenedor de contratos | — | Convertir reproducciones de H01/H02 en regresiones y diseñar estados versionados. | 4–6 h | Negativos documentados; consumidores de estados inventariados. |
| G02 | P0 | Motor de grafo/validación | G01 | Resolver citas/IDs, preservar ambigüedad y separar finalización de soporte. | 8–14 h | H01 corregido en CLI, API y MCP, sin promover negativos. |
| G03 | P0 | Memoria/evidencia | G01 | Separar informe importado de medición; enlazar ejecución y dependencias; migración explícita. | 12–20 h | H02 corregido; evidencia histórica no se eleva ni borra automáticamente. |
| G04 | P1 | Recuperación de memoria | — | Unión de candidatos autorizados y regresiones sobre más de 500 memorias. | 4–8 h | H03 resuelto, con aislamiento y vigencia conservados. |
| G05 | P1 | Recuperación de memoria | G04 | Selección de términos a lo largo de la consulta y evaluación de abstención. | 6–12 h | H04 resuelto en conjunto reservado, sin rellenar con distractores. |
| G06 | P1 | Grafo/impacto | G01 | Separar categorías de riesgo y unificar plan por ID/archivo/acción. | 8–14 h | H05/H06 resueltos; homónimos preservados. |
| G07 | P2 | Integraciones | G03 | Unificar diagnóstico y estado efectivo de captura. | 4–8 h | H07 cubierto por matriz de fallos. |
| G08 | P2 | Contexto y calidad | G02–G06 | Proyección compacta y evaluación de tareas completas. | 8–16 h | H08 medido; no regresión de calidad al recortar. |

**Total orientativo: 54–98 horas**, más el costo variable de corridas externas y
la revisión de cambios de contrato. G04 puede avanzar mientras se diseña G01;
G07/G08 no deben retrasar las correcciones P0. Todos los elementos están
**Pendientes**: este documento no implementa ni aprueba su cierre.

## 7. Evaluación y criterios de publicación

Separar pruebas funcionales, regresiones adversariales y evaluación de producto:

- **Funcionales:** vigencia de archivos enlazados, permisos, aislamiento,
  idempotencia, presupuestos y paridad de contratos entre CLI/API/MCP.
- **Adversariales:** citas falsas, IDs inexistentes, negaciones, relaciones
  ambiguas, informes inventados, homónimos, historias largas y consultas con tema
  al final. Los casos de este informe son regresiones obligatorias; no bastan como
  conjunto de evaluación independiente.
- **Producto:** tareas de varios repositorios y agentes, con decisiones y fuentes
  anotadas antes de evaluar. Reservar casos que no se utilicen al ajustar ranking
  o umbrales. Comparar con una base sin Graphtyn y con la versión anterior.

Medir precisión del respaldo por afirmación y cita, tasa de promoción incorrecta,
Recall@k, MRR, abstención ante preguntas sin respuesta, atribución, p50/p95 de
latencia y éxito de tarea. Desglosar por idioma, tamaño de historial y tipo de
consulta. Los escenarios reformulados de una misma decisión no son observaciones
completamente independientes; los intervalos deben respetar esa agrupación.

Para publicar las correcciones, los negativos deterministas de H01/H02 deben dejar
de promover respaldo/medición; H03/H04 deben recuperar sus ejemplos; H06 debe
conservar consumidores homónimos. Fijar los objetivos agregados del conjunto
reservado antes de mirar resultados. No declarar «100% fiable» porque pase la
suite ni interpretar `confidence=1.0` como certeza estadística.

## 8. Comprobaciones realizadas

**Suite seleccionada: 15 passed in 4.44s.** No representa toda la suite del
repositorio. Comando ejecutado desde la raíz:

```bash
.venv/bin/python -m pytest -q \
  tests/test_delivery_features.py \
  tests/test_competitive_features.py::test_pr_impact_reports_risk_and_changed_file \
  tests/test_competitive_features.py::test_symbol_level_diff_impacts_callers_not_every_symbol \
  tests/test_shared_memory.py::test_context_prefers_current_branch_and_marks_changed_sources_stale \
  tests/test_shared_memory.py::test_context_warns_when_memory_commit_diverged \
  tests/test_shared_memory.py::test_benchmark_evidence_is_verified_revision_bound_and_idempotent \
  tests/test_shared_memory.py::test_memory_sync_watcher_appears_in_status_and_expires \
  tests/test_shared_memory.py::test_doctor_detects_and_reindex_repairs_missing_embedding \
  tests/test_shared_memory.py::test_continuity_context_finds_older_query_matched_message_across_agents \
  tests/test_memory_topics.py::test_context_complete_response_budget
```

**Diez comprobaciones diagnósticas aisladas:**

| Caso | Resultado observado |
|---|---|
| Cita inexistente + término coincidente | `supported`, `ok=true`. |
| ID de evidencia inexistente + término coincidente | `supported`, `ok=true`. |
| Afirmación sin evidencia, con longitud suficiente | `unsupported`, `ok=true` (operación/formato). |
| Única relación `AMBIGUOUS` | `supported`; se conserva la etiqueta ambigua dentro de la relación. |
| Frase editada en README de cuarenta secciones | 100/100; 0 símbolos; 41 nodos directos; 41 entradas de plan. |
| Dos consumidores `validate` de rutas distintas | Una entrada de plan. |
| Decisión antigua después de otras 500 memorias | Recuperable antes, omitida después; existe y FTS conserva una coincidencia. |
| Tres términos pertinentes precedidos por doce verbos | Una coincidencia con consulta corta; cero con la larga. |
| Informe sintético y posterior cambio de código nombrado en él | `verified_measured`, confianza 1.0; solo hash del informe y ninguna obsolescencia detectada. |
| Watcher con heartbeat caducado | `status=watching`, `active=false`: detección correcta, presentación mejorable. |

Son observaciones del comportamiento actual, no pruebas de correcciones ya
implementadas. La primera ejecución del reproductor necesitó habilitar captura
en su sesión **temporal** para insertar mensajes; la negativa inicial era el
control de consentimiento esperado, no un defecto del producto. El apéndice
incorpora esa configuración y las consultas de longitud suficiente.

## 9. Reproducción autocontenida

Guardar el bloque Python siguiente en un archivo temporal y ejecutarlo desde la
raíz mediante `PYTHONPATH=. .venv/bin/python /tmp/graphtyn_review_probes.py`.
Requiere la instalación de desarrollo y Git. Crea 501 memorias sintéticas en un
almacén temporal; puede tardar. Imprime JSON y elimina sus proyectos al terminar.
No necesita credenciales, datos del proyecto usuario ni servicios externos.

```python
import json
import os
import subprocess
import tempfile
from pathlib import Path

from graphtyn.core.answer_validation import validate_answer
from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.impact import analyze_impact
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.core.verification import verification_plan

results = {}
graph = {
    'nodes': [{'id': 's:service', 'name': 'Service', 'kind': 'class',
               'file': 'src/service.py', 'line': 1, 'end_line': 3,
               'details': 'Coordinates jobs'}],
    'links': [],
}
for name, claim in {
    'unrelated_citation': {'text': 'Service sends payments (missing.py:999999).'},
    'missing_evidence_id': {'text': 'Service sends payments automatically every evening.', 'evidence_ids': ['missing-node']},
    'unsupported_ok': {'text': 'Zebras transport galaxies safely across distant universes.'},
}.items():
    response = validate_answer(graph, claim['text'], [claim])
    results[name] = {'ok': response['ok'], 'claim': response['claims'][0]}

graph['nodes'].append({'id': 's:handler', 'name': 'handler', 'kind': 'function',
                       'file': 'src/handler.py', 'line': 1})
graph['links'].append({'source': 's:handler', 'target': 's:service',
                       'label': 'llama', 'confidence': 'AMBIGUOUS'})
results['ambiguous_link'] = validate_answer(graph, 'handler calls Service during request processing.')['claims'][0]
results['verification_name_collision'] = {
    'input_consumers': 2,
    'plan': verification_plan({'changed_symbols': [], 'impacted_nodes': [
        {'node': {'id': 'symbol:a.py:validate', 'name': 'validate', 'file': 'a.py'}, 'hop': 1},
        {'node': {'id': 'symbol:b.py:validate', 'name': 'validate', 'file': 'b.py'}, 'hop': 1},
    ]}),
}

with tempfile.TemporaryDirectory(prefix='graphtyn-product-audit-') as td:
    root = Path(td)
    os.environ['GRAPHTYN_HOME'] = str(root / 'store')
    os.environ['GRAPHTYN_EMBED_MODEL'] = ''
    project = root / 'project'
    project.mkdir()
    def git(*args):
        subprocess.run(['git', *args], cwd=project, check=True, capture_output=True)
    git('init', '-q')
    readme = project / 'README.md'
    content = '# Example\n\nIntro original.\n\n' + ''.join(
        f'## Section {i:02}\n\nExplanatory text.\n\n' for i in range(40))
    readme.write_text(content)
    git('add', 'README.md')
    git('-c', 'user.name=Audit', '-c', 'user.email=audit@example.test',
        'commit', '-qm', 'temporary baseline')
    readme.write_text(content.replace('Intro original.', 'Intro corregida.'))
    parsed = ASTParser().scan_directory(project, respect_git=True)
    impact = analyze_impact(project, parsed, base='HEAD')
    results['documentation_impact'] = {
        'changed_files': impact['changed_files'],
        'changed_symbols': len(impact['changed_symbols']),
        'risk': impact['risk'], 'impacted_count': impact['impacted_count'],
        'structured_plan': impact['verification_plan'],
        'cli_plan_count': len(verification_plan(impact)),
        'cli_plan_sample': verification_plan(impact)[:2],
    }

    store = SharedMemoryStore(project)
    session = store.start_session('codex', 'Isolated product audit', capture_enabled=True)
    target = store.checkpoint(session['id'], 'decision', 'xylophorino',
                              'xylophorino is the archived decision')
    before = store.search('xylophorino', requester_agent='codex')
    for i in range(500):
        store.checkpoint(session['id'], 'decision', f'Routine {i}', f'Routine event {i}')
    after = store.search('xylophorino', requester_agent='codex')
    with store._connect() as conn:
        fts = conn.execute("SELECT COUNT(*) FROM memories_fts WHERE memories_fts MATCH 'xylophorino'").fetchone()[0]
    results['old_memory_501'] = {
        'found_before': any(x['id'] == target['id'] for x in before),
        'found_after': any(x['id'] == target['id'] for x in after),
        'still_exists': bool(store.get(target['id'], requester_agent='codex')),
        'fts_matches': fts,
    }

    store.append_message(session['id'], 'assistant',
                         'La fotometria y su incertidumbre requieren calibracion.')
    short = 'fotometria incertidumbre calibracion'
    prefix = 'analizar proponer revisar preparar entregar documentar investigar contrastar reproducir priorizar organizar evaluar '
    short_result = store.search_messages(short)
    long_result = store.search_messages(prefix + short)
    results['long_query_messages'] = {
        'short_query': short, 'long_query': prefix + short,
        'short_matches': short_result['matched_messages'],
        'long_matches': long_result['matched_messages'],
    }

    source = project / 'unreferenced_model.py'
    source.write_text('def model(): return 1\n')
    artifact = project / 'benchmarks' / 'probe' / 'summary.json'
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({'description': 'Synthetic claim; no command executed.',
                                    'subject': 'unreferenced_model.py',
                                    'tests_passed': 123456}))
    imported = store.ingest_benchmark_evidence(['benchmarks/probe/summary.json'])
    item = store.get(imported['imported'][0], requester_agent='graphtyn-evidence')
    old_stale = store._stale_files(item)
    source.write_text('def model(): return 2\n')
    results['artifact_trust'] = {
        'status': item['status'], 'confidence': item['confidence'],
        'verification': item['metadata']['verification'],
        'fingerprinted_files': list(item['metadata']['source_fingerprints']),
        'claim_policy': store._claim_policy(item, store._revision_status(item, store._git_state())),
        'stale_before': old_stale, 'stale_after_unreferenced_code_change': store._stale_files(item),
    }

    store.update_sync_watcher('audit:stale', 'watching', interval=5)
    with store._connect() as conn:
        conn.execute('UPDATE memory_sync_watchers SET heartbeat=0 WHERE watcher_id=?', ('audit:stale',))
    watcher = next(w for w in store.status()['sync_watchers'] if w['watcher_id'] == 'audit:stale')
    results['watcher'] = {k: watcher[k] for k in ('status', 'active', 'heartbeat')}

print(json.dumps(results, ensure_ascii=False, indent=2))
```
