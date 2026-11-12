"""
Rutas del sitio: qué URL atiende cada controlador.
Cliente: / (tienda), /seguimiento, /ingresar, /registro.
Admin: /panel, /pedidos, /repartidores, /menu.  Repartidor: /repartidor/<id>?t=<clave>.
"""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from sistema import views
from sistema.controllers.usuarios_controller import UsuariosController
from sistema.controllers.inicio_controller import *
from sistema.controllers.reparto_controller import (
    EstadoApi, PanelController, PedidoEstadoApi, PedidoReasignarApi, PedidosController,
    RepartidorAppController, RepartidorRutaApi, RepartidorSalirApi, RepartidorTurnoApi,
    RepartidorUbicacionApi, RepartidoresController, SeguimientoApi, SeguimientoController,
)
from sistema.controllers.pedidos_controller import BorrarPedidoController, EditarPedidoController
from sistema.controllers.cuentas_controller import IngresarController, RegistroController, SalirController
from sistema.controllers.tienda_controller import (
    CotizarApi, CrearPedidoApi, MenuController, MisPedidosApi, TiendaController,
)

urlpatterns = [
    #path('admin/', admin.site.urls),
    path('admin', UsuariosController.as_view(), name="admin"),
    path('inicio', InicioController.as_view(), name="inicio"),

    # ---------------- Cuentas ----------------
    path('ingresar', IngresarController.as_view(), name="ingresar"),
    path('registro', RegistroController.as_view(), name="registro"),
    path('salir', SalirController.as_view(), name="salir"),

    # ---------------- Cliente (tienda online) ----------------
    path('', TiendaController.as_view(), name="tienda"),
    path('api/tienda/cotizar', CotizarApi.as_view(), name="api_cotizar"),
    path('api/tienda/pedido', CrearPedidoApi.as_view(), name="api_crear_pedido"),
    path('api/tienda/mis-pedidos', MisPedidosApi.as_view(), name="api_mis_pedidos"),

    # ---------------- Gestión de repartos (comercio) ----------------
    path('menu', MenuController.as_view(), name="menu"),
    path('panel', PanelController.as_view(), name="panel"),
    path('pedidos', PedidosController.as_view(), name="pedidos"),
    path('pedidos/<int:id>/editar', EditarPedidoController.as_view(), name="editar_pedido"),
    path('pedidos/<int:id>/borrar', BorrarPedidoController.as_view(), name="borrar_pedido"),
    path('repartidores', RepartidoresController.as_view(), name="repartidores"),
    path('repartidor/<int:id>', RepartidorAppController.as_view(), name="repartidor_app"),
    path('seguimiento/<str:codigo>', SeguimientoController.as_view(), name="seguimiento"),

    # ---------------- API (JSON) ----------------
    path('api/estado', EstadoApi.as_view(), name="api_estado"),
    path('api/pedidos/<int:id>/estado', PedidoEstadoApi.as_view(), name="api_pedido_estado"),
    path('api/pedidos/<int:id>/reasignar', PedidoReasignarApi.as_view(), name="api_pedido_reasignar"),
    path('api/repartidores/<int:id>/ubicacion', RepartidorUbicacionApi.as_view(), name="api_ubicacion"),
    path('api/repartidores/<int:id>/ruta', RepartidorRutaApi.as_view(), name="api_ruta"),
    path('api/repartidores/<int:id>/salir', RepartidorSalirApi.as_view(), name="api_salir"),
    path('api/repartidores/<int:id>/turno', RepartidorTurnoApi.as_view(), name="api_turno"),
    path('api/seguimiento/<str:codigo>', SeguimientoApi.as_view(), name="api_seguimiento"),
]
