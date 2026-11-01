# Benchmark local de paquetes C/C++

Se ejecutó `language-packs-c-cpp-v1` con 30 repeticiones por lenguaje y una
ejecución de calentamiento. Es una medición local del parser: no llamó agentes,
modelos, red ni servicios externos y no mide tokens.

| Lenguaje | Hechos cubiertos | Mediana | p95 |
|---|---:|---:|---:|
| C | 6/6 | 0.165 ms | 0.232 ms |
| C++ | 7/7 | 0.240 ms | 0.368 ms |

La cobertura agregada fue 13/13 hechos (100 %).

El grafo final procesó los dos archivos con los paquetes `c` y `cpp`, produjo
dos aristas de llamada y verificó la herencia `Service → Base`. El resultado
completo, incluidos los 30 tiempos crudos de cada brazo y las versiones de las
gramáticas, está en [result.json](result.json).

Una regresión adicional verifica que `.h` permanezca C para un encabezado C y
seleccione C++ al encontrar `namespace` y `template`; esto cubre bibliotecas C++
que conservan la extensión histórica `.h`.

Este resultado comprueba la cobertura de las construcciones incluidas en las
fixtures pequeñas. No demuestra la cobertura de macros o plantillas complejas,
ni implica por sí mismo una reducción del consumo total de tokens de un agente.
