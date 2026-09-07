import sys
import io

# Forzar codificacion UTF-8 para evitar errores de caracteres en Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from thetadata import ThetaClient

def probar_cliente_directo():
    print("Inicializando ThetaClient con correo y contraseña...")
    
    try:
        client = ThetaClient(email="alejandro.vasquez.aracena@gmail.com", password="Alejandr0**")
        print("Cliente inicializado con exito.\n")
        
        print("Consultando simbolos disponibles para opciones...")
        simbolos = client.option_list_symbols()
        
        print(f"Conexion exitosa! Primeros simbolos encontrados: {simbolos[:5]}")
        
    except Exception as e:
        print(f"Ocurrio un error al invocar el cliente: {e}")

if __name__ == "__main__":
    probar_cliente_directo()