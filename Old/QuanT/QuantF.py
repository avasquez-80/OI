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
        return resumen_dark, resumen_lit
    except Exception as e:
        print(f"Advertencia al procesar pools institucionales: {e}")
        return None, None

def calcular_indicadores_tecnicos(stock_df):
    """Calcula EMA 9, EMA 21, MACD (12,26,9), Volumen y Canales según estrategia de TradingView."""
    if stock_df.empty or 'Close' not in stock_df.columns:
        return stock_df
    df = stock_df.copy()
    df = df.sort_values('Trade Date')
    
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Line'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD_Line'] - df['MACD_Signal']
    
    if 'Open' in df.columns:
        df['Vol_Color'] = np.where(df['Close'] >= df['Open'], '#38a169', '#e53e3e')
    else:
        df['Vol_Color'] = np.where(df['Close'] >= df['Close'].shift(1), '#38a169', '#e53e3e')
        
    df['Support'] = df['Low'].rolling(window=20, min_periods=5).min()
    df['Resistance'] = df['High'].rolling(window=20, min_periods=5).max()
    
    return df

def obtener_info_fundamental_y_noticias(ticker_symbol):
    """Extrae datos fundamentales, fecha de earnings y titulares de noticias recientes usando yfinance."""
    if not YFINANCE_DISPONIBLE:
        return {"proximo_earnings": "No disponible", "market_cap": "No disponible", "titulares": []}
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info
        market_cap = info.get('marketCap', 0)
        market_cap_str = f"${market_cap:,.0f}" if market_cap else "No disponible"
        
        prox_earnings = "No especificada"
        try:
            cal = t.calendar
            if cal is not None and isinstance(cal, dict) and 'Earnings Date' in cal:
                ed_list = cal['Earnings Date']
                if len(ed_list) > 0:
                    prox_earnings = str(ed_list[0]).split()[0]
        except Exception:
            try:
                ed_df = t.earnings_dates
                if ed_df is not None and not ed_df.empty:
                    futuros = ed_df[ed_df.index > pd.Timestamp.now()]
                    if not futuros.empty:
                        prox_earnings = futuros.index[0].strftime('%Y-%m-%d')
            except Exception:
                pass
                
        # Extraer noticias recientes
        titulares = []
        try:
            news_list = t.news
            if news_list:
                for item in news_list[:5]: # Tomar los 5 titulares más recientes
                    # yfinance news structure varies slightly across versions
                    title = item.get('title') or item.get('content', {}).get('title')
                    publisher = item.get('publisher') or item.get('content', {}).get('provider', {}).get('displayName')
                    if title:
                        titulares.append(f"- {title} ({publisher if publisher else 'Medio Financiero'})")
        except Exception:
            pass
                
        return {
            "market_cap": market_cap_str,
            "proximo_earnings": prox_earnings,
            "titulares": titulares
        }
    except Exception as e:
        return {"proximo_earnings": "No disponible", "market_cap": "No disponible", "titulares": []}

def obtener_analisis_ia(ranking, ganador, stock_data, datos_dark=None, datos_lit=None, info_fund=None):
    """Consulta a la IA integrando derivados, microestructura, técnica EMA 9/21, fundamentales y noticias de mercado."""
    
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

    contexto_tecnico = ""
    if not stock_data.empty and 'Close' in stock_data.columns:
        ult = stock_data.iloc[-1]
        p_act = ult['Close']
        ema9 = ult.get('EMA_9', p_act)
        ema21 = ult.get('EMA_21', p_act)
        macd_h = ult.get('MACD_Hist', 0)
        
        cruce_ema = "Alcista (EMA 9 sobre EMA 21)" if ema9 > ema21 else "Bajista (EMA 9 bajo EMA 21)"
        momentum_macd = "Positivo (Bullish)" if macd_h > 0 else "Negativo (Bearish)"
        
        contexto_tecnico = f"""
        - Análisis Técnico Diario (TradingView Style):
          * Precio de Cierre Actual: ${p_act:.2f}
          * Tendencia EMA (9 y 21): {cruce_ema} (EMA 9: ${ema9:.2f}, EMA 21: ${ema21:.2f})
          * Momentum MACD (12,26,9): Histograma {momentum_macd} ({macd_h:.4f})
        """

    info_fund_str = ""
    if info_fund:
        titulares_str = "\n".join(info_fund.get('titulares', [])) if info_fund.get('titulares') else "No hay titulares recientes destacados."
        info_fund_str = f"""
        - Contexto Fundamental, Noticias y Riesgo de Evento:
          * Capitalización de Mercado: {info_fund.get('market_cap', 'N/D')}
          * Próximo Reporte de Ganancias (Earnings): {info_fund.get('proximo_earnings', 'N/D')}
          * Titulares y Noticias Recientes del Mercado:
          {titulares_str}
        """

    if not GEMINI_DISPONIBLE or not os.environ.get("GEMINI_API_KEY"):
        return f"""
        <div class="card" style="border-left: 4px solid #3182ce; background-color: #f7fafc;">
            <h3 style="margin-top: 0; color: #1a365d;">🔍 Análisis Institucional Estándar (Noticias + Opciones)</h3>
            <ul>
                <li><strong>Opciones (Smart Money):</strong> Contrato líder Strike ${ganador['Strike ($)']} {ganador['C/P']}.</li>
                <li><strong>Recomendación:</strong> Vigilar catalizadores de noticias alineados al vencimiento del {ganador['Expiry'].strftime('%Y-%m-%d')}.</li>
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
        Actúa como un analista cuantitativo senior de derivados, microestructura, trading técnico y análisis de riesgo fundamental. 
        Analiza estos datos cuantitativos completos para el ticker {top_ticker}:
        - Contrato líder de opciones: Opción {cp} con strike ${strike}, expiración {exp}.
        - Prima total acumulada en opciones: ${prima:,.2f} | Heat Score Máx: {heat} | Sentimiento: {ganador['Sentiment_Dominante']}
        {contexto_tecnico}
        {contexto_pools}
        {info_fund_str}
        
        Redacta un análisis institucional riguroso, profesional y directo (en español) con 4 viñetas estructuradas que incluyan:
        1. Lectura conjunta del sistema técnico (EMA 9/21, MACD y Volumen) y su concordancia con el flujo institucional de opciones.
        2. Confluencia entre los muros institucionales (Dark/Lit Pools) y los niveles de precio actuales de la acción.
        3. Evaluación de riesgos derivados de noticias recientes, comunicados o reportes de ganancias pendientes frente al vencimiento del contrato.
        4. Una recomendación operativa clara de entrada/salida y gestión de riesgo basada en la confluencia de todas estas capas.
        Devuélvelo formateado en código HTML limpio usando etiquetas <ul> y <li> con formato profesional.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return f"""
        <div class="card" style="border-left: 4px solid #3182ce; background-color: #f7fafc;">
            <h3 style="margin-top: 0; color: #1a365d;">🤖 Análisis Institucional Integral con Noticias y Riesgo (IA Gemini)</h3>
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
    
    ganador = ranking.iloc[0]
    exp_ganadora = ganador['Expiry']
    strike_ganador = ganador['Strike ($)']
    cp_ganador = ganador['C/P']
    ticker_ganador = ganador['Ticker']
    
    print(f"\nContrato ganador detectado para {ticker_ganador}: Strike ${strike_ganador} {cp_ganador} (Exp: {exp_ganadora.strftime('%Y-%m-%d')})")
    
    print("Consultando información fundamental, calendario de earnings y noticias recientes...")
    info_fund = obtener_info_fundamental_y_noticias(ticker_ganador)
    
    stock_data = pd.DataFrame()
    if YFINANCE_DISPONIBLE:
        print(f"Descargando historial técnico diario y calculando indicadores para {ticker_ganador}...")
        inicio_hist = df['Trade Date'].min() - pd.Timedelta(days=60)
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
                
            stock_data = calcular_indicadores_tecnicos(stock_data)
        except Exception as e:
            print(f"Advertencia al descargar Yahoo Finance: {e}")
            
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
        tendencia_diaria = tendencia_diaria.merge(stock_data[['Trade Date', 'Close', 'Volume', 'EMA_9', 'EMA_21', 'MACD_Hist']], on='Trade Date', how='left')
    
    print("Generando dashboard gráfico institucional estilo TradingView...")
    tiene_dark = datos_dark is not None and not datos_dark['top_niveles'].empty
    tiene_lit = datos_lit is not None and not datos_lit['top_niveles'].empty
    
    num_panels = 4
    if tiene_dark: num_panels += 1
    if tiene_lit: num_panels += 1
    
    fig, axes = plt.subplots(num_panels, 1, figsize=(10, 3.2 * num_panels), dpi=300, sharex=False)
    
    ax_price = axes[0]
    ax_vol = axes[1]
    ax_macd = axes[2]
    ax_opt = axes[3]
    
    panel_idx = 4
    ax_dark = axes[panel_idx] if tiene_dark and panel_idx < num_panels else None
    if tiene_dark: panel_idx += 1
    ax_lit = axes[panel_idx] if tiene_lit and panel_idx < num_panels else None

    # Panel 1: Precio + EMA 9 / EMA 21
    if not stock_data.empty and 'Close' in stock_data.columns and not stock_data['Close'].isna().all():
        ax_price.plot(stock_data['Trade Date'], stock_data['Close'], color='#2b6cb0', linewidth=1.2, alpha=0.6, label=f'Cierre {ticker_ganador}')
        if 'EMA_9' in stock_data.columns:
            ax_price.plot(stock_data['Trade Date'], stock_data['EMA_9'], color='#3182ce', linewidth=1.8, label='EMA 9')
        if 'EMA_21' in stock_data.columns:
            ax_price.plot(stock_data['Trade Date'], stock_data['EMA_21'], color='#e53e3e', linewidth=1.8, label='EMA 21')
            
        ax_price.set_ylabel('Precio ($)', color='#2b6cb0', fontweight='bold', fontsize=9)
        ax_price.grid(True, linestyle='--', alpha=0.4)
        
        if tiene_dark:
            top_muros_d = datos_dark['top_niveles'].head(3)
            for _, row in top_muros_d.iterrows():
                p_lvl = row['Price_Clean']
                amt_m = row['Total_Amount'] / 1e6
                ax_price.axhline(y=p_lvl, color='#805ad5', linestyle='--', alpha=0.8, linewidth=1.2)
                ax_price.text(stock_data['Trade Date'].iloc[0], p_lvl, f'  Dark Wall: ${p_lvl:.2f} (${amt_m:.1f}M)', 
                              color='#6b46c1', fontsize=7.5, fontweight='bold', verticalalignment='bottom')

        ax_price.legend(loc='upper left', fontsize=8)
        ax_price.set_title(f'Estrategia Tendencial: EMA 9 y EMA 21 ({ticker_ganador})', fontsize=10, fontweight='bold', pad=8)

    # Panel 2: Volumen Diario
    if not stock_data.empty and 'Volume' in stock_data.columns:
        v_colors = stock_data['Vol_Color'] if 'Vol_Color' in stock_data.columns else '#3182ce'
        ax_vol.bar(stock_data['Trade Date'], stock_data['Volume'], color=v_colors, alpha=0.7, width=0.8)
        ax_vol.set_ylabel('Volumen', fontweight='bold', fontsize=9)
        ax_vol.grid(True, linestyle='--', alpha=0.4)
        ax_vol.set_title('Volumen Diario', fontsize=10, fontweight='bold', pad=8)

    # Panel 3: MACD
    if not stock_data.empty and 'MACD_Hist' in stock_data.columns:
        ax_macd.plot(stock_data['Trade Date'], stock_data['MACD_Line'], color='#3182ce', linewidth=1.2, label='MACD Line')
        ax_macd.plot(stock_data['Trade Date'], stock_data['MACD_Signal'], color='#e53e3e', linewidth=1.2, label='Signal')
        colors_hist = ['#38a169' if val >= 0 else '#e53e3e' for val in stock_data['MACD_Hist']]
        ax_macd.bar(stock_data['Trade Date'], stock_data['MACD_Hist'], color=colors_hist, alpha=0.6, width=0.8, label='Histograma')
        ax_macd.axhline(0, color='gray', linestyle='-', linewidth=0.8)
        ax_macd.set_ylabel('MACD', fontweight='bold', fontsize=9)
        ax_macd.grid(True, linestyle='--', alpha=0.4)
        ax_macd.legend(loc='upper left', fontsize=8)
        ax_macd.set_title('MACD (12, 26, 9)', fontsize=10, fontweight='bold', pad=8)

    # Panel 4: Opciones
    color_oi = '#3182ce'
    ax_opt.set_ylabel('Open Interest', color=color_oi, fontweight='bold', fontsize=9)
    ax_opt.plot(tendencia_diaria['Trade Date'], tendencia_diaria['Open_Interest'], color=color_oi, marker='o', linewidth=2, label='Open Interest')
    ax_opt.tick_params(axis='y', labelcolor=color_oi)
    
    ax_prem = ax_opt.twinx()
    color_prem = '#e53e3e'
    ax_prem.set_ylabel('Prima Diaria ($)', color=color_prem, fontweight='bold', fontsize=9)
    ax_prem.bar(tendencia_diaria['Trade Date'], tendencia_diaria['Daily_Premium'], color=color_prem, alpha=0.35, width=0.6, label='Prima Diaria')
    ax_prem.tick_params(axis='y', labelcolor=color_prem)
    ax_opt.grid(True, linestyle='--', alpha=0.4)
    ax_opt.set_title(f'Dinámica del Contrato: Strike ${strike_ganador} {cp_ganador} (Exp: {exp_ganadora.strftime("%Y-%m-%d")})', fontsize=10, fontweight='bold', pad=8)

    # Panel 5: Dark Pools
    if tiene_dark and ax_dark is not None:
        top_d = datos_dark['top_niveles'].head(5).sort_values(by='Total_Amount', ascending=True)
        precios_d = [f"${p:.2f}" for p in top_d['Price_Clean']]
        montos_d = top_d['Total_Amount'] / 1e6
        bars_d = ax_dark.barh(precios_d, montos_d, color='#805ad5', alpha=0.8, height=0.55)
        ax_dark.set_xlabel('Monto Negociado (Millones de $)', fontweight='bold', fontsize=9, color='#553c9a')
        ax_dark.set_title('Top Muros de Acumulación Oculta (Dark Pool Levels)', fontsize=10, fontweight='bold', pad=8, color='#553c9a')
        ax_dark.grid(True, linestyle='--', alpha=0.4, axis='x')
        for bar in bars_d:
            w = bar.get_width()
            ax_dark.text(w + (w * 0.02), bar.get_y() + bar.get_height()/2, f'${w:.1f}M', ha='left', va='center', fontsize=8, fontweight='bold', color='#553c9a')

    # Panel 6: Lit Pools
    if tiene_lit and ax_lit is not None:
        top_l = datos_lit['top_niveles'].head(5).sort_values(by='Total_Amount', ascending=True)
        precios_l = [f"${p:.2f}" for p in top_l['Price_Clean']]
        montos_l = top_l['Total_Amount'] / 1e6
        bars_l = ax_lit.barh(precios_l, montos_l, color='#d69e2e', alpha=0.8, height=0.55)
        ax_lit.set_xlabel('Monto Negociado (Millones de $)', fontweight='bold', fontsize=9, color='#b7791f')
        ax_lit.set_title('Top Bloques de Ejecución Pública (Lit Pool Levels)', fontsize=10, fontweight='bold', pad=8, color='#b7791f')
        ax_lit.grid(True, linestyle='--', alpha=0.4, axis='x')
        for bar in bars_l:
            w = bar.get_width()
            ax_lit.text(w + (w * 0.02), bar.get_y() + bar.get_height()/2, f'${w:.1f}M', ha='left', va='center', fontsize=8, fontweight='bold', color='#b7791f')

    fig.tight_layout()
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
        plt.savefig(tmp_img.name, bbox_inches='tight')
        tmp_img_path = tmp_img.name
    plt.close()
    
    with open(tmp_img_path, 'rb') as img_file:
        chart_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    os.unlink(tmp_img_path)
        
    top_5 = ranking.head(5)
    analisis_ia_html = obtener_analisis_ia(ranking, ganador, stock_data, datos_dark, datos_lit, info_fund)
    
    titulares_html = ""
    if info_fund.get('titulares'):
        titulares_html = "<ul>" + "".join([f"<li>{t}</li>" for t in info_fund.get('titulares')]) + "</ul>"
    else:
        titulares_html = "<p>No hay noticias recientes destacadas.</p>"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
    <meta charset="UTF-8">
    <title>Informe Cuantitativo Integral con IA y Noticias</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #2c3e50; line-height: 1.6; background-color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 950px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        .header-banner {{ background-color: #1a365d; color: white; margin: -30px -30px 25px -30px; padding: 25px 30px; border-radius: 8px 8px 0 0; border-bottom: 4px solid #3182ce; }}
        .header-banner h1 {{ margin: 0 0 5px 0; font-size: 22pt; }}
        .header-banner p {{ margin: 0; font-size: 11pt; color: #e2e8f0; }}
        h2 {{ font-size: 14pt; color: #1a365d; border-left: 4px solid #3182ce; padding-left: 10px; margin-top: 25px; margin-bottom: 12px; }}
        .card {{ background: #fdfdfd; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px 20px; margin-bottom: 15px; }}
        .winner-grid {{ display: flex; justify-content: space-between; gap: 15px; margin-bottom: 20px; }}
        .metric-box {{ background: #ebf8ff; border: 1px solid #bee3f8; border-radius: 6px; padding: 12px; text-align: center; flex: 1; }}
        .metric-value {{ font-size: 14pt; font-weight: bold; color: #2b6cb0; margin-top: 4px; }}
        .metric-label {{ font-size: 8.5pt; color: #4a5568; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 20px; background: #ffffff; font-size: 10pt; }}
        th {{ background-color: #2d3748; color: white; text-align: left; padding: 10px 12px; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #4a5568; }}
        tr:nth-child(even) {{ background-color: #f7fafc; }}
        .chart-container {{ text-align: center; margin: 20px 0; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px; }}
        .chart-container img {{ max-width: 100%; height: auto; }}
        .footer {{ margin-top: 30px; font-size: 9pt; color: #718096; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px; }}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header-banner">
            <h1>Informe Cuantitativo Integral con Noticias y IA</h1>
            <p>Estrategia TV (EMA 9/21, Volumen, MACD), Muros y Risk News (Ticker: {ticker_ganador})</p>
        </div>

        <h2>Resumen Metodológico</h2>
        <div class="card">
            <p>Análisis integral cruzando derivados, microestructura institucional (Dark/Lit), estrategia técnica de TradingView y titulares recientes de mercado para <strong>{ticker_ganador}</strong>.</p>
            <p><strong>Próximo Reporte de Ganancias:</strong> {info_fund.get('proximo_earnings')} &bull; <strong>Market Cap:</strong> {info_fund.get('market_cap')}</p>
        </div>

        {analisis_ia_html}

        <h2>Noticias y Titulares Recientes del Mercado</h2>
        <div class="card">
            {titulares_html}
        </div>

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

        <h2>Dashboard Técnico Estilo TradingView + Institucional</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{chart_base64}" alt="Dashboard Estilo TradingView">
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
            Informe generado con tu estrategia de TradingView, Noticias y Google Gemini IA &bull; Referencia: {fecha_analisis.strftime('%Y-%m-%d')}
        </div>
    </div>
    </body>
    </html>
    """

    with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as tmp_html:
        tmp_html.write(html_content)
        tmp_html_path = tmp_html.name

    print("\nAbriendo el informe interactivo con noticias y tu configuración de TradingView...")
    webbrowser.open('file://' + os.path.abspath(tmp_html_path))

if __name__ == "__main__":
    generar_analisis_robusto()