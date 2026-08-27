# Checklist de release

## Código y evidencia

- [ ] Worktree limpio y tag coincide con `graphtyn.__version__`.
- [ ] Suite Python completa pasa en 3.10, 3.11, 3.12 y 3.13.
- [ ] Pruebas adversariales de fugas pasan.
- [ ] Smoke de Chromium pasa sin errores JS ni controles fuera del viewport.
- [ ] Wheel y sdist se construyen y el wheel se instala en un entorno vacío.
- [ ] `graphtyn --version`, `setup`, `reindex`, `report` y MCP stdio funcionan.
- [ ] Imagen Docker construye y `/health` responde como usuario sin privilegios.

## Publicación

- [ ] `docs/CHANGELOG.md` describe límites y cambios reales.
- [ ] README no promete destinos de instalación aún inexistentes.
- [ ] Artefactos y hashes se adjuntan a la release.
- [ ] PyPI Trusted Publishing está configurado antes de habilitar publicación.
- [ ] Se revisan vulnerabilidades y dependencias del artefacto final.

El workflow `release.yml` ejecuta estas comprobaciones y crea artefactos para
tags `v*`. La publicación en PyPI permanece deshabilitada deliberadamente.
