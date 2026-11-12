"""
Pantallas y API del reparto: carga de pedidos, panel en vivo, repartidores,
app del cadete y seguimiento del cliente. Las páginas consultan la API cada
pocos segundos para mostrar todo "en tiempo real".
"""
import json
import os
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.views import View

from ..models import Notificacion, Pedido, Repartidor
from ..src import rutas
from ..src.permisos import AdminOCadeteMixin, SoloAdminMixin, es_admin, puede_usar_repartidor

# Colores con que se dibuja a cada repartidor en el mapa
COLORES = ["#0d6efd", "#dc3545", "#198754", "#fd7e14", "#6f42c1", "#20c997", "#d63384"]


# ---------------------------------------------------------------- utilidades
def _datos(request):
    """Acepta tanto formularios como JSON (fetch desde el navegador)."""
    if request.content_type == "application/json":
        try:
            return json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST


def _inicio_del_dia():
    # Evita el lookup __date (en MySQL necesita tablas de zonas horarias cargadas)
    """Hoy a las 00:00 en la zona horaria del comercio."""
    return timezone.make_aware(datetime.combine(timezone.localdate(), time.min))


def _txt(valor):
    """Escapa texto escrito por personas antes de mandarlo a las pantallas.
    Las páginas arman HTML con JavaScript: sin esto, un nombre como <script> se ejecutaría."""
    return escape(valor) if valor else valor


def json_seguro(datos):
    """JSON para incrustar dentro de <script> sin que un texto pueda cerrar la etiqueta."""
    return json.dumps(datos).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _hora(dt):
    """Fecha/hora a texto HH:MM en hora local (o None)."""
    return timezone.localtime(dt).strftime("%H:%M") if dt else None


def _contexto_comercio():
    """Nombre y ubicación del comercio, que usan todas las plantillas."""
    return {
        "comercio_nombre": os.getenv("COMERCIO_NOMBRE", "Mi Comercio"),
        "comercio_lat": rutas.COMERCIO[0],
        "comercio_lng": rutas.COMERCIO[1],
    }


def serializar_pedido(p, publico=False):
    """Pedido a diccionario para la API. Con publico=True oculta datos que el cliente no necesita."""
    data = {
        "id": p.id,
        "codigo": p.codigo,
        "estado": p.estado,
        "estado_txt": p.get_estado_display(),
        "direccion": _txt(p.direccion),
        "lat": p.lat,
        "lng": p.lng,
        "orden_ruta": p.orden_ruta,
        "hora_estimada": _hora(p.hora_estimada),
        "minutos_restantes": p.minutos_restantes,
        "entregado": _hora(p.entregado),
        "demorado": p.alerta_demora and p.estado in Pedido.ACTIVOS,
        "repartidor": _txt(p.repartidor.nombre_completo) if p.repartidor else None,
        "repartidor_id": p.repartidor_id,
        "origen": p.origen,
        "forma_pago": p.get_forma_pago_display(),
        "subtotal": float(p.subtotal),
        "costo_envio": float(p.costo_envio),
        "total": float(p.total),
        "items": [{"nombre": _txt(i.nombre), "cantidad": i.cantidad, "aclaracion": _txt(i.aclaracion),
                   "importe": float(i.importe)} for i in p.items.all()],
    }
    if not publico:
        data.update({
            "cliente": _txt(p.cliente_nombre),
            "telefono": _txt(p.cliente_telefono),
            "detalle": _txt(p.detalle),
            "notas": _txt(p.notas),
            "creado": _hora(p.creado),
            "distancia_km": p.distancia_km,
        })
    return data


def serializar_repartidor(r):
    """Repartidor a diccionario para el panel, con su situación actual."""
    activos = r.pedidos.filter(estado__in=Pedido.ACTIVOS)
    if activos.filter(estado=Pedido.EN_CAMINO).exists():
        situacion = "En reparto"
    elif activos.exists():
        situacion = "Esperando pedidos"
    else:
        situacion = "Libre" if r.disponible else "Fuera de turno"
    return {
        "id": r.id,
        "nombre": _txt(r.nombre_completo),
        "telefono": _txt(r.telefono),
        "disponible": r.disponible,
        "color": r.color,
        "lat": r.lat,
        "lng": r.lng,
        "ultima_ubicacion": _hora(r.ultima_ubicacion),
        "situacion": situacion,
        "pedidos": [p.id for p in activos.order_by("orden_ruta")],
        "app_url": f"/repartidor/{r.id}?t={r.token}",
    }


# ======================================================================
#  Páginas
# ======================================================================
class PedidosController(SoloAdminMixin, View):
    """Carga de pedidos: guarda los datos del cliente y asigna automáticamente."""

    def get(self, request):
        """Lista los pedidos de hoy y los activos."""
        contexto = _contexto_comercio()
        contexto["pedidos"] = Pedido.objects.select_related("repartidor").filter(
            creado__gte=_inicio_del_dia()) | Pedido.objects.filter(estado__in=Pedido.ACTIVOS)
        contexto["pedidos"] = contexto["pedidos"].distinct().order_by("-creado")[:50]
        contexto["hay_repartidores"] = Repartidor.objects.filter(disponible=True).exists()
        return render(request, "reparto/pedidos.html", contexto)

    def post(self, request):
        """Crea el pedido cargado en el local y lo asigna automáticamente."""
        d = request.POST
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            messages.error(request, "Marcá la ubicación del cliente en el mapa (o buscá la dirección).")
            return redirect("pedidos")
        if not d.get("cliente_nombre") or not d.get("direccion"):
            messages.error(request, "Faltan el nombre del cliente o la dirección.")
            return redirect("pedidos")

        pedido = Pedido.objects.create(
            cliente_nombre=d.get("cliente_nombre").strip(),
            cliente_telefono=d.get("cliente_telefono", "").strip(),
            direccion=d.get("direccion").strip(),
            lat=lat, lng=lng,
            detalle=d.get("detalle", "").strip(),
            notas=d.get("notas", "").strip(),
            tiempo_preparacion_min=int(d.get("tiempo_preparacion_min") or 15),
        )
        repartidor = rutas.asignar_pedido(pedido)
        pedido.refresh_from_db()
        link = request.build_absolute_uri(f"/seguimiento/{pedido.codigo}")
        if repartidor:
            messages.success(
                request,
                f"Pedido #{pedido.id} asignado a {repartidor.nombre_completo}. "
                f"Llega aprox. {_hora(pedido.hora_estimada)}. Link para el cliente: {link}")
        else:
            messages.warning(request, f"Pedido #{pedido.id} guardado, pero no hay repartidores disponibles. "
                                      f"Link para el cliente: {link}")
        return redirect("pedidos")


class PanelController(SoloAdminMixin, View):
    """Panel central: mapa en vivo + estado de cada envío + alertas."""

    def get(self, request):
        """La página es fija: los datos los trae el JavaScript desde /api/estado."""
        return render(request, "reparto/panel.html", _contexto_comercio())


class RepartidoresController(SoloAdminMixin, View):
    """Alta de repartidores y manejo de su turno."""
    def get(self, request):
        """Lista el equipo con su link para el celular."""
        contexto = _contexto_comercio()
        contexto["repartidores"] = Repartidor.objects.all().order_by("nombre")
        return render(request, "reparto/repartidores.html", contexto)

    def post(self, request):
        """Agrega un repartidor o le cambia el turno."""
        d = request.POST
        if d.get("accion") == "turno":
            r = get_object_or_404(Repartidor, pk=d.get("id"))
            r.disponible = not r.disponible
            r.save(update_fields=["disponible"])
            if r.disponible:
                rutas.asignar_sin_repartidor()
            messages.info(request, f"{r.nombre_completo}: {'en turno' if r.disponible else 'fuera de turno'}.")
        elif d.get("nombre"):
            r = Repartidor.objects.create(
                nombre=d.get("nombre").strip(),
                apellido=d.get("apellido", "").strip(),
                telefono=d.get("telefono", "").strip(),
                color=COLORES[Repartidor.objects.count() % len(COLORES)],
                lat=rutas.COMERCIO[0], lng=rutas.COMERCIO[1],
            )
            rutas.asignar_sin_repartidor()
            messages.success(request, f"Repartidor {r.nombre_completo} agregado.")
        return redirect("repartidores")


class RepartidorAppController(AdminOCadeteMixin, View):
    """Pantalla para el celular del cadete: su ruta, botones y envío de GPS."""

    def get(self, request, id):
        """Muestra la app del cadete."""
        r = get_object_or_404(Repartidor, pk=id)
        contexto = _contexto_comercio()
        contexto["repartidor"] = r
        return render(request, "reparto/repartidor_app.html", contexto)


class SeguimientoController(View):
    """Página pública que recibe el cliente: estado, mapa y hora estimada."""

    def get(self, request, codigo):
        """Muestra el seguimiento de un pedido por su código."""
        pedido = get_object_or_404(Pedido, codigo=codigo.upper())
        contexto = _contexto_comercio()
        contexto["pedido"] = pedido
        return render(request, "reparto/seguimiento.html", contexto)


# ======================================================================
#  API JSON (la consultan el panel, el cadete y el cliente cada pocos seg.)
# ======================================================================
class EstadoApi(SoloAdminMixin, View):
    """Todo lo que necesita el panel en vivo, en una sola consulta."""
    def get(self, request):
        """Repartidores, pedidos, resumen y avisos nuevos (desde_notif=último id visto)."""
        rutas.revisar_demoras()   # genera alertas de pedidos que pasaron su hora estimada
        pedidos = Pedido.objects.select_related("repartidor").filter(estado__in=Pedido.ACTIVOS) | \
            Pedido.objects.select_related("repartidor").filter(creado__gte=_inicio_del_dia())
        pedidos = pedidos.distinct().order_by("repartidor_id", "orden_ruta", "-creado").prefetch_related("items")

        # El panel manda el último aviso que ya mostró, así solo recibe los nuevos
        desde = int(request.GET.get("desde_notif") or 0)
        notifs = Notificacion.objects.filter(id__gt=desde).order_by("-id")[:20]

        entregados = [p for p in pedidos if p.estado == Pedido.ENTREGADO]
        a_tiempo = sum(1 for p in entregados if p.hora_estimada is None or p.entregado <= p.hora_estimada
                       + timedelta(minutes=rutas.DEMORA_ALERTA_MIN))
        return JsonResponse({
            "ahora": _hora(timezone.now()),
            "comercio": {"lat": rutas.COMERCIO[0], "lng": rutas.COMERCIO[1]},
            "repartidores": [serializar_repartidor(r) for r in Repartidor.objects.all().order_by("nombre")],
            "pedidos": [serializar_pedido(p) for p in pedidos],
            "notificaciones": [
                {"id": n.id, "mensaje": _txt(n.mensaje), "tipo": n.tipo, "hora": _hora(n.creada)}
                for n in reversed(list(notifs))
            ],
            "resumen": {
                "preparacion": sum(1 for p in pedidos if p.estado == Pedido.PREPARACION),
                "en_camino": sum(1 for p in pedidos if p.estado == Pedido.EN_CAMINO),
                "entregados": len(entregados),
                "a_tiempo": a_tiempo,
                "demorados": sum(1 for p in pedidos if p.alerta_demora and p.estado in Pedido.ACTIVOS),
            },
        })


class PedidoEstadoApi(View):
    """Cambia el estado de un pedido (admin o el repartidor de ese pedido)."""
    def post(self, request, id):
        """Recibe {estado} y aplica el cambio con sus avisos."""
        pedido = get_object_or_404(Pedido, pk=id)
        nuevo = _datos(request).get("estado")
        if nuevo not in dict(Pedido.ESTADOS):
            return JsonResponse({"ok": False, "error": "Estado inválido"}, status=400)
        # El repartidor solo puede marcar SUS pedidos como en camino o entregados
        if not es_admin(request):
            es_suyo = pedido.repartidor is not None and puede_usar_repartidor(request, pedido.repartidor)
            if not es_suyo or nuevo not in (Pedido.EN_CAMINO, Pedido.ENTREGADO):
                return JsonResponse({"ok": False, "error": "No autorizado"}, status=403)
        rutas.cambiar_estado(pedido, nuevo)
        return JsonResponse({"ok": True, "pedido": serializar_pedido(pedido)})


class PedidoReasignarApi(SoloAdminMixin, View):
    """Pasa un pedido en preparación a otro repartidor."""
    def post(self, request, id):
        """Con repartidor_id lo asigna a mano; sin él, elige el mejor automáticamente."""
        pedido = get_object_or_404(Pedido, pk=id)
        if pedido.estado != Pedido.PREPARACION:
            return JsonResponse({"ok": False, "error": "Solo se reasignan pedidos en preparación"}, status=400)
        rid = _datos(request).get("repartidor_id")
        anterior = pedido.repartidor
        if rid:
            pedido.repartidor = get_object_or_404(Repartidor, pk=rid)
            pedido.save(update_fields=["repartidor"])
            rutas.recalcular_ruta(pedido.repartidor)
            if anterior and anterior != pedido.repartidor:
                rutas.recalcular_ruta(anterior)
            Notificacion.objects.create(pedido=pedido, mensaje=(
                f"Pedido #{pedido.id} reasignado manualmente a {pedido.repartidor.nombre_completo}."))
        else:
            rutas.asignar_pedido(pedido)
        pedido.refresh_from_db()
        return JsonResponse({"ok": True, "pedido": serializar_pedido(pedido)})


class RepartidorUbicacionApi(AdminOCadeteMixin, View):
    """Recibe el GPS del celular del cadete."""
    def post(self, request, id):
        """Guarda la posición y recalcula las horas estimadas de sus entregas."""
        r = get_object_or_404(Repartidor, pk=id)
        d = _datos(request)
        try:
            r.lat, r.lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "lat/lng inválidos"}, status=400)
        r.ultima_ubicacion = timezone.now()
        r.save(update_fields=["lat", "lng", "ultima_ubicacion"])
        # La ETA se recalcula con la posición real del cadete
        if r.pedidos.filter(estado=Pedido.EN_CAMINO).exists():
            rutas.recalcular_ruta(r)
        return JsonResponse({"ok": True})


class RepartidorRutaApi(AdminOCadeteMixin, View):
    """La ruta ordenada de un repartidor, para su app."""
    def get(self, request, id):
        """Devuelve el repartidor y sus pedidos activos en orden de visita."""
        r = get_object_or_404(Repartidor, pk=id)
        pedidos = r.pedidos.filter(estado__in=Pedido.ACTIVOS).order_by("orden_ruta")
        return JsonResponse({
            "repartidor": serializar_repartidor(r),
            "pedidos": [serializar_pedido(p) for p in pedidos],
            "comercio": {"lat": rutas.COMERCIO[0], "lng": rutas.COMERCIO[1]},
        })


class RepartidorSalirApi(AdminOCadeteMixin, View):
    """Botón 'Salir a reparto' del cadete."""
    def post(self, request, id):
        """Pasa todos sus pedidos en preparación a 'en camino'."""
        r = get_object_or_404(Repartidor, pk=id)
        rutas.salir_a_reparto(r)
        return JsonResponse({"ok": True})


class RepartidorTurnoApi(AdminOCadeteMixin, View):
    """Prende o apaga el turno de un repartidor."""
    def post(self, request, id):
        """Si entra en turno, toma los pedidos que estaban sin repartidor."""
        r = get_object_or_404(Repartidor, pk=id)
        r.disponible = bool(_datos(request).get("disponible", not r.disponible))
        r.save(update_fields=["disponible"])
        if r.disponible:
            rutas.asignar_sin_repartidor()
        return JsonResponse({"ok": True, "disponible": r.disponible})


class SeguimientoApi(View):
    """Datos públicos que consulta la página del cliente cada pocos segundos."""
    def get(self, request, codigo):
        """Estado, hora estimada, posición del cadete (si va en camino) y avisos."""
        p = get_object_or_404(Pedido, codigo=codigo.upper())
        r = p.repartidor
        mostrar_cadete = r is not None and p.estado == Pedido.EN_CAMINO and r.lat is not None
        return JsonResponse({
            "pedido": serializar_pedido(p, publico=True),
            "repartidor": {"lat": r.lat, "lng": r.lng, "nombre": _txt(r.nombre),
                           "ultima_ubicacion": _hora(r.ultima_ubicacion)} if mostrar_cadete else None,
            "entregas_antes": (r.pedidos.filter(estado=Pedido.EN_CAMINO, orden_ruta__lt=p.orden_ruta).count()
                               if mostrar_cadete and p.orden_ruta else 0),
            "notificaciones": [
                {"id": n.id, "mensaje": _txt(n.mensaje), "tipo": n.tipo, "hora": _hora(n.creada)}
                for n in p.notificaciones.filter(para_cliente=True).order_by("id")
            ],
        })
