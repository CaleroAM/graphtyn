"""API HTTP: recibe pedidos y los delega al servicio de pedidos."""
from fastapi import FastAPI

from .modelos import PedidoEntrada
from .pedidos import cancelar_pedido, crear_pedido, listar_pedidos

app = FastAPI()


@app.post("/pedidos")
def post_pedido(entrada: PedidoEntrada):
    return crear_pedido(entrada)


@app.get("/pedidos")
def get_pedidos():
    return listar_pedidos()


@app.delete("/pedidos/{pedido_id}")
def delete_pedido(pedido_id: int):
    return cancelar_pedido(pedido_id)
