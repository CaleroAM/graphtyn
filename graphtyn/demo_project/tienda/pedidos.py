"""Servicio de pedidos: valida, calcula, guarda y publica."""
from .eventos import publicar
from .modelos import Pedido, PedidoEntrada
from .precios import calcular_total
from .repositorio import RepositorioPedidos

repositorio = RepositorioPedidos()


def crear_pedido(entrada: PedidoEntrada) -> Pedido:
    entrada.validar()
    total = calcular_total(entrada)
    pedido = repositorio.guardar(entrada.cliente, total)
    publicar("pedido_creado", pedido)
    return pedido


def cancelar_pedido(pedido_id: int) -> dict:
    repositorio.marcar_cancelado(pedido_id)
    publicar("pedido_cancelado", pedido_id)
    return {"id": pedido_id, "estado": "cancelado"}


def listar_pedidos() -> list[Pedido]:
    return repositorio.todos()
