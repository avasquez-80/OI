import tkinter as tk
from tkinter import filedialog
import numpy as np
import pandas as pd

root = tk.Tk()
root.withdraw()

archivo_entrada = filedialog.askopenfilename(
    title="Selecciona tu archivo Excel",
    filetypes=[("Archivos de Excel", "*.xlsx *.xls *.csv")],
)

if not archivo_entrada:
  print("Operación cancelada.")
else:
  print("1/5. Leyendo el archivo (esto puede tomar unos minutos debido al tamaño)...")
  if archivo_entrada.endswith(".csv"):
    df = pd.read_csv(archivo_entrada)
  else:
    df = pd.read_excel(archivo_entrada)

  print(
      f"¡Archivo cargado con éxito! Total de filas leídas: {len(df):,}"
  )

  df.columns = [str(col).strip().upper() for col in df.columns]

  columnas_necesarias = ["FECHA", "TEMP", "CARGA"]
  for col in columnas_necesarias:
    if col not in df.columns:
      raise ValueError(f"No se encontró la columna '{col}' en el archivo.")

  print("2/5. Ordenando registros cronológicamente...")
  df["FECHA"] = pd.to_datetime(df["FECHA"])
  df = df.sort_values("FECHA").reset_index(drop=True)

  print(
      "3/5. Limpiando y corrigiendo rampas artificiales en la columna CARGA..."
  )
  df["CARGA_NUM"] = pd.to_numeric(df["CARGA"], errors="coerce")
  df["CARGA_NUM"] = df["CARGA_NUM"].clip(lower=0)


  def corregir_rampas_carga_baja(
      series, limite_max=900.0, ventana_min=8, pendiente_max=2.0
  ):
    corregida = series.copy()
    n = len(series)
    diff = series.diff()
    i = 0
    while i < n:
      val = series.iloc[i]
      if not pd.isna(val) and 0 <= val <= 50.0:
        inicio = i
        j = i + 1
        while (
            j < n
            and not pd.isna(diff.iloc[j])
            and 0 < diff.iloc[j] <= pendiente_max
            and series.iloc[j] <= limite_max
        ):
          j += 1
        if (
            j < n
            and (j - inicio) > ventana_min
            and not pd.isna(series.iloc[j])
            and series.iloc[j] <= limite_max
            and series.iloc[j] > val + 15
        ):
          val_base = series.iloc[inicio]
          corregida.iloc[inicio:j] = val_base
          i = j
        else:
          i += 1
      else:
        i += 1
    return corregida


  df["CARGA_CORREGIDA"] = corregir_rampas_carga_baja(df["CARGA_NUM"])
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].interpolate(
      method="linear", limit=15
  )
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].ffill()
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].bfill()
  df["CARGA_CORREGIDA"] = df["CARGA_CORREGIDA"].clip(lower=0)

  print("4/5. Modelando y rellenando la temperatura (TEMP) estadísticamente...")
  df["TEMP_NUM"] = pd.to_numeric(df["TEMP"], errors="coerce")
  df["TEMP_NUM"] = df["TEMP_NUM"].clip(lower=0)

  validos = df.dropna(subset=["TEMP_NUM", "CARGA_CORREGIDA"])
  if len(validos) > 20:
    coeffs = np.polyfit(validos["CARGA_CORREGIDA"], validos["TEMP_NUM"], deg=2)
    modelo_termico = np.poly1d(coeffs)
    temp_estimada = modelo_termico(df["CARGA_CORREGIDA"])
    df["TEMP_CORREGIDA"] = df["TEMP_NUM"].copy()
    mask_vacias = df["TEMP_CORREGIDA"].isna()
    df.loc[mask_vacias, "TEMP_CORREGIDA"] = temp_estimada[mask_vacias]
  else:
    df["TEMP_CORREGIDA"] = df["TEMP_NUM"].interpolate(method="linear")

  df["TEMP_CORREGIDA"] = df["TEMP_CORREGIDA"].clip(lower=0)

  print("5/5. Guardando el archivo de salida procesado...")
  df_final = pd.DataFrame({
      "FECHA": df["FECHA"],
      "TEMP": df["TEMP_CORREGIDA"],
      "CARGA": df["CARGA_CORREGIDA"],
  })

  archivo_salida = archivo_entrada.replace(".xlsx", "_CORREGIDO_TOTAL.xlsx")
  if archivo_salida == archivo_entrada:
    archivo_salida = archivo_entrada.replace(".csv", "_CORREGIDO_TOTAL.xlsx")

  df_final.to_excel(archivo_salida, index=False)

  print(f"¡Proceso completado con éxito! Archivo guardado en: {archivo_salida}")