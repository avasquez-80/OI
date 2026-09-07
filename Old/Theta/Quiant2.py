import sys
import io
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import matplotlib.pyplot as plt

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def analizar_y_graficar_secuencial():
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
    columnas_necesarias = ['Ticker', 'Trade Date', 'Expiry', 'Premium ($)', 'Size', 'Heat Score', 'Strike ($)', 'C/P', 'Trade Sentiment', 'Open Interest']
    for col in columnas_necesarias:
        if col not in df.columns:
            print(f"Error: El archivo CSV no contiene la columna obligatoria '{col}'.")
            return
            
    # Asegurar formato de fechas
    df['Trade Date'] = pd.to_datetime(df['Trade Date'])
    df['Expiry'] = pd.to_datetime(df['Expiry'])
    
    # 2. Definir fecha de referencia (última sesión en el archivo) y ventana de proyección (ej. 10 semanas / 70 días hacia adelante)
    fecha_analisis = df['Trade Date'].max()
    semanas_proyeccion = 10
    dias_proyeccion = semanas_proyeccion * 7
    fecha_limite = fecha_analisis + pd.Timedelta(days=dias_proyeccion)
    
    print(f"\nFecha de referencia (última sesión en CSV): {fecha_analisis.strftime('%Y-%m-%d')}")
    print(f"Ventana de proyección ({semanas_proyeccion} semanas hacia adelante): hasta {fecha_limite.strftime('%Y-%m-%d')}")
    
    # Filtrar contratos cuya expiración esté desde la fecha de análisis en adelante dentro del límite
    df_window = df[(df['Expiry'] >= fecha_analisis) & (df['Expiry'] <= fecha_limite)].copy()
    
    if df_window.empty:
        print("No se encontraron contratos con expiración en el rango especificado.")
        return
        
    # 3. Agrupar y calcular puntaje compuesto
    ranking = df_window.groupby(['Ticker', 'Expiry', 'Strike ($)', 'C/P']).agg(
        Total_Premium=('Premium ($)', 'sum'),
        Total_Size=('Size', 'sum'),
        Max_Heat=('Heat Score', 'max'),
        Avg_IV=('Implied Vol', 'mean'),
        Transacciones=('Trade Date', 'count'),
        Sentiment_Dominante=('Trade Sentiment', lambda x: x.mode()[0] if not x.empty else 'Neutral')
    ).reset_index()
    
    ranking['Score'] = (
        (ranking['Total_Premium'] / ranking['Total_Premium'].max()) * 0.6 + 
        (ranking['Max_Heat'] / ranking['Max_Heat'].max()) * 0.4
    ) * 100
    
    ranking = ranking.sort_values(by='Score', ascending=False)
    
    # Preparar formato para impresión en texto PRIMERO
    ranking_display = ranking.copy()
    ranking_display['Expiry'] = ranking_display['Expiry'].dt.strftime('%Y-%m-%d')
    
    print("\n" + "="*70)
    print(f" TOP 5 CONTRATOS ÓPTIMOS (PROYECCIÓN A {semanas_proyeccion} SEMANAS) ")
    print("="*70)
    print(ranking_display[['Ticker', 'Expiry', 'Strike ($)', 'C/P', 'Total_Premium', 'Max_Heat', 'Sentiment_Dominante', 'Score']].head(5).to_string(index=False))
    
    # Seleccionar el ganador absoluto
    ganador = ranking.iloc[0]
    exp_ganadora = ganador['Expiry']
    strike_ganador = ganador['Strike ($)']
    cp_ganador = ganador['C/P']
    ticker_ganador = ganador['Ticker']
    
    print("\n" + "*"*70)
    print(" MEJOR CONTRATO DETECTADO:")
    print(f" • Ticker: {ticker_ganador}")
    print(f" • Tipo / Opción: {ganador['C/P']}")
    print(f" • Strike: {strike_ganador} | Expiración: {exp_ganadora.strftime('%Y-%m-%d')}")
    print(f" • Prima Total Acumulada: ${ganador['Total_Premium']:,.2f}")
    print(f" • Volumen Total de Contratos (Size): {ganador['Total_Size']:,}")
    print(f" • Puntuación de Calor Máxima (Heat Score): {ganador['Max_Heat']}")
    print(f" • Sentimiento Institucional Predominante: {ganador['Sentiment_Dominante']}")
    print(f" • Score Cuantitativo Global: {ganador['Score']:.2f} / 100")
    print("*"*70)
    
    # 4. Extraer la serie histórica diaria del contrato ganador para graficar AL FINAL
    print("\nGenerando gráfica de tendencia y flujo diario para el contrato líder...")
    
    contrato_hist = df[
        (df['Ticker'] == ticker_ganador) &
        (df['Expiry'] == exp_ganadora) &
        (df['Strike ($)'] == strike_ganador) &
        (df['C/P'] == cp_ganador)
    ].sort_values(by=['Trade Date', 'Time'])
    
    tendencia_diaria = contrato_hist.groupby('Trade Date').agg(
        Open_Interest=('Open Interest', 'last'),
        Daily_Premium=('Premium ($)', 'sum')
    ).reset_index()
    
    # 5. Generar y mostrar la Gráfica Dual al final del proceso
    fig, ax1 = plt.subplots(figsize=(11, 5))
    
    color_oi = 'tab:blue'
    ax1.set_xlabel('Fecha de Negociación', fontweight='bold')
    ax1.set_ylabel('Open Interest', color=color_oi, fontweight='bold')
    ax1.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Open_Interest'], color=color_oi, marker='o', linewidth=2.5, label='Open Interest')
    ax1.tick_params(axis='y', labelcolor=color_oi)
    plt.xticks(rotation=45)
    
    ax2 = ax1.twinx()
    color_prem = 'tab:red'
    ax2.set_ylabel('Prima Diaria Acumulada ($)', color=color_prem, fontweight='bold')
    ax2.bar(tendencia_diaria['Trade Date'], tendencia_diaria['Daily_Premium'], color=color_prem, alpha=0.35, width=0.7, label='Prima Diaria')
    ax2.tick_params(axis='y', labelcolor=color_prem)
    
    plt.title(f'Evolución del Contrato Líder: {ticker_ganador} {strike_ganador} {cp_ganador} (Exp: {exp_ganadora.strftime("%Y-%m-%d")})', fontsize=12, fontweight='bold')
    fig.tight_layout()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.show()

if __name__ == "__main__":
    analizar_y_graficar_secuencial()