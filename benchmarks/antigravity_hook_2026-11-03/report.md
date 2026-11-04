# Hook de primer turno en Antigravity — 3 nov 2026

## Resultado

El hook funciona, pero no ahorra tokens de forma general en Antigravity. Sólo
evita una sesión larga cuando el paquete basta para responder, como en el flujo
de comandos de Redis. Se mantiene opcional y no se recomienda como ahorro.

## Qué se midió

| Parámetro | Valor |
|---|---|
| Cliente y modelo | `agy` 1.3.5, `gemini-3.8-flash-high` |
| Brazos | `graphtyn` (MCP lean) y `graphtyn_hook` (mismo MCP más hook `PreInvocation`) |
| Tareas vistas | 3 tareas de `real_multi_client_hook_2026-10-27`, n=3 |
| Tareas no vistas | 6 tareas de `heldout_v2_2026-10-27`, n=2 |
| Regla de parada | `targeted`, la de la política actual |
| Sesiones | 42 de 42 completas |
| Calidad | Rúbrica literal congelada de cada tarea de origen |

En el brazo hook, el mensaje es sólo la pregunta y las instrucciones del brazo
van en `GEMINI.md`. El MCP se registró con `agy mcp add` en los dos brazos.

Las sesiones de este informe usan la regla `targeted`, y las de Antigravity del
27 oct usaban `strict`: las cifras de MCP lean no son comparables entre ambos.

## Dos formas de contar tokens

Antigravity informa la caché aparte del resto de la entrada, y sus aciertos de
caché varían entre sesiones iguales.

- **Sin caché:** `total_tokens` del cliente, la misma serie que los informes
  anteriores.
- **Con caché:** `total_tokens` más `cached_input_tokens`, el volumen procesado.

## Agregados

| Conjunto | Brazo | n | Sin caché | Con caché | Herramientas | Segundos | Rúbrica |
|---|---|---:|---:|---:|---:|---:|---:|
| Vistas | MCP lean | 9 | 111.079 | 310.081 | 14,1 | 153 | 72/72 |
| Vistas | Hook | 9 | 106.455 (−4,2 %) | 180.102 (−41,9 %) | 9,9 | 108 | 72/72 |
| No vistas | MCP lean | 12 | 157.739 | 545.381 | 22,8 | 190 | 94/96 |
| No vistas | Hook | 12 | 178.488 (+13,2 %) | 569.997 (+4,5 %) | 24,3 | 187 | 94/96 |

## Por tarea

Medias por tarea; la variación es la del hook frente a MCP lean.

| Tarea | Conjunto | MCP lean, sin caché | Hook, sin caché | Variación sin caché | Variación con caché |
|---|---|---:|---:|---:|---:|
| Redis, comandos | Vista | 50.888 | 23.822 | −53,2 % | −53,2 % |
| fmt, `format` | Vista | 100.598 | 115.765 | +15,1 % | −21,2 % |
| Rails, `save` | Vista | 181.750 | 179.779 | −1,1 % | −48,4 % |
| Redis, evicción * | No vista | 154.443 | 128.970 | −16,5 % | −7,9 % |
| Redis, límite de búfer | No vista | 154.010 | 186.009 | +20,8 % | +9,9 % |
| fmt, coma flotante | No vista | 113.644 | 202.462 | +78,2 % | +118,7 % |
| fmt, `format_to_n` | No vista | 119.956 | 88.372 | −26,3 % | −49,7 % |
| Rails, `update` | No vista | 236.086 | 292.869 | +24,1 % | −6,3 % |
| Rails, `find` | No vista | 168.296 | 172.245 | +2,3 % | −18,5 % |

\* En evicción el hook se abstuvo en las dos sesiones (paquete sin evidencia),
así que ambos brazos usaron el MCP. Esa diferencia es una referencia del ruido
de este diseño, no un efecto del hook.

## Lectura

- **La inyección funciona.** El contexto llegó al modelo en 19 de 21 sesiones,
  según la propia transcripción de Antigravity. Las otras 2 son las de evicción.
- **Sustituye la consulta MCP.** Con inyección, ninguna sesión volvió a llamar
  al MCP; sin ella, sí lo hicieron.
- **No detiene la exploración.** Salvo en el flujo de comandos de Redis, el modelo siguió buscando y
  leyendo 5–51 veces, tanto con hook como sin él. Por eso el ahorro de la
  consulta se pierde en el resto de la sesión.
- **Calidad igual.** La rúbrica no cambia entre brazos. El único hecho que falta
  es `random` en evicción, en todas las sesiones de ambos brazos.

## Limitaciones

- **Repeticiones:** n=2–3 por tarea. Una sola sesión pesa mucho: la de coma
  flotante con 254.595 tokens explica buena parte de su +78,2 %.
- **Cuenta y entorno:** una sola cuenta y un solo modelo, con la configuración
  global de usuario de `agy`.
- **Alcance:** CLI `agy` 1.3.5; ni el IDE ni Antigravity 2.0.
- **Hook pinado:** el del benchmark usa ruta absoluta y `--path`. El comando que
  instala Graphtyn se probó aparte en sesiones reales sobre el proyecto demo.
- **Transcripción sin contrato:** el hook depende de un formato no documentado.
  Una transcripción desconocida no inyecta nada, comprobado con tests.
- **Calidad medida sólo con rúbrica literal:** no hubo adjudicación ciega.

Eventos crudos, fuera del repositorio:
`/home/calero/Documentos/docker/graphtyn-benchmark-runs-antigravity-hook-2026-11-03/`.
