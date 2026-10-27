# Benchmark Ruby/Rails con tres agentes

Este piloto fijó Ruby on Rails en el commit
`3f0b675158e8284241bb1213c00375bc1fb9c52f` y comparó lectura local contra
Graphtyn en OpenCode, Codex y Antigravity. Las seis sesiones terminaron y las
seis respuestas cubrieron 8/8 hechos de la rúbrica después de una adjudicación
manual declarada y no independiente. Hubo una repetición por celda: el resultado
sirve para detectar comportamiento y regresiones, no para prometer un porcentaje
general de ahorro.

| Cliente y modelo | Total base | Total Graphtyn | Delta | Tiempo base | Tiempo Graphtyn | Primera consulta con índice | Calidad |
|---|---:|---:|---:|---:|---:|---:|---:|
| OpenCode · `opencode/deepseek-v4.1-flash-free` | 1.233.520 | 403.413 | −67,30 % | 267,756 s | 67,953 s | 255,330 s | 8/8 ↔ 8/8 |
| Codex · `gpt-6-astra` | 203.645 | 379.839 | +86,52 % | 98,841 s | 285,888 s | 471,563 s | 8/8 ↔ 8/8 |
| Antigravity · `gemini-3.8-flash-high` | 319.618 | 195.629 | −38,79 % | 392,924 s | 188,960 s | 369,438 s | 8/8 ↔ 8/8 |

“Primera consulta con índice” suma el índice frío, que el protocolo registró
fuera del tiempo de sesión. En OpenCode y Antigravity el coste inicial aún quedó
4,64 % y 5,98 % por debajo de sus bases; en Codex quedó 377,09 % por encima.
Las consultas siguientes reutilizan el índice y no pagan ese coste completo.

## Qué miden los tokens

Los deltas sólo se comparan dentro del mismo cliente y modelo. OpenCode suma los
eventos `step_finish`, cuyo contador en esta versión es por paso; su total incluye
entrada, entrada en caché, salida y razonamiento. En Codex, la entrada cacheada es
un subconjunto de `input_tokens` y el razonamiento es un subconjunto de salida:
sumarlos otra vez duplicaría consumo. Antigravity expone la caché aparte. Al
añadirla como volumen técnico observado, Antigravity pasa de 1.932.386 a 796.143
(−58,80 %); OpenCode y Codex conservan su total informado.

OpenCode declaró coste de proveedor 0 porque se usó el modelo gratuito. Codex y
Antigravity no entregaron coste monetario. Por ello este piloto compara consumo
de tokens y tiempo, pero no permite calcular ahorro en dinero entre proveedores.
No hubo eventos explícitos de reintento; los reintentos invisibles al cliente no
se pueden reconstruir.

## Calidad y recuperación

La rúbrica automática dio 8/8 a ambos brazos de OpenCode y Antigravity, 7/8 a la
base de Codex y 5/8 a Codex con Graphtyn. La revisión del texto congelado elevó
las dos respuestas de Codex a 8/8: sí describían la rama de creación; el brazo
Graphtyn también describía el filtrado de atributos y las ramas de fallo con
palabras distintas de los términos estrechos del grader. Las decisiones y sus
líneas están en [`manual_adjudication.json`](manual_adjudication.json). Esta
revisión no es independiente y se publica como tal.

OpenCode recibió 3.035 tokens de contexto en 11 nodos y Codex 2.756 en 10; ambos
paquetes declararon cero obligaciones faltantes y `do_not_expand=true`.
Antigravity conservó la duración de su llamada MCP (10,920 s), pero su stream no
guardó el cuerpo, así que no se reconstruyen su payload ni sus nodos. Las citas
resolubles de los brazos Graphtyn apuntan a líneas existentes; algunos textos
también usan nombres cortos ambiguos como `base.rb`, que el analizador conserva
como no resolubles sin calificarlos de línea inválida.

La regresión de Codex coincide con una carga anómala del índice: su paquete
registró 179,972 s en `load_index` y 4,083 s en recuperación. El índice previo
contenía 691.917 relaciones y ocupaba 581.948.108 bytes, debido sobre todo a
llamadas Ruby homónimas materializadas contra cientos de candidatos. Por tanto,
esa celda prueba que Graphtyn puede consumir más cuando cargar el grafo domina la
sesión y el agente continúa explorando; no demuestra que Codex siempre empeore.

## Corrección posterior sin alterar el histórico

La resolución actual ya no materializa una relación cuando hay más de cuatro
candidatos empatados para una llamada, herencia o mixin. En el mismo commit de
Rails, una reindexación local redujo las relaciones de 691.917 a 244.592
(−64,65 %) y `index.json` de 581.948.108 a 253.461.644 bytes (−56,45 %). El
índice frío pasó de 187,162 a 175,308 s (−6,33 %) y la misma consulta CLI de
13,282 a 7,296 s (−45,07 %). Conservó las ocho obligaciones, 10 entidades, cero
faltantes y un payload de 2.756 tokens.

No se repitieron sesiones de modelos después de esa corrección. Los deltas de la
tabla pertenecen al grafo anterior y permanecen intactos. La evidencia posterior
está en [`post_fix_verification.json`](post_fix_verification.json) y
[`post_fix_retrieval.json`](post_fix_retrieval.json); los resultados analizables
están en [`results.json`](results.json) y [`grades_by_run.json`](grades_by_run.json).
Los eventos crudos siguen fuera del repositorio en la ruta registrada dentro de
cada fila de `grades_by_run.json`.

## Lectura del resultado

Graphtyn redujo tokens con OpenCode y Antigravity y los aumentó con Codex en esta
tarea. El resultado favorable depende de que la recuperación acote exploración
que el agente habría realizado; el resultado desfavorable aparece cuando el
índice o la integración añaden trabajo sin desplazar suficiente lectura. La
próxima comparación debe usar al menos tres repeticiones, índice precalentado y
frío por separado, el mismo commit y una evaluación ciega. También debe mantener
las sesiones fallidas y publicar por separado payload recuperado, total de
sesión, caché, salida, razonamiento, tiempo y coste monetario disponible.
