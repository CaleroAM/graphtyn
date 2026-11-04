# Clasificación de intención, `impact` y explicación de símbolos

Fecha: 2026-11-04. Cliente: Antigravity CLI (`gemini-3.8-flash-high`), regla de
parada `targeted`. 80 sesiones reales, todas completas, 5.938.989 tokens.

**Veredicto: MIXED, favorable.** En los dos conjuntos que aún no había visto al
medirlos, la calidad no baja y el gasto cae. Quedan una tarea que no se recupera
y dos que cuestan más; sólo se midió en un cliente, con n=2.

## Resultado

Promedios por sesión. «Anterior» es `3de6e0e`, la rama sin estas correcciones.

| Conjunto | Versión | Rúbrica | Tokens | Con caché | Herramientas |
|---|---|---:|---:|---:|---:|
| 2 (6 tareas, impact y explicación) | anterior | 67/78 | 105.688 | 126.729 | 8,8 |
| 2 | `95e53ff` | 68/78 | 43.556 | 43.556 | 2,9 |
| 3 (4 tareas, sólo explicación) | anterior | 52/66 | 85.461 | 99.864 | 6,6 |
| 3 | `4c14669` | 58/66 | 59.878 | 60.576 | 4,0 |

Con n=2 por tarea, la diferencia del conjunto 2 es un empate en calidad. La del
conjunto 3 viene sobre todo de una tarea (`scanGenericCommand`, 9→13/16).

«Con caché» suma los tokens de entrada servidos desde caché, que Antigravity
informa aparte. Los aciertos de caché varían entre sesiones, así que se dan las
dos cifras.

## Qué pasó, en orden

Cada corrección se validó con tareas congeladas antes de escribirla, porque
corregir mirando las mismas tareas sesga el resultado.

1. **Primera corrección, conjunto 1 (24 sesiones): más barata pero peor.** Enviar
   las preguntas de consumidores a `impact` bajó el gasto de 98.009 a 58.412
   tokens, y la calidad de 65/78 a 55/78. El índice no capta llamadas con plantilla
   como `write_padded<Char>(...)`, las sobrecargas omitidas no se informaban y
   `compact` no traía el cuerpo de la función, pero el paquete declaraba que
   bastaba.
2. **Segunda corrección, conjunto 2 (24 sesiones) y repetición del 1 (12).** Empata
   en calidad con un 59 % menos de tokens. El conjunto 1 sube a 69/78, ya no a
   ciegas. Pero la media ocultaba una regresión: `REDIS_ACTIVE_EXPIRE_WHAT` pasó de
   15/16 a 8/16.
3. **Tercera corrección, conjunto 3 (16 sesiones) y repetición de dos tareas (4).**
   Para «¿Qué hace X?», las líneas del extracto se elegían con las palabras de la
   pregunta: `con` coincidía con `config_`, quedaban 69 de 233 líneas y el paquete
   declaraba `complete: true`. Ahora esas preguntas reciben el cuerpo entero y los
   llamadores, y un cuerpo que no cabe se informa en `missing`.

## Por tarea

Hechos de la rúbrica sumando las dos repeticiones, y tokens medios.

| Tarea | Anterior | Final | Tokens anterior → final |
|---|---:|---:|---:|
| `V2_REDIS_ASYNC_DELETE_CALLERS` | 12/12 | 12/12 | 167.540 → 46.857 |
| `V2_REDIS_POOL_WHAT` | 14/16 | 12/16 | 79.668 → 44.505 |
| `V2_FMT_WRITE_BYTES_IMPACT` | 11/12 | 12/12 | 89.171 → 31.409 |
| `V2_FMT_SPECS_WHAT` | 4/12 | 6/12 | 42.938 → 53.915 |
| `V2_RAILS_UPDATE_RECORD_CALLERS` | 12/12 | 12/12 | 160.341 → 41.737 |
| `V2_RAILS_TX_STATUS_WHAT` | 14/14 | 14/14 | 94.471 → 42.912 |
| `V3_REDIS_SCAN_WHAT` | 9/16 | 13/16 | 115.769 → 50.381 |
| `V3_REDIS_FREE_CLIENT_WHAT` | 14/16 | 15/16 | 91.872 → 47.845 |
| `V3_FMT_PARSE_SPECS_WHAT` | 13/16 | 14/16 | 67.245 → 45.188 |
| `V3_RAILS_WITHIN_TX_WHAT` | 16/18 | 16/18 | 66.958 → 96.102 |

Las filas V2 son de `95e53ff`, las V3 de `4c14669`. Al repetir con `4c14669`:

| Tarea | Anterior | `95e53ff` | `4c14669` |
|---|---:|---:|---:|
| `REDIS_ACTIVE_EXPIRE_WHAT` | 15/16 | 8/16 | 13/16 |
| `V2_REDIS_POOL_WHAT` | 14/16 | 12/16 | 11/16 |

## Lo que sigue sin estar bien

- **`V2_REDIS_POOL_WHAT` no se recupera:** 11/16 frente a 14/16. El paquete
  contiene los hechos que faltan (`EVPOOL_SIZE`, `memmove`); el agente responde sin
  mencionarlos. Es más barato que antes (44.517 frente a 79.668 tokens), pero
  también menos detallado.
- **`V3_RAILS_WITHIN_TX_WHAT` cuesta un 44 % más.** La palabra «transaction» exige
  obligaciones (`transaction_entry`, `transaction_rollback`) que este método no
  cumple, así que el paquete dice que falta evidencia y el agente sigue buscando.
  No se corrigió.
- **`RAILS_TOUCH_IMPACT` cuesta un 44 % más** (115.748 → 165.717 tokens) y gana un
  hecho por sesión. Tiene 167 consumidores y el agente sigue el aviso de que la
  lista no está completa. Este coste es esperable, pero es un coste.
- **La causa de las llamadas con plantilla sigue en el parser.** La búsqueda de
  texto la cubre como pista sin verificar; no resuelve el enlace en el grafo.
- **El foco por palabras sigue igual en las preguntas concretas.** La coincidencia
  de `con` con `config_` también puede ocurrir allí; cambiarla afectaría a
  recuperaciones ya medidas y merece su propia medición.

## Clasificación

53 de 53 en `classification_heldout.json`, frente a 52 de 53 en la primera
evaluación. Yo escribí tanto esas etiquetas como los marcadores, y corregí el
fallo tras verlo, así que esto es una prueba de regresión, no una medida de
generalización. De los 428 prompts de benchmarks previos, sólo 2 cambian de
intención: «Assess repository contract change.» y «Assess model field change.»,
ambos a `impact`, que es lo que su protocolo esperaba.

Portugués, francés, alemán e italiano están cubiertos por pruebas de clasificación.
**Ninguna sesión con agente se hizo en esos idiomas.**

## Límites de la medición

- Un solo cliente y modelo; Claude, Codex y OpenCode no se midieron aquí.
- n=2 por tarea y versión: sirve para ver diferencias grandes, no pequeñas.
- La rúbrica es literal por subcadenas y la escribí yo, leyendo el código antes de
  implementar. Una respuesta que dice «ciclo lento» sin citar
  `ACTIVE_EXPIRE_CYCLE_SLOW` no suma, y un número de línea puede coincidir por azar.
- `rm_unlink` del conjunto 2 se corrigió antes de implementar: decía `RM_DeleteKey`
  y el llamador real es `RM_UnlinkKey`.
- `V3_FMT_PARSE_SPECS_WHAT` pregunta por la misma función que `V2_FMT_SPECS_WHAT`,
  por descuido mío: sólo 3 de las 4 tareas del conjunto 3 son inéditas.
- `4c14669` sólo se midió con el conjunto 3 y las dos repeticiones. Las demás tareas
  de explicación de los conjuntos 1 y 2 no se repitieron con esa versión.
- La versión final se midió con la instalación editable de la rama, ejecutada a
  través de `--graphtyn-executable`; la anterior, desde un worktree en `3de6e0e`.

## Reproducir

```bash
python benchmarks/intent_impact_2026-11-04/analyze_results.py --run-root <directorio de ejecuciones>
```

`grades_by_run.json` y `results.json` guardan las calificaciones. Las sesiones
crudas no están en el repositorio porque incluyen copias de los corpus.
