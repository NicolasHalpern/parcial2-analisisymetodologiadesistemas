# Controlador del ejercicio de la clase (ruta /inicio).
from django.shortcuts import render
from django.core.exceptions import ImproperlyConfigured
from django.views import View
from ..models import *
from ..src.services import obtener_datos_api

import os
from dotenv import load_dotenv #pip install dotenv
from pathlib import Path


class InicioController(View):
    """Página de inicio de ejemplo de la clase (/inicio)."""
    def inicio(self, request):
         """Renderiza inicio.html."""
         return render(request, 'inicio.html')
    def get(self, request): #metodo para manejar solicitudes GET, hereda de view.
            #pass
            """GET: muestra la página."""
            return self.inicio(request)
    
    def post(self, request): #metodo para manejar solicitudes POST, hereda de view.
            #pass
        """POST: muestra la misma página."""
        return self.inicio(request)
    