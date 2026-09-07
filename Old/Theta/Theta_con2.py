import requests

def descubrir_endpoints_v3():
    print("Consultando el mapa de rutas de la API v3...")
    
    # Intentemos atacar directamente el endpoint principal de opciones de la v3
    # Probemos variaciones comunes de la nueva estructura de la API v3
    urls_a_probar = [
        "http://127.0.0.1:25503/v3/hist/option/eod",
        "http://127.0.0.1:25503/bulk/hist/option/eod",
        "http://127.0.0.1:25503/query",
        "http://127.0.0.1:25503/history/option/eod"
    ]
    
    for url in urls_a_probar:
        print(f"\nProbando ruta: {url}")
        try:
            respuesta = requests.get(url, params={"symbol": "SPY", "expiration": "20260814"})
            print(f"Status Code: {respuesta.status_code}")
            print(f"Respuesta: {respuesta.text[:200]}")
            
            if respuesta.status_code != 404:
                print("¡Encontramos una ruta activa!")
                break
        except Exception as e:
            print(f"Error de conexion: {e}")

if __name__ == "__main__":
descubrir_endpoints_v3()