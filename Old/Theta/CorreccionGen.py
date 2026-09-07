import tkinter as tk
from tkinter import filedialog
import numpy as np
import pandas as pd

# 1. Selección interactiva del archivo
root = tk.Tk()
root.withdraw()

archivo_entrada = filedialog.askopenfilename(
    title="Selecciona tu archivo Excel",
    filetypes=[("Archivos de Excel", "*.xlsx *.xls")],
)

if not archivo_entrada:
  print("Operación cancelada.")
else:
  print("Cargando y procesando el archivo masivo...")
  df = pd.read_excel(archivo_entrada)

  # Normalizar nombres de columnas a mayúsculas para evitar errores de sintaxis
  df.columns = [str(col).strip().upper() for col in df.columns]

  # Verificar columnas requeridas
  columnas_necesarias = ["FECHA", "TEMP", "CARGA"]
  for col in columnas_necesarias:
    if col not in df.columns:
      raise ValueError(
          f"No se encontró la columna '{col}' en el archivo. Revisa los"
          " nombres."
      )

  # Ordenar cronológicamente
  df["FECHA"] = pd.to_datetime(df["FECHA"])
  df = df.sort_values("FECHA").reset_index(drop=True)

  # ==========================================
  # PASO 1: LIMPIEZA Y CORRECCIÓN DE "CARGA"
  # ==========================================
  # Convertir a numérico forzando errores ("Error", "No Result", espacios) a NaN
  df["CARGA_NUM"] = pd.to_numeric(df["CARGA"], errors="coerce")


  # Función para corregir rampas de interpolación falsas en paradas
  def corregir_rampas_carga(
      series, umbral_bajo=15.0, ventana_min=5, pendiente_max=2.0
  ):
    corregida = series.copy()
    n = len(series)
    diff = series.diff()
    i = 0
    while i < n:
      val = series.iloc[i]
      if not pd.isna(val) and 0 <= val <= umbral_bajo:
        inicio = i
        j = i + 1
        while (
            j < n
            and not pd.isna(diff.iloc[j])
            and 0 < diff.iloc[j] <= pendiente_max
        ):
          j += 1
        if (
            j < n
            and (j - inicio) > ventana_min
            and not pd.isna(series.iloc[j])
            and series.iloc[j] > umbral_bajo * 4
        ):
          val_base = series.iloc[inicio]
          corregida.iloc[inicio:j] = (
              val_base  # Mantiene el valor real de reposo
          )
          i = j
        else:
          i += 1
      else:
        i += 1
    return corregida


  df["CARGA_CORREGIDA"] = corregir_rampas_carga(df["CARGA_NUM"])

  # Rellenar baches cortos de comunicación en CARGA usando la sintaxis moderna
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].interpolate(
      method="linear", limit=15
  )
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].ffill()
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].bfill()

  # ==========================================
  # PASO 2: LIMPIEZA Y RELLENO DE "TEMP"
  # ==========================================
  # Convertir TEMP a numérico, aislando textos de error
  df["TEMP_NUM"] = pd.to_numeric(df["TEMP"], errors="coerce")

  # Modelar estadísticamente la relación físico-térmica entre CARGA y TEMP usando los datos válidos
  validos = df.dropna(subset=["TEMP_NUM", "CARGA_CORREGIDA"])

  if len(validos) > 20:
    # Ajuste polinómico de grado 2 para capturar la curva térmica del equipo en función de su carga en KW
    coeffs = np.polyfit(validos["CARGA_CORREGIDA"], validos["TEMP_NUM"], deg=2)
    modelo_termico = np.poly1d(coeffs)

    # Estimar temperatura teórica basada en la carga corregida
    temp_estimada = modelo_termico(df["CARGA_CORREGIDA"])

    # Rellenar celdas vacías o con errores en TEMP con la estimación basada en carga
    df["TEMP_CORREGIDA"] = df["TEMP_NUM"].copy()
    mask_vacias = df["TEMP_CORREGIDA"].isna()
    df.loc[mask_vacias, "TEMP_CORREGIDA"] = temp_estimada[mask_vacias]
  else:
    # Fallback si faltan demasiados datos cruzados: interpolación lineal temporal
    df["TEMP_CORREGIDA"] = df["TEMP_NUM"].interpolate(method="linear")

  # Asegurar límites lógicos (la temperatura no debe ser negativa)
  df["TEMP_CORREGIDA"] = df["TEMP_CORREGIDA"].clip(lower=0)

  # ==========================================
  # PASO 3: EXPORTAR RESULTADO FINAL
  # ==========================================
  df_final = pd.DataFrame({
      "FECHA": df["FECHA"],
      "TEMP": df["TEMP_CORREGIDA"],
      "CARGA": df["CARGA_CORREGIDA"],
  })

  archivo_salida = archivo_entrada.replace(".xlsx", "_CORREGIDO_TOTAL.xlsx")
  df_final.to_excel(archivo_salida, index=False)

  print("¡Proceso completado con éxito!")
  print(f"Archivo limpio guardado en: {archivo_salida}")