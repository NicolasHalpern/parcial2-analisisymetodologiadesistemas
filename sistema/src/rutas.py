"""
Lógica de reparto: distancias, ruta óptima, asignación automática y ETA.

- Distancia: fórmula de Haversine (línea recta) multiplicada por un factor
  urbano (las calles no son línea recta). Es una estimación sin depender de
  APIs pagas; se puede reemplazar por OSRM/Google más adelante cambiando
  solo `distancia_km`.
- Ruta óptima por repartidor: vecino más cercano + mejora 2-opt.
- Asignación: el pedido nuevo va al repartidor disponible para el que la
  ruta resultante termina antes (combina cercanía y carga de trabajo).
"""
import math
import os
from datetime import timedelta
from pathlib import Path

from django.utils import timezone
from dotenv import load_dotenv

# Parámetros configurables en sistema/.env (con valores por defecto)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

COMERCIO = (
    float(os.getenv("COMERCIO_LAT", "-34.6037")),
    float(os.getenv("COMERCIO_LNG", "-58.3816")),
)
VELOCIDAD_KMH = float(os.getenv("VELOCIDAD_KMH", "22"))   # moto/bici en ciudad
FACTOR_URBANO = float(os.getenv("FACTOR_URBANO", "1.35"))  # recorrido real vs línea recta
MIN_POR_ENTREGA = float(os.getenv("MIN_POR_ENTREGA", "3"))  # estacionar, tocar timbre, cobrar
MAX_PEDIDOS_POR_VIAJE = int(os.getenv("MAX_PEDIDOS_POR_VIAJE", "6"))
DEMORA_ALERTA_MIN = int(os.getenv("DEMORA_ALERTA_MIN", "10"))
# Tienda online
TIEMPO_PREPARACION_MIN = int(os.getenv("TIEMPO_PREPARACION_MIN", "15"))
RADIO_ENTREGA_KM = float(os.getenv("RADIO_ENTREGA_KM", "6"))
COSTO_ENVIO_BASE = float(os.getenv("COSTO_ENVIO_BASE", "1500"))
COSTO_ENVIO_POR_KM = float(os.getenv("COSTO_ENVIO_POR_KM", "400"))


# ---------------------------------------------------------------- distancias
def distancia_km(a, b):
    """Distancia entre dos puntos (lat, lng): Haversine por el factor urbano."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h)) * FACTOR_URBANO


def minutos_viaje(km):
    """Minutos que tarda en recorrer esos km a la velocidad configurada."""
    return km / VELOCIDAD_KMH * 60


def _largo(origen, puntos):
    """Km totales de recorrer los puntos en ese orden, desde el origen."""
    total, actual = 0.0, origen
    for p in puntos:
        total += distancia_km(actual, p)
        actual = p
    return total


# --------------------------------------------------------------- ruta óptima
def ordenar_ruta(origen, pedidos):
    """Devuelve los pedidos en el orden de visita más corto encontrado."""
    pendientes = list(pedidos)
    if len(pendientes) <= 1:
        return pendientes

    # 1) Vecino más cercano: desde donde estoy, voy siempre al pedido más próximo
    ruta, actual = [], origen
    while pendientes:
        prox = min(pendientes, key=lambda p: distancia_km(actual, (p.lat, p.lng)))
        ruta.append(prox)
        pendientes.remove(prox)
        actual = (prox.lat, prox.lng)

    # 2) Mejora 2-opt: prueba invertir tramos de la ruta y se queda con el cambio
    #    si el recorrido total queda más corto (repite hasta que no mejore más)
    def coords(r):
        """Lista de (lat, lng) de los pedidos de la ruta."""
        return [(p.lat, p.lng) for p in r]

    mejor = _largo(origen, coords(ruta))
    mejoro = True
    while mejoro:
        mejoro = False
        for i in range(len(ruta) - 1):
            for j in range(i + 1, len(ruta)):
                nueva = ruta[:i] + ruta[i:j + 1][::-1] + ruta[j + 1:]
                largo = _largo(origen, coords(nueva))
                if largo + 1e-9 < mejor:
                    ruta, mejor, mejoro = nueva, largo, True
    return ruta


def simular_ruta(repartidor, pedidos):
    """
    Calcula orden de visita + ETA sin guardar nada.

    Si el repartidor ya está en la calle, primero termina los pedidos que lleva
    (desde su ubicación actual), vuelve al local y recién ahí sale con la tanda
    siguiente. Si está en el local, sale cuando el último pedido esté listo.
    Devuelve (ruta, [(pedido, eta, km)], hora_fin).
    """
    from ..models import Pedido

    ahora = timezone.now()
    if not pedidos:
        return [], [], ahora
    en_camino = [p for p in pedidos if p.estado == Pedido.EN_CAMINO]
    en_prep = [p for p in pedidos if p.estado == Pedido.PREPARACION]

    plan, ruta, t = [], [], ahora

    def recorrer(origen, lista, inicio):
        """Recorre un tramo en orden óptimo y anota la hora de cada entrega."""
        tramo = ordenar_ruta(origen, lista)
        hora, actual = inicio, origen
        for p in tramo:
            km = distancia_km(actual, (p.lat, p.lng))
            hora = hora + timedelta(minutes=minutos_viaje(km) + MIN_POR_ENTREGA)
            plan.append((p, hora, km))
            actual = (p.lat, p.lng)
        return tramo, hora, actual

    if en_camino:
        origen = (repartidor.lat, repartidor.lng) if repartidor.lat is not None else COMERCIO
        tramo, t, ultimo = recorrer(origen, en_camino, ahora)
        ruta += tramo
        if en_prep:  # vuelve al local a buscar la próxima tanda
            t = t + timedelta(minutes=minutos_viaje(distancia_km(ultimo, COMERCIO)))
    if en_prep:
        salida = max([t] + [p.listo_a for p in en_prep])
        tramo, t, _ = recorrer(COMERCIO, en_prep, salida)
        ruta += tramo
    return ruta, plan, t


def recalcular_ruta(repartidor):
    """Reordena y actualiza la ETA de todos los pedidos activos del repartidor."""
    from ..models import Pedido

    if repartidor is None:
        return []
    activos = list(repartidor.pedidos.filter(estado__in=Pedido.ACTIVOS))
    _, plan, _ = simular_ruta(repartidor, activos)
    for orden, (p, eta, km) in enumerate(plan, start=1):
        p.orden_ruta, p.hora_estimada, p.distancia_km = orden, eta, round(km, 2)
        p.save(update_fields=["orden_ruta", "hora_estimada", "distancia_km"])
    return plan


# ---------------------------------------------------------------- asignación
def _mejor_opcion(pedido):
    """
    Repartidor disponible cuya ruta, sumándole este pedido, termina antes.
    Así se tiene en cuenta a la vez la cercanía (km extra que agrega el pedido)
    y la disponibilidad/carga (cuánto trabajo pendiente tiene cada uno).
    Devuelve (repartidor, plan) o (None, []).
    """
    from ..models import Pedido, Repartidor

    mejor, mejor_fin, mejor_plan = None, None, []
    for r in Repartidor.objects.filter(disponible=True):
        activos = list(r.pedidos.filter(estado__in=Pedido.ACTIVOS))
        if pedido.pk:
            activos = [p for p in activos if p.pk != pedido.pk]
        tanda = [p for p in activos if p.estado == Pedido.PREPARACION]
        if len(tanda) >= MAX_PEDIDOS_POR_VIAJE:
            continue
        _, plan, fin = simular_ruta(r, activos + [pedido])
        if mejor_fin is None or fin < mejor_fin:
            mejor, mejor_fin, mejor_plan = r, fin, plan
    return mejor, mejor_plan


def elegir_repartidor(pedido):
    """Solo el repartidor elegido (ver _mejor_opcion)."""
    return _mejor_opcion(pedido)[0]


def asignar_pedido(pedido):
    """Asigna el pedido al mejor repartidor, recalcula rutas y avisa al panel."""
    from ..models import Notificacion

    anterior = pedido.repartidor
    pedido.repartidor = elegir_repartidor(pedido)
    pedido.save(update_fields=["repartidor"])
    if anterior and anterior != pedido.repartidor:
        recalcular_ruta(anterior)
    if pedido.repartidor is None:
        pedido.hora_estimada = None
        pedido.save(update_fields=["hora_estimada"])
        Notificacion.objects.create(
            pedido=pedido, tipo=Notificacion.PELIGRO,
            mensaje=f"Pedido #{pedido.id}: no hay repartidores disponibles.")
        return None
    recalcular_ruta(pedido.repartidor)
    pedido.refresh_from_db()
    Notificacion.objects.create(
        pedido=pedido, tipo=Notificacion.INFO,
        mensaje=(f"Pedido #{pedido.id} asignado a {pedido.repartidor.nombre_completo} "
                 f"(llega ~{timezone.localtime(pedido.hora_estimada):%H:%M})."))
    return pedido.repartidor


def asignar_sin_repartidor():
    """Intenta asignar los pedidos que quedaron esperando repartidor."""
    from ..models import Pedido

    for p in Pedido.objects.filter(estado=Pedido.PREPARACION, repartidor__isnull=True).order_by("creado"):
        asignar_pedido(p)


# ------------------------------------------------------------------ estados
def cambiar_estado(pedido, nuevo):
    """Cambia el estado del pedido, recalcula la ruta y genera los avisos."""
    from ..models import Notificacion, Pedido

    if nuevo == pedido.estado:
        return pedido
    ahora = timezone.now()
    pedido.estado = nuevo
    if nuevo == Pedido.EN_CAMINO:
        pedido.salida = ahora
    if nuevo == Pedido.ENTREGADO:
        pedido.entregado = ahora
        pedido.orden_ruta = None
    pedido.save()

    if pedido.repartidor:
        recalcular_ruta(pedido.repartidor)
        pedido.refresh_from_db()

    if nuevo == Pedido.EN_CAMINO:
        hora = timezone.localtime(pedido.hora_estimada).strftime("%H:%M") if pedido.hora_estimada else "--"
        Notificacion.objects.create(
            pedido=pedido, tipo=Notificacion.INFO, para_cliente=True,
            mensaje=f"Pedido #{pedido.id} salió con {pedido.repartidor or 'el repartidor'}. Llega aprox. {hora}.")
    elif nuevo == Pedido.ENTREGADO:
        Notificacion.objects.create(
            pedido=pedido, tipo=Notificacion.EXITO, para_cliente=True,
            mensaje=f"Pedido #{pedido.id} entregado a {pedido.cliente_nombre}.")
    elif nuevo == Pedido.CANCELADO:
        Notificacion.objects.create(
            pedido=pedido, tipo=Notificacion.PELIGRO, para_cliente=True,
            mensaje=f"Pedido #{pedido.id} cancelado.")
    if nuevo != Pedido.PREPARACION:
        asignar_sin_repartidor()  # se liberó lugar: toman los pedidos que esperaban
    return pedido


def salir_a_reparto(repartidor):
    """El cadete sale del local con todos sus pedidos en preparación."""
    from ..models import Pedido

    repartidor.lat, repartidor.lng = repartidor.lat or COMERCIO[0], repartidor.lng or COMERCIO[1]
    repartidor.ultima_ubicacion = timezone.now()
    repartidor.save()
    for p in repartidor.pedidos.filter(estado=Pedido.PREPARACION):
        cambiar_estado(p, Pedido.EN_CAMINO)


def revisar_demoras():
    """Genera una alerta (una sola vez) para los pedidos que pasaron su ETA."""
    from ..models import Notificacion, Pedido

    limite = timezone.now() - timedelta(minutes=DEMORA_ALERTA_MIN)
    for p in Pedido.objects.filter(estado__in=Pedido.ACTIVOS, alerta_demora=False,
                                   hora_estimada__lt=limite):
        p.alerta_demora = True
        p.save(update_fields=["alerta_demora"])
        Notificacion.objects.create(
            pedido=p, tipo=Notificacion.ALERTA,
            mensaje=f"Pedido #{p.id} demorado: ya pasaron {DEMORA_ALERTA_MIN} min de la hora estimada.")


# ------------------------------------------------------------ tienda online
def costo_envio(km):
    """Costo de envío según la distancia, redondeado a $100."""
    return round((COSTO_ENVIO_BASE + COSTO_ENVIO_POR_KM * km) / 100) * 100


def cotizar(lat, lng, tiempo_preparacion_min=None):
    """
    Antes de confirmar: ¿llegamos?, ¿cuánto sale el envío? y ¿a qué hora llega?
    Simula la asignación sin guardar nada en la base.
    """
    from ..models import Pedido, Repartidor

    km = distancia_km(COMERCIO, (lat, lng))
    if km > RADIO_ENTREGA_KM:
        return {"ok": False, "km": round(km, 1),
                "error": f"Tu dirección está a {km:.1f} km y entregamos hasta {RADIO_ENTREGA_KM:g} km."}

    prueba = Pedido(lat=lat, lng=lng, estado=Pedido.PREPARACION, creado=timezone.now(),
                    tiempo_preparacion_min=tiempo_preparacion_min or TIEMPO_PREPARACION_MIN)
    # Misma decisión que tomará asignar_pedido(): lo prometido coincide con lo asignado
    _, plan = _mejor_opcion(prueba)
    mejor_eta = next((t for p, t, _ in plan if p is prueba), None)
    con_lugar = mejor_eta is not None
    if mejor_eta is None:  # sin cadetes: estimación directa desde el local
        mejor_eta = prueba.listo_a + timedelta(minutes=minutos_viaje(km) + MIN_POR_ENTREGA + 15)
    minutos = max(1, round((mejor_eta - timezone.now()).total_seconds() / 60))
    return {"ok": True, "km": round(km, 1), "costo_envio": costo_envio(km),
            "hora_estimada": timezone.localtime(mejor_eta).strftime("%H:%M"),
            "minutos": minutos, "hay_repartidores": con_lugar}
