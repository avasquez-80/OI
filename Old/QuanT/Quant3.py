import sys
import io
import os
import base64
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import matplotlib.pyplot as plt

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def generar_informe_integral():
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
    
    # 4. Generar Gráfica para el contrato ganador
    print("\nGenerando gráfica de tendencia y exportando informe integral...")
    
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
    
    fig, ax1 = plt.subplots(figsize=(10, 4.5), dpi=300)
    
    color_oi = '#1f77b4'
    ax1.set_xlabel('Fecha de Negociación', fontweight='bold', fontsize=10)
    ax1.set_ylabel('Open Interest', color=color_oi, fontweight='bold', fontsize=10)
    ax1.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Open_Interest'], color=color_oi, marker='o', linewidth=2, label='Open Interest')
    ax1.tick_params(axis='y', labelcolor=color_oi)
    plt.xticks(rotation=30, fontsize=9)
    
    ax2 = ax1.twinx()
    color_prem = '#d62728'
    ax2.set_ylabel('Prima Diaria Acumulada ($)', color=color_prem, fontweight='bold', fontsize=10)
    ax2.bar(tendencia_diaria['Trade Date'], tendencia_diaria['Daily_Premium'], color=color_prem, alpha=0.3, width=0.6, label='Prima Diaria')
    ax2.tick_params(axis='y', labelcolor=color_prem)
    
    plt.title(f'Evolución del Contrato Líder: {ticker_ganador} Strike {strike_ganador} {cp_ganador} (Exp: {exp_ganadora.strftime("%Y-%m-%d")})', fontsize=11, fontweight='bold', pad=12)
    fig.tight_layout()
    plt.grid(True, linestyle='--', alpha=0.4)
    
    chart_path = 'contract_trend.png'
    plt.savefig(chart_path, bbox_inches='tight')
    plt.close()
    
    # 5. Generar Reporte PDF All-in-One
    with open(chart_path, 'rb') as img_file:
        chart_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        
    top_5 = ranking.head(5)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 15mm;
            background-color: #fcfbf9;
            @bottom-right {{
                content: "Página " counter(page);
                font-size: 9pt;
                color: #666;
            }}
        }}
        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #2c3e50;
            line-height: 1.5;
            font-size: 10pt;
        }}
        .header-banner {{
            background-color: #1a365d;
            color: white;
            margin: -15mm -15mm 15mm -15mm;
            padding: 18mm 15mm 12mm 15mm;
            border-bottom: 4px solid #3182ce;
        }}
        .header-banner h1 {{
            margin: 0 0 4px 0;
            font-size: 20pt;
            font-weight: 700;
        }}
        .header-banner p {{
            margin: 0;
            font-size: 10.5pt;
            color: #e2e8f0;
        }}
        h2 {{
            font-size: 13pt;
            color: #1a365d;
            border-left: 4px solid #3182ce;
            padding-left: 8px;
            margin-top: 18px;
            margin-bottom: 8px;
            page-break-after: avoid;
        }}
        .card {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 10px 14px;
            margin-bottom: 12px;
        }}
        .winner-grid {{
            width: 100%;
            margin-bottom: 12px;
        }}
        .metric-box {{
            background: #ebf8ff;
            border: 1px solid #bee3f8;
            border-radius: 6px;
            padding: 10px;
            text-align: center;
            width: 23%;
            display: inline-block;
            margin-right: 2%;
            vertical-align: top;
        }}
        .metric-box:last-child {{
            margin-right: 0;
        }}
        .metric-value {{
            font-size: 12pt;
            font-weight: bold;
            color: #2b6cb0;
            margin-top: 3px;
        }}
        .metric-label {{
            font-size: 8pt;
            color: #4a5568;
            text-transform: uppercase;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            margin-bottom: 12px;
            background: #ffffff;
            font-size: 9pt;
        }}
        th {{
            background-color: #2d3748;
            color: white;
            text-align: left;
            padding: 7px 9px;
            font-weight: 600;
        }}
        td {{
            padding: 7px 9px;
            border-bottom: 1px solid #e2e8f0;
            color: #4a5568;
        }}
        tr:nth-child(even) {{
            background-color: #f7fafc;
        }}
        .chart-container {{
            text-align: center;
            margin: 12px 0;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 8px;
            page-break-inside: avoid;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
        }}
        .footer {{
            margin-top: 25px;
            font-size: 8pt;
            color: #718096;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            padding-top: 8px;
        }}
    </style>
    </head>
    <body>

    <div class="header-banner">
        <h1>Informe Cuantitativo de Flujo de Opciones</h1>
        <p>Análisis Institucional, Ranking y Proyección a 10 Semanas (Ticker: {ticker_ganador})</p>
    </div>

    <h2>Resumen Metodológico</h2>
    <div class="card">
        <p>Este informe consolida el análisis cuantitativo de flujo de opciones para <strong>{ticker_ganador}</strong>. Tomando como referencia la última fecha de negociación (<strong>{fecha_analisis.strftime('%Y-%m-%d')}</strong>), se proyecta una ventana de <strong>10 semanas (70 días)</strong>. El modelo pondera la <strong>Prima Total (60%)</strong> y el <strong>Heat Score Máximo (40%)</strong>.</p>
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

    <h2>Gráfica de Tendencia y Flujo Diario del Contrato Líder</h2>
    <div class="chart-container">
        <img src="data:image/png;base64,{chart_base64}" alt="Evolución y Flujo Diario">
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
        Informe generado automáticamente mediante análisis cuantitativo de flujo de opciones &bull; Referencia: {fecha_analisis.strftime('%Y-%m-%d')}
    </div>

    </body>
    </html>
    """

    html_filename = 'report.html'
    pdf_filename = 'informe_flujo_opciones_integral.pdf'
    
    with open(html_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    try:
        from weasyprint import HTML
        HTML(html_filename).write_pdf(pdf_filename)
        print(f"\n¡Informe PDF generado con éxito como '{pdf_filename}'!")
    except Exception as e:
        print(f"\nNota: Se generó el archivo HTML ('{html_filename}'). Para exportar a PDF automáticamente instale weasyprint.")

if __name__ == "__main__":
    generar_informe_integral()