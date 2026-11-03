"""Cálculo del total de un pedido."""
from .modelos import PedidoEntrada

CUPONES = {"BIENVENIDA": 0.10, "VERANO": 0.15}


def subtotal(entrada: PedidoEntrada) -> float:
    return sum(linea.cantidad * linea.precio_unitario for linea in entrada.lineas)


def aplicar_descuento(importe: float, cupon: str | None) -> float:
    return round(importe * (1 - CUPONES.get(cupon or "", 0.0)), 2)


def calcular_total(entrada: PedidoEntrada) -> float:
    return aplicar_descuento(subtotal(entrada), entrada.cupon)
