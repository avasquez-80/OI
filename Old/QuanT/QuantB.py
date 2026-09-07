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

# Intentar importar yfinance
try:
    import yfinance as yf
    YFINANCE_DISPONIBLE = True
except ImportError:
    YFINANCE_DISPONIBLE = False

# Intentar importar la API de Google GenAI
try:
    from google import genai
    GEMINI_DISPONIBLE = True
except ImportError:
    GEMINI_DISPONIBLE = False

# Forzar codificacion UTF-8 para la consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def limpiar_valor_numerico(val):
    """Limpia cadenas numéricas con separadores de miles por puntos y sufijos M/K."""
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip().replace('$', '')
    
    mult = 1.0
    if val_str.endswith('M'):
        mult = 1_000_000.0
        val_str = val_str[:-1]
    elif val_str.endswith('K'):
        mult = 1_000.0
        val_str = val_str[:-1]
    elif val_str.endswith('B'):
        mult = 1_000_000_000.0
        val_str = val_str[:-1]
        
    val_str = val_str.replace(',', '')
    if val_str.count('.') > 1:
        val_str = val_str.replace('.', '')
    elif val_str.count('.') == 1:
        partes = val_str.split('.')
        if len(partes[1]) == 3 and len(partes[0]) <= 3:
            val_str = val_str.replace('.', '')
            
    try:
        return float(val_str) * mult
    except ValueError:
        return 0.0

def procesar_pools_institucionales(ruta_dp):
    """Procesa el CSV segregando estrictamente entre Dark Pools y Lit Pools."""
    if not ruta_dp:
        return None, None
    try:
        df_dp = pd.read_csv(ruta_dp)
        df_dp['Amount_Clean'] = df_dp['Amount'].apply(limpiar_valor_numerico)
        df_dp['Size_Clean'] = df_dp['Size'].apply(limpiar_valor_numerico)
        df_dp['Price_Clean'] = df_dp['Price'].astype(str).str.replace('$', '').str.replace(',', '').astype(float)
        
        # Segregar por tipo de Pool
        df_dark = df_dp[df_dp['Pool'].str.strip().str.lower() == 'dark'].copy()
        df_lit = df_dp[df_dp['Pool'].str.strip().str.lower() == 'lit'].copy()
        
        def resumir_subpool(sub_df):
            if sub_df.empty:
                return None
            total_monto = sub_df['Amount_Clean'].sum()
            total_volumen = sub_df['Size_Clean'].sum()
            impresiones = len(sub_df)
            
            niveles = sub_df.groupby('Price_Clean').agg(
                Total_Amount=('Amount_Clean', 'sum'),
                Total_Size=('Size_Clean', 'sum'),
                Prints=('Date', 'count')
            ).reset_index().sort_values(by='Total_Amount', ascending=False)
            
            return {
                "total_monto": total_monto,
                "total_volumen": total_volumen,
                "impresiones": impresiones,
                "top_niveles": niveles.head(5)
            }
            
        resumen_dark = resumir_subpool(df_dark)
        resumen_lit = resumir_subpool(df_lit)
        
        print(f" -> Análisis segregado completado:")
        if resumen_dark:
            print(f"    • Dark Pools: {resumen_dark['impresiones']} bloques (${resumen_dark['total_monto']:,.2f})")
        if resumen_lit:
            print(f"    • Lit Pools: {resumen_lit['impresiones']} bloques (${resumen_lit['total_monto']:,.2f})")
            
        return resumen_dark, resumen_lit
    except Exception as e:
        print(f"Advertencia al procesar pools institucionales: {e}")
        return None, None

def obtener_analisis_ia(ranking, ganador, stock_data, datos_dark=None, datos_lit=None):
    """Consulta a la IA cruzando derivados, subyacente, Dark Pools y Lit Pools segregados."""
    
    contexto_pools = ""
    if datos_dark:
        niveles_dark_str = ""
        for _, row in datos_dark['top_niveles'].iterrows():
            niveles_dark_str += f"   - Nivel Dark ${row['Price_Clean']:.2f}: {row['Prints']} prints, Vol: {row['Total_Size']:,.0f}, Monto: ${row['Total_Amount']:,.2f}\n"
        contexto_pools += f"""
        - Acumulación Oculta (Dark Pools): {datos_dark['impresiones']} bloques, Monto total: ${datos_dark['total_monto']:,.2f}.
        Top Muros Dark:
        {niveles_dark_str}
        """
        
    if datos_lit:
        niveles_lit_str = ""
        for _, row in datos_lit['top_niveles'].iterrows():
            niveles_lit_str += f"   - Nivel Lit ${row['Price_Clean']:.2f}: {row['Prints']} prints, Vol: {row['Total_Size']:,.0f}, Monto: ${row['Total_Amount']:,.2f}\n"
        contexto_pools += f"""
        - Ejecución Pública en Bloque (Lit Pools): {datos_lit['impresiones']} bloques, Monto total: ${datos_lit['total_monto']:,.2f}.
        Top Muros Lit:
        {niveles_lit_str}
        """

    if not contexto_pools:
        contexto_pools = "- Actividad Institucional (Dark/Lit): No se cargaron registros opcionales."

    if not GEMINI_DISPONIBLE or not os.environ.get("GEMINI_API_KEY"):
        return f"""
        <div class="card" style="border-left: 4px solid #3182ce; background-color: #f7fafc;">
            <h3 style="margin-top: 0; color: #1a365d;">🔍 Análisis Institucional Estándar (Segregado)</h3>
            <ul>
                <li><strong>Opciones (Smart Money):</strong> Contrato líder Strike ${ganador['Strike ($)']} {ganador['C/P']}.</li>
                {f"<li><strong>Dark Pools:</strong> {datos_dark['impresiones']} bloques por ${datos_dark['total_monto']:,.2f}</li>" if datos_dark else ""}
                {f"<li><strong>Lit Pools:</strong> {datos_lit['impresiones']} bloques por ${datos_lit['total_monto']:,.2f}</li>" if datos_lit else ""}
                <li><strong>Recomendación:</strong> Vigilar niveles clave alineados al vencimiento del {ganador['Expiry'].strftime('%Y-%m-%d')}.</li>
            </ul>
        </div>
        """

    try:
        client = genai.Client()
        top_ticker = ganador['Ticker']
        strike = ganador['Strike ($)']
        cp = ganador['C/P']
        prima = ganador['Total_Premium']
        heat = ganador['Max_Heat']
        exp = ganador['Expiry'].strftime('%Y-%m-%d')
        
        prompt = f"""
        Actúa como un analista cuantitativo senior de derivados y microestructura de mercado institucional. 
        Analiza estos datos cuantitativos segregados para el ticker {top_ticker}:
        - Contrato líder de opciones: Opción {cp} con strike ${strike}, expiración {exp}.
        - Prima total acumulada en opciones: ${prima:,.2f} | Heat Score Máx: {heat} | Sentimiento: {ganador['Sentiment_Dominante']}
        {contexto_pools}
        
        Redacta un análisis institucional breve, profesional y directo (en español) con 4 viñetas estructuradas que incluyan:
        1. Concentración de capital en derivados y lectura de smart money.
        2. Análisis cruzado y contraste entre la acumulación silenciosa en Dark Pools y la ejecución pública en Lit Pools con respecto al Strike ganador (${strike}).
        3. Perspectiva de riesgo/recompensa para este contrato.
        4. Una recomendación operativa clara de gestión de riesgo basada en la microestructura segregada.
        Devuélvelo formateado en código HTML limpio usando etiquetas <ul> y <li> con formato profesional.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return f"""
        <div class="card" style="border-left: 4px solid #3182ce; background-color: #f7fafc;">
            <h3 style="margin-top: 0; color: #1a365d;">🤖 Análisis Institucional Dinámico Segregado (IA Gemini)</h3>
            {response.text}
        </div>
        """
    except Exception as e:
        return f"<p><em>No se pudo generar el análisis de IA en tiempo real: {e}</em></p>"

def generar_analisis_robusto():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    print("Abriendo ventana de selección de archivos (Option Flow)...")
    ruta_csv = filedialog.askopenfilename(
        title="Selecciona el archivo CSV de flujo de opciones",
        filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
    )
    
    if not ruta_csv:
        print("Operación cancelada. No se seleccionó ningún archivo de opciones.")
        return
        
    print(f"Archivo de opciones seleccionado: {ruta_csv}")
    
    print("Abriendo ventana de selección de archivos (Dark/Lit Pools - Opcional)...")
    ruta_dp = filedialog.askopenfilename(
        title="Selecciona el archivo CSV de Dark/Lit Pools (Opcional - Presiona Cancelar para omitir)",
        filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
    )
    
    datos_dark, datos_lit = None, None
    if ruta_dp:
        print(f"Archivo institucional seleccionado: {ruta_dp}")
        datos_dark, datos_lit = procesar_pools_institucionales(ruta_dp)
    else:
        print("Análisis de Dark/Lit Pools omitido por el usuario.")
    
    try:
        df = pd.read_csv(ruta_csv)
    except Exception as e:
        print(f"Error al leer el archivo CSV de opciones: {e}")
        return
    
    columnas_necesarias = ['Ticker', 'Trade Date', 'Expiry', 'Premium ($)', 'Size', 'Heat Score', 'Strike ($)', 'C/P', 'Trade Sentiment', 'Open Interest']
    for col in columnas_necesarias:
        if col not in df.columns:
            print(f"Error: El archivo CSV no contiene la columna obligatoria '{col}'.")
            return
            
    df['Trade Date'] = pd.to_datetime(df['Trade Date'])
    df['Expiry'] = pd.to_datetime(df['Expiry'])
    
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
    
    stock_data = pd.DataFrame()
    if YFINANCE_DISPONIBLE:
        print(f"\nDescargando historial técnico de {ticker_ganador} desde Yahoo Finance...")
        inicio_hist = df['Trade Date'].min() - pd.Timedelta(days=5)
        fin_hist = fecha_analisis + pd.Timedelta(days=1)
        try:
            stock_data = yf.download(ticker_ganador, start=inicio_hist.strftime('%Y-%m-%d'), end=fin_hist.strftime('%Y-%m-%d'), progress=False)
            if isinstance(stock_data.columns, pd.MultiIndex):
                stock_data.columns = stock_data.columns.get_level_values(0)
            stock_data = stock_data.reset_index()
            if 'Date' in stock_data.columns:
                stock_data['Trade Date'] = pd.to_datetime(stock_data['Date']).dt.normalize()
            elif 'Datetime' in stock_data.columns:
                stock_data['Trade Date'] = pd.to_datetime(stock_data['Datetime']).dt.normalize()
        except Exception as e:
            print(f"Advertencia: No se pudo descargar datos de Yahoo Finance: {e}")
            
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
    
    if not stock_data.empty and 'Close' in stock_data.columns:
        tendencia_diaria = tendencia_diaria.merge(stock_data[['Trade Date', 'Close', 'Volume']], on='Trade Date', how='left')
    
    # 8. Generar Dashboard Gráfico Dinámico Segregado
    print("\nGenerando dashboard gráfico institucional segregado y consultando a la IA...")
    
    tiene_dark = datos_dark is not None and not datos_dark['top_niveles'].empty
    tiene_lit = datos_lit is not None and not datos_lit['top_niveles'].empty
    
    # Determinar número exacto de paneles
    num_panels = 2
    if tiene_dark: num_panels += 1
    if tiene_lit: num_panels += 1
    
    # Crear figura y ejes de forma robusta
    fig, axes = plt.subplots(num_panels, 1, figsize=(10, 4 * num_panels), dpi=300, sharex=False)
    
    # Asegurar que axes sea siempre una lista iterable aunque sea 1 solo subplot (aquí siempre son >= 2)
    if num_panels == 2:
        ax1, ax2 = axes
        ax3, ax4 = None, None
    elif num_panels == 3:
        ax1, ax2, ax3 = axes
        ax4 = None
    elif num_panels == 4:
        ax1, ax2, ax3, ax4 = axes
        
    # Panel 1: Precio Subyacente + Muros Dark Pool superpuestos
    if not stock_data.empty and 'Close' in stock_data.columns and not stock_data['Close'].isna().all():
        ax1.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Close'], color='#2b6cb0', marker='s', linewidth=2, label=f'Precio Cierre {ticker_ganador}')
        ax1.set_ylabel('Precio Subyacente ($)', color='#2b6cb0', fontweight='bold', fontsize=9)
        ax1.tick_params(axis='y', labelcolor='#2b6cb0')
        ax1.grid(True, linestyle='--', alpha=0.4)
        
        if tiene_dark:
            top_muros_d = datos_dark['top_niveles'].head(3)
            for _, row in top_muros_d.iterrows():
                p_lvl = row['Price_Clean']
                amt_m = row['Total_Amount'] / 1e6
                ax1.axhline(y=p_lvl, color='#805ad5', linestyle='--', alpha=0.8, linewidth=1.5)
                ax1.text(tendencia_diaria['Trade Date'].iloc[0], p_lvl, f'  Dark Wall: ${p_lvl:.2f} (${amt_m:.1f}M)', 
                         color='#6b46c1', fontsize=8, fontweight='bold', verticalalignment='bottom')

        ax1.legend(loc='upper left')
        ax1.set_title(f'Validación Cruzada: Acción Subyacente y Muros Dark Pool ({ticker_ganador})', fontsize=11, fontweight='bold', pad=10)
    else:
        ax1.text(0.5, 0.5, 'Datos de precio no disponibles para este ticker', horizontalalignment='center', verticalalignment='center')
        ax1.set_title(f'Acción Subyacente ({ticker_ganador})', fontsize=11, fontweight='bold', pad=10)

    # Panel 2: Open Interest y Primas Diarias de Opciones
    color_oi = '#3182ce'
    ax2.set_xlabel('Fecha de Negociación', fontweight='bold', fontsize=9)
    ax2.set_ylabel('Open Interest', color=color_oi, fontweight='bold', fontsize=9)
    ax2.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Open_Interest'], color=color_oi, marker='o', linewidth=2, label='Open Interest')
    ax2.tick_params(axis='y', labelcolor=color_oi)
    
    ax_prem = ax2.twinx()
    color_prem = '#e53e3e'
    ax_prem.set_ylabel('Prima Diaria ($)', color=color_prem, fontweight='bold', fontsize=9)
    ax_prem.bar(tendencia_diaria['Trade Date'], tendencia_diaria['Daily_Premium'], color=color_prem, alpha=0.35, width=0.6, label='Prima Diaria')
    ax_prem.tick_params(axis='y', labelcolor=color_prem)
    
    ax2.grid(True, linestyle='--', alpha=0.4)
    ax2.set_title(f'Dinámica del Contrato: Strike ${strike_ganador} {cp_ganador} (Exp: {exp_ganadora.strftime("%Y-%m-%d")})', fontsize=10, fontweight='bold', pad=8)

    # Panel 3: Muros Dark Pools segregados (si existe)
    if tiene_dark and ax3 is not None:
        top_d = datos_dark['top_niveles'].head(5).sort_values(by='Total_Amount', ascending=True)
        precios_d = [f"${p:.2f}" for p in top_d['Price_Clean']]
        montos_d = top_d['Total_Amount'] / 1e6
        
        bars_d = ax3.barh(precios_d, montos_d, color='#805ad5', alpha=0.8, height=0.55)
        ax3.set_xlabel('Monto Negociado (Millones de $)', fontweight='bold', fontsize=9, color='#553c9a')
        ax3.set_title('Top Muros de Acumulación Oculta (Dark Pool Levels)', fontsize=10, fontweight='bold', pad=8, color='#553c9a')
        ax3.grid(True, linestyle='--', alpha=0.4, axis='x')
        
        for bar in bars_d:
            w = bar.get_width()
            ax3.text(w + (w * 0.02), bar.get_y() + bar.get_height()/2, f'${w:.1f}M', 
                     ha='left', va='center', fontsize=8, fontweight='bold', color='#553c9a')

    # Panel 4: Muros Lit Pools segregados (si existe)
    target_ax_lit = ax4 if ax4 is not None else (ax3 if tiene_lit and not tiene_dark else None)
    if tiene_lit and target_ax_lit is not None:
        top_l = datos_lit['top_niveles'].head(5).sort_values(by='Total_Amount', ascending=True)
        precios_l = [f"${p:.2f}" for p in top_l['Price_Clean']]
        montos_l = top_l['Total_Amount'] / 1e6
        
        bars_l = target_ax_lit.barh(precios_l, montos_l, color='#d69e2e', alpha=0.8, height=0.55)
        target_ax_lit.set_xlabel('Monto Negociado (Millones de $)', fontweight='bold', fontsize=9, color='#b7791f')
        target_ax_lit.set_title('Top Bloques de Ejecución Pública (Lit Pool Levels)', fontsize=10, fontweight='bold', pad=8, color='#b7791f')
        target_ax_lit.grid(True, linestyle='--', alpha=0.4, axis='x')
        
        for bar in bars_l:
            w = bar.get_width()
            target_ax_lit.text(w + (w * 0.02), bar.get_y() + bar.get_height()/2, f'${w:.1f}M', 
                     ha='left', va='center', fontsize=8, fontweight='bold', color='#b7791f')
            
    fig.tight_layout()
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
        plt.savefig(tmp_img.name, bbox_inches='tight')
        tmp_img_path = tmp_img.name
    plt.close()
    
    with open(tmp_img_path, 'rb') as img_file:
        chart_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    os.unlink(tmp_img_path)
        
    top_5 = ranking.head(5)
    
    # 9. Obtener el análisis inteligente de la IA con datos segregados
    analisis_ia_html = obtener_analisis_ia(ranking, ganador, stock_data, datos_dark, datos_lit)
    
    # 10. Construcción del informe HTML interactivo
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
    <meta charset="UTF-8">
    <title>Informe Cuantitativo Segregado con IA</title>
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
        .header-banner {{
            background-color: #1a365d;
            color: white;
            margin: -30px -30px 25px -30px;
            padding: 25px 30px;
            border-radius: 8px 8px 0 0;
            border-bottom: 4px solid #3182ce;
        }}
        <div class="header-banner">
            <h1>Informe Cuantitativo Segregado (Dark vs Lit)</h1>
            <p>Microestructura Institucional Integrada y Validación (Ticker: {ticker_ganador})</p>
        </div>

        <h2>Resumen Metodológico</h2>
        <div class="card">
            <p>Este informe segrega y contrasta la acumulación oculta (<strong>Dark Pools</strong>) frente a la ejecución pública en bloque (<strong>Lit Pools</strong>), cruzándola con derivados y precios (vía <strong>Yahoo Finance</strong>) para <strong>{ticker_ganador}</strong> en una ventana de <strong>10 semanas</strong>.</p>
        </div>

        {analisis_ia_html}

        <h2>Contrato Ganador Detectado</h2>
        <div class="card" style="background-color: #f7fafc; border-left: 4px solid #3182ce; padding-left: 15px;">
            <p style="margin-bottom: 6px;"><strong>Opción Líder:</strong> Call con Strike <strong>${strike_ganador}</strong> y Vencimiento <span>{exp_ganadora.strftime('%Y-%m-%d')}</span></p>
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

        <h2>Dashboard Institucional Segregado (Dark & Lit Pools)</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{chart_base64}" alt="Dashboard Segregado Dark/Lit">
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
            Informe cuantitativo institucional con análisis segregado &bull; Referencia: {fecha_analisis.strftime('%Y-%m-%d')}
        </div>
    </div>

    </body>
    </html>
    """

    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp_html:
        tmp_html.write(html_content)
        tmp_html_path = tmp_html.name

    print("\nAbriendo el dashboard institucional segregado en tu navegador web...")
    webbrowser.open('file://' + os.path.abspath(tmp_html_path))

if __name__ == "__main__":
    generar_analisis_robusto()