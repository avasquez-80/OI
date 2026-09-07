import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

ARCHIVO_BASE_DATOS = "contratos_seguidos_db.csv"

# Configuración de Telegram (Lee las credenciales de las variables de entorno del sistema o GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def enviar_alerta_telegram(mensaje):
    """Envía un mensaje de alerta a tu chat de Telegram de forma segura."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Credenciales de Telegram no configuradas. Omitiendo notificación push.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("📱 Alerta enviada con éxito a Telegram.")
        else:
            print(f"⚠️ Error al enviar alerta a Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Excepción al conectar con la API de Telegram: {e}")
def probar_telegram():
    """Envía un mensaje de prueba a Telegram para verificar la conexión."""
    print("\nVerificando configuración y enviando mensaje de prueba a Telegram...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ ATENCIÓN: Las variables de entorno 'TELEGRAM_BOT_TOKEN' o 'TELEGRAM_CHAT_ID' no están configuradas en esta terminal.")
        return
        
    mensaje = (
        "🧪 *MENSAJE DE PRUEBA - QUANT SYSTEM* 🧪\n\n"
        "¡Conexión exitosa! El bot de Telegram está configurado y listo para enviar alertas de oportunidades."
    )
    enviar_alerta_telegram(mensaje)
def importar_o_actualizar_historial(df_nuevo_lote):
    """Fusiona de forma segura nuevos datos en la base de datos central."""
    if df_nuevo_lote is None or df_nuevo_lote.empty:
        print("⚠️ El lote de datos entrantes está vacío.")
        return

    columnas_clave = ['Trade Date', 'Ticker', 'Expiry', 'Strike ($)', 'C/P']

    if os.path.exists(ARCHIVO_BASE_DATOS):
        df_db = pd.read_csv(ARCHIVO_BASE_DATOS)
        df_combinado = pd.concat([df_db, df_nuevo_lote], ignore_index=True)
        df_combinado.drop_duplicates(subset=columnas_clave, keep='last', inplace=True)
        df_combinado.sort_values(by=['Ticker', 'Trade Date', 'Expiry', 'Strike ($)'], inplace=True)
        df_final = df_combinado
    else:
        df_nuevo_lote.sort_values(by=['Ticker', 'Trade Date', 'Expiry', 'Strike ($)'], inplace=True)
        df_final = df_nuevo_lote

    df_final.to_csv(ARCHIVO_BASE_DATOS, index=False)
    print(f"✅ Base de datos actualizada con éxito. Total de registros en la BD: {len(df_final)}")

def registrar_o_actualizar_contrato(ticker_symbol, expiry_date, strike_price, tipo_cp):
    """Consulta Yahoo Finance, evalúa cambios relevantes y actualiza la base de datos."""
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    # Validar si el contrato ya expiró
    try:
        exp_dt = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        if exp_dt < datetime.now().date():
            print(f"\n[{hoy}] ℹ️ El contrato {ticker_symbol.upper()} | {tipo_cp.upper()} Strike ${strike_price} (Exp: {expiry_date}) ya ha expirado.")
            return True
    except Exception:
        pass

    print(f"\n[{hoy}] Actualizando seguimiento diario para {ticker_symbol.upper()} | {tipo_cp.upper()} Strike ${strike_price} (Exp: {expiry_date})...")
    
    try:
        # 1. Obtener el registro previo de este contrato en el CSV para comparar cambios
        oi_anterior = 0
        if os.path.exists(ARCHIVO_BASE_DATOS):
            df_hist_prev = pd.read_csv(ARCHIVO_BASE_DATOS)
            filtro_prev = (
                (df_hist_prev['Ticker'] == ticker_symbol.upper()) &
                (df_hist_prev['Expiry'] == expiry_date) &
                (df_hist_prev['Strike ($)'] == float(strike_price)) &
                (df_hist_prev['C/P'] == tipo_cp.upper())
            )
            datos_previos = df_hist_prev[filtro_prev]
            if not datos_previos.empty:
                # Tomar el último Open Interest registrado antes de hoy
                oi_anterior = int(datos_previos.iloc[-1]['Open Interest'])

        # 2. Consultar datos frescos en Yahoo Finance
        t = yf.Ticker(ticker_symbol)
        opt_chain = t.option_chain(expiry_date)
        
        df_target = opt_chain.calls if tipo_cp.upper() == 'CALL' else opt_chain.puts
        contrato_encontrado = df_target[df_target['strike'] == float(strike_price)]
        
        if contrato_encontrado.empty:
            print(f"⚠️ No se encontró el strike {strike_price} para la expiración {expiry_date} en {ticker_symbol}.")
            return False
            
        row = contrato_encontrado.iloc[0]
        oi_actual = int(row['openInterest']) if pd.notna(row['openInterest']) else 0
        vol_actual = int(row['volume']) if pd.notna(row['volume']) else 0
        last_price = float(row['lastPrice']) if pd.notna(row['lastPrice']) else 0.0
        
        premium_diario = vol_actual * last_price * 100
        
        # 3. Evaluar reglas de oportunidad / cambio relevante
        variacion_oi = oi_actual - oi_anterior
        porc_cambio_oi = (variacion_oi / oi_anterior * 100) if oi_anterior > 0 else 0
        
        alerta_disparada = False
        razones_alerta = []
        
        # Criterio A: Salto de Open Interest superior o igual al 10%
        if porc_cambio_oi >= 10.0 and oi_anterior > 500:
            alerta_disparada = True
            razones_alerta.append(f"📈 *Salto Institucional de OI:* +{porc_cambio_oi:.1f}% ({oi_anterior:,} ➡️ {oi_actual:,})")
            
        # Criterio B: Volumen diario masivo o prima negociada inusual (> $200,000)
        if premium_diario >= 200_000 or vol_actual >= 5_000:
            alerta_disparada = True
            razones_alerta.append(f"💰 *Flujo Masivo Detectado:* Volumen de {vol_actual:,} contratos | Prima Diaria: ${premium_diario:,.2f}")

        # Si se detecta oportunidad, disparar mensaje a Telegram
        if alerta_disparada:
            detalle_razones = "\n".join(razones_alerta)
            mensaje_telegram = (
                f"🚨 *ALERTA DE OPORTUNIDAD - QUANT SYSTEM* 🚨\n\n"
                f"*Activo:* `{ticker_symbol.upper()}`\n"
                f"*Contrato:* `{tipo_cp.upper()} ${strike_price}` (Exp: `{expiry_date}`)\n\n"
                f"{detalle_razones}\n\n"
                f"⚡ _Revisa tu terminal para ejecutar análisis técnico detallado._"
            )
            enviar_alerta_telegram(mensaje_telegram)

        # ==========================================
        # VALIDACIÓN MEJORADA CONTRA MERCADO CERRADO / FERIADOS
        # ==========================================
        if not datos_previos.empty:
            ultimo_reg = datos_previos.iloc[-1]
            ultimo_oi = int(ultimo_reg['Open Interest']) if pd.notna(ultimo_reg['Open Interest']) else 0
            ultimo_vol = int(ultimo_reg['Volume']) if pd.notna(ultimo_reg['Volume']) else 0
            ultima_prima = float(ultimo_reg['Premium ($)']) if pd.notna(ultimo_reg['Premium ($)']) else 0.0
            ultima_fecha = str(ultimo_reg['Trade Date']).split(' ')[0]

            # 1. Si ya se guardó un registro para el día de hoy, se omite
            if ultima_fecha == hoy:
                print(f"ℹ️ Ya existe un registro para hoy ({hoy}). Omitiendo duplicado.")
                return True

            # 2. Si el mercado está cerrado (Feriado/Fin de semana) y tanto el OI, 
            # el volumen como la prima no muestran actividad real nueva respecto al cierre previo:
            if ultimo_oi == oi_actual and ultimo_vol == vol_actual and ultima_prima == round(premium_diario, 2):
                print(f"ℹ️ Sin cambios en el mercado (posible día festivo/cerrado). Omitiendo.")
                return True

        # 4. Guardar registro en la base de datos
        nuevo_registro = pd.DataFrame([{
            'Trade Date': hoy,
            'Ticker': ticker_symbol.upper(),
            'Expiry': expiry_date,
            'Strike ($)': float(strike_price),
            'C/P': tipo_cp.upper(),
            'Open Interest': oi_actual,
            'Volume': vol_actual,
            'Premium ($)': round(premium_diario, 2)
        }])
        
        importar_o_actualizar_historial(nuevo_registro)
        return True
        
    except Exception as e:
        print(f"❌ Error al consultar Yahoo Finance: {e}")
        return False

def listar_contratos_unicos():
    """Retorna un DataFrame con los contratos únicos bajo seguimiento."""
    if not os.path.exists(ARCHIVO_BASE_DATOS):
        return None
    df_db = pd.read_csv(ARCHIVO_BASE_DATOS)
    if df_db.empty:
        return None
    return df_db[['Ticker', 'Expiry', 'Strike ($)', 'C/P']].drop_duplicates().reset_index(drop=True)

def eliminar_contrato_interactivo():
    """Permite seleccionar y eliminar un contrato y su historial."""
    unicos = listar_contratos_unicos()
    if unicos is None or unicos.empty:
        print("\n⚠️ No hay contratos registrados.")
        return

    print("\n--- CONTRATOS ACTUALMENTE EN SEGUIMIENTO ---")
    for idx, row in unicos.iterrows():
        print(f"[{idx}] Ticker: {row['Ticker']} | {row['C/P']} | Strike: ${row['Strike ($)']} | Exp: {row['Expiry']}")
    
    try:
        seleccion = input("\nNúmero del contrato a ELIMINAR (Enter para cancelar): ").strip()
        if not seleccion:
            return
        idx_elegido = int(seleccion)
        c = unicos.loc[idx_elegido]
        df_db = pd.read_csv(ARCHIVO_BASE_DATOS)
        df_filtrado = df_db[~(
            (df_db['Ticker'] == c['Ticker']) & (df_db['Expiry'] == c['Expiry']) &
            (df_db['Strike ($)'] == c['Strike ($)']) & (df_db['C/P'] == c['C/P'])
        )]
        df_filtrado.to_csv(ARCHIVO_BASE_DATOS, index=False)
        print(f"🗑️ Contrato eliminado: {c['Ticker']} ({c['C/P']} ${c['Strike ($)']})")
    except Exception as e:
        print(f"❌ Error al eliminar: {e}")

def graficar_contrato_interactivo():
    """Grafica la evolución histórica de un contrato."""
    unicos = listar_contratos_unicos()
    if unicos is None or unicos.empty:
        print("\n⚠️ No hay contratos para graficar.")
        return

    print("\n--- SELECCIONA UN CONTRATO PARA GRAFICAR ---")
    for idx, row in unicos.iterrows():
        print(f"[{idx}] Ticker: {row['Ticker']} | {row['C/P']} | Strike: ${row['Strike ($)']} | Exp: {row['Expiry']}")
    
    try:
        seleccion = input("\nNúmero del contrato: ").strip()
        if not seleccion:
            return
        idx_elegido = int(seleccion)
        c = unicos.loc[idx_elegido]
        df_db = pd.read_csv(ARCHIVO_BASE_DATOS)
        df_c = df_db[
            (df_db['Ticker'] == c['Ticker']) & (df_db['Expiry'] == c['Expiry']) &
            (df_db['Strike ($)'] == c['Strike ($)']) & (df_db['C/P'] == c['C/P'])
        ].copy()
        
        if df_c.empty:
            return
            
        df_c['Trade Date'] = pd.to_datetime(df_c['Trade Date'])
        df_c.sort_values('Trade Date', inplace=True)
        
        fig, ax1 = plt.subplots(figsize=(10, 5), dpi=100)
        ax1.set_xlabel('Fecha', fontweight='bold')
        ax1.set_ylabel('Open Interest', color='#3182ce', fontweight='bold')
        ax1.plot(df_c['Trade Date'], df_c['Open Interest'], color='#3182ce', marker='o', linewidth=2)
        ax1.tick_params(axis='y', labelcolor='#3182ce')
        ax1.grid(True, linestyle='--', alpha=0.4)
        
        ax2 = ax1.twinx()
        ax2.set_ylabel('Prima Diaria ($)', color='#e53e3e', fontweight='bold')
        ax2.bar(df_c['Trade Date'], df_c['Premium ($)'], color='#e53e3e', alpha=0.35, width=0.6)
        ax2.tick_params(axis='y', labelcolor='#e53e3e')
        
        plt.title(f'Evolución: {c["Ticker"]} - {c["C/P"]} Strike ${c["Strike ($)"]} (Exp: {c["Expiry"]})', fontsize=11, fontweight='bold', pad=12)
        fig.tight_layout()
        plt.show()
    except Exception as e:
        print(f"❌ Error al graficar: {e}")

def barrido_diario_contratos_seguidos():
    """Ejecuta el barrido masivo de todos los contratos."""
    if not os.path.exists(ARCHIVO_BASE_DATOS):
        print("⚠️ No existe base de datos previa.")
        return
        
    df_db = pd.read_csv(ARCHIVO_BASE_DATOS)
    contratos_unicos = df_db[['Ticker', 'Expiry', 'Strike ($)', 'C/P']].drop_duplicates()
    
    print(f"\n--- INICIANDO BARRIDO DIARIO DE {len(contratos_unicos)} CONTRATOS EN SEGUIMIENTO ---")
    for _, row in contratos_unicos.iterrows():
        registrar_o_actualizar_contrato(
            ticker_symbol=row['Ticker'],
            expiry_date=row['Expiry'],
            strike_price=row['Strike ($)'],
            tipo_cp=row['C/P']
        )
    print("--- BARRIDO DIARIO FINALIZADO ---\n")
    enviar_alerta_telegram("🤖 *QuantR3 Bot*: Barrido diario completado y base de datos actualizada.")

def graficar_todas_las_tendencias():
    """Genera una vista multipanel con scroll vertical y fuentes optimizadas para todos los contratos."""
    unicos = listar_contratos_unicos()
    if unicos is None or unicos.empty:
        print("\n⚠️ No hay contratos registrados para graficar.")
        return

    archivo_db = "contratos_seguidos_db.csv"
    if not os.path.exists(archivo_db):
        print("\n⚠️ No existe base de datos para graficar.")
        return

    df_db = pd.read_csv(archivo_db)
    total_contratos = len(unicos)

    # Altura dinámica: otorga 3.2 pulgadas de alto por cada contrato para evitar saturación
    altura_figura = max(6, total_contratos * 3.2)

    # Crear la figura con tamaños de fuente balanceados
    fig, axes = plt.subplots(total_contratos, 1, figsize=(11, altura_figura), dpi=100, sharex=True)
    if total_contratos == 1:
        axes = [axes]

    for ax1, (_, row) in zip(axes, unicos.iterrows()):
        df_c = df_db[
            (df_db['Ticker'] == row['Ticker']) & 
            (df_db['Expiry'] == row['Expiry']) &
            (df_db['Strike ($)'] == row['Strike ($)']) & 
            (df_c_cp := (df_db['C/P'] == row['C/P'])) # Mantiene compatibilidad de filtrado
        ].copy() if 'df_c_cp' else df_db[
            (df_db['Ticker'] == row['Ticker']) & 
            (df_db['Expiry'] == row['Expiry']) &
            (df_db['Strike ($)'] == row['Strike ($)']) & 
            (df_db['C/P'] == row['C/P'])
        ].copy()
        
        if df_c.empty:
            continue
            
        df_c['Trade Date'] = pd.to_datetime(df_c['Trade Date'])
        df_c.sort_values('Trade Date', inplace=True)
        
        # Eje principal: Open Interest (Optimizado)
        ax1.set_ylabel('Open Interest', color='#3182ce', fontweight='bold', fontsize=9)
        ax1.plot(df_c['Trade Date'], df_c['Open Interest'], color='#3182ce', marker='o', linewidth=1.5, markersize=4)
        ax1.tick_params(axis='y', labelcolor='#3182ce', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8)
        ax1.grid(True, linestyle='--', alpha=0.4)
        
        # Eje secundario: Prima Diaria
        ax2 = ax1.twinx()
        ax2.set_ylabel('Prima ($)', color='#e53e3e', fontweight='bold', fontsize=9)
        ax2.bar(df_c['Trade Date'], df_c['Premium ($)'], color='#e53e3e', alpha=0.35, width=0.5)
        ax2.tick_params(axis='y', labelcolor='#e53e3e', labelsize=8)
        
        # Título compacto y legible por contrato
        ax1.set_title(f'{row["Ticker"]} | {row["C/P"]} | Strike: ${row["Strike ($)"]} | Exp: {row["Expiry"]}', fontsize=10, fontweight='bold', pad=6)

    axes[-1].set_xlabel('Fecha', fontweight='bold', fontsize=10)
    fig.tight_layout()

    # --- Interfaz Gráfica con Scrollbar (Tkinter) ---
    root = tk.Tk()
    root.title("Tendencias Históricas - Open Interest y Primas")
    root.geometry("1100x750")

    # Función para cerrar limpiamente y devolver control a la terminal
    def cerrar_ventana():
        root.quit()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", cerrar_ventana)

    main_frame = tk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=1)

    canvas_scroll = tk.Canvas(main_frame, highlightthickness=0)
    scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas_scroll.yview)
    
    scrollable_frame = tk.Frame(canvas_scroll)
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
    )

    canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas_scroll.configure(yscrollcommand=scrollbar.set)

    canvas_scroll.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Incrustar la gráfica en el contenedor con scroll
    canvas_agg = FigureCanvasTkAgg(fig, master=scrollable_frame)
    canvas_agg.draw()
    canvas_agg.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Activar desplazamiento con la rueda del mouse
    def _on_mousewheel(event):
        canvas_scroll.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)

    root.mainloop()
    plt.close(fig) # Libera memoria al cerrar la ventana

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "barrido":
        barrido_diario_contratos_seguidos()
    else:
        while True:
            print("\n=== GESTOR DE SEGUIMIENTO DE CONTRATOS ===")
            print("1. Registrar / Actualizar un contrato para el día de hoy")
            print("2. Ejecutar barrido diario (actualización automática) de todos los contratos")
            print("3. Listar contratos bajo seguimiento")
            print("4. Eliminar un contrato de la base de datos")
            print("5. Graficar evolución histórica de un contrato")
            print("6. Graficar todas las tendencias de Open Interest de los contratos")
            print("7. Salir")
            
            opcion = input("\nSelecciona una opción (1-7): ").strip()
            if opcion == "1":
                tck = input("Ticker (ej. SMH): ").strip()
                exp = input("Fecha de Expiración [YYYY-MM-DD]: ").strip()
                stk = input("Strike: ").strip()
                cp = input("Tipo [CALL / PUT]: ").strip()
                if tck and exp and stk and cp:
                    registrar_o_actualizar_contrato(tck, exp, stk, cp)
            elif opcion == "2":
                barrido_diario_contratos_seguidos()
            elif opcion == "3":
                unicos = listar_contratos_unicos()
                if unicos is not None and not unicos.empty:
                    print("\n--- CONTRATOS EN SEGUIMIENTO ---")
                    print(unicos.to_string(index=True))
                else:
                    print("\n⚠️ No hay contratos registrados.")
            elif opcion == "4":
                eliminar_contrato_interactivo()
            elif opcion == "5":
                graficar_contrato_interactivo()
            elif opcion == "6":
                graficar_todas_las_tendencias()
            elif opcion == "7":
                print("¡Hasta luego!")
                break
            else:
                print("❌ Opción no válida. Ingresa un número del 1 al 7.")