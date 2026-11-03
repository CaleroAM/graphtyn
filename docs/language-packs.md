# Contrato de paquetes de lenguajes

Graphtyn separa el recorrido del repositorio de la extracción estructural. Cada
paquete declara un nombre, extensiones, módulo de gramática y capacidades. El
contrato ejecutable vive en `graphtyn/core/tree_sitter_backend.py`; el índice
publica en `metadata.language_packs` los paquetes que realmente procesaron al
menos un archivo.

Un paquete se considera aceptado cuando:

1. sus extensiones son únicas y forman parte de `TREE_SITTER_EXTENSIONS`;
2. la gramática ausente produce `None` y permite el extractor integrado;
3. la gramática instalada entrega símbolos y ubicaciones sin error sintáctico;
4. cada capacidad declarada tiene una prueba con una construcción real;
5. el grafo final conserva relaciones y procedencia `file:line`.

## Cobertura actual

| Paquete | Extensiones | Capacidades declaradas |
|---|---|---|
| C# | `.cs` | símbolos, imports, llamadas, miembros, herencia |
| JavaScript | `.js`, `.jsx` | símbolos, imports, llamadas, miembros |
| TypeScript | `.ts`, `.tsx` | símbolos, imports, llamadas, miembros, herencia |
| PHP | `.php` | símbolos, imports, llamadas, miembros, herencia |
| Python | `.py` | símbolos, imports, llamadas, herencia |
| Java | `.java` | símbolos, imports, llamadas, miembros, herencia |
| Go | `.go` | símbolos, imports, llamadas, miembros |
| Rust | `.rs` | símbolos, imports, llamadas, miembros, herencia |
| C | `.c`, `.h` | símbolos, includes, llamadas, miembros |
| C++ | `.cc`, `.cpp`, `.cxx`, `.hh`, `.hpp`, `.hxx` | símbolos, includes, llamadas, miembros, herencia |
| Ruby | `.rb` | símbolos, requires, llamadas, herencia, mixins |
| Kotlin | `.kt`, `.kts` | símbolos (clases, `object`, interfaces, enums), imports, llamadas, herencia |
| Swift | `.swift` | símbolos (clases, structs, enums, protocolos, `init`), imports, llamadas, herencia |
| Scala | `.scala` | símbolos (clases, `object`, traits), imports, llamadas, herencia |

El paquete C/C++ reconoce clases, `struct`, `union`, `enum`, funciones,
métodos, campos, `#include`, espacios de nombres, llamadas y bases. La
extensión ambigua `.h` usa C por defecto y cambia a C++ cuando detecta sintaxis
como `namespace`, `template`, `class`, `constexpr`, `std::` o especificadores de
acceso. Esto permite indexar bibliotecas C++ que conservan encabezados `.h` sin
clasificar como C un encabezado C convencional. La
resolución entre archivos sigue usando el ranker común de Graphtyn; macros,
plantillas complejas, compilación condicional y sobrecargas que requieren tipos
del compilador pueden quedar `INFERRED` o `AMBIGUOUS` y deben verificarse en la
fuente.

El paquete Ruby reconoce clases, módulos, métodos de instancia, métodos
singleton, llamadas, parámetros, superclases, `require`, `require_relative` y
los mixins `include`, `prepend` y `extend`. La herencia conserva la relación
`hereda`; los mixins usan `incluye` y registran su operación exacta en
`mixin_kind`, evitando presentar composición como herencia. Las macros y DSL de
Rails se conservan como llamadas y operaciones con evidencia, pero inferir su
semántica de framework requiere una relación especializada adicional.
Cuando varios símbolos homónimos empatan, el ensamblador evita materializar un
abanico de más de cuatro destinos y registra la ambigüedad. Así se conserva la
señal sin convertir una llamada genérica como `setup` en cientos de relaciones.

Las llamadas Ruby sin receptor a métodos de `Kernel`/`Module` (`require`,
`include`, `raise`, `puts`…) se marcan como builtins y no se resuelven contra un
método homónimo del proyecto; `params.require(:x)`, con receptor, sí se resuelve.

Los paquetes Kotlin, Swift y Scala reconocen clases, `object`, interfaces,
protocolos y traits, structs y enums, funciones y métodos con su contenedor,
`init` de Swift, imports y cláusulas de herencia (`: Base(), Payable`,
`: Base, Payable`, `extends Base with Payable`), que se convierten en `hereda` o
`implementa`. Las propiedades, extensiones de Swift como tipo propio, genéricos
y llamadas a constructores todavía no se modelan como relaciones.

## Cómo añadir otro paquete

Se añade una entrada a `LANGUAGE_PACKS`, se incluye su gramática en las
dependencias del paquete y se extienden los tipos de nodo sólo cuando la gramática lo
requiere. Las pruebas deben cubrir el resultado directo del parser y al menos
una relación en el grafo ensamblado. Los benchmarks locales de C/C++ y Ruby
sirven como plantilla: `python benchmarks/run_language_pack_benchmark.py` y
`python benchmarks/run_ruby_language_pack_benchmark.py`.

La medición de este benchmark es determinista y local. Mide cobertura de hechos
y latencia del parser; no mide tokens de un agente ni demuestra ahorro de coste
de una sesión con modelos.
