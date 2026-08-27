# Estudio de mercado — 25 de agosto de 2026

Se separan capacidades verificadas en Graphtyn de afirmaciones de proveedores.
Los nombres se abrevian en la tabla; los enlaces apuntan a fuentes oficiales.

## Referencias

- **Gra…ify** publica análisis de 25 lenguajes, multimodalidad, comunidades Leiden,
  consulta, `update/watch`, MCP y exportaciones a Wiki, Obsidian, GraphML y Neo4j
  ([producto](https://graphify.net/),
  [skill](https://graphify.net/skills/graphify/),
  [CLI](https://graphify.net/graphify-cli-commands.html)).
- **Sou…aph** combina búsqueda global, definiciones/referencias y contexto
  multirrepositorio. Cody Enterprise sustituyó embeddings por Sourcegraph Search
  para simplificar escala y mantenimiento
  ([code graph](https://sourcegraph.com/docs/cody/core-concepts/code-graph),
  [contexto](https://sourcegraph.com/docs/cody/core-concepts/context),
  [FAQ](https://sourcegraph.com/docs/cody/faq)).
- **Aug…ent** afirma indexación viva entre repositorios, servicios e historial. Su
  cifra de ahorro es una evaluación del proveedor, no comparable directamente con
  nuestras corridas
  ([Context Engine](https://www.augmentcode.com/context-engine)).
- **Gre…ile** ofrece grafo de archivos, funciones y dependencias, revisión de PR,
  aprendizaje de comentarios, MCP y despliegue autónomo
  ([sitio oficial](https://www.greptile.com/)).
- **Gra…iti** se especializa en memoria temporal: episodios con procedencia,
  validez bitemporal, recuperación híbrida y varios backends
  ([repositorio](https://github.com/getzep/graphiti),
  [MCP](https://github.com/getzep/graphiti/blob/main/mcp_server/README.md)).

## Posición actual

| Capacidad | Graphtyn | Referencia |
|---|---|---|
| AST, llamadas, impacto y archivo:línea | implementado/local | Gra…ify, Sou…aph |
| Contexto compacto con presupuesto | implementado | Gra…ify, Aug…ent |
| Memoria compartida atribuida | implementado | Gra…iti |
| Grafos visuales de código y memoria | implementado | Gra…ify |
| Git/PR, correcciones y procedencia | alcance local | Gre…ile automatiza más PR |
| Incremental y embeddings por hash | implementado | esperado en el segmento |
| Bitemporalidad completa | pendiente | Gra…iti |
| Multi-repo empresarial, RBAC y SSO | pendiente | Sou…aph |
| Agentes autónomos de revisión | pendiente | Gre…ile |
| Exportadores y ecosistema | parcial | Gra…ify |

## Veredicto

Sí hubo un salto importante: Graphtyn pasó de visualizador AST a combinar evidencia
estructural local, contexto presupuestado, impacto Git y memoria semántica
compartida con atribución entre agentes. Es una alternativa diferenciada para
privacidad, interoperabilidad MCP y control de contexto.

No hay evidencia suficiente para afirmar superioridad global. Faltan completar las
108 celdas, evaluación independiente, bitemporalidad, escala empresarial/RBAC y
mayor automatización de PR. La afirmación defendible es: **diferenciación técnica
fuerte con validación competitiva todavía parcial**.

Las cifras externas son `VENDOR`; las mediciones propias están en
[`BENCHMARKS.md`](BENCHMARKS.md).
