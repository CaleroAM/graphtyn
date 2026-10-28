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
