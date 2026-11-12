"""
Quién puede entrar a qué.

- Admin (usuario con is_staff): panel, pedidos, repartidores, menú y todas las APIs.
- Repartidor: no tiene usuario; entra con el link secreto de su celular
  (/repartidor/<id>?t=<token>) y solo puede tocar SU ruta y SUS pedidos.
- Cliente: cuenta propia para pedir en la tienda. La página de seguimiento
  es pública por código, para poder compartir el link.
"""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import urlencode


def es_admin(request):
    """True si quien navega es el administrador del comercio."""
    return request.user.is_authenticated and request.user.is_staff


def _rechazar(request, mensaje):
    """Respuesta cuando no tiene permiso: JSON en la API, redirección en las páginas."""
    if request.path.startswith("/api/"):
        codigo = 403 if request.user.is_authenticated else 401
        return JsonResponse({"ok": False, "error": mensaje, "login": "/ingresar"}, status=codigo)
    if request.user.is_authenticated:
        messages.error(request, "Esa sección es solo para el administrador del comercio.")
        return redirect("tienda")
    messages.info(request, mensaje)
    return redirect("/ingresar?" + urlencode({"next": request.get_full_path()}))


class SoloAdminMixin:
    """Para las vistas del comercio."""

    def dispatch(self, request, *args, **kwargs):
        """Corta el pedido antes de llegar a la vista si no es admin."""
        if not es_admin(request):
            return _rechazar(request, "Ingresá con el usuario del comercio para ver esta sección.")
        return super().dispatch(request, *args, **kwargs)


def token_de(request):
    """Clave del repartidor que viene en el encabezado o en el link (?t=)."""
    return request.headers.get("X-Cadete-Token") or request.GET.get("t") or ""


def puede_usar_repartidor(request, repartidor):
    """El admin, o el propio repartidor con su link secreto."""
    return es_admin(request) or (bool(repartidor.token) and token_de(request) == repartidor.token)


class AdminOCadeteMixin:
    """Para las vistas que usa el repartidor en su celular (reciben `id` del repartidor)."""

    def dispatch(self, request, *args, **kwargs):
        """Deja pasar al admin o al repartidor dueño de ese link."""
        from django.shortcuts import get_object_or_404
        from ..models import Repartidor

        r = get_object_or_404(Repartidor, pk=kwargs.get("id"))
        if not puede_usar_repartidor(request, r):
            return _rechazar(request, "Este link de repartidor no es válido. Pedile el link al comercio.")
        return super().dispatch(request, *args, **kwargs)


class SoloClienteMixin:
    """Para pedir en la tienda hace falta haber iniciado sesión."""

    def dispatch(self, request, *args, **kwargs):
        """Exige sesión iniciada para seguir."""
        if not request.user.is_authenticated:
            return _rechazar(request, "Iniciá sesión o creá tu cuenta para confirmar el pedido.")
        return super().dispatch(request, *args, **kwargs)
