"""Datos de un pedido y su validación."""
from dataclasses import dataclass, field


class PedidoInvalido(ValueError):
    pass


@dataclass
class Linea:
    producto: str
    cantidad: int
    precio_unitario: float


@dataclass
class PedidoEntrada:
    cliente: str
    lineas: list[Linea] = field(default_factory=list)
    cupon: str | None = None

    def validar(self) -> None:
        if not self.cliente.strip():
            raise PedidoInvalido("falta el cliente")
        if not self.lineas:
            raise PedidoInvalido("el pedido no tiene productos")
        for linea in self.lineas:
            if linea.cantidad <= 0:
                raise PedidoInvalido(f"cantidad inválida para {linea.producto}")


@dataclass
class Pedido:
    id: int
    cliente: str
    total: float
    estado: str = "creado"
