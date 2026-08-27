# Contribuir a Graphtyn

## Preparación

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev,treesitter]'
.venv/bin/pytest -q
```

Los cambios deben conservar la procedencia de relaciones, diferenciar
`EXTRACTED`, `INFERRED` y `AMBIGUOUS`, y no introducir usuarios, IP, contenedores
o rutas personales como valores por defecto.

## Antes de solicitar revisión

```bash
.venv/bin/pytest -q
.venv/bin/python -m build
git diff --check
```

Si cambia el dashboard, ejecuta también `python tests/smoke_frontend.py` en un
entorno con Playwright y Chromium. Si cambia memoria, importación o exportación,
ejecuta `tests/test_security_leaks.py` explícitamente.

Incluye pruebas, documentación del comportamiento observable y una nota de
compatibilidad. No incluyas conversaciones, índices, tokens ni benchmarks con
datos privados.
