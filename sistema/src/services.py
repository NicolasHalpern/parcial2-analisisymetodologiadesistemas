# Utilidades para consumir APIs externas (se usa en el ejercicio de la clase).
import requests

def obtener_datos_api(url):
    """Hace un GET a una API externa y devuelve el JSON, o None si falla."""
    try:
        respone = requests.get(url, timeout=10)
        if respone.status_code == 200:
            return respone.json()
    except requests.exceptions.RequestException as e:
        return None