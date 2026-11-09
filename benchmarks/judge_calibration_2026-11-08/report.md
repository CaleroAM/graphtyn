# Calibración de los jueces

Fecha: 2026-11-08. Sin sesiones de cliente nuevas: se recalificaron cuatro validaciones existentes.

**Veredicto: cambia la regla principal.** La nota de un hecho pasa del consenso de dos jueces
(cuenta solo si coinciden) a la mayoría de tres. El tercer juez solo interviene donde los dos
primeros discrepan. Además, los jueces reciben resueltas las citas `archivo:línea` de la respuesta.

## Qué fallaba

- **Acuerdo en descenso:** el kappa entre Gemini y GPT bajó de 0,95, en la comparación con
  Graphify, a 0,67 en la validación del paquete de impacto.
- **Citas sin resolver:** los jueces no tienen el código. Una respuesta que nombra un consumidor
  por su línea (`app.py:890`) en vez de por su nombre (`handle_user_exception`) perdía el hecho.
- **Consenso estricto:** con la regla de consenso, cualquier error de un juez quita el hecho.

## Cambios

- **Citas resueltas:** `judge_grades.py --repos` añade al final de cada respuesta un apéndice
  con sus propias citas. Cada una lleva el símbolo que rodea la línea y el código de esa línea,
  leídos del corpus fijado. Un hecho citado solo por su ubicación cuenta si el apéndice muestra
  que la cita apunta a él y la respuesta dice qué es.
- **Desempate:** con `--tiebreak`, si los dos jueces discrepan en algún hecho de una respuesta,
  Claude (`claude-sonnet-5-5`, sin herramientas ni MCP) la califica. La regla `majority` toma la
  mayoría de los tres.

## Revisión contra el código

Revisé, leyendo las respuestas y el código citado, los 13 hechos en los que Gemini y GPT
discreparon, y 30 hechos tomados al azar de los 449 en los que coincidieron. Los datos están
en `labels.json`.

Esa revisión es mía y la hizo otro modelo, no una persona. Sirve para comparar las reglas,
no como verdad absoluta.

| Regla | Desacuerdos acertados | Acuerdos acertados |
|---|---:|---:|
| Solo Gemini | 9/13 | 29/30 |
| Solo GPT | 4/13 | 29/30 |
| Consenso (regla anterior) | 6/13 | 29/30 |
| Basta con uno | 7/13 | 29/30 |
| **Mayoría con desempate** | **8/13** | 29/30 |

- **Errores de GPT:** suele dar por presentes hechos que la respuesta no nombra, como
  `alsoPropagateForced`, `binary_byte_offset` o la detección de `Psr17FactoryProvider`.
- **Errores de Gemini:** a veces no reconoce una descripción sin el identificador, como «añade
  recursivamente los prefijos» para la lista de padres.
- **Tamaño de la muestra:** 13 desacuerdos son pocos. Gemini solo saca un acierto más que la
  mayoría, pero un único proveedor es una dependencia más frágil que tres.

## Efecto en el acuerdo

Kappa entre Gemini y GPT, antes y después de resolver las citas:

| Validación | Antes | Con citas resueltas |
|---|---:|---:|
| Correcciones tras Graphify | 0,81 | 0,91 |
| Conformidad por lenguaje | 0,80 | 0,89 |
| `self` a métodos heredados | 0,90 | 0,86 |
| Paquete de impacto completo | 0,67 | 0,68 |

## Validaciones recalculadas

Diferencia de la proporción de hechos (versión nueva menos `main`) e intervalo del 95 %. El
intervalo sale de remuestrear las tareas (`benchmarks/paired_stats.py`) con la regla de mayoría:

| Validación | Tareas | Diferencia | IC 95 % | Razón de tokens |
|---|---:|---:|---|---:|
| Correcciones tras Graphify | 6 | +6,4 % | [+0,9 %, +12,7 %] | 0,99 |
| `self` a métodos heredados | 4 | +8,9 % | [−12,5 %, +32,1 %] | 1,02 |
| Conformidad por lenguaje | 8 | +5,6 % | [−3,5 %, +16,0 %] | 0,98 |
| Paquete de impacto completo | 8 | −0,2 % | [−7,5 %, +7,1 %] | 0,90 |

Solo la primera mejora queda fuera del cero. La conformidad por lenguaje se publicó como
«POSITIVE moderado», pero su intervalo incluye el cero: mejoró el grafo, no una diferencia
medible en las respuestas. Con 4 a 8 tareas, los intervalos son anchos. Las próximas
validaciones usan 20 tareas o más, con una repetición.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root <validación> --run-root <ejecuciones> \
  --variant codex-main --variant codex-fix --tiebreak \
  --repos <corpus de 2026-10-20> --repos <corpus de 2026-11-06>
python benchmarks/paired_stats.py <validación>/judge_grades.json --base codex-main --new codex-fix --rule majority
```
