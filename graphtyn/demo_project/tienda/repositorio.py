"""Persistencia de pedidos en SQLite."""
import sqlite3

from .modelos import Pedido


class RepositorioPedidos:
    def __init__(self, ruta: str = "tienda.db"):
        self.conexion = sqlite3.connect(ruta)
        self.conexion.execute(
            "CREATE TABLE IF NOT EXISTS pedidos (id INTEGER PRIMARY KEY, cliente TEXT, total REAL, estado TEXT)")

    def guardar(self, cliente: str, total: float) -> Pedido:
        cursor = self.conexion.execute(
            "INSERT INTO pedidos (cliente, total, estado) VALUES (?, ?, 'creado')", (cliente, total))
        self.conexion.commit()
        return Pedido(cursor.lastrowid, cliente, total)

    def marcar_cancelado(self, pedido_id: int) -> None:
        self.conexion.execute("UPDATE pedidos SET estado = 'cancelado' WHERE id = ?", (pedido_id,))
        self.conexion.commit()

    def todos(self) -> list[Pedido]:
        rows = self.conexion.execute("SELECT id, cliente, total, estado FROM pedidos").fetchall()
        return [Pedido(*row) for row in rows]
