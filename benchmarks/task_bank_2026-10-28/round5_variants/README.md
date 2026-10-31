# Variantes de la quinta ronda

Cobertura del paquete (`coverage.py`) por variante y conjunto, en
`<variante>_<conjunto>.jsonl`:

| Variante | Qué cambia |
|---|---|
| `base` | Política anterior a la ronda |
| `A` | `FLOW_NODE_CAP=14` y presupuesto de 18 entidades |
| `B` | `CHAIN_SHARE=0.5`, `CHAIN_SEEDS=1`: mitad del presupuesto para la cadena de llamadas |
| `C` | `OUTLINE_LIMIT=12`: esquema `call_outline` |
| `D` | `COMMAND_NAMES`: `BLPOP` → `blpopCommand` |
| `E` | Anclaje sin código de terceros y con los obligatorios conservados (descartada; ya no está en el código) |
| Combinaciones | `BC`, `BD`, `CD`, `BCD`, `AD`, `ABD`, `BCDE` |

`chain_grid_dev.txt` es la búsqueda de parámetros de B en desarrollo y
`agent_paired_test3.txt` las diferencias emparejadas por tarea de las sesiones
con agentes (intervalo bootstrap del 95 %).

Las sesiones se lanzaron con ejecutables que fijaban cada política. Ese
mecanismo está ahora en `../run_variants.py`, que genera los ejecutables a partir
de `GRAPHTYN_FLOW_POLICY` y no contiene rutas de ninguna máquina. Por ejemplo, la
política anterior a la ronda es
`CHAIN_SHARE=0,CHAIN_SEEDS=2,COMMAND_NAMES=0,OUTLINE_LIMIT=0`, y la variante A
usaba además un presupuesto de 18 entidades. La cobertura de cualquier variante
se mide con `../coverage.py --policy`.
