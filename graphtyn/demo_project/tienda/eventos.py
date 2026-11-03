"""Bus de eventos en memoria."""
from collections import defaultdict

_suscriptores = defaultdict(list)


def suscribir(evento: str, funcion) -> None:
    _suscriptores[evento].append(funcion)


def publicar(evento: str, datos) -> None:
    for funcion in _suscriptores[evento]:
        funcion(datos)
