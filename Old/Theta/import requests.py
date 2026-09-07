from thetadata import ThetaClient
print("Metodos y atributos disponibles en ThetaClient:")
for attr in dir(ThetaClient):
    if not attr.startswith('_'):
        print(f" - {attr}")
def probar_conexion_oficial():
    print("Estableciendo puente gRPC con el Theta Terminal...")
    
    # Inicializamos el cliente pasando las credenciales de forma explícita
    client = ThetaClient(
        email="alejandro.vasquez.aracena@gmail.com", 
        password="Alejandr0**"
    )
    
    try:
        with client.connect():
            print("\n¡CONEXION gRPC EXITOSA!")
            print("El cliente se comunico correctamente con el terminal local.")
    except Exception as e:
        print(f"\nError al conectar: {e}")

if __name__ == "__main__":
    probar_conexion_oficial()