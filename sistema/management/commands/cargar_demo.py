"""
Carga datos de ejemplo: 3 repartidores y algunos pedidos alrededor del comercio.
Uso:  python manage.py cargar_demo
"""
import random

from django.core.management.base import BaseCommand

from sistema.models import Pedido, Producto, Repartidor
from sistema.src import rutas

# (nombre, apellido, color en el mapa)
REPARTIDORES = [("Juan", "Pérez", "#0d6efd"), ("Lucía", "Gómez", "#dc3545"), ("Martín", "Díaz", "#198754")]
CLIENTES = [
    ("Ana Torres", "Av. Rivadavia 2100"), ("Carlos Ruiz", "Av. Callao 800"),
    ("Sofía López", "Av. Belgrano 1500"), ("Diego Fernández", "Tucumán 1800"),
    ("Valentina Sosa", "Av. de Mayo 1200"), ("Pablo Medina", "Defensa 900"),
    ("Camila Rojas", "Santa Fe 1700"), ("Nicolás Vega", "Bolívar 1100"),
]

# Menú de ejemplo: (categoría, emoji, nombre, descripción, precio)
MENU = [
    ("Pizzas", "🍕", "Muzzarella", "Salsa de tomate, muzzarella y aceitunas", 9500),
    ("Pizzas", "🍕", "Napolitana", "Muzzarella, rodajas de tomate, ajo y albahaca", 11000),
    ("Pizzas", "🍕", "Fugazzeta", "Rellena de muzzarella con cebolla", 12500),
    ("Burgers", "🍔", "Clásica", "Medallón 150 g, lechuga, tomate y cheddar. Con papas", 9800),
    ("Burgers", "🍔", "Doble bacon", "Doble medallón, cheddar, bacon y barbacoa. Con papas", 13500),
    ("Empanadas", "🥟", "Empanada de carne", "Cortada a cuchillo, al horno", 1600),
    ("Empanadas", "🥟", "Empanada jamón y queso", "Al horno", 1500),
    ("Empanadas", "🥟", "Docena surtida", "12 empanadas a elección del local", 17000),
    ("Acompañamientos", "🍟", "Papas fritas", "Porción grande", 5200),
    ("Bebidas", "🥤", "Gaseosa 1,5 L", "Línea Coca-Cola", 3800),
    ("Bebidas", "🍺", "Cerveza 1 L", "Rubia", 4500),
    ("Postres", "🍰", "Flan casero", "Con dulce de leche", 4200),
]


class Command(BaseCommand):
    """Comando 'python manage.py cargar_demo'."""
    help = "Carga repartidores y pedidos de ejemplo para probar el sistema de repartos"

    def handle(self, *args, **opciones):
        """Crea repartidores, menú y pedidos de ejemplo (sin duplicar si se corre otra vez)."""
        lat0, lng0 = rutas.COMERCIO
        for orden, (cat, emoji, nombre, desc, precio) in enumerate(MENU):
            Producto.objects.get_or_create(
                nombre=nombre, defaults={"categoria": cat, "emoji": emoji, "descripcion": desc,
                                         "precio": precio, "orden": orden})
        self.stdout.write(f"Menú: {Producto.objects.count()} productos")
        for nombre, apellido, color in REPARTIDORES:
            Repartidor.objects.get_or_create(
                nombre=nombre, apellido=apellido,
                defaults={"color": color, "telefono": "11 5555-0000", "lat": lat0, "lng": lng0})
        random.seed(7)
        for cliente, direccion in CLIENTES:
            p = Pedido.objects.create(
                cliente_nombre=cliente, cliente_telefono="11 4444-0000",
                direccion=direccion + ", CABA",
                lat=lat0 + random.uniform(-0.025, 0.025), lng=lng0 + random.uniform(-0.03, 0.03),
                detalle="Pedido de ejemplo", tiempo_preparacion_min=random.choice([5, 10, 15]),
            )
            r = rutas.asignar_pedido(p)
            self.stdout.write(f"Pedido #{p.id} {cliente} -> {r}")
        self.stdout.write(self.style.SUCCESS("Listo. Cliente: http://127.0.0.1:8000/  ·  Comercio: http://127.0.0.1:8000/panel"))
