"""Avisos al cliente cuando cambia un pedido."""
from .eventos import suscribir
from .modelos import Pedido


def enviar_confirmacion(pedido: Pedido) -> str:
    return f"Hola {pedido.cliente}: recibimos tu pedido #{pedido.id} por {pedido.total:.2f} €"


def avisar_cancelacion(pedido_id: int) -> str:
    return f"El pedido #{pedido_id} fue cancelado"


suscribir("pedido_creado", enviar_confirmacion)
suscribir("pedido_cancelado", avisar_cancelacion)
