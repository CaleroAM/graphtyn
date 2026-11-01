# Segundo conjunto no visto y regla de parada dirigida — 27 oct 2026

## Qué se midió

Tras el resultado negativo del primer conjunto no visto
(`../heldout_tasks_2026-10-27/report.md`) se aplicaron estos cambios (`ef8d71d`):

- **Regla de parada dirigida.** Con `do_not_expand=true`, el agente responde sin
  releer la evidencia, pero consulta la parte de la petición que no cubra.
- **Llamadas Ruby sin paréntesis.** Se registran como llamadas.
- **Intención.** «registro» ya no activa `bindings`.
- **Ruido en la recuperación.** Se filtran tipos en prosa, tests, código
  vendorizado y homónimos de otros paquetes.

Se midieron dos cosas:

1. **Conjunto v2.** Seis tareas nuevas, congeladas en `87abad6` antes de
   ejecutar y no usadas para ajustar nada: evicción de Redis, límite del búfer de
   salida, coma flotante y `format_to_n` en fmt, `update` y `find` en Rails.
2. **Conjunto 1 repetido.** Las seis tareas del primer conjunto, con la regla
   dirigida, para ver su efecto donde la estricta fallaba.

| Cliente | Modelo | Brazos | Repeticiones (v2) |
|---|---|---|---:|
| Claude Code | `claude-sonnet-5-5` | MCP lean, hook | 3 |
| Codex | `gpt-5.6-luna` | sin grafo, MCP lean, hook | 2 |
| OpenCode | `opencode/deepseek-v4.1-flash-free` | MCP lean, hook | 2 |

- **Sesiones:** 114, de las que 100 terminaron.
- **Fallos de Claude:** la cuota de la cuenta se agotó a mitad de la ejecución.
  Esas sesiones se repitieron tras restablecerse y se conservan en
  `failed_attempts/`.
- **Fallos de OpenCode:** 14 sesiones fallaron por el proveedor del modelo
  gratuito. En la ronda original fue su filtro de contenido
  (`ContentFilterError`); en la repetición, un timeout de 600 s sin ningún
  evento. Faltan sus celdas de `find`, `update` con hook y límite de búfer.

## Cobertura del paquete en v2, sin agentes

| Tarea | Hechos de la rúbrica en el paquete | `do_not_expand` |
|---|---:|---|
| Redis evicción | 0/8 | true |
| Redis límite de búfer | 0/8 | true |
| fmt coma flotante | 0/7 | true |
| fmt `format_to_n` | 1/8 | true |
| Rails `update` | 1/8 | false |
| Rails `find` | 5/9 | false |

La recuperación no generaliza. En la evicción, por ejemplo, encuentra los campos
`maxmemory` y `lru` de una struct y funciones de RDB. No relaciona «evicción»
con `evict` (`performEvictions` queda fuera), y el vocabulario de operaciones de
`flow` (`save`, `send`, `publish`…) está sesgado hacia aplicaciones web. Cuatro
paquetes casi vacíos se declaran completos.

## Sesiones en v2

Tokens medios y rúbrica literal por repetición:

| Tarea | Claude lean | Claude hook | Codex sin grafo | Codex lean | Codex hook | OpenCode lean | OpenCode hook |
|---|---|---|---|---|---|---|---|
| Redis evicción | 280k · 7,7,7 | 212k · 7,7,7 | 186k · 5,5 | 237k · 4,3 | 175k · 4,4 | 228k · 6,6 | 285k · 7,7 |
| Redis búfer | 176k · 8,8,8 | 160k · 8,8,8 | 302k · 4,5 | 159k · 0,4 | 220k · 3,2 | — | — |
| fmt flotante (/7) | 207k · 7,7,7 | 157k · 7,7,7 | 225k · 4,2 | 225k · 5,2 | 194k · 3,4 | 558k · 7,7 | 151k · 7 |
| fmt `format_to_n` | 150k · 8,8,8 | 113k · 8,8,8 | 123k · 6,7 | 86k · 6,7 | 61k · 5,6 | 93k · 7 | 137k · 8 |
| Rails `update` | 211k · 8,8,8 | 183k · 8,8,8 | 245k · 6,7 | 180k · 6,7 | 106k · 6,7 | 437k · 8 | — |
| Rails `find` (/9) | 211k · 9,9,9 | 132k · 9,9,9 | 156k · 6,6 | 233k · 5,6 | 101k · 5,4 | — | — |

Agregados en v2:

| Cliente y brazo | n | Tokens medios | Rúbrica media |
|---|---:|---:|---:|
| Claude, MCP lean | 18 | 205.866 | 97,9 % |
| Claude, hook | 18 | 159.641 | 97,9 % |
| Codex, sin grafo | 12 | 206.051 | 65,1 % |
| Codex, MCP lean | 12 | 186.573 | 57,1 % |
| Codex, hook | 12 | 142.808 | 55,2 % |
| OpenCode, MCP lean | 6 | 350.217 | 89,6 % |
| OpenCode, hook | 4 | 214.393 | 93,8 % |

## Conjunto 1: regla estricta frente a dirigida

| Cliente y brazo | Estricta: tokens · rúbrica | Dirigida: tokens · rúbrica |
|---|---|---|
| Claude, hook | 102k · 85,4 % (n=12) | 194k · 97,9 % (n=6) |
| Codex, MCP lean | 80k · 63,4 % | 164k · 78,6 % |
| Codex, hook | 27k · 63,4 % | 117k · 79,2 % |
| Codex, sin grafo (referencia) | 206k · 85,4 % | — |

## Conclusiones

1. **La regla dirigida recupera calidad, pero no el ahorro.**
   - Con paquetes incompletos, los agentes ahora buscan lo que falta. Claude con
     hook pasa del 85 % al 98 % y Codex del 63 % al 79 %.
   - El precio es que el gasto sube: de ~100k a ~190k tokens en Claude y de 27k
     a 117k en Codex.
   - Es el comportamiento correcto: el ahorro anterior venía, en parte, de
     responder menos.
2. **En tareas nuevas el ahorro es modesto y depende del cliente.**
   - **Claude:** misma calidad (98 %) con y sin hook; el hook gasta un 22 %
     menos que el MCP lean. Las sesiones de 33k de las tareas originales no se
     repiten, porque el agente tiene que buscar.
   - **Codex:** Graphtyn gasta un 9 % (lean) y un 31 % (hook) menos que sin
     grafo, pero con peor rúbrica (57 % y 55 % frente a 65 %). Codex responde con
     paquetes casi vacíos; en el límite de búfer, una sesión lean sacó 0/8.
3. **El cuello de botella es la recuperación.**
   - **Detector léxico descartado:** sobre las tareas de desarrollo no
     discriminaba de forma estable.
   - **Cambios de recuperación de `ef8d71d`:** mejoran el grafo (la cadena
     `destroy` de Rails), pero no la cobertura de los paquetes.
   - **Lo que hace falta:**
     - vocabulario de programación entre idiomas (`evicción`→`evict`);
     - un vocabulario de operaciones de `flow` que no esté sesgado hacia
       aplicaciones web;
     - una comprobación que no declare completo un paquete sin evidencia de
       las partes pedidas.
   - **Cómo iterar sin sobreajustar:** con la cobertura del paquete (sin
     agentes, barata) sobre un banco amplio de tareas dividido en desarrollo y
     prueba. Este conjunto v2 ya se ha mirado.

## Limitaciones

- **Repeticiones:** n=3 en Claude y n=2 en Codex y OpenCode, con celdas de
  OpenCode incompletas.
- **Sin grafo:** sólo hay referencia contemporánea con Codex. En v2 no hay
  brazo sin grafo para Claude.
- **Rúbrica:** es literal y no hubo adjudicación ciega.
- **Eventos crudos:**
  `/home/calero/Documentos/docker/graphtyn-benchmark-runs-heldout-v2-2026-10-27/`.
