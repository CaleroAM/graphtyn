"""Which kind of evidence package a request needs, from its wording alone."""
from __future__ import annotations

import re

from .retrieval_signals import CODE_IDENTIFIER as _CODE_IDENTIFIER

_INTENT_MARKERS = {
    "overview": ("overview", "purpose", "architecture", "summary", "what is this", "de qué trata", "de que trata", "resumen", "arquitectura", "technologies", "tecnologías", "tecnologias", "stack", "entry points", "puntos de entrada", "subsystems", "subsistemas"),
    "bindings": ("binding", "bindings", "addscoped", "addsingleton", "addtransient", "dependency", "dependencia", "registr", "inyección", "injection"),
    "persistence": ("persist", "repository", "repositorio", "database", "base de datos", "save", "deleteasync", "addasync", "query", "consulta"),
    "tests": ("test", "tests", "prueba", "pruebas", "coverage", "cobertura"),
    "impact": ("impact", "impacto", "consumer", "consumidor", "blast", "afecta"),
    "flow": ("flow", "flujo", "trace", "traza", "desde", "hasta", "event", "evento"),
}

# "En este proyecto" says where to look, not what is asked: it must not decide the
# intent, and a bare "repositorio" there is not the data-access pattern.
_PROJECT_NOUN = r"(?:proyecto|project|repositorio|repository|repo|codebase)"
_PROJECT_DETERMINER = r"(?:el|la|the|este|esta|this|mi|my|nuestro|our)"
_PROJECT_NAME = r"`?(?-i:[\w-]*(?:_|[a-z][A-Z])[\w-]*)`?"
_PROJECT_SCOPE = re.compile(
    rf"\b(?:(?:en|de|del|in|of|within)\s+(?:{_PROJECT_DETERMINER}\s+)?|(?:este|esta|this|mi|my|nuestro|our)\s+)"
    rf"{_PROJECT_NOUN}\b(?:\s+{_PROJECT_NAME})?|\b{_PROJECT_NOUN}\s+{_PROJECT_NAME}", re.IGNORECASE)
# The project itself is the subject: "¿qué hace este proyecto?", "explain this repo".
_PROJECT_SUBJECT = re.compile(
    r"\b(?:qu[eé] hace|qu[eé] es|para qu[eé] sirve|c[oó]mo funciona|explica(?:me)?|describe|analiza|revisa|resume|"
    r"h[aá]blame (?:de|sobre)|what does|what is|what's|how does|explain|analy[sz]e|review|summari[sz]e|tell me about)"
    rf"\s+(?:(?:de|del|{_PROJECT_DETERMINER})\s+)?{_PROJECT_NOUN}\b(?!\s+(?:de|of|que|that|para|for)\b)", re.IGNORECASE)
_CODE_UNIT = re.compile(
    r"\b(?:funci[oó]n|function|clase|class|m[eé]todo|method|m[oó]dulo|module)\b", re.IGNORECASE)

_DI_CONTEXT = re.compile(
    r"servic|service|dependen|inyecci|inject|contenedor|container|provider|proveedor|binding|singleton|scoped|transient"
    r"|extensi|plugin|middleware|helper")
_INFLECTION = r"(?:s|es|e|en|n|r|do|da|dos|das|ría)?"
_INFLECTED_MARKERS = {"afecta", "consumidor", "consumer", "persist", "prueba", "test"}


def without_project_scope(request: str) -> str:
    """The request without phrases that only say where to look ("en este proyecto")."""
    return _PROJECT_SCOPE.sub(" ", str(request or ""))


def is_change_request(request: str) -> bool:
    """Identify requests where an agent is expected to edit the repository."""
    return bool(re.search(
        # A reflexive passive describes behaviour ("cuando se añade una ruta").
        r"(?<!\bse )\b(?:implement(?:a|ar|e)|a(?:ñ|n)ad(?:e|ir)|agreg(?:a|ar)|modific(?:a|ar)|"
        r"corrig(?:e|ir)|cambi(?:a|ar)|refactor(?:iza|izar)?|fix|edit|update|remove|elimina)\b",
        str(request or ""),
        re.I,
    ))


def classify_intent(request: str, requested: str = "auto") -> str:
    text = str(request or "").lower()
    enumerated = len(set(re.findall(r"\bq\d+\s*[):]", text))) >= 2
    operational = bool(re.search(
        r"\b(?:c[oó]mo|cu[aá]les?|qu[eé] ocurre|si falta|comprueba|valida|genera|"
        r"docker|worker|api|archivo|manifiesto|integridad|esquema|script)\b",
        text,
    ))
    # Models sometimes choose ``overview`` merely because the prompt names a
    # repository. An enumerated operational question needs symbol/operation
    # evidence, even when the caller supplied that overly broad intent.
    if requested == "overview" and enumerated and operational:
        return "flow"
    if requested in _INTENT_MARKERS:
        return requested
    if is_change_request(text):
        return "flow"
    question = without_project_scope(request)
    names_code = bool(_CODE_IDENTIFIER.search(question) or _CODE_UNIT.search(question))
    if not names_code and _PROJECT_SUBJECT.search(text):
        return "overview"
    text = question.lower()

    def marker_matches(marker: str) -> bool:
        if marker == "registr":
            # "registrar/register" a service, not "registro(s)" (a record) nor a
            # function that records keys or names: the verb only signals
            # bindings next to dependency-injection vocabulary.
            return bool(re.search(r"registr(?!os?\b)", text) and _DI_CONTEXT.search(text))
        # Inflected forms count: "afectado", "consumidores", "persiste".
        inflection = _INFLECTION if marker in _INFLECTED_MARKERS else ""
        return bool(re.search(rf"(?<!\w){re.escape(marker)}{inflection}(?!\w)", text))

    scores = {intent: sum(marker_matches(marker) for marker in markers)
              for intent, markers in _INTENT_MARKERS.items()}
    if names_code:
        scores["overview"] = 0  # a summary of a named function or class is about that code
    best = max(scores, key=lambda intent: scores[intent])
    if scores[best] and scores.get("flow") == scores[best]:
        return "flow"  # a tie with an explicit trace/flow request is a flow
    return best if scores[best] else "flow"
