# Validación de memoria temática

Se verificó el almacén que usa el dashboard: `/home/calero/.graphtyn/TourMuseosPuebla-4c86bddd50/memory-v2.db`. Antes de la migración se creó un respaldo SQLite en `/tmp/TourMuseosPuebla-before-topics.db`; `PRAGMA integrity_check` devolvió `ok`.

La validación reprocesó tres fuentes autorizadas de TourMuseosPuebla: dos historiales AGY y un historial Codex. El lector recorrió 62.597 registros, conservó 3.360 mensajes, excluyó 59.237 registros técnicos, no tuvo errores de parseo y usó como máximo unos 60 MiB de RSS. La extracción se ejecutó en modo `deterministic-limited`; la cobertura pendiente queda visible en el dashboard y no se interpreta como calidad de recuperación.

La muestra real contiene asuntos sobre texturas, botones y generación de APK. En tres casos de referencia con mensajes fuente conocidos, la recuperación temática tuvo recall 3/3 y atribución 3/3. Las latencias de búsqueda fueron 78–85 ms; los contextos completos midieron 1.610–1.749 tokens y las ventanas 2.783–3.000 tokens. Es una muestra positiva pequeña, no una medición exhaustiva de precisión o recall.

Pasaron 286 pruebas unitarias y de integración de memoria, historiales, CLI, MCP y dashboard; 2 pruebas opcionales quedaron omitidas. La prueba de navegador con Chromium verificó títulos, expansión de episodios, panel de conversación, filtro de estado y reintento tras error recuperable. El dashboard conserva el estado de procesamiento, pendientes y exclusiones; el modelo local es opt-in y la API externa no se activa como fallback.

Limitaciones conocidas: la extracción determinista conserva episodios con contexto limitado; la similitud léxica/embeddings propone asociaciones, pero no fusiona asuntos automáticamente. La precisión completa requiere un conjunto etiquetado mayor y pruebas de navegador en el entorno de despliegue final.

## Identidad de elementos y asuntos relacionados

La migración de entidades conserva los temas y episodios existentes y añade
`entities`, `topic_entities`, `topic_work_terms` y `topic_relations`. En la
captura nueva, un asunto sólo continúa otro cuando comparte una entidad
concreta y una acción o término de trabajo estable; una señal conversacional
como “ahora” puede continuar el mismo elemento con nueva evidencia. Compartir
la categoría `button` no fusiona controles distintos.

La extracción reconoce nombres como `botón de Jugar`, `botón de Fichas`,
`botón de Ajustes` y `botón de Volver`, además de funcionalidades, módulos,
reportes, pantallas, plataformas, identificadores numéricos, referencias de
archivo y símbolos Python (`función calcular_reporte`, `clase ReportService` o
`método listar_operadores`). Los vínculos se etiquetan `mismo elemento`, `mismo
símbolo`, `mismo concepto`, `mismo tipo`, `misma plataforma` o `tema de diseño` y conservan confianza y
procedencia.

En el almacén efectivo de TourMuseosPuebla se enriquecieron 372 episodios sin
borrar memorias. El grafo resultante contiene 32 entidades y 633 relaciones
explícitas antes de limitar la vista; la respuesta acotada del dashboard queda
en 2.574 enlaces simplificados y 3.419 detallados, con 829 sugerencias
léxicas marcadas como ambiguas.
