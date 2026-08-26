# Validación de `0.6.0b1`

Fecha: 2026-08-25. Entorno local: Linux/NixOS, Python 3.13; CI define la
matriz Python 3.10–3.13.

## Resultado local

- Suite completa: **246 passed, 2 skipped** en 41.05 s.
- Seguridad: `pip-audit` sin vulnerabilidades conocidas después de exigir
  `starlette>=1.3.1` y actualizar pip.
- Navegador: smoke Playwright en Chromium 149 correcto; cero errores JS,
  menús dentro del viewport y paneles de calidad/memoria operativos.
- Paquete: wheel y sdist construidos en aislamiento; wheel reinstalado en un
  virtualenv limpio y verificados CLI, MCP, dashboard, favicon y módulos JS.
- Flujo empaquetado: `setup` dry-run, `reindex --engine ast_pure`, `report` y
  MCP `initialize/tools/list` correctos sobre un proyecto temporal.
- Docker: imagen `graphtyn:0.6.0b1` construida; CLI correcta y `/health`
  respondió `0.6.0b1` dentro del contenedor sin privilegios.

## Artefactos locales

```text
8a8d9d6b6b5b9dd66d9c704fc8ff7e1db8912eb27ab398f2d353cc0def80a636  graphtyn-0.6.0b1-py3-none-any.whl
9efc4fc5a3c9d43fac8f3594ec6eba03fc4bba1d779bf71b9ce00569138fdfcd  graphtyn-0.6.0b1.tar.gz
```

Estos hashes corresponden a la construcción local previa al commit definitivo.
El workflow de release vuelve a construir, genera sus propios `SHA256SUMS` y
adjunta procedencia; esos hashes serán los autoritativos para distribución.

## Pendiente externo

- Crear/configurar el repositorio remoto y ejecutar CI alojado.
- Proteger la rama principal y exigir todos los checks.
- Crear el tag `v0.6.0b1` sólo después de CI verde.
- Configurar PyPI Trusted Publishing antes de anunciar instalación desde PyPI.

