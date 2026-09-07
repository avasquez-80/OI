import sys
import io
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import matplotlib.pyplot as plt

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def seleccionar_archivo_graficar():
    # Inicializar tkinter de forma oculta para mostrar solo el explorador de archivos
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True) # Asegurar que la ventana emergente aparezca al frente
    
    print("Abriendo ventana de selección de archivos...")
    ruta_csv = filedialog.askopenfilename(
        title="Selecciona el archivo CSV de flujo de opciones",
        filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
    )
    
    if not ruta_csv:
        print("Operación cancelada. No se seleccionó ningún archivo.")
        return
        
    print(f"Archivo seleccionado: {ruta_csv}")
    
    try:
        df = pd.read_csv(ruta_csv)
    except Exception as e:
        print(f"Error al leer el archivo CSV: {e}")
        return
    
    # Validar columnas requeridas
    columnas_necesarias = ['Ticker', 'Trade Date', 'Open Interest', 'Expiry', 'Strike ($)', 'C/P']
    for col in columnas_necesarias:
        if col not in df.columns:
            print(f"Error: El archivo CSV no contiene la columna obligatoria '{col}'.")
            return
            
    # Detectar automáticamente los tickers disponibles en el archivo
    tickers_disponibles = df['Ticker'].unique().tolist()
    print(f"\nTickers detectados en el archivo: {tickers_disponibles}")
    
    if len(tickers_disponibles) == 1:
        ticker_elegido = tickers_disponibles[0]
        print(f"Ticker seleccionado automáticamente: {ticker_elegido}")
    else:
        seleccion = input(f"Hay varios tickers. Elige uno de la lista {tickers_disponibles}: ").strip().upper()
        ticker_elegido = seleccion if seleccion in tickers_disponibles else tickers_disponibles[0]
        print(f"Ticker seleccionado: {ticker_elegido}")
            
    # Filtrar dataframe para el ticker elegido
    df_ticker = df[df['Ticker'] == ticker_elegido].copy()
    df_ticker['Trade Date'] = pd.to_datetime(df_ticker['Trade Date'])
    
    # Detectar automáticamente el contrato con mayor variación de Open Interest
    print("\nAnalizando contratos y detectando el de mayor movimiento en Open Interest...")
    
    resumen_contratos = df_ticker.groupby(['Expiry', 'Strike ($)', 'C/P']).agg(
        OI_min=('Open Interest', 'min'),
        OI_max=('Open Interest', 'max')
    ).reset_index()
    
    resumen_contratos['OI_diff'] = resumen_contratos['OI_max'] - resumen_contratos['OI_min']
    resumen_contratos = resumen_contratos.sort_values(by='OI_diff', ascending=False)
    
    if resumen_contratos.empty:
        print("No se encontraron contratos válidos para analizar.")
        return
        
    top_contrato = resumen_contratos.iloc[0]
    exp_elegida = top_contrato['Expiry']
    strike_elegido = top_contrato['Strike ($)']
    tipo_elegido = top_contrato['C/P']
    
    print(f"Contrato más activo detectado automáticamente:")
    print(f" -> Ticker: {ticker_elegido} | Tipo: {tipo_elegido} | Strike: {strike_elegido} | Expiración: {exp_elegida}")
    
    # Filtrar la serie temporal para ese contrato específico
    contrato_df = df_ticker[
        (df_ticker['Expiry'] == exp_elegida) &
        (df_ticker['Strike ($)'] == strike_elegido) &
        (df_ticker['C/P'] == tipo_elegido)
    ].sort_values(by=['Trade Date', 'Time'])
    
    tendencia_diaria = contrato_df.groupby('Trade Date')['Open Interest'].last().reset_index()
    
    print("\n--- Tendencia Diaria de Open Interest ---")
    print(tendencia_diaria)
    
    # Generar el gráfico de la evolución
    plt.figure(figsize=(10, 5))
    plt.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Open Interest'], marker='o', linestyle='-', color='royalblue', linewidth=2)
    plt.title(f'Evolución del Open Interest - {ticker_elegido} Strike {strike_elegido} {tipo_elegido} (Exp: {exp_elegida})')
    plt.xlabel('Fecha de Negociación')
    plt.ylabel('Open Interest')
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    seleccionar_archivo_graficar()