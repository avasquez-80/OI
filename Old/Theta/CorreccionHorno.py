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

  # Normalizar nombres de columnas (quitar espacios sobrantes)
  df.columns = [str(col).strip() for col in df.columns]

  # Identificar automáticamente la columna de fecha y la columna de estado
  col_fecha = [
      c for c in df.columns if "FECHA" in c.upper() or "TIME" in c.upper()
  ][0]
  col_estado = [c for c in df.columns if "ESDV" in c or "ESTADO" in c.upper()][
      0
  ]

  # Ordenar cronológicamente
  df[col_fecha] = pd.to_datetime(df[col_fecha])
  df = df.sort_values(col_fecha).reset_index(drop=True)

  # ==========================================================
  # PASO 1: LIMPIEZA DE LA COLUMNA DE ESTADO
  # ==========================================================
  # Reemplazar textos de error o vacíos por NaN en la columna de estado
  df[col_estado] = df[col_estado].replace(
      ["Error", "No Result", "ERR", "nan", ""], np.nan
  )
  # Propagar el último estado válido conocido (Forward Fill / Backward Fill)
  df[col_estado] = df[col_estado].ffill().bfill()

  # Mapear estado a binario: "Normal" (fuera de servicio) = 0, "Activo" (en servicio) = 1
  df["ESTADO_BIN"] = (
      df[col_estado].astype(str).str.strip().str.lower().eq("activo").astype(int)
  )

  # ==========================================================
  # PASO 2: LIMPIEZA DE COLUMNAS NUMÉRICAS Y DE COMUNICACIÓN
  # ==========================================================
  columnas_numericas = [
      c
      for c in df.columns
      if c not in [col_fecha, col_estado, "ESTADO_BIN"]
      and pd.api.types.is_numeric_dtype(df[c])
      or df[c].dtype == object
  ]

  for col in columnas_numericas:
    # Forzar errores de texto en mediciones numéricas a NaN
    df[col] = pd.to_numeric(df[col], errors="coerce")

    # Rellenar baches cortos de comunicación usando interpolación lineal y límites
    df[col] = df[col].interpolate(method="linear", limit=15)
    df[col] = df[col].ffill().bfill()

    # Corrección estricta por Estado "Normal" (Fuera de servicio / Detenido) en flujos
    if col.upper().startswith("FI") or col.upper().startswith("FIC"):
      df.loc[df["ESTADO_BIN"] == 0, col] = 0.0

  # Eliminar columna auxiliar de control
  df = df.drop(columns=["ESTADO_BIN"])

  # ==========================================
  # PASO 3: EXPORTAR RESULTADO FINAL
  # ==========================================
  archivo_salida = archivo_entrada.replace(".xlsx", "_CORREGIDO_MULTICOLUMNA.xlsx")
  df.to_excel(archivo_salida, index=False)

  print("¡Proceso completado con éxito!")
  print(f"Archivo limpio guardado en: {archivo_salida}")