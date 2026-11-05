# Clasificación de intención, `impact` y explicación de símbolos

Fecha: 2026-11-04. Cliente: Antigravity CLI (`gemini-3.8-flash-high`), regla de
parada `targeted`. 122 sesiones reales, todas completas, 8.933.034 tokens.

**Veredicto: MIXED, favorable.** En los conjuntos 2 y 3, la calidad no baja y el
gasto cae. En el conjunto 4, el gasto baja un 54 % y la calidad pasa de 51/54 a
48/54, casi todo por `V4_RAILS_RELOAD_IMPACT`. Sólo se midió en un cliente, con n=2.

## Resultado

Promedios por sesión. «Anterior» es `3de6e0e`, la rama sin estas correcciones.

| Conjunto | Versión | Rúbrica | Tokens | Con caché | Herramientas |
|---|---|---:|---:|---:|---:|
| 2 (6 tareas, impact y explicación) | anterior | 67/78 | 105.688 | 126.729 | 8,8 |
| 2 | `95e53ff` | 68/78 | 43.556 | 43.556 | 2,9 |
| 3 (4 tareas, sólo explicación) | anterior | 52/66 | 85.461 | 99.864 | 6,6 |
| 3 | `4c14669` | 58/66 | 59.878 | 60.576 | 4,0 |
| 4 (4 tareas, punta previa del PR) | `f6544c3` | 51/54 | 109.134 | 213.092 | 11,1 |
| 4 | `3ff1c90` y `7b11c85` | 48/54 | 50.226 | 50.226 | 3,3 |

Con n=2 por tarea, la diferencia del conjunto 2 es un empate en calidad. La del
conjunto 3 viene sobre todo de una tarea (`scanGenericCommand`, 9→13/16). En el
conjunto 4, la fila final combina `7b11c85` en las dos tareas de `impact` con
`3ff1c90` en las otras dos, que no se repitieron.

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
4. **Cuarta corrección, conjunto 4 (16 sesiones) y repetición de cinco tareas (10).**
   Cuatro causas: el nombre `within_new_transaction` activaba obligaciones por
   contener «transaction»; una lista larga se declaraba incompleta y mandaba a usar
   `grep`; `write_exponent<Char>(...)` se registraba como llamada a `Char`; y palabras
   cortas de la pregunta elegían líneas por subcadena.
5. **Dos repeticiones más (8 + 8 sesiones).** Quitar el duplicado de texto de una
   llamada ya resuelta empeoró fmt: `write_exponent` pasó de 2 a 6-7 herramientas,
   porque el único llamador visible era `format.h`. Ahora esas llamadas se listan con
   la función que las hace, y las dos tareas de fmt vuelven a 2-3 herramientas.

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

### Tareas repetidas tras la cuarta corrección

Ya las había visto, así que muestran si el problema se corrigió, no cuánto
generaliza la corrección.

| Tarea | Versión | Punta previa | Última medición | Tokens punta previa → última |
|---|---|---:|---:|---:|
| `V3_RAILS_WITHIN_TX_WHAT` | `3ff1c90` | 16/18 | 18/18 | 96.102 → 43.296 |
| `RAILS_TOUCH_IMPACT` | `7b11c85` | 12/12 | 12/12 | 165.717 → 59.886 |
| `V2_REDIS_POOL_WHAT` | `3ff1c90` | 11/16 | 16/16 | 44.517 → 47.713 |
| `REDIS_ACTIVE_EXPIRE_WHAT` | `3ff1c90` | 13/16 | 16/16 | 46.825 → 48.956 |
| `FMT_WRITE_PADDED_IMPACT` | `7b11c85` | 12/12 | 12/12 | 45.855 → 46.158 |

### Conjunto 4, por tarea

| Tarea | Versión | `f6544c3` | Última medición | Tokens |
|---|---|---:|---:|---:|
| `V4_RAILS_COMMIT_TX_WHAT` | `3ff1c90` | 14/14 | 14/14 | 114.632 → 38.596 |
| `V4_RAILS_RELOAD_IMPACT` | `7b11c85` | 15/16 | 12/16 | 181.266 → 65.652 |
| `V4_FMT_EXPONENT_CALLERS` | `7b11c85` | 8/8 | 8/8 | 28.916 → 27.854 |
| `V4_REDIS_MIGRATE_RETRY` | `3ff1c90` | 14/16 | 14/16 | 111.724 → 68.800 |

## Lo que sigue sin estar bien

- **`V4_RAILS_RELOAD_IMPACT` pierde calidad:** 15/16 → 12/16 con un 64 % menos de
  tokens. `reload` tiene unas 690 menciones y la mayoría de archivos quedan como un
  total: 209 ni siquiera aparecen en el resumen por archivo. Antes el agente hacía
  25-27 lecturas y encontraba más; ahora para antes. Es el coste de no mandarlo a
  buscar, y con un nombre tan común puede no compensar.
- **El grafo atribuye muchas llamadas al archivo:** 3.233 de 5.583 en fmt, porque
  `ast_parser.py` se rinde si quien llama tiene sobrecargas. Elegir la sobrecarga por
  rango de líneas lo baja a 271, pero la cobertura de `flow` cae del 69,3 % al 65,9 %
  y `FMT_DYNAMIC_WIDTH_FLOW` de 6/8 a 3/8. Se revirtió: `impact` lo resuelve al listar,
  y el arreglo de fondo necesita medir `flow` con agentes. En Rails son 49.739 de
  93.183; no se investigó cuántas tienen esta causa.
- **Las obligaciones siguen siendo específicas de Rails:** dejar de activarlas por un
  nombre quita el falso positivo, pero «transacción» en prosa sigue exigiendo evidencia
  de `save`, aunque se pregunte por otro código.
- **La guía de nombrar constantes y funciones favorece a esta rúbrica,** que busca
  esos nombres literalmente. Parte de la mejora de `V2_REDIS_POOL_WHAT` (11→16/16) y
  `REDIS_ACTIVE_EXPIRE_WHAT` puede venir de ahí, no de respuestas mejores.

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
- Tras medir `4c14669`, la puerta de cobertura de CI detectó que empezar todos los
  extractos en el comentario de la declaración perdía hechos en Flask: las líneas
  previas traían una función vecina relevante. Ese cambio quedó limitado a las
  preguntas de cuerpo entero, las únicas donde se midió. La misma puerta detectó que
  una explicación de varias partes pasaba a `precision` y se declaraba completa con
  3/8 hechos, así que `precision` por «explica…» también quedó limitado a esas
  preguntas. Con estos ajustes, los paquetes de las tareas medidas conservan los
  mismos hechos (106/111), pero no se repitieron sesiones con agentes.
- El conjunto 4 no es del todo a ciegas: ajusté cuándo se usa `precision` tras ver
  que el paquete de `V4_REDIS_MIGRATE_RETRY` cubría 2/8, sin sesiones con agentes.
- Las tareas de explicación y las de los conjuntos 2 y 3 no se repitieron con
  `78a52f3` ni `7b11c85`, que cambian cómo se listan los consumidores.
- La versión final se midió con la instalación editable de la rama, ejecutada a
  través de `--graphtyn-executable`; la anterior, desde un worktree en `3de6e0e`.

## Reproducir

```bash
python benchmarks/intent_impact_2026-11-04/analyze_results.py --run-root <directorio de ejecuciones>
```

`grades_by_run.json` y `results.json` guardan las calificaciones. Las sesiones
crudas no están en el repositorio porque incluyen copias de los corpus.
