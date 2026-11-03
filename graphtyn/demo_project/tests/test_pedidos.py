from tienda.modelos import Linea, PedidoEntrada
from tienda.precios import calcular_total


def test_el_cupon_descuenta_del_subtotal():
    entrada = PedidoEntrada("Ana", [Linea("taza", 2, 10.0)], cupon="BIENVENIDA")
    assert calcular_total(entrada) == 18.0
