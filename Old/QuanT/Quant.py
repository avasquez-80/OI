import sys
import io
import tkinter as tk
from tkinter import filedialog
import pandas as pd

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def analizar_mejor_contrato_5_semanas_proyectadas():
    # 1. Ventana emergente para seleccionar el archivo CSV
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
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
    columnas_necesarias = ['Ticker', 'Trade Date', 'Expiry', 'Premium ($)', 'Size', 'Heat Score', 'Strike ($)', 'C/P', 'Trade Sentiment']
    for col in columnas_necesarias:
        if col not in df.columns:
            print(f"Error: El archivo CSV no contiene la columna obligatoria '{col}'.")
            return
            
    # Asegurar formato de fechas
    df['Trade Date'] = pd.to_datetime(df['Trade Date'])
    df['Expiry'] = pd.to_datetime(df['Expiry'])
    
    # 2. Definir la fecha de análisis actual (última fecha registrada en el archivo)
    fecha_analisis = df['Trade Date'].max()
    fecha_limite = fecha_analisis + pd.Timedelta(days=35) # 5 semanas en adelante
    
    print(f"\nFecha de análisis (última sesión en CSV): {fecha_analisis.strftime('%Y-%m-%d')}")
    print(f"Ventana de expiración objetivo: desde {fecha_analisis.strftime('%Y-%m-%d')} hasta {fecha_limite.strftime('%Y-%m-%d')}")
    
    # 3. Filtrar contratos cuya fecha de expiración caiga dentro de las 5 semanas proyectadas
    df_window = df[(df['Expiry'] >= fecha_analisis) & (df['Expiry'] <= fecha_limite)].copy()
    
    if df_window.empty:
        print("No se encontraron contratos con expiración en el rango de las 5 semanas proyectadas.")
        return
        
    # 4. Agrupar y consolidar métricas por contrato único
    ranking = df_window.groupby(['Ticker', 'Expiry', 'Strike ($)', 'C/P']).agg(
        Total_Premium=('Premium ($)', 'sum'),
        Total_Size=('Size', 'sum'),
        Max_Heat=('Heat Score', 'max'),
        Avg_IV=('Implied Vol', 'mean'),
        Transacciones=('Trade Date', 'count'),
        Sentiment_Dominante=('Trade Sentiment', lambda x: x.mode()[0] if not x.empty else 'Neutral')
    ).reset_index()
    
    # 5. Calcular puntaje cuantitativo compuesto (60% Prima Total + 40% Heat Score Máximo)
    ranking['Score'] = (
        (ranking['Total_Premium'] / ranking['Total_Premium'].max()) * 0.6 + 
        (ranking['Max_Heat'] / ranking['Max_Heat'].max()) * 0.4
    ) * 100
    
    ranking = ranking.sort_values(by='Score', ascending=False)
    
    # Formatear la fecha de expiración para visualización limpia
    ranking['Expiry'] = ranking['Expiry'].dt.strftime('%Y-%m-%d')
    
    print("\n" + "="*70)
    print(" TOP 5 CONTRATOS ÓPTIMOS (VENTANA PROYECTADA A 5 SEMANAS) ")
    print("="*70)
    print(ranking[['Ticker', 'Expiry', 'Strike ($)', 'C/P', 'Total_Premium', 'Max_Heat', 'Sentiment_Dominante', 'Score']].head(5).to_string(index=False))
    
    # Mostrar detalle del ganador absoluto
    ganador = ranking.iloc[0]
    print("\n" + "*"*70)
    print(" MEJOR CONTRATO DETECTADO PARA LAS PRÓXIMAS 5 SEMANAS:")
    print(f" • Ticker: {ganador['Ticker']}")
    print(f" • Tipo / Opción: {ganador['C/P']}")
    print(f" • Strike: {ganador['Strike ($)']} | Expiración: {ganador['Expiry']}")
    print(f" • Prima Total Acumulada: ${ganador['Total_Premium']:,.2f}")
    print(f" • Volumen Total de Contratos (Size): {ganador['Total_Size']:,}")
    print(f" • Puntuación de Calor Máxima (Heat Score): {ganador['Max_Heat']}")
    print(f" • Sentimiento Institucional Predominante: {ganador['Sentiment_Dominante']}")
    print(f" • Score Cuantitativo Global: {ganador['Score']:.2f} / 100")
    print("*"*70)

if __name__ == "__main__":
    analizar_mejor_contrato_5_semanas_proyectadas()