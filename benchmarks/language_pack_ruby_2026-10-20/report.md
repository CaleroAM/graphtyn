# Benchmark local del paquete Ruby

Se ejecutó `language-pack-ruby-v1` con 30 repeticiones y una ejecución de
calentamiento. Es una prueba local del parser y del grafo: no llamó agentes,
modelos, red ni servicios externos y no mide tokens.

| Cobertura | Mediana | p95 |
|---:|---:|---:|
| 12/12 hechos (100 %) | 0,398 ms | 0,488 ms |

Los hechos cubren análisis sin error, `require`, módulos, clases, herencia,
mixins, métodos de instancia y singleton, llamadas y las relaciones `hereda`,
`incluye` y `llama` en el grafo ensamblado. La prueba procesó tres archivos con
el paquete `ruby` y `tree-sitter-ruby` 0.23.1.

Los 30 tiempos crudos, versiones y hechos individuales están en
[`result.json`](result.json). Esta fixture comprueba el contrato estructural;
no demuestra por sí sola cobertura completa de metaprogramación o DSL de Rails,
ni reducción de tokens en una sesión de agente.
