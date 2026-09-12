# Checklist de release

## Código y evidencia

- [ ] Worktree limpio y tag coincide con `graphtyn.__version__`.
- [ ] Suite Python completa pasa en 3.10, 3.11, 3.12 y 3.13.
- [ ] Todas las comprobaciones requeridas del SHA exacto están verdes en GitHub;
  el workflow de release no crea artefactos antes de confirmar ese resultado.
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

El workflow release.yml espera la CI del commit del tag antes de construir y
crear artefactos para tags v*. No se etiqueta ni se publica si CI falla. El
resumen de validación declara métricas medidas y controles pendientes; no afirma
escalabilidad multi-GB ni estabilidad de 24 horas sin medirlas. PyPI Trusted
Publishing permanece deshabilitado deliberadamente.
