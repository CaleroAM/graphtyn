# Banco de tareas con división desarrollo/prueba — 28 oct 2026

## Qué se midió

El conjunto v2 (`../heldout_v2_2026-10-27/report.md`) mostró que la recuperación
no generalizaba. Para corregirla sin sobreajustar se creó un banco de 30 tareas
sobre Redis, fmt y Rails:

- **Desarrollo (15 tareas):** las ya vistas antes de este banco. Son las 3
  originales, las 6 del primer conjunto no visto y las 6 de v2. Sólo con ellas
  se iteraron los cambios.
- **Prueba (15 tareas):** escritas y congeladas en `78c705a` antes de cualquier
  cambio, con la rúbrica sacada de leer la fuente y sin consultar Graphtyn. Su
  cobertura se midió una sola vez, al terminar.

La métrica es la **cobertura del paquete**: cuántos hechos de la rúbrica aparecen
en la respuesta lean de `graph_query_intent`. No hace falta ningún agente.
Hay una **falsa completitud** cuando el paquete declara `do_not_expand=true`
cubriendo menos de la mitad de la rúbrica.

```bash
GRAPHTYN_HOME=<índices> PYTHONPATH=. python benchmarks/task_bank_2026-10-28/coverage.py dev|test <corpus>
```

## Cambios

1. **Vocabulario entre idiomas** (`graphtyn/core/vocabulary.py`):
   - un glosario genérico de programación español→inglés, por raíces
     (`evicci`→`evict`, `búfer`→`buffer`, `flotante`→`float`);
   - una lista de palabras españolas que aparecen dentro de identificadores
     ingleses (`forma` en `format`, `entre` en `centre`) y no cuentan como
     coincidencia.
2. **Términos distintivos** (`retrieval_signals.NameFrequency`):
   - un término de la petición deletreado por pocos nombres de función puntúa
     cuando aparece dentro de un nombre (`evict` en `performEvictions`);
   - uno deletreado por demasiados nombres (`redis` en Redis, `format` en fmt)
     deja de puntuar en las operaciones.
3. **Operaciones de `flow` sin sesgo web:**
   - `save`, `send`, `publish`… sólo filtran y puntúan si la petición los
     nombra;
   - los campos de struct (`lru`, `maxmemory`) ya no anclan un `flow` al
     fichero que los declara.
4. **Homónimos y cadena de llamadas:**
   - como mucho dos candidatos con el mismo nombre, salvo los obligatorios;
   - en `flow`, las funciones llamadas por el punto de entrada que deletrean un
     término de la petición entran justo después de él
     (`format_to_n`→`vformat_to_n`).
5. **Regla de completitud** (`graphtyn/core/evidence_sufficiency.py`):
   - una petición con cuatro o más partes necesita al menos 250 tokens de
     evidencia por parte para mantener `do_not_expand=true`;
   - si no los tiene, el paquete pasa a `missing=["request_parts"]` y la guía
     (MCP y hook) pide responder con lo que hay y buscar sólo las partes que no
     aborda;
   - al no declararse completo, el paquete lean conserva entidades que antes
     podaba.

Dos señales se probaron y se descartaron porque, sobre desarrollo, no separaban
paquetes buenos de malos:

- **Cobertura léxica de cada parte de la petición:** Rails `update` (0/8)
  quedaba casi cubierta y Redis `command` (8/8) no, igual que con el detector
  descartado en v2.
- **Nodos anclados a un término raro:** Redis `output limit` tenía 8 de 10
  anclados con 1/8 de cobertura.

El umbral de 250 tokens por parte se calibró sobre las 15 tareas de desarrollo.

## Resultados

| Conjunto | Código | Cobertura media | Tareas ≥ 50 % | `do_not_expand=true` | Falsas completitudes | Tokens medios |
|---|---|---:|---:|---:|---:|---:|
| Desarrollo | antes (`78c705a`) | 46,6 % | 7/15 | 11 | 5 | 2.416 |
| Desarrollo | después | 73,1 % | 13/15 | 8 | 0 | 2.991 |
| **Prueba** | antes (`78c705a`) | **20,0 %** | 3/15 | 11 | **8** | 2.296 |
| **Prueba** | después | **37,5 %** | 4/15 | 4 | **3** | 2.556 |

Detalle por tarea: `dev_before.jsonl`, `dev_after.jsonl`, `test_before.jsonl`
y `test_after.jsonl`.

Prueba, tarea a tarea (antes → después):

| Tarea | Antes | Después | `do_not_expand` después |
|---|---:|---:|---|
| Redis reescritura AOF | 0/8 | 8/8 | false |
| Redis PUBLISH | 6/8 | 8/8 | true |
| Redis BLPOP | 0/8 | 1/8 | **true** |
| Redis MULTI/EXEC | 0/8 | 2/8 | false |
| Redis redirección de cluster | 0/8 | 0/8 | **true** |
| fmt argumentos con nombre | 0/8 | 1/8 | false |
| fmt ancho dinámico | 0/8 | 3/8 | false |
| fmt rangos | 1/8 | 3/8 | false |
| fmt duración chrono | 1/8 | 1/8 | false |
| fmt color y estilo | 7/8 | 5/8 | false |
| Rails validaciones | 2/8 | 3/8 | false |
| Rails `after_commit` | 3/8 | 3/8 | false |
| Rails strong parameters | 4/8 | 7/8 | false |
| Rails migraciones | 0/8 | 0/8 | false |
| Rails despacho de rutas | 0/8 | 0/8 | **true** |

## Conclusiones

1. **Los cambios generalizan, pero sólo en parte.**
   - La cobertura de prueba casi se duplica (20 %→37,5 %) y las falsas
     completitudes bajan de 8 a 3.
   - Aun así, la prueba queda muy por debajo de desarrollo (73 %). La distancia
     es la medida honesta del sobreajuste que queda.
   - Una tarea empeora: fmt color pasa de 7/8 a 5/8.
2. **La regla de completitud detecta paquetes escasos, no paquetes
   equivocados.**
   - BLPOP, la redirección de cluster y el despacho de rutas traen mucha
     evidencia de otra parte del código.
   - Siguen declarándose completos.
3. **Fallos vistos en prueba y no corregidos**, para no contaminarla:
   - **Intención mal clasificada:** «registra»/«se registran» activa `bindings`
     en tres tareas (MULTI/EXEC, argumentos con nombre, migraciones). El
     marcador `registr` sólo excluye «registro(s)».
   - **Composición de módulos Ruby:** Rails sigue sin llegar a los métodos que
     se componen por módulos (`Persistence#update`, `Migrator`, Journey).
4. **Siguiente paso:**
   - corregir esos fallos;
   - escribir un **nuevo** conjunto de prueba congelado antes de medirlos, porque
     este ya se ha mirado.

## Limitaciones

- **Cobertura no es calidad de respuesta:** mide si el paquete contiene la
  evidencia, no si el agente la usa. No se han repetido sesiones de agentes con
  estos cambios.
- **Coste:** los paquetes son algo mayores (+11 % en prueba), y los que ya no se
  declaran completos pueden hacer que el agente busque más.
- **Autoría:** las tareas y rúbricas las escribió el mismo agente que hizo los
  cambios. El glosario es genérico, pero quien lo escribió conocía las
  peticiones de prueba, así que no se puede excluir cierta fuga.
- **Índices:** los de los tres corpus se construyeron con `ast_pure` en modo
  `fast`, con el código de esta rama.

## Segunda ronda: fallos vistos en prueba y segundo conjunto de prueba

### Diseño

Primero se escribió y congeló un **segundo conjunto de prueba** (`test2/`, en
`406ed5f`), antes de tocar el código:

- 9 tareas nuevas sobre Redis, fmt y Rails;
- 6 sobre **Flask** (`d086db8`), un corpus nunca usado para ajustar.

El primer conjunto de prueba pasó a desarrollo, que queda en 30 tareas.

### Cambios

- **Intención:** «registra»/«se registran» sólo cuenta como `bindings` si hay
  vocabulario de inyección de dependencias cerca.
- **Completitud por identificadores** (`evidence_sufficiency`): si la petición
  nombra un identificador (`BLPOP`, `TRYAGAIN`, `snake_case`, `camelCase`) y la
  evidencia no lo contiene, el paquete no es completo y `evidence_sufficiency`
  lista los que faltan. Es la señal que detecta paquetes grandes pero
  equivocados.
- **Homónimos:**
  - se prefiere el dueño que describe la petición (`persistido` →
    `Persistence#update`);
  - se prefiere la firma escrita en la petición (`update(attributes)`).
- **Términos:** las palabras españolas en prosa y los nombres de directorio
  del árbol (`activerecord`) ya no puntúan.
- **Tests:** penalización mayor fuera de la intención `tests`.
- **Cadena de llamadas:** hasta tres saltos por métodos hermanos del punto de
  entrada (`update`→`save`→`create_or_update`→`_update_record`).

### Descartado durante la ronda

| Cambio | Resultado en desarrollo |
|---|---|
| Excluir los tests del recuento de frecuencia de nombres | Bajaba la cobertura (Rails `find` de 8/9 a 1/9) |
| Elegir como semilla de la cadena el candidato mejor puntuado | 55,3 % → 52,6 % |

### Cobertura

Desarrollo (30 tareas): de 55,3 % a 56,1 %, con las falsas completitudes de
3 a 0.

Segundo conjunto de prueba, medido una sola vez con tres versiones del código
(`*` = `do_not_expand=true`):

| Tarea | Original (`78c705a`) | Ronda 1 (`406ed5f`) | Ronda 2 |
|---|---:|---:|---:|
| Redis notificaciones keyspace | 6/7* | 6/7* | 6/7* |
| Redis INCRBY | 0/8* | 0/8* | 0/8* |
| Redis SCAN | 0/8* | 1/8 | 1/8 |
| fmt printf | 5/8* | 5/8 | 5/8 |
| fmt ostream | 2/7* | 6/7* | 4/7 |
| fmt FMT_COMPILE | 1/8* | 5/8 | 5/8 |
| Rails has_many | 0/9 | 3/9 | 3/9 |
| Rails enum | 0/9* | 4/9 | 0/9 |
| Rails render json | 4/9* | 4/9* | 4/9* |
| Flask despacho | 7/8* | 7/8* | 7/8* |
| Flask errores | 8/8* | 8/8* | 8/8* |
| Flask sesión | 7/8* | 3/8* | 7/8* |
| Flask blueprints | 5/8* | 5/8* | 5/8* |
| Flask url_for | 7/7* | 7/7* | 7/7* |
| Flask contexto | 8/8* | 8/8* | 8/8* |
| **Media** | **51,4 %** | **61,2 %** | **59,7 %** |
| **Falsas completitudes** | **6** | **3** | **2** |

- **La ronda 1 generaliza.** El grueso de la mejora en tareas nuevas (de 26 %
  a 48 % fuera de Flask) viene de ella.
- **La ronda 2 no sube la cobertura**, pero quita otra falsa completitud.
- **Rails enum** retrocede: 4/9 → 0/9.
- **Falsas completitudes que quedan:**
  - Redis INCRBY: la evidencia nombra `incrby`, pero no la función que lo
    implementa;
  - Rails render json.
- **Flask** ya salía bien con el código original (89,6 %): en un proyecto
  pequeño y en inglés el problema era menor.

### Tamaño de los paquetes

En el segundo conjunto de prueba los paquetes pasan de 2.589 a 2.893 tokens de
media (+12 %). El crecimiento sale entero de los 5 paquetes que dejaron de
declararse completos: pasan de 1.320 a 2.273 tokens, porque el paquete lean ya
no poda sus entidades. Donde la completitud no cambia, el tamaño es el mismo
(3.223 frente a 3.203). Todos quedan dentro del presupuesto de 4.000 tokens.

### Sesiones con agentes

- **Sesiones:** 75, todas completas.
- **Diseño:** una repetición por celda, sobre las 15 tareas del segundo
  conjunto de prueba, con la regla de parada dirigida.
- **Clientes:**
  - Claude Code `claude-sonnet-5-5`: sin grafo y hook;
  - Codex `gpt-5.6-luna`: sin grafo, MCP lean y hook.
- **OpenCode:** no se ejecutó, porque su proveedor gratuito falló en la ronda
  anterior.
- **Datos:** detalle en `agent_grades_by_run.json` y `agent_results.json`;
  eventos crudos en
  `/home/calero/Documentos/docker/graphtyn-benchmark-runs-task-bank-2026-10-28/`.

| Cliente y brazo | n | Tokens medios | Rúbrica media | Herramientas |
|---|---:|---:|---:|---:|
| Claude, sin grafo | 15 | 145.898 | 93,8 % | 3,9 |
| Claude, hook | 15 | 124.813 (−14 %) | 93,8 % | 2,9 |
| Codex, sin grafo | 15 | 144.407 | 69,9 % | 5,4 |
| Codex, MCP lean | 15 | 115.945 (−20 %) | 64,9 % | 5,0 |
| Codex, hook | 15 | 106.241 (−26 %) | 72,3 % | 4,1 |

1. **Con el hook, ninguno de los dos clientes pierde calidad respecto a no
   usar grafo, y ambos gastan menos.**
   - En Claude, la calidad es igual.
   - En Codex, el hook pasa de 55 % en v2, por debajo de su referencia sin
     grafo, a 72 % frente a 70 % sin grafo.
2. **Codex con MCP lean sigue por debajo de la referencia** (65 % frente a
   70 %). La diferencia se concentra en Redis INCRBY y SCAN, fmt printf y Rails
   render json: tareas cuyo paquete cubre poco.
3. **Alcance:** con n=1 por celda, las diferencias de unos pocos puntos están
   dentro del ruido. La rúbrica es literal, sin adjudicación ciega.

## Tercera ronda: CI, composición Ruby y pesos aprendidos

### Prueba de regresión en CI

`tools/check_retrieval_coverage.py` clona fmt y Flask en commits fijados,
los indexa y construye el paquete lean de sus 19 tareas del banco, sin
agentes. Tarda unos segundos.

El job `retrieval` del CI falla si ocurre cualquiera de estas cosas:

- la cobertura media baja más de un punto;
- una tarea pierde dos hechos o más;
- aparece una falsa completitud nueva.

La línea base está en `tools/retrieval_coverage_baseline.json`.

### Composición de módulos Ruby (`graphtyn/core/ruby_mro.py`)

- **Búsqueda de constantes:** `include`/`prepend`/`extend` se resuelven como lo
  hace Ruby, por ámbito léxico. Un módulo reabierto en varios archivos cuenta
  como una sola constante.
- **Despacho de llamadas:** las llamadas sin receptor y `super` dentro de un
  módulo se resuelven por la cadena de ancestros de cada clase que lo incluye.

Efecto en Rails:

| Relación | Antes | Después |
|---|---:|---:|
| `include` ambiguos | 1.166 | 54 |
| Llamadas resueltas por despacho | 0 | 16.181 |
| Relaciones `super` | 0 | 527 |

Por ejemplo, ahora existe la cadena
`Suppressor#save`→`Transactions#save`→`Validations#save`→`Persistence#save`.

**La cobertura de los paquetes no cambia** (56,1 % en desarrollo). Las
aristas están en el grafo, pero la cadena de llamadas de la recuperación arranca
desde el primer símbolo nombrado (`Transactions#save` en Rails `update`), no
desde `Persistence#update`. Seguir esas aristas o sembrar desde el candidato
mejor puntuado empeoraba Redis y fmt (53,8–55,3 %), así que se revirtió. El
grafo queda corregido para los agentes que recorren relaciones.

### Pesos aprendidos (`graphtyn/core/ranking_weights.py`)

La puntuación de candidatos de `query_intent` es ahora una tabla de 25 rasgos
con nombre y pesos. Antes de cambiar ningún peso se comprobó que la conversión
daba resultados idénticos en las 30 tareas de desarrollo.

`tools/learn_ranking_weights.py` ajusta los pesos:

- **Objetivo:** hechos de la rúbrica que cubren los 10 primeros candidatos de
  cada tarea de desarrollo.
- **Búsqueda:** por coordenadas, con multiplicadores de los pesos actuales.
- **Primer intento, sin restricción:** sobreajustó. El objetivo subía en
  desarrollo de 0,408 a 0,501 y bajaba en test2 de 0,631 a 0,573.
- **Regla añadida:** un paso sólo se acepta si no empeora ningún corpus.
- **Resultado:** el objetivo pasa de 0,408 a 0,474 en desarrollo y de 0,631 a
  0,635 en test2.

| Pesos | Desarrollo (30) | Test2 (15) |
|---|---:|---:|
| Manuales | 56,1 % | 59,7 % |
| Ajustados | 55,7 % | 60,8 % |

Con el pipeline completo, los pesos ajustados empatan con los manuales: un
hecho menos en desarrollo y uno más en test2. Se adoptan porque no pierden en
tareas no vistas y apagan dos rasgos que no aportaban (`concept_hits` y
`described_owner`).

La lección: **el ranking ya no es el cuello de botella**. Lo que decide la
cobertura es la selección posterior (representantes obligatorios, archivos
ancla, cadena de llamadas), que sigue siendo heurística.

## Cuarta ronda: dónde se pierde la evidencia

### Diagnóstico por etapas

`selection_diagnosis.py` traza cada etapa de selección de `query_intent`
(`ranking_weights.trace_selection`). Para cada una cuenta los hechos de la
rúbrica que deletrean sus N primeros candidatos, donde N es el número de nodos
seleccionados. En las 30 tareas de desarrollo (`selection_diagnosis_dev.jsonl`):

| Etapa | Hechos alcanzables |
|---|---:|
| En algún nodo del grafo | 99,6 % |
| N primeros del ranking | 46,6 % |
| Tras ordenar símbolos cualificados (antes de los obligatorios) | 33,3 % |
| Tras representantes obligatorios y límite de homónimos | 49,9 % |
| Tras archivos ancla | 48,8 % |
| Tras cadena de llamadas | 54,0 % |
| Nodos seleccionados | 54,9 % |
| Paquete lean (con fragmentos de fuente) | 55,7 % |

**El índice no es el problema; el ranking sí.** La ronda anterior concluyó lo
contrario porque sólo ajustaba pesos de rasgos existentes.

De los hechos perdidos, 52 quedan por debajo del puesto 100 y 7 ni siquiera son
candidatos. Casi todos son etapas a las que llama el punto de entrada y que no
comparten ninguna palabra con la petición: `_update_record` y `_update_row` en
Rails `update`, `handleClientsBlockedOnKeys` en BLPOP. Ningún rasgo léxico puede
encontrarlas.

### Cambios

- **Orden de los símbolos nombrados:** los representantes obligatorios siguen
  el orden en que la petición los nombra, no el alfabético. Antes, Rails
  `update` sembraba la cadena desde `Transactions#save` (alfabéticamente,
  `save` va antes que `update`).
- **Despacho Ruby en la cadena:** las llamadas resueltas por despacho Ruby
  cuentan como llamadas entre hermanos del mismo objeto. Ahora la cadena de
  Rails `update` recorre `Persistence#save`→`create_or_update`.

### Probado y descartado: proximidad en el grafo de llamadas

Se añadió como rasgo de ranking una activación que se propaga por las llamadas
desde los cinco mejores candidatos, con decaimiento por salto y sin coste entre
overrides del mismo nombre.

| Peso | Desarrollo |
|---:|---:|
| 0 | 55,7 % |
| 300 | 55,4 % |
| 600 | 56,2 % |
| 1000 | 55,0 % |
| 1500 | 52,3 % |

A tres saltos la activación aporta unos 200 puntos frente a los ~1.400 del ruido
léxico; subirla desplaza evidencia buena en fmt y Redis. Se retiró.

### Presupuesto de nodos

`query_intent` limita los flujos a 9 nodos más uno por cada «y» de la petición
(máximo 12), dentro del límite de 10 que pide el MCP.

| Nodos | Cobertura en desarrollo | Tokens del paquete |
|---:|---:|---:|
| 10 | 56,2 % | 2.833 |
| 18 (con el tope de flujo en 14) | 60,0 % | 3.092 |

Es la palanca más barata medida: +3,8 puntos por un 9 % más de tokens. No se
aplicó, porque cambia el presupuesto por defecto que documentan `AGENTS.md` y la
skill.

### Resultado

| Conjunto | Ronda 3 | Ronda 4 |
|---|---:|---:|
| Desarrollo | 55,7 % | 56,2 % |
| Test2 | 60,8 % | 60,8 % (ninguna tarea cambia) |

- **Rails `update`:** de 1/8 a 2/8.
- **Rails `destroy`:** de 6/8 a 7/8.
- **Redis `expire`:** de 6/8 a 5/8.

Rails ya usa las aristas nuevas, pero la mejora es pequeña. Las etapas
profundas (`_update_record`, `_update_row`) quedan fuera del presupuesto de
nodos, ocupado por coincidencias léxicas como `Attributes`, `update_all` o
`cache_sql`.

### Próximo paso con más efecto

Con estos datos, lo que más rendiría es reemplazar el relleno léxico por la
cadena de llamadas: una vez identificado el punto de entrada, dedicar la mitad
del presupuesto a sus etapas en el grafo. Habría que validarlo con un tercer
conjunto de prueba, porque test2 ya se ha medido cuatro veces.

## Quinta ronda: presupuesto de flujo, cadena reservada y coste por tipo de token

### Diseño

Antes de cambiar código se congeló un tercer conjunto de prueba (`test3/`,
commit `a2cd6f6`): 15 tareas sobre Redis, Rails, Flask y **Lua**, un corpus
nunca usado para ajustar. Las variantes se ajustaron sólo en desarrollo y se
midieron una vez en test2 y test3.

| Variante | Qué cambia |
|---|---|
| A | Más presupuesto: tope de flujo 14 y 18 entidades |
| B | La mitad del presupuesto se reserva para las etapas a las que llama el punto de entrada, aunque no compartan palabras con la petición; se excluyen las utilidades con más de 12 llamadores |
| C | `call_outline`: hasta 12 etapas más, sólo nombre y `archivo:línea` |
| D | Un comando escrito en mayúsculas (`BLPOP`) incluye su función (`blpopCommand`) |
| E | Anclaje sin código de terceros y con los obligatorios conservados |

D surgió al ver que Redis SET/DEL/HSET no encontraban su `…Command` en la línea
base de test3; se validó en desarrollo (MULTI/EXEC 1/8 → 6/8), pero su cifra en
test3 no está limpia. B+C, sin D, sí lo está.

### Cobertura del paquete

| Variante | Desarrollo | test2 | test3 | Tokens test3 |
|---|---:|---:|---:|---:|
| Anterior | 56,2 % | 60,8 % | 35,9 % | 2.780 |
| A | 60,0 % | 58,5 % | 35,9 % | 2.936 |
| B | 58,7 % | 59,9 % | 40,5 % | 2.783 |
| C | 57,1 % | 62,4 % | 43,6 % | 2.814 |
| D | 59,1 % | 62,4 % | 36,8 % | 2.747 |
| B+C | 59,1 % | 61,6 % | 44,4 % | 2.840 |
| **B+C+D (adoptada)** | **62,8 %** | **66,6 %** | **48,8 %** | 2.809 |
| B+C+D+E | 60,5 % | 66,6 % | 50,2 % | 2.863 |

- **A no generaliza.** El paquete tiene un tope de 4.000 tokens: con más nodos se
  recortan los fragmentos de código (Flask teardown 8/8 → 4/8).
- **E se descartó:** baja desarrollo 2,4 puntos.
- Siguen a cero en todas las variantes: Redis HSET («hash» ancla el paquete al
  `hash.h` de jemalloc), Redis DEL y Rails `reload` (homónimo equivocado).

Los resultados por variante están en `round5_variants/`.

### Sesiones con agentes

300 sesiones en test3: Claude (Sonnet 5.5) y Codex (gpt-5.6-luna), sin Graphtyn,
con la política anterior y con B+C+D, tres repeticiones por tarea (45 sesiones
por celda), más una repetición de A. Las sesiones que fallaron por límites de
uso (Claude) o errores 429 (Codex) se repitieron; los intentos fallidos se
conservan en `failed_attempts/`.

El total de tokens mezcla tipos con precios muy distintos. En Claude, unos
125.000 de los ~150.000 tokens de una sesión son lecturas de caché del prompt y
las herramientas del cliente, que Graphtyn no puede reducir. `analyze_variants.py`
separa los tipos y los pondera por precio relativo a un token de entrada sin
caché (lectura de caché 0,1; escritura 1,25; salida 5 en Claude y 8 en Codex).

| Cliente y variante | Calidad | Total | Escritura de caché | Entrada sin caché | Salida | Ponderado |
|---|---:|---:|---:|---:|---:|---:|
| Claude, sin Graphtyn | 93,5 % | 159.425 | 17.604 | — | 3.634 | 54.002 |
| Claude, anterior | 94,8 % | 151.922 | 15.943 | — | 3.040 | 48.428 |
| Claude, B+C+D | 94,9 % | 139.025 | 13.544 | — | 2.945 | 43.916 |
| Codex, sin Graphtyn | 69,3 % | 141.269 | — | 29.909 | 2.415 | 60.126 |
| Codex, anterior | 66,6 % | 135.894 | — | 25.013 | 2.181 | 53.328 |
| Codex, B+C+D | 71,2 % | 115.167 | — | 22.604 | 2.018 | 47.805 |

Diferencias emparejadas por tarea, con intervalo bootstrap del 95 %:

| Comparación | Coste ponderado | Calidad |
|---|---:|---:|
| Claude, B+C+D frente a sin Graphtyn | −18,7 % [−31,4; −7,5] | +1,3 pt [0,0; +3,0] |
| Claude, B+C+D frente a anterior | −9,3 % [−15,6; −2,9] | +0,1 pt [−0,7; +1,0] |
| Codex, B+C+D frente a sin Graphtyn | −20,5 % [−28,5; −12,7] | +1,9 pt [−4,4; +7,4] |
| Codex, B+C+D frente a anterior | −10,4 % [−19,4; −2,2] | +4,6 pt [+0,8; +7,7] |
| Codex, anterior frente a sin Graphtyn | −11,3 % [−20,6; −2,4] | −2,6 pt [−8,0; +2,3] |

- **B+C+D reduce el coste ponderado en torno a un 20 % frente a no usar
  Graphtyn en ambos clientes, sin perder calidad.**
- Frente a la política anterior ahorra un 9–10 % y, en Codex, recupera la
  calidad que aquélla perdía.
- La calidad depende sobre todo del modelo. En la primera repetición, Claude respondía con unas 600
  palabras y omite el 4 % de los hechos que el paquete le dio; Codex, con unas 300, y omite el 26 %. La rúbrica cuenta nombres literales, lo que
  penaliza las respuestas breves.

### Cambios adoptados

- `graphtyn/core/retrieval_signals.py`: `with_call_chain(reserved=…)`,
  `call_outline`, `flow_outline`, `render_call_outline`, `command_handlers` y
  la política por defecto (`CHAIN_SHARE=0.5`, `CHAIN_SEEDS=1`,
  `OUTLINE_LIMIT=12`, `COMMAND_NAMES=True`, `FLOW_NODE_CAP=9`).
- `source_evidence`: los fragmentos que empatan conservan el orden de
  selección, no el de sus rutas.
- `analyze_variants.py`: tokens por tipo y coste ponderado.
- Prueba de cobertura de CI con 22 tareas (incluye las de Flask de test3).

### Pendiente

- Anclaje en dependencias incluidas (`deps/jemalloc`) y homónimos de Ruby sin
  pista de propietario. Habría que validarlo con un cuarto conjunto nuevo.
- Que Codex use lo recuperado: una guía que pida citar cada etapa de `entities`
  y `call_outline`.

## Sexta ronda: correcciones pendientes, cuarto conjunto y coste real

### Diseño

Antes de cambiar código se congeló un cuarto conjunto (`test4/`, commit
`c049b65`): 16 tareas sobre **jq** y **Sinatra**, dos corpus nunca usados, más
una tarea de persistencia en Redis. Incluye por primera vez tareas `impact`,
`tests`, `bindings` y `persistence`. Desde esta ronda test3 cuenta como conjunto
de ajuste; sólo test4 es una medición limpia.

### Cambios

| Cambio | Desarrollo | test2 | test3 |
|---|---:|---:|---:|
| Punto de partida (quinta ronda) | 62,8 % | 66,6 % | 48,8 % |
| Dependencias incluidas no anclan el paquete | = | = | = (menos tokens) |
| El handler de un comando sobrevive al anclaje si no hay identificadores escritos | = | = | 55,5 % (HSET 0 → 7/7) |
| Tipos nombrados sólo con su mayúscula; propietario como desempate | 63,7 % | 70,3 % | 54,5 % |
| Completitud con identificadores enteros | 64,1 % | = | Lua pcall deja de declararse completo |
| `call_outline` con estado compartido (`S`) | 64,1 % | = | 55,3 % |

Se descartó conservar fuera del anclaje todos los símbolos obligatorios
(desarrollo −2,7 puntos). La clasificación de intenciones (formas flexionadas y
pasivas reflejas) no cambia la cobertura de flujos; se corrigió al ver que test4
clasificaba como flujo sus tareas de impacto y de registro, así que esa mejora
no está validada en un conjunto limpio.

### Cobertura en el cuarto conjunto

61,3 % antes y **61,4 %** después: las correcciones de recuperación **no
generalizan** a jq y Sinatra. Lo que sí cambia es la intención: las tareas de
impacto y de registro reciben su intención y paquetes más pequeños
(`process_route`: 1.589 → 1.002 tokens). Siguen sin resolverse Redis RDB (1/7,
ahora con falsa completitud), jq try/catch (1/8) y las pruebas de ficheros
estáticos de Sinatra (0/3).

### Coste real y juez semántico

`analyze_variants.py` usa los precios de lista comprobados el 2026-10-31:
Sonnet 5.5 a 2 $ de entrada, 0,10 $ de lectura de caché, 4 $ de escritura de
caché a una hora (la que usa Claude Code) y 10 $ de salida por millón;
gpt-5.6-luna a 0,20 $, 0,02 $ y 1,20 $. `judge_answers.py` pide a Claude Haiku
5.5 que decida qué hechos de la rúbrica afirma cada respuesta, por nombre o por
una descripción inequívoca.

Tercer conjunto, recalculado (45 sesiones por celda):

| Comparación | Coste USD | Calidad literal | Calidad juzgada |
|---|---:|---:|---:|
| Claude, B+C+D frente a sin Graphtyn | −20,5 % [−34,4; −8,0] | +1,3 pt | −0,1 pt [−1,9; +1,5] |
| Codex, B+C+D frente a sin Graphtyn | −20,8 % [−29,2; −12,8] | +1,9 pt | +0,3 pt [−3,2; +4,0] |

Con el juez, Codex pasa del 67–71 % literal al ~90 %: la rúbrica literal
penalizaba que describe las etapas sin nombrarlas. La distancia con Claude
(~99 %) baja de unos 25 puntos a unos 9.

### Sesiones en el cuarto conjunto

192 sesiones: Claude y Codex, sin Graphtyn, con la política actual y con la guía
`CITE_STAGES`, dos repeticiones por tarea.

| Cliente y variante | Coste USD | Tokens totales | Calidad juzgada | Herramientas |
|---|---:|---:|---:|---:|
| Claude, sin Graphtyn | 0,0926 | 145.149 | 97,9 % | 3,6 |
| Claude, actual | 0,0843 | 122.145 | 99,0 % | 2,5 |
| Claude, con `CITE_STAGES` | 0,0771 | 116.924 | 97,5 % | 2,8 |
| Codex, sin Graphtyn | 0,0097 | 132.378 | 92,5 % | 5,6 |
| Codex, actual | 0,0070 | 89.338 | 91,1 % | 3,5 |
| Codex, con `CITE_STAGES` | 0,0073 | 97.885 | 92,1 % | 3,8 |

| Comparación | Coste USD | Calidad juzgada |
|---|---:|---:|
| Claude, actual frente a sin Graphtyn | −9,0 % [−25,4; +7,6] | +1,0 pt [0,0; +3,1] |
| Codex, actual frente a sin Graphtyn | −27,6 % [−38,9; −15,3] | −1,4 pt [−5,2; +2,5] |
| Codex, `CITE_STAGES` frente a actual | +4,0 % [−9,1; +17,2] | +1,1 pt [−2,3; +4,3] |

- En corpus nuevos el ahorro se mantiene en Codex (−28 %) y en Claude es menor
  y no significativo (−9 %), sin pérdida de calidad en ninguno.
- **`CITE_STAGES` no se adopta:** no mejora la calidad de Codex de forma
  significativa y en Claude la baja 1,4 puntos. Queda como opción de la política.

### Pendiente

- Redis RDB y jq try/catch: el punto de entrada correcto no llega al paquete.
- Validar la clasificación de intenciones en un conjunto que no la haya motivado.
