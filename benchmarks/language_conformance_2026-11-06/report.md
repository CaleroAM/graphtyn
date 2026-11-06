# Conformidad por lenguaje: validación en Java, PHP, Go y Rust

Fecha: 2026-11-06. 32 sesiones de Codex: 8 tareas nuevas × 2 versiones de Graphtyn × 2
repeticiones. Unos 1,9 millones de tokens.

**Veredicto: POSITIVE, moderado.**

- **Hechos:** la rama corregida acertó 143/152 (94 %) y `main` 136/152 (89 %).
- **Tokens:** la media bajó de 59.084 a 53.291; la mediana subió un 2 %.
- **Dónde está la mejora:** PHP gana en calidad (34/34 frente a 26/34) y Java en coste (mitad
  de tokens).
- **Por parejas:** la rama acierta más en 4 de 16 y menos en 6, casi siempre por un solo
  hecho.
- **Ripgrep:** la versión congelada elegía el `Parser` equivocado en una tarea y gastó más
  del doble de tokens. Ese fallo se corrigió después, como se explica abajo.

## Qué se corrigió

Una prueba de conformidad (`tests/test_language_conformance.py`) comprueba, con un ejemplo por
lenguaje, que cada capacidad declarada se produce de verdad. En `main` falla en seis lenguajes:

| Lenguaje | Fallo en `main` |
|---|---|
| Java | Ninguna llamada a métodos (`method_invocation` no era un tipo de llamada) y sin `implements`. |
| PHP | `$this->helper()` se guardaba como llamada a `this`; sin `extends` ni `implements`. |
| Go | Sin símbolo para `type X struct`, métodos sin dueño y `c.Own()` sin resolver. |
| Rust | Métodos de `impl` sin dueño, así que `self.own()` se descartaba; sin supertraits. |
| TypeScript, JavaScript | Ningún campo con tipo, así que `this.repo.save()` no se resolvía por `repo`. |

Efecto en el grafo de los cuatro repositorios de la validación:

| Repositorio | Llamadas | De ellas `EXTRACTED` | Herencia |
|---|---|---|---|
| google/gson (Java) | 3.457 → 11.548 | 350 → 5.758 | 225 → 387 |
| slimphp/Slim (PHP) | 674 → 534 | 4 → 524 | 0 → 76 |
| spf13/cobra (Go) | 1.157 → 1.414 | 282 → 533 | 0 → 0 |
| BurntSushi/ripgrep (Rust) | 1.510 → 3.475 | 902 → 2.360 | 0 → 1 |

En Slim desaparecen 664 llamadas, 580 de ellas `AMBIGUOUS` y 84 `INFERRED`, que unían un
nombre con homónimos de interfaces y pruebas. Los corpus de los benchmarks anteriores (C, C++,
Ruby y Python) producen el mismo grafo y los mismos 46 paquetes.

## Diseño

- **Repositorios públicos en su commit más reciente, fijado:**
  - google/gson `65df6e5a`;
  - slimphp/Slim `3675bf6b`;
  - spf13/cobra `adbc8813`;
  - BurntSushi/ripgrep `91f5d22e`.
- **Tareas:** 8 nuevas, una de impacto y una de flujo por repositorio, con 76 hechos.
  Las escribí leyendo el código y las congelé en `65b8498` antes de ejecutar. Cada una
  depende de llamadas a métodos sobre el propio objeto o heredados.
- **Versiones:** `main` (`f2a1e1d`) frente a la rama en `d38f930`, cada una desde un worktree
  congelado. MCP lean y regla de parada `targeted`.
- **Cliente:** Codex 0.153.2 con `gpt-5.6-luna` y `--ignore-user-config`. Cada sesión usa una
  copia del repositorio y un `GRAPHTYN_HOME` propio. El orden se alterna entre repeticiones.
- **Calificación:** dos jueces (Gemini y GPT), sin herramientas; un hecho cuenta solo si
  coinciden. Kappa entre jueces: 0,80.

## Resultado

| Versión | Hechos (jueces) | Tokens: media | Tokens: mediana | Herramientas |
|---|---:|---:|---:|---:|
| `main` | 136/152 (89 %) | 59.084 | 30.340 | 2,6 |
| Corregida | **143/152 (94 %)** | **53.291** | 31.059 | 2,4 |

| Tarea | `main` | Corregida | Tokens: `main` → corregida |
|---|---:|---:|---|
| gson `popStack`, impacto | 17/18 | 16/18 | 93.196 → **32.074** |
| gson `doPeek`, flujo | 20/22 | 20/22 | 119.770 → **67.294** |
| Slim `map`, impacto | 14/16 | **16/16** | 29.354 → 29.285 |
| Slim `App::run`, flujo | 12/18 | **18/18** | 86.889 → 89.056 |
| cobra `mergePersistentFlags`, impacto | 18/18 | 17/18 | 27.098 → 28.496 |
| cobra `ExecuteC`, flujo | 20/20 | 18/20 | 42.423 → 29.866 |
| ripgrep `has_exceeded_match_limit`, impacto | 16/16 | 15/16 | 27.088 → 28.414 |
| ripgrep `Parser::parse` (globset), flujo | 19/24 | **23/24** | 46.853 → **121.843** |

- **Java:** sin llamadas en el grafo, Codex con `main` buscó por su cuenta y acertó casi
  lo mismo, pero gastó el triple en `popStack` y casi el doble en `doPeek`.
- **PHP:** la rama nombró en las dos repeticiones que `App` hereda `map` de
  `RouteCollectorProxy`, y `main` en ninguna. En `App::run`, una sesión de `main` paró
  pronto, con 27.231 tokens, y acertó 3 de 9 hechos.
- **Go y Rust (impacto):** `main` ya acertaba todo, porque los consumidores salían como
  referencias de texto. Las pérdidas de un hecho de la rama son del tamaño de la variación
  entre sesiones.
- **Ripgrep `Parser::parse`:** en `d38f930`, los métodos de Rust ya tenían dueño. Entonces
  `Parser::parse` encajaba con dos declaraciones (`crates/globset` y `crates/core/flags`), y
  ganaba la equivocada. Codex se dio cuenta y buscó la correcta, así que acertó más, pero
  gastó 2,6 veces más tokens. Sin cliente, los hechos presentes en el paquete bajaron de 9 a 3 de 12.

## Corrección posterior: alcance por miembro de workspace

La causa del caso de ripgrep tenía tres partes:
- solo una carpeta de primer nivel contaba como paquete, y `crates/globset` no lo era;
- el alcance sumaba los paquetes de los dos homónimos, en vez de quedarse con el nombrado;
- una heurística daba 5.000 puntos a un archivo llamado como el símbolo (`parse.rs`).

El commit `afff470` lo corrige. Los miembros de `crates/`, `packages/`, `libs/` y carpetas
similares cuentan como paquetes. El paquete que nombra la pregunta reduce el alcance y pesa
más que el nombre del archivo.

- **En la tarea de globset:** sin cliente, los hechos presentes en el paquete pasan de 3 a 10
  de 12. Esa tarea sirvió para encontrar el fallo, así que no es evidencia independiente de
  la corrección.
- **Tareas de reserva:** escribí dos más antes de medir (`benchmarks/workspace_scope_2026-11-06`).
  Piden el mismo `RegexMatcherBuilder::build_many`, nombrando una vez `pcre2` y otra `regex`.
  Las dos versiones dan los mismos hechos (8/10 y 9/9), así que no ejecuté sesiones: solo
  medirían variación.
- **Puertas:** cobertura, mantenibilidad y 927 pruebas en verde. Las 46 tareas anteriores no
  cambian.

## Límites

- **Pocas repeticiones:** n=2 por celda, una tarea de cada tipo por lenguaje, un solo cliente.
- **Varianza alta en flujos:** una sola sesión que para pronto o que explora mucho mueve la media.
- **Rúbricas mías:** las escribí yo y los jueces son modelos.
- **Fuera del modelo:**
  - Rust: `impl Trait for Type` sigue sin modelarse.
  - Go: una llamada sobre un parámetro (`stripFlags(args, c *Command)` → `c.mergePersistentFlags()`)
    no se resuelve, porque `c` no es el receptor del método.

## Reproducir

```bash
python benchmarks/judge_grades.py --tasks-root benchmarks/language_conformance_2026-11-06 \
  --run-root <ejecuciones> --variant codex-main --variant codex-fix
python benchmarks/language_conformance_2026-11-06/analyze.py --run-root <ejecuciones>
```

`runs.json`, `results.json` y `judge_grades.json` guardan los datos por sesión.
