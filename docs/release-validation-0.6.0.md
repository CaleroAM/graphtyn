# Validación de `0.6.0`

Fecha: 2026-08-26. Entorno local: Linux/NixOS, Python 3.13; CI define la
matriz Python 3.10–3.13.

## Resultado local

- Suite completa: **252 passed, 2 skipped**, ejecutada en dos grupos para
  respetar el límite del terminal (`79 passed` + `173 passed, 2 skipped`).
- Seguridad: `pip-audit` sin vulnerabilidades conocidas después de exigir
  `starlette>=1.3.1` y actualizar pip.
- Navegador: el smoke de Playwright verifica Chromium, cero errores JS, menús
  dentro del viewport y que las acciones flotantes no cubran los filtros.
- Paquete: wheel y sdist `0.6.0` construidos correctamente desde la versión estable.
- Flujo empaquetado: `setup`, `reindex`, `report` y MCP forman parte del contrato.
- Docker: la imagen ejecuta la CLI y `/health` como usuario sin privilegios.
- Servicio systemd de usuario: instalación, activación, reinicio, estado y
  `/health` validados realmente en `127.0.0.1:9210` sin privilegios root.

## Artefactos locales

```text
31a2b3f0386558b6e792da4b3eaa6d12fe001ff9cdbaef98912a85055b63d875  graphtyn-0.6.0-py3-none-any.whl
45dfb2460f81fbbf4aaad34d8fe3636d0d185c3d9e816f2706b450b835de0d82  graphtyn-0.6.0.tar.gz
```

Estos hashes corresponden a la construcción local validada. El workflow de
release vuelve a construir, genera `SHA256SUMS` y adjunta procedencia; sus
hashes serán los autoritativos para distribución.

## Pendiente externo

- Crear/configurar el repositorio remoto y ejecutar CI alojado.
- Proteger la rama principal y exigir todos los checks.
- Crear el tag `v0.6.0` sólo después de CI verde.
- Configurar PyPI Trusted Publishing antes de anunciar instalación desde PyPI.
