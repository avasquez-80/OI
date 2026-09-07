import sys
import io

# Forzar codificacion UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from thetadata import ThetaClient

def consultar_expiraciones_spy():
    print("Inicializando cliente...")
    client = ThetaClient(email="alejandro.vasquez.aracena@gmail.com", password="Alejandr0**")
    
    print("Consultando fechas de expiracion para SPY...")
    expiraciones = client.option_list_expirations(symbol="SPY")
    
    print(f"\nFechas de expiracion encontradas:\n{expiraciones}")

if __name__ == "__main__":
    consultar_expiraciones_spy()