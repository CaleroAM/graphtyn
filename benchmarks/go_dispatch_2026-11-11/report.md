# Despacho a implementaciones en Go: validación sobre afero

Fecha: 2026-11-11. Corpus nuevo con muchas interfaces: `spf13/afero` en `d2bffea`. Dos tareas de
impacto, congeladas en `8dedd8e` antes de ejecutar:
- `Fs.OpenFile`: 14 implementaciones, por encima del tope de 8, así que el despacho queda resumido.
- `Lstater.LstatIfPossible`: 6 implementaciones.

Hay 17 hechos en total. Todas las sesiones son de Codex con `gpt-5.6-luna`, MCP lean y regla de
parada `targeted`. Calificación por mayoría de tres jueces; kappa 0,85.

**Veredicto: NEGATIVE para `main` en tareas independientes.** `main` (`56fc73b`) acertó 12 de 17 hechos
frente a 16 de 17 de v0.12.0, que no tiene despacho. Tras corregir las dos causas en #59, la rama
acierta 17 de 17 con un 40 % menos de tokens que v0.12.0. Esas dos tareas ya no son independientes.

| Versión | `OpenFile` | `LstatIfPossible` | Total | Tokens |
|---|---|---|---|---|
| v0.12.0 (`e81721a`) | 9/9 (76.834) | 7/8 (28.133) | 16/17 | 104.967 |
| `main` (`56fc73b`) | 6/9 (31.945) | 6/8 (29.512) | 12/17 | 61.457 |
| #59, primera versión | 9/9 (33.085) | 6/8 (29.683) | 15/17 | 62.768 |
| #59, con el recuento corregido | — | 8/8 (29.649) | 17/17 | 62.734 |

## Qué falló en `main`

El grafo es correcto: encuentra las 14 implementaciones de `Fs` y las 6 de `Lstater` por conjunto de
métodos, con sus aristas `implementa` y de override. El fallo estaba en el paquete:

1. **Homónimos sin dueño.** El paquete mostraba unas implementaciones y mandaba el resto a
   `omitted_homonyms` como `archivo:línea`. Codex citó `os.go:64` y `memmap.go:262` como
   «definiciones homónimas» sin decir que eran `OsFs` y `MemMapFs`, y los jueces no pudieron dar esos
   hechos por buenos.
2. **Recuento parcial.** `coverage.implementations` contaba solo las seleccionadas. Codex respondió
   «el grafo registra 4 implementaciones» cuando eran 6, y omitió `OsFs` y `ReadOnlyFs`.

v0.12.0, sin despacho, no daba lista de implementaciones. Codex buscó por su cuenta, gastó más
tokens en `OpenFile` (76.834) y acertó más. Es el mismo patrón que en las validaciones anteriores: un
paquete que parece completo y omite consumidores lleva al cliente a dejar de buscar.

## Comprobación sin cliente

Rúbrica presente en el paquete:

| Versión | `OpenFile` | `LstatIfPossible` |
|---|---|---|
| v0.12.0 | 6/9 | 7/8 |
| `main` | 9/9 | 6/8 |
| #59 | 9/9 | 8/8 |

La comprobación de `main` daba 9/9 en `OpenFile`, pero los nombres aparecían fuera de los
consumidores y de las implementaciones. No detectó el fallo.

## Límites

- **Muestra:** dos tareas, una repetición y un solo cliente.
- **Evidencia no independiente:** el resultado de #59 se midió con las mismas tareas que destaparon
  sus fallos.
