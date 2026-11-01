# Hook de primer turno y paquete MCP lean en cuatro clientes — 27 oct 2026

## Qué se midió

Mismas tareas, commits y rúbricas congeladas que
`real_claude_agents_lean_hook_2026-10-26`, tras cuatro cambios en la selección
de fuente del modo `precision`:

- un tipo cuyo nombre exacto aparece en la petición (`format_string/fstring`)
  pasa a ser símbolo obligatorio;
- los homónimos de un símbolo ya resuelto en otro archivo dejan de serlo;
- una clase o struct cerrada por el parser en su primer miembro (cabeceras con
  macros) se extiende hasta su llave de cierre;
- el recorte de cuerpos largos amortigua los términos frecuentes y resta peso a
  los comentarios, de modo que las ramas `rejectCommand` de `processCommand`
  ya no pierden frente a palabras raras de comentarios.

El bloque inyectado repite además la regla de parada al final.

| Cliente | Modelo | Brazos | Repeticiones |
|---|---|---|---:|
| Claude Code 2.1.310 | `claude-sonnet-5-5` | `graphtyn` (MCP lean), `graphtyn_hook` | 5 |
| Codex 0.153.2 | `gpt-5.6-luna` | `baseline`, `graphtyn_full`, `graphtyn`, `graphtyn_hook` | 2 |
| OpenCode 1.18.13 | `opencode/deepseek-v4.1-flash-free` | `graphtyn_full`, `graphtyn`, `graphtyn_hook` | 2 |
| Antigravity | `gemini-3.8-flash-high` | `graphtyn_full`, `graphtyn` | 2 |

`graphtyn_full` es el mismo servidor con `--response-detail debug`: el paquete
previo al recorte, como control contemporáneo del recorte. Los hooks son los que
instala Graphtyn:

- **Claude:** dos hooks `UserPromptSubmit`.
- **Codex:** un hook `UserPromptSubmit` con `additionalContextLimit=8000`,
  declarado inline y con `--dangerously-bypass-hook-trust`.
- **OpenCode:** el plugin `chat.message`. Sin `--pure` en los tres brazos,
  porque `--pure` desactiva los plugins de proyecto.

En el brazo hook, el mensaje es sólo la pregunta. Las instrucciones del brazo
van como política de proyecto: `--append-system-prompt` en Claude,
`developer_instructions` en Codex y `instructions` en OpenCode.

Las 84 sesiones del diseño terminaron (84/84 completas). Antigravity no tiene
un mecanismo de hook. `gpt-6-astra`, el modelo de Codex en las ejecuciones del
20 y 21 de octubre, ya no está disponible para esta cuenta; por eso Codex
incluye un brazo `baseline` contemporáneo.

## Tokens totales por sesión (media)

| Corpus | Cliente | Sin grafo | MCP completo | MCP lean | **Hook** | Hook vs lean |
|---|---|---:|---:|---:|---:|---:|
| Redis | Claude | 181.883 † | — | 61.136 | **34.158** | −44,1 % |
| | Codex | 171.640 | 29.462 | 29.331 | **12.150** | −58,6 % |
| | OpenCode | — | 64.630 | 63.913 | **34.832** | −45,5 % |
| | Antigravity | — | 48.764 | 46.502 | — | — |
| fmt | Claude | 295.890 † | — | 61.752 | **34.420** | −44,3 % |
| | Codex | 172.200 | 29.819 | 30.095 | **12.425** | −58,7 % |
| | OpenCode | — | 65.918 | 64.377 | **34.525** | −46,4 % |
| | Antigravity | — | 50.365 | 50.254 | — | — |
| Rails | Claude | 213.902 † | — | 60.932 | **33.304** | −45,3 % |
| | Codex | 217.558 | 50.719 | 50.711 | **11.751** | −76,8 % |
| | OpenCode | — | 36.224 ‡ | 25.959 | **15.668** | −39,6 % |
| | Antigravity | — | 49.100 | 51.150 | — | — |

† Lectura directa con Claude del 25 oct (n=3), mismo modelo y tareas; no
contemporánea. ‡ Una de las dos sesiones leyó además un archivo (44.040 tokens); la otra,
28.409.

Variación entre repeticiones del hook: desviación típica de 104–244 tokens en
Claude (n=5) y ≤ 644 en Codex y OpenCode (n=2). En todas las sesiones con hook
el agente respondió sin herramientas, en una sola llamada al modelo (Claude,
OpenCode; Codex no informa llamadas por separado). En cada una, el hook inyectó
el bloque.

### Lectura

- **El hook es estable en fmt.** Antes de los cambios, 2 de 3 sesiones de fmt
  verificaron `basic_fstring`/`vargs` en fuente (98.645 y 134.115 tokens).
  Ahora el paquete incluye la struct `fstring` completa (constructor `consteval`,
  `parse_format_string`, constructor `runtime_format_string`), y las 5 sesiones
  de Claude dieron 34.420 ± 244 tokens, sin herramientas.
- **El hook ahorra en los tres clientes que lo admiten:** −44 a −45 % frente al
  MCP lean en Claude, −59 a −77 % en Codex y −40 a −46 % en OpenCode. Frente a
  Codex sin grafo, el hook baja de 172–218k a 12k (−93 a −95 %).
- **El recorte lean apenas cambia el gasto fuera de Claude:** Codex ±1 %,
  OpenCode −1 a −2 % (en Rails, −28 %, por una sesión `full` que leyó un archivo) y
  Antigravity entre −5 % y +4 %, dentro del ruido. En
  Claude el efecto fue −3 a −4 % (26 oct). Con los cambios de fuente, el MCP lean
  de Claude sube un 1–2 % frente al 26 oct (61k frente a 60,3–60,9k), porque el
  paquete trae más evidencia útil (`fstring`, ramas de rechazo).
- **Redis `operational_rejections`:** 5/5 sesiones de Claude en cada brazo lo
  cumplen; el 26 oct falló en 3 de 6.

## Calidad

Rúbrica literal congelada (/8), por repetición:

| Corpus | Claude lean | Claude hook | Codex base | Codex full | Codex lean | Codex hook | OpenCode full / lean / hook | Antigravity full / lean |
|---|---|---|---|---|---|---|---|---|
| Redis | 8,8,8,8,8 | 8,8,8,8,8 | 7,7 | 7,8 | 8,7 | 8,7 | 8,8 / 8,8 / 8,8 | 8,8 / 7,8 |
| fmt | 8 ×5 | 8 ×5 | 8,8 | 8,8 | 8,8 | 8,8 | 8,8 / 8,8 / 8,8 | 8,8 / 8,8 |
| Rails | 7,7,8,8,8 | 8,8,7,8,7 | 5,7 | 5,5 | 5,5 | 5,6 | 8,7 / 8,7 / 8,8 | 8,8 / 8,8 |

**Adjudicación conceptual ciega (rúbrica v2,
[`manual_adjudication.json`](manual_adjudication.json)).** El paquete
contenía todas las respuestas con algún fallo literal (20) más 3 respuestas al
azar con 8/8 por corpus, barajadas y con etiqueta aleatoria. La clave
([`blind_key.json`](blind_key.json)) se abrió después de puntuar
([`blind_judgments.json`](blind_judgments.json)).

- **27 de 29 respuestas cumplen los 8 criterios.** Los 5/8 de Codex en Rails son
  paráfrasis: «devuelve `false`» en lugar de `ActiveRecord::Rollback unless
  status`, o la rama `new_record?` descrita sin el literal. Afectan por igual
  al brazo sin grafo.
- **Hay 2 fallos reales:**
  - Codex `graphtyn_full` r1 en Redis no nombra ninguna rama operativa
    concreta.
  - Codex hook r2 en Rails no dice que `Persistence#save` llame a
    `create_or_update`. Es un caso dudoso y se puntuó en contra.
- **Las 9 respuestas de control con 8/8 literal también cumplen los 8
  criterios.**
- **Límites del ciegado:** el adjudicador es el mismo agente que implementó los
  cambios. Algunas respuestas citan rutas de workspace con el nombre del
  cliente y del brazo, de modo que el ciegado es parcial.

## Incidencias

Conservadas en `failed_attempts/` y `pilot/` del directorio de ejecución:

1. **Piloto de Codex sin stdin cerrado.** `codex exec` esperó más entrada por
   stdin hasta el timeout. El runner ahora cierra stdin en todas las sesiones.
2. **Modelo no disponible.** El segundo piloto falló con `model_not_found`
   (`gpt-6-astra`), sin consumo.
3. **Pilotos válidos.** Codex hook (12.017 tokens) y OpenCode hook (15.347) en
   Redis comprobaron la inyección antes de la ejecución. No cuentan en las
   tablas.
4. **`--pure` en OpenCode.** También desactiva los plugins de proyecto, así que
   el hook no se carga con él. Una prueba directa lo confirmó. Además, OpenCode
   no envía al modelo las partes `synthetic`; el plugin añade una parte de texto
   normal.

## Limitaciones

- **Generalización:** con seis tareas no vistas el resultado no se sostiene;
  ver [`../heldout_tasks_2026-10-27/report.md`](../heldout_tasks_2026-10-27/report.md).

- **Repeticiones:** n=5 en Claude y n=2 en los demás clientes.
- **Comparaciones no contemporáneas:**
  - La referencia sin grafo de Claude es del 25 oct.
  - Los brazos sin grafo de OpenCode y Antigravity no se repitieron. Del 20 oct
    (n=1, versión anterior de Graphtyn): OpenCode 388.682, 859.913 y
    1.233.520 tokens; Antigravity 158.966, 263.050 y 319.618.
- **Coste:** se informa en tokens. El coste en USD depende de la caché de cada
  proveedor.
- **Hooks de proyecto en Codex:** en la sesión real exigen confiar en la capa
  `.codex/` y aprobar el hook con `/hooks`. Aquí se declararon inline.
- **Eventos crudos:**
  `/home/calero/Documentos/docker/graphtyn-benchmark-runs-multi-client-hook-2026-10-27/`.
