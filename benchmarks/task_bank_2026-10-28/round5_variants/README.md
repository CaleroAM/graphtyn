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

`graphtyn-A`, `graphtyn-BCD` y `graphtyn-previous` son los ejecutables de cada
variante para el harness; `run_agents.sh`, `run_agent_repetitions.sh` y
`retry_agent_sessions.py` lanzaron las 300 sesiones. Contienen rutas absolutas
de la máquina donde se ejecutaron.
