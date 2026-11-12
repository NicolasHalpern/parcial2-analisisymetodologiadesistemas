# Controlador del ejercicio de la clase (ruta /admin).
from django.shortcuts import render
from django.core.exceptions import ImproperlyConfigured
from django.views import View
from ..models import *
from ..src.services import obtener_datos_api

import os
from dotenv import load_dotenv #pip install dotenv
from pathlib import Path


class UsuariosController(View):
    """Ejercicio de la clase (/admin): alta de repartidores y lectura de una API externa."""
    def registrarUsuario(self, request):
        """Si es POST guarda un repartidor; si no, trae productos de la API del .env."""
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        API_URL = os.getenv("API_URL")

        if not API_URL:
            raise ImproperlyConfigured("ENDPOINT_API no está definida en el entorno.")
        
        if request.method == 'POST':
            #nombreForm = request.POST.get('nombreForm')
            #apellidoForm = request.POST.get('apellidoForm')

            #prueba = Prueba(nombre=nombreForm, apellido=apellidoForm)
            
            nombreRepartidor = request.POST.get('nombreRepartidor')
            apellidoRepartidor = request.POST.get('apellidoRepartidor')
            repartidor = Repartidor(nombre=nombreRepartidor, apellido=apellidoRepartidor)
            #prueba.save()
            repartidor.save()
            return render(request, 'index.html')
        


        url_api = f"{API_URL}products/?limit=10" #Esto NO Es HARDCODEO, muy bien escrito.
        datos = obtener_datos_api(url_api)
    
        contexto = {
            'elementos': datos
        }

        return render(request, 'index.html', {'contexto': contexto})
    
    def get(self, request): #metodo para manejar solicitudes GET, hereda de view.
        #pass
        """GET: muestra la página con los datos de la API."""
        return self.registrarUsuario(request)

    def post(self, request): #metodo para manejar solicitudes POST, hereda de view.
        #pass
        """POST: guarda el repartidor enviado."""
        return self.registrarUsuario(request)