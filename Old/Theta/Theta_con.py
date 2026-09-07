from thetadata import ThetaClient, OptionReqType, OptionRight, DateRange
import pandas as pd
import datetime

def probar_conexion_thetadata():
    print("🔌 Intentando conectar con Theta Terminal...")
    
    # Iniciamos el cliente de ThetaData
    client = ThetaClient()
    
    # Usamos "with" para asegurar que la conexión se cierre correctamente al terminar
    with client.connect():
        print("✅ ¡Conexión exitosa al Terminal!\n")
        
        # Vamos a solicitar el historial de Fin de Día (EOD) de un contrato específico
        # Ejemplo: SPY, Strike 550, Call, Vencimiento 18 de Octubre 2026
        ticker = "SPY"
        vencimiento = datetime.date(2026, 10, 18)
        strike = 550
        
        print(f"📊 Solicitando datos históricos de Open Interest para {ticker} {strike}C...")
        
        # Hacemos la petición a la base de datos
        datos = client.get_hist_option(
            req=OptionReqType.EOD,           # Datos de fin de día (Gratis)
            root=ticker,                     # Símbolo
            exp=vencimiento,                 # Fecha de expiración
            strike=strike,                   # Nivel de precio
            right=OptionRight.CALL,          # Call o Put
            date_range=DateRange(            # Rango de fechas a buscar
                datetime.date(2026, 8, 1), 
                datetime.date.today()
            )
        )
        
        # ThetaData devuelve los datos en un formato súper rápido, lo convertimos a Pandas
        df = datos.to_df()
        
        if df.empty:
            print("⚠️ No se encontraron datos. Verifica si el mercado está abierto o si el contrato existe.")
        else:
            print("\n🎯 DATOS EXTRAÍDOS CON ÉXITO:")
            # Seleccionamos solo las columnas que nos importan para nuestro análisis
            df_limpio = df[['date', 'open_interest', 'volume', 'close']]
            print(df_limpio.tail()) # Mostramos los últimos 5 días

if __name__ == "__main__":
    probar_conexion_thetadata()