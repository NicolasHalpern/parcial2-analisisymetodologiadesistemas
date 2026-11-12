"""
Lado del cliente: la tienda online del restaurante.
El cliente arma el carrito, ubica su dirección, ve costo de envío y hora estimada,
confirma, y el pedido entra al mismo circuito de reparto (asignación automática).
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from ..models import Cliente, Notificacion, Pedido, PedidoItem, Producto
from ..src import rutas
from ..src.permisos import SoloAdminMixin, SoloClienteMixin
from .reparto_controller import _contexto_comercio, json_seguro, _hora


def _precio(valor):
    """Decimal a float para mandarlo en JSON."""
    return float(valor)


def _perfil(request):
    """Datos para precargar el checkout del cliente logueado."""
    u = request.user
    if not u.is_authenticated:
        return None
    c = Cliente.objects.filter(usuario=u).first()
    return {
        "nombre": u.get_full_name() or u.first_name or u.username,
        "tel": c.telefono if c else "",
        "dir": c.direccion if c else "",
        "lat": c.lat if c else None,
        "lng": c.lng if c else None,
    }


class TiendaController(View):
    """La tienda online (página principal del sitio)."""
    def get(self, request):
        """Menú agrupado por categoría y, si hay sesión, los datos del cliente."""
        productos = list(Producto.objects.all())
        categorias = []
        for p in productos:
            if p.categoria not in categorias:
                categorias.append(p.categoria)
        contexto = _contexto_comercio()
        contexto.update({
            "categorias": categorias,
            "productos": productos,
            "productos_json": json_seguro([
                {"id": p.id, "nombre": p.nombre, "precio": _precio(p.precio), "emoji": p.emoji,
                 "disponible": p.disponible} for p in productos
            ]),
            "radio_km": rutas.RADIO_ENTREGA_KM,
            "perfil_json": json_seguro(_perfil(request)),
            "pagos": Pedido.PAGOS,
        })
        return render(request, "tienda/tienda.html", contexto)


class CotizarApi(View):
    """Antes de confirmar: si llegamos, cuánto sale el envío y a qué hora llega."""
    def get(self, request):
        """Recibe lat/lng (sin ellos estima desde el local)."""
        try:
            lat, lng = float(request.GET.get("lat")), float(request.GET.get("lng"))
        except (TypeError, ValueError):
            # Sin dirección: estimación genérica desde el local
            lat, lng = rutas.COMERCIO
        return JsonResponse(rutas.cotizar(lat, lng))


class CrearPedidoApi(SoloClienteMixin, View):
    """Confirma el pedido del cliente (requiere sesión)."""
    def post(self, request):
        """Valida, calcula precios en el servidor, guarda y asigna repartidor."""
        try:
            d = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Datos inválidos"}, status=400)

        nombre = (d.get("cliente_nombre") or "").strip()
        telefono = (d.get("cliente_telefono") or "").strip()
        direccion = (d.get("direccion") or "").strip()
        if not nombre or not telefono or not direccion:
            return JsonResponse({"ok": False, "error": "Completá nombre, teléfono y dirección."}, status=400)
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Ubicá tu dirección en el mapa."}, status=400)

        # Se vuelve a cotizar en el servidor: el envío no se toma de lo que mande el navegador
        cot = rutas.cotizar(lat, lng)
        if not cot["ok"]:
            return JsonResponse({"ok": False, "error": cot["error"]}, status=400)

        # Los precios salen SIEMPRE de la base, nunca de lo que manda el navegador
        renglones = []
        for it in d.get("items") or []:
            try:
                cantidad = int(it.get("cantidad", 1))
            except (TypeError, ValueError):
                continue
            if cantidad < 1:
                continue
            prod = Producto.objects.filter(pk=it.get("id")).first()
            if not prod:
                continue
            if not prod.disponible:
                return JsonResponse({"ok": False, "error": f"Se agotó: {prod.nombre}. Sacalo del carrito."}, status=400)
            renglones.append((prod, min(cantidad, 20), (it.get("aclaracion") or "").strip()[:120]))
        if not renglones:
            return JsonResponse({"ok": False, "error": "El carrito está vacío."}, status=400)

        forma_pago = d.get("forma_pago") if d.get("forma_pago") in dict(Pedido.PAGOS) else "EFECTIVO"
        subtotal = sum((p.precio * c for p, c, _ in renglones), Decimal("0"))
        envio = Decimal(str(cot["costo_envio"]))
        try:
            paga_con = Decimal(str(d.get("paga_con") or "0"))
        except InvalidOperation:
            paga_con = Decimal("0")

        notas = (d.get("notas") or "").strip()[:200]
        if forma_pago == "EFECTIVO" and paga_con > subtotal + envio:
            notas = (notas + f" · Paga con ${paga_con:,.0f}".replace(",", ".")).strip(" ·")

        # Se guarda la dirección en la cuenta para precargarla la próxima vez
        perfil, _ = Cliente.objects.get_or_create(usuario=request.user, defaults={"telefono": telefono[:30]})
        perfil.telefono, perfil.direccion, perfil.lat, perfil.lng = telefono[:30], direccion[:255], lat, lng
        perfil.save()

        pedido = Pedido.objects.create(
            cliente=request.user,
            cliente_nombre=nombre[:100], cliente_telefono=telefono[:30], direccion=direccion[:255],
            lat=lat, lng=lng, notas=notas[:255], origen=Pedido.WEB, forma_pago=forma_pago,
            detalle=", ".join(f"{c}x {p.nombre}" + (f" ({a})" if a else "") for p, c, a in renglones),
            subtotal=subtotal, costo_envio=envio, total=subtotal + envio,
            tiempo_preparacion_min=rutas.TIEMPO_PREPARACION_MIN,
        )
        PedidoItem.objects.bulk_create([
            PedidoItem(pedido=pedido, producto=p, nombre=p.nombre, precio_unitario=p.precio,
                       cantidad=c, aclaracion=a) for p, c, a in renglones
        ])
        Notificacion.objects.create(
            pedido=pedido, tipo=Notificacion.EXITO,
            mensaje=f"🛒 Nuevo pedido web #{pedido.id} de {nombre} — ${pedido.total:,.0f}".replace(",", "."))
        Notificacion.objects.create(
            pedido=pedido, tipo=Notificacion.INFO, para_cliente=True,
            mensaje="¡Recibimos tu pedido! Ya lo estamos preparando.")
        rutas.asignar_pedido(pedido)   # entra al mismo circuito que los pedidos del local
        pedido.refresh_from_db()
        return JsonResponse({
            "ok": True, "codigo": pedido.codigo, "id": pedido.id,
            "url": f"/seguimiento/{pedido.codigo}", "hora_estimada": _hora(pedido.hora_estimada),
        })


class MisPedidosApi(View):
    """Estado resumido de los pedidos guardados en el navegador del cliente."""

    def get(self, request):
        """Pedidos de la cuenta, o los códigos guardados en el navegador si no hay sesión."""
        if request.user.is_authenticated:
            pedidos = Pedido.objects.filter(cliente=request.user).order_by("-creado")[:10]
        else:
            codigos = [c.strip().upper() for c in request.GET.get("codigos", "").split(",") if c.strip()][:10]
            pedidos = Pedido.objects.filter(codigo__in=codigos)
        return JsonResponse({"cuenta": request.user.is_authenticated, "pedidos": [
            {"codigo": p.codigo, "id": p.id, "estado": p.estado, "estado_txt": p.get_estado_display(),
             "hora_estimada": _hora(p.hora_estimada), "total": float(p.total), "creado": _hora(p.creado)}
            for p in pedidos
        ]})


class MenuController(SoloAdminMixin, View):
    """Administración del menú (precios, stock) para el comercio."""

    def get(self, request):
        """Lista los productos para editarlos."""
        contexto = _contexto_comercio()
        contexto["productos"] = Producto.objects.all()
        return render(request, "reparto/menu.html", contexto)

    def post(self, request):
        """Agrega un producto, cambia su precio o lo marca sin stock."""
        d = request.POST
        accion = d.get("accion")
        if accion == "stock":
            p = get_object_or_404(Producto, pk=d.get("id"))
            p.disponible = not p.disponible
            p.save(update_fields=["disponible"])
            messages.info(request, f"{p.nombre}: {'disponible' if p.disponible else 'sin stock'}.")
        elif accion == "precio":
            p = get_object_or_404(Producto, pk=d.get("id"))
            try:
                p.precio = Decimal(d.get("precio").replace(",", "."))
                p.save(update_fields=["precio"])
                messages.success(request, f"Precio de {p.nombre} actualizado.")
            except (InvalidOperation, AttributeError):
                messages.error(request, "Precio inválido.")
        elif d.get("nombre"):
            try:
                precio = Decimal((d.get("precio") or "0").replace(",", "."))
            except InvalidOperation:
                precio = Decimal("0")
            Producto.objects.create(
                nombre=d.get("nombre").strip()[:60], categoria=(d.get("categoria") or "Otros").strip()[:25],
                descripcion=(d.get("descripcion") or "").strip()[:200], precio=precio,
                emoji=(d.get("emoji") or "🍽️").strip()[:8], orden=Producto.objects.count())
            messages.success(request, "Producto agregado al menú.")
        return redirect("menu")
