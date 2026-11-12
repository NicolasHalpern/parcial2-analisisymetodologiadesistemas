"""
Edición y borrado de pedidos desde el admin.

Al guardar se recalculan totales, la ruta del repartidor (y la del anterior si se
cambió) y se avisa al cliente en su página de seguimiento si algo le afecta.
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from ..models import Notificacion, Pedido, PedidoItem, Producto, Repartidor
from ..src import rutas
from ..src.permisos import SoloAdminMixin
from .reparto_controller import _contexto_comercio, json_seguro


def _decimal(valor, defecto="0"):
    """Convierte lo que escribe el usuario ("1.500", "1500,50") a Decimal."""
    texto = str(valor if valor not in (None, "") else defecto).strip().replace("$", "")
    if "," in texto:                       # formato argentino: 1.500,50
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return max(Decimal(texto), Decimal("0"))
    except InvalidOperation:
        return Decimal(defecto)


def _volver(request):
    """A dónde regresar después de guardar (solo rutas internas del sitio)."""
    destino = request.POST.get("volver") or ""
    return destino if destino.startswith("/") and not destino.startswith("//") else "pedidos"


class EditarPedidoController(SoloAdminMixin, View):
    """Pantalla del admin para editar todo un pedido."""
    def get(self, request, id):
        """Muestra el formulario con los datos actuales del pedido."""
        pedido = get_object_or_404(Pedido.objects.select_related("repartidor"), pk=id)
        contexto = _contexto_comercio()
        contexto.update({
            "pedido": pedido,
            "estados": Pedido.ESTADOS,
            "pagos": Pedido.PAGOS,
            "repartidores": Repartidor.objects.all().order_by("nombre"),
            # Ítems actuales y menú, en JSON para el editor de productos (JS)
            "items_json": json_seguro([
                {"producto_id": i.producto_id, "nombre": i.nombre, "precio": float(i.precio_unitario),
                 "cantidad": i.cantidad, "aclaracion": i.aclaracion} for i in pedido.items.all()
            ]),
            "menu_json": json_seguro([
                {"id": p.id, "nombre": p.nombre, "precio": float(p.precio), "emoji": p.emoji,
                 "disponible": p.disponible} for p in Producto.objects.all()
            ]),
        })
        return render(request, "reparto/pedido_editar.html", contexto)

    def post(self, request, id):
        """Guarda los cambios y deja rutas, horas y avisos al día."""
        pedido = get_object_or_404(Pedido, pk=id)
        d = request.POST
        anterior = pedido.repartidor
        antes = (pedido.direccion, pedido.lat, pedido.lng, pedido.detalle, pedido.total)

        # --- Cliente y entrega ---
        nombre = d.get("cliente_nombre", "").strip()
        direccion = d.get("direccion", "").strip()
        if not nombre or not direccion:
            messages.error(request, "El pedido necesita nombre del cliente y dirección.")
            return redirect("editar_pedido", id=id)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            messages.error(request, "La dirección escrita y el pin del mapa no coinciden. Ubicala de nuevo.")
            return redirect("editar_pedido", id=id)
        pedido.cliente_nombre, pedido.cliente_telefono = nombre[:100], d.get("cliente_telefono", "").strip()[:30]
        pedido.direccion, pedido.lat, pedido.lng = direccion[:255], lat, lng
        pedido.notas = d.get("notas", "").strip()[:255]
        pedido.tiempo_preparacion_min = int(_decimal(d.get("tiempo_preparacion_min"), "15"))
        if d.get("forma_pago") in dict(Pedido.PAGOS):
            pedido.forma_pago = d.get("forma_pago")

        # --- Productos: se reemplazan todos los renglones por los del editor ---
        try:
            items = json.loads(d.get("items_json") or "[]")
        except json.JSONDecodeError:
            items = []
        renglones = []
        for it in items:
            cantidad = int(_decimal(it.get("cantidad"), "0"))
            nombre_item = str(it.get("nombre") or "").strip()[:60]
            if cantidad < 1 or not nombre_item:
                continue
            producto = Producto.objects.filter(pk=it.get("producto_id")).first() if it.get("producto_id") else None
            renglones.append(PedidoItem(
                pedido=pedido, producto=producto, nombre=nombre_item, cantidad=min(cantidad, 99),
                precio_unitario=_decimal(it.get("precio")), aclaracion=str(it.get("aclaracion") or "")[:120]))
        pedido.items.all().delete()
        PedidoItem.objects.bulk_create(renglones)

        # Con productos, el detalle y el subtotal salen de ellos; si no, se usa el texto libre
        if renglones:
            pedido.detalle = ", ".join(f"{r.cantidad}x {r.nombre}" + (f" ({r.aclaracion})" if r.aclaracion else "")
                                       for r in renglones)
            pedido.subtotal = sum((r.precio_unitario * r.cantidad for r in renglones), Decimal("0"))
        else:
            pedido.detalle = d.get("detalle", "").strip()
            pedido.subtotal = _decimal(d.get("subtotal"))
        pedido.costo_envio = _decimal(d.get("costo_envio"))
        pedido.total = pedido.subtotal + pedido.costo_envio
        pedido.save()

        # --- Repartidor: automático, ninguno o uno elegido ---
        eleccion = d.get("repartidor", "mantener")
        if eleccion == "auto":
            rutas.asignar_pedido(pedido)
        elif eleccion == "ninguno":
            pedido.repartidor = None
            pedido.save(update_fields=["repartidor"])
        elif eleccion.isdigit():
            pedido.repartidor = get_object_or_404(Repartidor, pk=int(eleccion))
            pedido.save(update_fields=["repartidor"])

        # --- Estado (usa cambiar_estado para que se generen los avisos) ---
        nuevo_estado = d.get("estado")
        if nuevo_estado in dict(Pedido.ESTADOS) and nuevo_estado != pedido.estado:
            rutas.cambiar_estado(pedido, nuevo_estado)
        pedido.refresh_from_db()

        # --- Rutas y horas estimadas al día ---
        for r in {anterior, pedido.repartidor} - {None}:
            rutas.recalcular_ruta(r)
        if pedido.estado == Pedido.PREPARACION and pedido.repartidor is None:
            pedido.hora_estimada = None
            pedido.save(update_fields=["hora_estimada"])

        # --- Avisos ---
        despues = (pedido.direccion, pedido.lat, pedido.lng, pedido.detalle, pedido.total)
        if antes != despues and pedido.estado in Pedido.ACTIVOS:
            Notificacion.objects.create(pedido=pedido, para_cliente=True, tipo=Notificacion.INFO,
                                        mensaje="El comercio actualizó los datos de tu pedido.")
        Notificacion.objects.create(pedido=pedido, tipo=Notificacion.INFO,
                                    mensaje=f"Pedido #{pedido.id} editado por {request.user.get_username()}.")
        messages.success(request, f"Pedido #{pedido.id} guardado.")
        return redirect(_volver(request))


class BorrarPedidoController(SoloAdminMixin, View):
    """Borra el pedido de la base (con sus productos y avisos). No se puede deshacer."""

    def post(self, request, id):
        """Borra el pedido y reordena la ruta del repartidor."""
        pedido = get_object_or_404(Pedido, pk=id)
        repartidor, numero = pedido.repartidor, pedido.id
        pedido.delete()
        if repartidor:                      # la ruta del cadete se reordena sin ese pedido
            rutas.recalcular_ruta(repartidor)
        Notificacion.objects.create(tipo=Notificacion.ALERTA,
                                    mensaje=f"Pedido #{numero} borrado por {request.user.get_username()}.")
        messages.warning(request, f"Pedido #{numero} borrado.")
        return redirect(_volver(request))
