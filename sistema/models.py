"""
Modelos (tablas) del sistema.

Repartidor y Pedido son el corazón del reparto; Producto y PedidoItem, de la tienda;
Cliente es el perfil de quien se crea una cuenta; Notificacion guarda los avisos.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


# Nombre de tabla
class Prueba(models.Model):
    """Tabla de prueba de la clase (nombre y apellido)."""
    nombre = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)

    def __str__(self):
        """Texto con que se muestra el registro."""
        return f"{self.nombre} {self.apellido}"


class Producto(models.Model):
    """Ítem del menú del restaurante."""
    nombre = models.CharField(max_length=60)
    categoria = models.CharField(max_length=25)
    descripcion = models.CharField(max_length=200, blank=True, default="")
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    emoji = models.CharField(max_length=8, blank=True, default="🍽️")
    # Si se puede pedir ahora (sin stock = False)
    disponible = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        """Orden en que aparecen en el menú."""
        ordering = ["orden", "categoria", "nombre"]

    def __str__(self):
        """Nombre del producto."""
        return self.nombre


def generar_token():
    """Clave aleatoria para el link secreto de cada repartidor."""
    return secrets.token_urlsafe(16)


class Repartidor(models.Model):
    """Cadete propio del comercio, con su turno y su última ubicación GPS."""
    nombre = models.CharField(max_length=25)
    apellido = models.CharField(max_length=25)
    telefono = models.CharField(max_length=30, blank=True, default="")
    # Si está en turno y puede recibir pedidos
    disponible = models.BooleanField(default=True)
    # Última ubicación GPS conocida
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    ultima_ubicacion = models.DateTimeField(null=True, blank=True)
    # Color con el que se dibuja en el mapa
    color = models.CharField(max_length=7, default="#0d6efd")
    # Clave secreta del link que usa el cadete en su celular (no necesita usuario)
    token = models.CharField(max_length=32, unique=True, default=generar_token)

    def __str__(self):
        """Nombre y apellido del repartidor."""
        return f"{self.nombre} {self.apellido}"

    @property
    def nombre_completo(self):
        """Nombre y apellido juntos."""
        return f"{self.nombre} {self.apellido}"


def generar_codigo():
    """Código corto y difícil de adivinar para el link de seguimiento del cliente."""
    return secrets.token_hex(4).upper()


class Pedido(models.Model):
    """Un envío: datos del cliente, qué pidió, cuánto paga y en qué estado está el reparto."""
    PREPARACION = "PREPARACION"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"
    ESTADOS = [
        (PREPARACION, "En preparación"),
        (EN_CAMINO, "En camino"),
        (ENTREGADO, "Entregado"),
        (CANCELADO, "Cancelado"),
    ]
    # Estados en los que el pedido todavía ocupa al repartidor
    ACTIVOS = [PREPARACION, EN_CAMINO]

    # Datos del cliente
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="pedidos")
    cliente_nombre = models.CharField(max_length=100)
    cliente_telefono = models.CharField(max_length=30)
    direccion = models.CharField(max_length=255)
    lat = models.FloatField()
    lng = models.FloatField()
    detalle = models.TextField(blank=True, default="")
    notas = models.CharField(max_length=255, blank=True, default="")

    # Logística: lo calcula src/rutas.py (orden de visita, km y hora estimada)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PREPARACION)
    repartidor = models.ForeignKey(
        Repartidor, null=True, blank=True, on_delete=models.SET_NULL, related_name="pedidos"
    )
    orden_ruta = models.PositiveIntegerField(null=True, blank=True)
    distancia_km = models.FloatField(null=True, blank=True)
    hora_estimada = models.DateTimeField(null=True, blank=True)
    tiempo_preparacion_min = models.PositiveIntegerField(default=15)
    alerta_demora = models.BooleanField(default=False)

    # Venta
    WEB = "WEB"
    LOCAL = "LOCAL"
    ORIGENES = [(WEB, "Tienda online"), (LOCAL, "Cargado en el local")]
    PAGOS = [("EFECTIVO", "Efectivo"), ("TRANSFERENCIA", "Transferencia"), ("TARJETA", "Tarjeta (posnet)")]
    origen = models.CharField(max_length=6, choices=ORIGENES, default=LOCAL)
    forma_pago = models.CharField(max_length=14, choices=PAGOS, default="EFECTIVO")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Código del link de seguimiento público (/seguimiento/<codigo>)
    codigo = models.CharField(max_length=8, unique=True, default=generar_codigo)
    creado = models.DateTimeField(default=timezone.now)
    salida = models.DateTimeField(null=True, blank=True)
    entregado = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Los pedidos más nuevos primero."""
        ordering = ["-creado"]

    def __str__(self):
        """Número y cliente del pedido."""
        return f"Pedido #{self.id} - {self.cliente_nombre}"

    @property
    def listo_a(self):
        """Momento en que la cocina/depósito termina de prepararlo."""
        return self.creado + timedelta(minutes=self.tiempo_preparacion_min)

    @property
    def minutos_restantes(self):
        """Minutos que faltan para la hora estimada (None si ya no está activo)."""
        if not self.hora_estimada or self.estado not in self.ACTIVOS:
            return None
        delta = (self.hora_estimada - timezone.now()).total_seconds() / 60
        return max(0, round(delta))


class Notificacion(models.Model):
    """Aviso del sistema. Lo ve el panel y, si para_cliente=True, también el cliente."""
    INFO = "info"
    EXITO = "success"
    ALERTA = "warning"
    PELIGRO = "danger"
    TIPOS = [(INFO, "Info"), (EXITO, "Éxito"), (ALERTA, "Alerta"), (PELIGRO, "Peligro")]

    pedido = models.ForeignKey(
        Pedido, null=True, blank=True, on_delete=models.CASCADE, related_name="notificaciones"
    )
    mensaje = models.CharField(max_length=255)
    tipo = models.CharField(max_length=10, choices=TIPOS, default=INFO)
    # True = también la ve el cliente en su página de seguimiento
    para_cliente = models.BooleanField(default=False)
    creada = models.DateTimeField(default=timezone.now)
    leida = models.BooleanField(default=False)

    class Meta:
        """Los avisos más nuevos primero."""
        ordering = ["-creada"]

    def __str__(self):
        """Texto del aviso."""
        return self.mensaje


class PedidoItem(models.Model):
    """Renglón del pedido. Se copian nombre y precio por si después cambia el menú."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Producto, null=True, blank=True, on_delete=models.SET_NULL)
    nombre = models.CharField(max_length=60)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad = models.PositiveIntegerField(default=1)
    aclaracion = models.CharField(max_length=120, blank=True, default="")

    @property
    def importe(self):
        """Precio unitario por cantidad."""
        return self.precio_unitario * self.cantidad

    def __str__(self):
        """Cantidad y producto, ej: 2 x Muzzarella."""
        return f"{self.cantidad} x {self.nombre}"


class Cliente(models.Model):
    """Perfil del cliente que se crea una cuenta en la tienda."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cliente")
    telefono = models.CharField(max_length=30)
    # Última dirección usada, para no cargarla de nuevo
    direccion = models.CharField(max_length=255, blank=True, default="")
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    def __str__(self):
        """Nombre del cliente o, si no cargó, su usuario."""
        return self.usuario.get_full_name() or self.usuario.username
