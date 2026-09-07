import sys
import io
import os
import base64
import tempfile
import webbrowser
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def generar_analisis_robusto():
    # 1. Seleccionar archivo CSV mediante ventana emergente
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
    
    # 2. Análisis cuantitativo (Proyección a 10 semanas desde la última fecha)
    fecha_analisis = df['Trade Date'].max()
    semanas_proyeccion = 10
    fecha_limite = fecha_analisis + pd.Timedelta(weeks=semanas_proyeccion)
    
    print(f"\nFecha de referencia (última sesión): {fecha_analisis.strftime('%Y-%m-%d')}")
    print(f"Horizonte de proyección ({semanas_proyeccion} semanas): hasta {fecha_limite.strftime('%Y-%m-%d')}")
    
    df_window = df[(df['Expiry'] >= fecha_analisis) & (df['Expiry'] <= fecha_limite)].copy()
    
    if df_window.empty:
        print("No se encontraron contratos en el rango especificado.")
        return
        
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
    
    # 3. Imprimir resultados en consola PRIMERO
    ranking_display = ranking.copy()
    ranking_display['Expiry'] = ranking_display['Expiry'].dt.strftime('%Y-%m-%d')
    
    print("\n" + "="*70)
    print(f" TOP 5 CONTRATOS ÓPTIMOS (PROYECCIÓN A {semanas_proyeccion} SEMANAS) ")
    print("="*70)
    print(ranking_display[['Ticker', 'Expiry', 'Strike ($)', 'C/P', 'Total_Premium', 'Max_Heat', 'Sentiment_Dominante', 'Score']].head(5).to_string(index=False))
    
    ganador = ranking.iloc[0]
    exp_ganadora = ganador['Expiry']
    strike_ganador = ganador['Strike ($)']
    cp_ganador = ganador['C/P']
    ticker_ganador = ganador['Ticker']
    
    print("\n" + "*"*70)
    print(" CONTRATO GANADOR ABSOLUTO:")
    print(f" • Ticker: {ticker_ganador}")
    print(f" • Tipo / Opción: {cp_ganador}")
    print(f" • Strike: {strike_ganador} | Expiración: {exp_ganadora.strftime('%Y-%m-%d')}")
    print(f" • Prima Total Acumulada: ${ganador['Total_Premium']:,.2f}")
    print(f" • Volumen Total (Size): {ganador['Total_Size']:,}")
    print(f" • Heat Score Máximo: {ganador['Max_Heat']}")
    print(f" • Sentimiento Predominante: {ganador['Sentiment_Dominante']}")
    print(f" • Score Global: {ganador['Score']:.2f} / 100")
    print("*"*70)
    
    # 4. Descargar datos del subyacente con Yahoo Finance
    print(f"\nDescargando historial técnico de {ticker_ganador} desde Yahoo Finance...")
    inicio_hist = df['Trade Date'].min() - pd.Timedelta(days=5)
    fin_hist = fecha_analisis + pd.Timedelta(days=1)
    
    stock_data = yf.download(ticker_ganador, start=inicio_hist.strftime('%Y-%m-%d'), end=fin_hist.strftime('%Y-%m-%d'), progress=False)
    if isinstance(stock_data.columns, pd.MultiIndex):
        stock_data.columns = stock_data.columns.get_level_values(0)
    stock_data = stock_data.reset_index()
    if 'Date' in stock_data.columns:
        stock_data['Trade Date'] = pd.to_datetime(stock_data['Date']).dt.normalize()
    elif 'Datetime' in stock_data.columns:
        stock_data['Trade Date'] = pd.to_datetime(stock_data['Datetime']).dt.normalize()
        
    # 5. Extraer serie histórica del contrato ganador y fusionar con el subyacente
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
    
    tendencia_diaria = tendencia_diaria.merge(stock_data[['Trade Date', 'Close', 'Volume']], on='Trade Date', how='left')
    
    # 6. Generar Gráfica Avanzada de Paneles Múltiples (Subplots)
    print("Generando gráfica técnica avanzada y abriendo el informe interactivo...")
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), dpi=300, sharex=True)
    
    # Panel Superior: Precio del Subyacente (Yahoo Finance)
    if 'Close' in tendencia_diaria.columns and not tendencia_diaria['Close'].isna().all():
        ax1.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Close'], color='#2b6cb0', marker='s', linewidth=2, label=f'Precio Cierre {ticker_ganador}')
        ax1.set_ylabel('Precio Subyacente ($)', color='#2b6cb0', fontweight='bold', fontsize=9)
        ax1.tick_params(axis='y', labelcolor='#2b6cb0')
        ax1.grid(True, linestyle='--', alpha=0.4)
        ax1.legend(loc='upper left')
        ax1.set_title(f'Validación Cruzada: Acción Subyacente vs Flujo de Opciones ({ticker_ganador})', fontsize=11, fontweight='bold', pad=10)
    else:
        ax1.text(0.5, 0.5, 'Datos de precio no disponibles en Yahoo Finance para el rango', horizontalalignment='center', verticalalignment='center')

    # Panel Inferior: Open Interest y Primas Diarias
    color_oi = '#3182ce'
    ax2.set_xlabel('Fecha de Negociación', fontweight='bold', fontsize=9)
    ax2.set_ylabel('Open Interest', color=color_oi, fontweight='bold', fontsize=9)
    line_oi = ax2.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Open_Interest'], color=color_oi, marker='o', linewidth=2, label='Open Interest')
    ax2.tick_params(axis='y', labelcolor=color_oi)
    plt.xticks(rotation=30, fontsize=9)
    
    ax3 = ax2.twinx()
    color_prem = '#e53e3e'
    ax3.set_ylabel('Prima Diaria Acumulada ($)', color=color_prem, fontweight='bold', fontsize=9)
    bar_prem = ax3.bar(tendencia_diaria['Trade Date'], tendencia_diaria['Daily_Premium'], color=color_prem, alpha=0.35, width=0.6, label='Prima Diaria')
    ax3.tick_params(axis='y', labelcolor=color_prem)
    
    ax2.grid(True, linestyle='--', alpha=0.4)
    ax2.set_title(f'Dinámica del Contrato: Strike ${strike_ganador} {cp_ganador} (Exp: {exp_ganadora.strftime("%Y-%m-%d")})', fontsize=10, fontweight='bold', pad=8)

    fig.tight_layout()
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
        plt.savefig(tmp_img.name, bbox_inches='tight')
        tmp_img_path = tmp_img.name
    plt.close()
    
    with open(tmp_img_path, 'rb') as img_file:
        chart_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    os.unlink(tmp_img_path)
        
    top_5 = ranking.head(5)
    
    # 7. Construcción del informe HTML interactivo
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
    <meta charset="UTF-8">
    <title>Informe Cuantitativo de Flujo de Opciones y Subyacente</title>
    <style>
        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #2c3e50;
            line-height: 1.6;
            background-color: #f8fafc;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 950px;
            margin: 0 auto;
            background: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }}
        .header-banner {{
            background-color: #1a365d;
            color: white;
            margin: -30px -30px 25px -30px;
            padding: 25px 30px;
            border-radius: 8px 8px 0 0;
            border-bottom: 4px solid #3182ce;
        }}
        .header-banner h1 {{
            margin: 0 0 5px 0;
            font-size: 22pt;
        }}
        .header-banner p {{
            margin: 0;
            font-size: 11pt;
            color: #e2e8f0;
        }}
        h2 {{
            font-size: 14pt;
            color: #1a365d;
            border-left: 4px solid #3182ce;
            padding-left: 10px;
            margin-top: 25px;
            margin-bottom: 12px;
        }}
        .card {{
            background: #fdfdfd;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 15px 20px;
            margin-bottom: 15px;
        }}
        .winner-grid {{
            display: flex;
            justify-content: space-between;
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-box {{
            background: #ebf8ff;
            border: 1px solid #bee3f8;
            border-radius: 6px;
            padding: 12px;
            text-align: center;
            flex: 1;
        }}
        .metric-value {{
            font-size: 14pt;
            font-weight: bold;
            color: #2b6cb0;
            margin-top: 4px;
        }}
        .metric-label {{
            font-size: 8.5pt;
            color: #4a5568;
            text-transform: uppercase;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            margin-bottom: 20px;
            background: #ffffff;
            font-size: 10pt;
        }}
        th {{
            background-color: #2d3748;
            color: white;
            text-align: left;
            padding: 10px 12px;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e2e8f0;
            color: #4a5568;
        }}
        tr:nth-child(even) {{
            background-color: #f7fafc;
        }}
        .chart-container {{
            text-align: center;
            margin: 20px 0;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 15px;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
        }}
        .footer {{
            margin-top: 30px;
            font-size: 9pt;
            color: #718096;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            padding-top: 15px;
        }}
    </style>
    </head>
    <body>

    <div class="container">
        <div class="header-banner">
            <h1>Informe Cuantitativo Integrado</h1>
            <p>Flujo Institucional de Opciones y Validación Técnica con Yahoo Finance (Ticker: {ticker_ganador})</p>
        </div>

        <h2>Resumen Metodológico y Validación Cruzada</h2>
        <div class="card">
            <p>Este informe integra el análisis de derivados con los datos de precio del activo subyacente extraídos en tiempo real vía <strong>Yahoo Finance</strong>. Se evalúa el comportamiento de <strong>{ticker_ganador}</strong> en una ventana proyectada de <strong>10 semanas</strong> a partir del <strong>{fecha_analisis.strftime('%Y-%m-%d')}</strong>, ponderando la Prima Total (60%) y el Heat Score Máximo (40%).</p>
        </div>

        <h2>Contrato Ganador Detectado</h2>
        <div class="card" style="background-color: #f7fafc; border-left: 4px solid #3182ce;">
            <p style="margin-bottom: 6px;"><strong>Opción Líder:</strong> Call con Strike <strong>${strike_ganador}</strong> y Vencimiento <strong>{exp_ganadora.strftime('%Y-%m-%d')}</strong></p>
            <p style="margin-bottom: 0;">Sentimiento institucional: <span style="color: #2b6cb0; font-weight: bold;">{ganador['Sentiment_Dominante']}</span> | Puntuación Global: <span style="color: #2b6cb0; font-weight: bold;">{ganador['Score']:.2f} / 100</span></p>
        </div>

        <div class="winner-grid">
            <div class="metric-box">
                <div class="metric-label">Prima Total</div>
                <div class="metric-value">${ganador['Total_Premium']:,.0f}</div>
            </div>
            <div class="metric-box">
                <div class="metric-label">Volumen (Size)</div>
                <div class="metric-value">{ganador['Total_Size']:,}</div>
            </div>
            <div class="metric-box">
                <div class="metric-label">Heat Score Máx.</div>
                <div class="metric-value">{ganador['Max_Heat']}</div>
            </div>
            <div class="metric-box">
                <div class="metric-label">Transacciones</div>
                <div class="metric-value">{ganador['Transacciones']}</div>
            </div>
        </div>

        <h2>Análisis Gráfico Integrado (Subyacente vs. Opciones)</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{chart_base64}" alt="Evolución y Validación Cruzada">
        </div>

        <h2>Ranking de los Top 5 Contratos (Ventana de 10 Semanas)</h2>
        <table>
            <thead>
                <tr>
                    <th>Expiración</th>
                    <th>Strike</th>
                    <th>Tipo</th>
                    <th>Prima Total ($)</th>
                    <th>Heat Máx.</th>
                    <th>Sentimiento</th>
                    <th>Score</th>
                </tr>
            </thead>
            <tbody>
    """

    for _, row in top_5.iterrows():
        html_content += f"""
                <tr>
                    <td>{row['Expiry'].strftime('%Y-%m-%d')}</td>
                    <td>${row['Strike ($)']}</td>
                    <td>{row['C/P']}</td>
                    <td>${row['Total_Premium']:,.0f}</td>
                    <td>{row['Max_Heat']}</td>
                    <td>{row['Sentiment_Dominante']}</td>
                    <td><strong>{row['Score']:.1f}</strong></td>
                </tr>
        """

    html_content += f"""
            </tbody>
        </table>

        <div class="footer">
            Informe generado mediante análisis cuantitativo de flujo de opciones y Yahoo Finance &bull; Referencia: {fecha_analisis.strftime('%Y-%m-%d')}
        </div>
    </div>

    </body>
    </html>
    """

    # 8. Abrir en el navegador de forma interactiva temporal
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp_html:
        tmp_html.write(html_content)
        tmp_html_path = tmp_html.name

    print("\nAbriendo el informe interactivo mejorado en tu navegador web predeterminado...")
    webbrowser.open('file://' + os.path.abspath(tmp_html_path))

if __name__ == "__main__":
    generar_analisis_robusto()