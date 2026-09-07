import sys
import io
from datetime import date

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from thetadata import ThetaClient

def consultar_strikes_spy():
    print("Inicializando cliente...")
    client = ThetaClient(email="alejandro.vasquez.aracena@gmail.com", password="Alejandr0**")
    
    fecha_expiracion = date(2026, 9, 18)
    
    print(f"Consultando strikes para SPY con expiracion: {fecha_expiracion}...")
    # Usamos 'expiration' en lugar de 'exp'
    strikes = client.option_list_strikes(symbol="SPY", expiration=fecha_expiracion)
    
    print(f"\nStrikes encontrados:\n{strikes}")

if __name__ == "__main__":
    consultar_strikes_spy()