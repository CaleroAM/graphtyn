"""Cross-language programming vocabulary for lexical retrieval.

Requests are often written in Spanish while identifiers are English
(``evicción`` → ``performEvictions``). Each entry maps a Spanish stem to the
English fragments that commonly spell the same programming concept inside
identifiers. Entries are generic programming vocabulary: they must never name
a product, framework or corpus-specific symbol.
"""

from __future__ import annotations

import re

# Spanish stem → English identifier fragments. A request word matches an entry
# when it starts with the stem, so one stem covers its inflections.
_ES_EN: dict[str, tuple[str, ...]] = {
    "abrir": ("open",), "abre": ("open",), "acceso": ("access",), "actualiz": ("update",),
    "agrega": ("append", "add"), "añad": ("append", "add"), "alinea": ("align",),
    "almacen": ("store", "storage"), "analiz": ("parse",), "ancho": ("width",),
    "argumento": ("arg",), "dinámic": ("dynamic",), "dinamic": ("dynamic",), "arranc": ("start", "init"), "asigna": ("assign",),
    "asíncron": ("async",), "asincron": ("async",), "atribut": ("attribute",),
    "autentic": ("auth",), "bloque": ("block", "lock"), "borra": ("delete", "remove"),
    "búfer": ("buffer",), "bufer": ("buffer",), "busca": ("find", "lookup", "search"),
    "caché": ("cache",), "cache": ("cache",), "caduc": ("expire",), "calcul": ("compute", "calc"),
    "campo": ("field",), "canal": ("channel",), "carga": ("load",), "cerrar": ("close",),
    "cierra": ("close",), "cifra": ("encrypt", "cipher"), "clase": ("class",), "clave": ("key",),
    "cliente": ("client",), "codific": ("encode",), "cola": ("queue",), "columna": ("column",),
    "compara": ("compare", "cmp"), "comprim": ("compress",), "comprueba": ("check",),
    "conexi": ("connection", "conn"), "configura": ("config",), "confirma": ("commit",),
    "consulta": ("query",), "contador": ("counter", "count"), "cuenta": ("count",),
    "copia": ("copy",), "crea": ("create",), "decodific": ("decode",), "descart": ("discard",),
    "descifr": ("decrypt",), "desconect": ("disconnect", "close"), "desbloque": ("unblock", "unlock"),
    "despach": ("dispatch",), "destru": ("destroy",), "dígito": ("digit",), "digito": ("digit",),
    "duraci": ("duration",), "elimina": ("delete", "remove"), "encola": ("queue", "enqueue"),
    "entero": ("int", "integer"), "entrada": ("input",), "enví": ("send",), "envia": ("send",),
    "error": ("error",), "escrib": ("write",), "escritura": ("write",), "espera": ("wait",),
    "especifica": ("spec",), "estilo": ("style",), "evento": ("event",), "evicci": ("evict",),
    "excepci": ("exception",), "expira": ("expire",), "exponen": ("exp",), "fecha": ("date", "time"),
    "fichero": ("file",), "archivo": ("file",), "filtr": ("filter",), "firma": ("sign",),
    "flotante": ("float", "double"), "fondo": ("background",), "formatea": ("format",),
    "fusiona": ("merge",), "genera": ("generate",), "guarda": ("save", "store"),
    "hijo": ("child",), "hilo": ("thread",), "índice": ("index",), "indice": ("index",),
    "inicia": ("init", "start"), "inserta": ("insert",), "lectura": ("read",), "lee": ("read",),
    "libera": ("free", "release"), "límite": ("limit",), "limite": ("limit",), "lista": ("list",),
    "llamada": ("call",), "memoria": ("memory", "mem"), "mensaje": ("message", "msg"),
    "migraci": ("migrat",), "nombre": ("name",), "notifica": ("notify",), "número": ("number", "num"),
    "numero": ("number", "num"), "objeto": ("object", "obj"), "ordena": ("sort",),
    "parámetro": ("param",), "parametro": ("param",), "patrón": ("pattern",), "patron": ("pattern",),
    "permis": ("permission", "permit"), "permit": ("permit",), "persist": ("persist",),
    "petici": ("request",), "plantilla": ("template",), "precisi": ("precision",),
    "proceso": ("process",), "propaga": ("propagate",), "puntero": ("pointer", "ptr"),
    "recorre": ("iterate", "each"), "reescrib": ("rewrite",),
    "registro": ("record", "log"), "relleno": ("pad", "fill"), "rellena": ("pad", "fill"),
    "renombra": ("rename",), "réplica": ("replica",), "replica": ("replica", "replicat"),
    "respuesta": ("reply", "response"), "restablec": ("reset",), "revert": ("rollback", "revert"),
    "ruta": ("route", "path"), "salida": ("output",), "separador": ("separator", "sep"),
    "serializ": ("serialize",), "sesi": ("session",), "signo": ("sign",), "sincroniz": ("sync",),
    "suscri": ("subscribe",), "tamaño": ("size",), "tamano": ("size",), "tarea": ("task", "job"),
    "temporal": ("temp", "tmp"), "temporizador": ("timer",), "tiempo": ("time",),
    "transacci": ("transaction",), "unidad": ("unit",), "valida": ("valid",), "valor": ("value",),
    "versi": ("version",), "víctima": ("victim",), "victima": ("victim",),
}

# Spanish words of five or more letters that are not programming concepts but
# occur inside English identifiers (``forma`` in ``format``, ``entre`` in
# ``centre``). They never count as a lexical match.
COMMON_WORDS = frozenset({
    "forma", "formas", "entre", "desde", "hasta", "donde", "dónde", "cuando", "cuándo",
    "cómo", "sobre", "puede", "pueden", "tiene", "tienen", "hace", "hacer", "ocurre",
    "explica", "explicar", "describe", "describir", "traza", "trazar", "ejemplo", "caso",
    "casos", "cita", "citar", "línea", "linea", "líneas", "lineas", "commit", "fijado",
    "primero", "después", "despues", "antes", "luego", "final", "finalmente", "también",
    "además", "mismo", "misma", "otro", "otra", "otros", "otras", "cada", "todos", "todas",
    "durante", "mientras", "según", "segun", "frente", "decide", "elige", "influye",
    "devuelve", "responde", "ocurre", "llega", "queda", "usado", "usada", "dada", "dado",
})

_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ_]+")


def translated_terms(request: str) -> list[str]:
    """English identifier fragments for the Spanish programming words in a request."""
    words = {word.lower() for word in _WORD.findall(str(request or "")) if len(word) >= 3}
    return list(dict.fromkeys(
        fragment
        for stem, fragments in _ES_EN.items()
        if any(word.startswith(stem) for word in words)
        for fragment in fragments
    ))


def is_prose_word(word: str) -> bool:
    """A Spanish word the glossary translates; its English fragments stand in for it."""
    lowered = word.lower()
    # English words sharing a Spanish stem (`validates`) start with their fragment.
    return any(lowered.startswith(stem) and not lowered.startswith(fragments)
               for stem, fragments in _ES_EN.items())
