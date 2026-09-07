import sys
import io
from datetime import date

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from thetadata import ThetaClient

def explorar_opciones_activas():
    print("Inicializando cliente...")
    client = ThetaClient(email="alejandro.vasquez.aracena@gmail.com", password="Alejandr0**")
    
    simbolo = "MRVL"
    
    print(f"Consultando expiraciones para {simbolo}...")
    df_exp = client.option_list_expirations(symbol=simbolo)
    
    # Definimos el rango de fechas que queremos analizar en el historico
    inicio_query = date(2026, 8, 1)
    fin_query = date(2026, 8, 10)
    
    # Filtramos expiraciones que sigan vivas (posteriores o iguales al fin del rango de consulta)
    fechas_str = df_exp["expiration"].to_list()
    fechas_validas = [f for f in fechas_str if date.fromisoformat(f) >= fin_query]
    
    if fechas_validas:
        # Tomamos la expiracion viva mas cercana
        fecha_elegida_str = sorted(fechas_validas)[0]
        proxima_exp = date.fromisoformat(fecha_elegida_str)
        
        print(f"Inspeccionando strikes para la expiracion activa: {proxima_exp}")
        
        df_strikes = client.option_list_strikes(symbol=simbolo, expiration=proxima_exp)
        print(f"Strikes disponibles: {len(df_strikes)}")
        
        if not df_strikes.is_empty():
            strike_ejemplo = df_strikes["strike"].item(len(df_strikes) // 2)
            print(f"Probando EOD para strike: {strike_ejemplo}")
            
            df_eod = client.option_history_eod(
                symbol=simbolo,
                expiration=proxima_exp,
                strike=str(strike_ejemplo),
                right="CALL",
                start_date=inicio_query,
                end_date=fin_query
            )
            print(f"\nDatos EOD obtenidos:\n{df_eod}")
    else:
        print("No se encontraron expiraciones válidas para el rango especificado.")

if __name__ == "__main__":
    explorar_opciones_activas()