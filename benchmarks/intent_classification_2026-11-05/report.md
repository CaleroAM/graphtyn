# Clasificación de intención con preguntas de otro modelo

Fecha: 2026-11-05. Sin sesiones de agente: solo `classify_intent` sobre preguntas
generadas y etiquetadas por Gemini (`gemini-3.8-flash-high`, Antigravity CLI), sin
herramientas ni acceso al código de Graphtyn. Cuatro lotes de 72 preguntas: seis
intenciones por seis idiomas (español, inglés, portugués, francés, alemán e italiano),
dos por combinación, sobre repositorios públicos distintos en cada lote.

**Veredicto: POSITIVE, con brecha de sobreajuste.** En el lote final, evaluado una sola
vez, acierta 59 de 72 (82 %), frente a 39 en la punta del PR #35 y 33 en `main`. En los
lotes que sirvieron para ajustar acierta 69-71 de 72, así que la cifra que vale es la del
lote final.

## Resultado

| Lote | Papel | `main` | PR #35 | Ahora |
|---|---|---:|---:|---:|
| 1 | ajuste | 34/72 | 39/72 | 69/72 |
| 2 | ajuste | 27/72 | 30/72 | 69/72 |
| 3 | prueba de la primera ronda | 30/72 | 33/72 | 57/72, luego ajuste: 71/72 |
| 4 | prueba final | 33/72 | 39/72 | **59/72** |

Antes de este cambio, el conjunto de 53 que escribí yo daba 53/53: medía regresión, no
generalización. Con preguntas ajenas, el clasificador mandaba casi todo `impact` y
`bindings` a `flow`, porque sus marcadores eran palabras sueltas, casi todas en español o
inglés.

## Qué cambió

- **Señales de concepto por intención** (`graphtyn/core/intent_lexicon.py`), en seis
  idiomas: «who directly calls», «se verían afectados», «quais classes chamam», «wird …
  eingehängt», «dove viene memorizzato». Pesan el doble que un marcador suelto, así que
  «save» o «query» en una pregunta sobre un ciclo de vida ya no la hacen de persistencia.
- **Una petición de cambio que pregunta qué se rompe es `impact`**, no `flow`.
- **«this Express repository» es ámbito**, igual que «este repositorio»: «repository» ya
  no suma a `persistence`.
- **Un nombre de producto no anula `overview`:** «la arquitectura de este repo NestJS»
  sigue siendo un resumen, pero «la arquitectura del módulo auth_service» es código.
- **Pedir la traza explícitamente** («traza», «trace», «flujo») pesa como una señal: una
  etapa que guarda datos no convierte la pregunta en `persistence`.

## Límites

- **Las etiquetas son de un solo modelo.** Algunas son discutibles: «¿qué pasos recorre
  `action_confirm` en el modelo?» la etiquetó `flow` y el clasificador dice
  `persistence`.
- **El lote 1 usaba otra definición de `bindings`:** incluía las rutas hacia sus
  controladores, que en Graphtyn son `flow`. Sus 3 fallos restantes son esas preguntas.
- **El lote 4 tiene 13 fallos** que no se corrigieron, para no convertirlo en ajuste. Por
  ejemplo, «¿dónde se romperá el binding?» sale `bindings` en vez de `impact`.
- **Cambian 3 de 164 prompts de benchmarks anteriores.** Dos pasan de `persistence` a
  `flow` por pedir la traza explícitamente; el tercero, «Explica SnapshotManager:
  contrato, serialización…», pasa de `flow` a `persistence`.
- **Solo afecta a `intent=auto`.** El agente suele elegir la intención; la clasificación
  automática cuenta en los hooks de primer turno y cuando el agente pasa `auto`.

## Reproducir

```bash
python benchmarks/intent_classification_2026-11-05/evaluate.py --misses
```

Cada `batchN.json` guarda el enunciado exacto que recibió Gemini y sus etiquetas. La
prueba `test_classification_of_generated_batches_does_not_fall_back` fija un mínimo por
lote como regresión, no como medida de generalización.
