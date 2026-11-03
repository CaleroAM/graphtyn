# Tienda de ejemplo

Proyecto pequeño e inventado que acompaña al dashboard de Graphtyn para
explorarlo sin registrar código propio. No se ejecuta: sólo se indexa.

Flujo principal: `POST /pedidos` (`tienda/app.py`) valida la entrada
(`tienda/modelos.py`), calcula el total (`tienda/precios.py`), guarda el pedido
(`tienda/repositorio.py`) y publica `pedido_creado` (`tienda/eventos.py`), que
dispara el correo de confirmación (`tienda/notificaciones.py`).
