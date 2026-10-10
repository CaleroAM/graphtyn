# Validación de `0.10.5`

Fecha: 2026-10-10. Esta versión incorpora la evaluación de proyectos reales,
el perfil mixto de RF07 y las correcciones de puntuación y evidencia de la
memoria compartida.

## Validación local

- Suite completa en Linux: **545 pruebas pasaron y 3 se omitieron**.
- Comprobación de mantenibilidad: **29 hotspots heredados sin crecimiento**.
- `git diff --check`: pasó.
- RF07: cinco repeticiones de 1.000, 10.000 y 50.000 registros, con métricas
  completas y sin errores en el protocolo local documentado.
- Perfil mixto: consultas exactas de control, decisiones en español,
  paráfrasis sin identificadores y negativos naturales; las 283 consultas
  quedaron separadas por tipo y sin errores.
- Evaluación de proyecto real: recuperación, procedencia de archivos/nodos y
  abstención verificada sobre el checkout actual; 3 casos, 0 errores.
- `graphtyn --version`: `0.10.5`.

## Paquete y CI

El wheel y el sdist deben construirse desde el commit de esta versión e
instalarse en un entorno vacío antes de etiquetar. La CI Windows de `0.10.4`
fue verde; el tag `v0.10.5` debe ejecutar de nuevo ese job sobre su SHA exacto
antes de publicarse.

La omisión del smoke visual por falta de `libstdc++.so.6` queda documentada y
no se cuenta como aprobación visual.

## Límites

Las mediciones RF07 acreditan el protocolo local con `feature-hash`; no
extrapolan a embeddings remotos, concurrencia multiusuario ni un SLA universal.
La publicación remota queda condicionada a CI verde para el tag exacto.
