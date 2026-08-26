# Regresión híbrida v2 sobre go-chi

Mismo repositorio, revisión, cuatro prompts, ground truth y modelo
`opencode/x-preview-f-free` que la corrida base. Solo se repitió Graphtyn después
de añadir recuperación dirigida de cuerpos; los controles permanecen inmutables.

| Versión | Calidad | Tokens/tarea | Tiempo/tarea | Consultas/tarea |
|---|---:|---:|---:|---:|
| Graphtyn compacto anterior | 72.92% | 10,515 | 95.82 s | 1.25 |
| Graphtyn híbrido v2 | **85.42%** | **8,624** | **71.50 s** | 1.25 |
| OpenCode puro (control anterior) | 95.84% | 16,491 | 145.30 s | 10.25 |

V2 ganó 12.50 puntos de calidad y, en esta repetición, redujo 17.98% de tokens y
25.38% de tiempo frente a Graphtyn compacto. Frente a lectura directa quedó a
10.42 puntos, usando 47.70% menos tokens y 50.79% menos tiempo. No hubo errores
factuales, fallos ni reintentos.

Resultados: ciclo de `Mux.ServeHTTP` 100%, middleware 58.33%, seguridad de
contexto 83.33% y fallos 100%. La auditoría del resultado de middleware descubrió
que `Middlewares.Handler` podía confundirse con otro método `Handler`; después de
esta corrida se corrigió la resolución del receptor Go y se verificó que los tres
fragmentos elegidos fueran `chain.go:Handler`, `chain.go:chain` y
`chain.go:ChainHandler.ServeHTTP`. Esa corrección posterior tiene regresión local,
pero no se atribuye una nueva puntuación remota sin otra corrida completa.

Una repetición por tarea sigue siendo insuficiente para significancia estadística.
