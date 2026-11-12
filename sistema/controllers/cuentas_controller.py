"""Ingreso, registro y salida (admin y clientes usan el mismo login)."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from ..models import Cliente
from .reparto_controller import _contexto_comercio


def _destino(request, usuario):
    """A dónde ir después de entrar: el 'next' pedido (si es del sitio) o panel/tienda según el rol."""
    siguiente = request.POST.get("next") or request.GET.get("next")
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}, request.is_secure()):
        return siguiente
    return "panel" if usuario.is_staff else "tienda"


def _contexto(request, **extra):
    """Datos comunes para las pantallas de login y registro."""
    contexto = _contexto_comercio()
    contexto["next"] = request.POST.get("next") or request.GET.get("next") or ""
    contexto.update(extra)
    return contexto


class IngresarController(View):
    """Login único para admin (por usuario) y clientes (por email)."""
    def get(self, request):
        """Muestra el formulario (o redirige si ya inició sesión)."""
        if request.user.is_authenticated:
            return redirect(_destino(request, request.user))
        return render(request, "cuentas/ingresar.html", _contexto(request))

    def post(self, request):
        """Valida usuario y contraseña e inicia la sesión."""
        dato = (request.POST.get("usuario") or "").strip()
        clave = request.POST.get("clave") or ""
        # Se puede entrar con el nombre de usuario (admin) o con el email (clientes)
        nombre = dato
        if "@" in dato:
            u = User.objects.filter(email__iexact=dato).first()
            nombre = u.username if u else dato.lower()
        usuario = authenticate(request, username=nombre, password=clave)
        if usuario is None:
            return render(request, "cuentas/ingresar.html", _contexto(
                request, error="Usuario o contraseña incorrectos.", usuario=dato), status=401)
        login(request, usuario)   # crea la sesión (cookie) del navegador
        return redirect(_destino(request, usuario))


class RegistroController(View):
    """Alta de clientes de la tienda."""
    def get(self, request):
        """Muestra el formulario de registro."""
        if request.user.is_authenticated:
            return redirect("tienda")
        return render(request, "cuentas/registro.html", _contexto(request, datos={}))

    def post(self, request):
        """Valida los datos, crea el usuario y su perfil, e inicia sesión."""
        d = {k: (request.POST.get(k) or "").strip() for k in ("nombre", "apellido", "email", "telefono")}
        clave, clave2 = request.POST.get("clave") or "", request.POST.get("clave2") or ""
        errores = []
        if not d["nombre"]:
            errores.append("Completá tu nombre.")
        if not d["telefono"]:
            errores.append("Completá tu teléfono: el repartidor lo usa si no encuentra la dirección.")
        try:
            validate_email(d["email"])
        except ValidationError:
            errores.append("El email no es válido.")
        else:
            if User.objects.filter(email__iexact=d["email"]).exists() or \
                    User.objects.filter(username__iexact=d["email"]).exists():
                errores.append("Ya hay una cuenta con ese email. Iniciá sesión.")
        if clave != clave2:
            errores.append("Las contraseñas no coinciden.")
        else:
            try:
                # Reglas de contraseña de settings.AUTH_PASSWORD_VALIDATORS (largo, comunes, solo números...)
                validate_password(clave, User(username=d["email"], email=d["email"], first_name=d["nombre"]))
            except ValidationError as e:
                errores.extend(e.messages)
        if errores:
            return render(request, "cuentas/registro.html", _contexto(request, errores=errores, datos=d), status=400)

        # El email es también el nombre de usuario; create_user guarda la contraseña encriptada
        usuario = User.objects.create_user(
            username=d["email"].lower(), email=d["email"].lower(), password=clave,
            first_name=d["nombre"][:150], last_name=d["apellido"][:150])
        Cliente.objects.create(usuario=usuario, telefono=d["telefono"][:30])
        login(request, usuario)
        messages.success(request, f"¡Bienvenido/a, {usuario.first_name}! Tu cuenta está lista.")
        return redirect(_destino(request, usuario))


class SalirController(View):
    """Cierra la sesión."""
    def post(self, request):
        """Cierra la sesión (por POST para que un link no pueda desloguear a nadie)."""
        logout(request)
        return redirect("tienda")
