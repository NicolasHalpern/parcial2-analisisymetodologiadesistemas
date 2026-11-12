# Vista de ejemplo de la clase. Las pantallas reales están en controllers/.
from django.shortcuts import render
from sistema.models import Prueba

def home(request):
    """Vista de ejemplo de la clase (hoy no está conectada a ninguna URL)."""
    nombre = "Elias"
    edad = 25

    #if request.method == 'POST':
        #nombreForm = request.POST.get('nombreForm')
        #apellidoForm = request.POST.get('apellidoForm')

        #prueba = Prueba(nombre=nombreForm, apellido=apellidoForm)
        #prueba.save()

    #return render(request, 'index.html', {'nombre': nombre, 'edad': edad})