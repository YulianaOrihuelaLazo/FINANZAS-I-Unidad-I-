 # Nombres y apellidos completos: Yuliana Orihuela Lazo
# Código de matrícula: 2024200514G
# Tema y número del temario: S04 - Perpetuidades y valuación de acciones (BVL)- Tema 27
# Fecha de extracción: 21/09/2026


# Validación de tickers para la selección final de emisores
"""
00_validacion_tickers.py
Etapa previa a 01_extraccion_api.py: prueba qué tickers de Yahoo Finance
(yfinance) sirven para el estudio 2018-2025 con dividendos y propone 10.

Instalación:  pip install yfinance pandas
Ejecución:    python 00_validacion_tickers.py
Salida:       consola + ./salidas/validacion_tickers.csv (ruta relativa)
"""

import os
import re
import sys
import time
import traceback
from datetime import datetime

import pandas as pd
import yfinance as yf

# ----------------------------------------------------------------------------
# 1. PARÁMETROS CONGELADOS (la consigna prohíbe fechas dinámicas tipo "hoy")
# ----------------------------------------------------------------------------
FECHA_INICIO = "2018-01-01"
FECHA_CORTE = "2025-12-31"           # último día que quieres INCLUIR
PAUSA_SEG = 1.0                      # pausa entre solicitudes (buena práctica)

# Criterios de aceptación por ticker (ajústalos si tu docente pide otra cosa)
MIN_OBS = 1500                       # 10 emisores x 1500 = 15 000 obs
MAX_ARRANQUE = "2018-03-31"          # la serie debe empezar a más tardar aquí
MIN_ULTIMA = "2025-11-30"            # y llegar hasta fines de 2025
MIN_ANIOS_CON_DIV = 6                # años (de 8) con al menos un dividendo
MAX_ANIOS_SEGUIDOS_SIN_DIV = 1       # no más de 1 año seguido sin dividendos

# ----------------------------------------------------------------------------
# 2. CANDIDATOS: (nombre, nemónico BVL, [tickers Yahoo a probar en orden])
#    Los 10 primeros son los titulares; los siguientes son reservas.
# ----------------------------------------------------------------------------
CANDIDATOS = [
  
    # --- TITULARES ---
    ("Southern Copper Corporation",          "SCCO",      ["SCCO"]),
    ("Credicorp Ltd.",                       "BAP",       ["BAP"]),
    ("Cementos Pacasmayo S.A.A.",            "CPACASC1",  ["CPACASC1.LM", "CPAC"]),
    ("Ferreycorp S.A.A.",                    "FERREYC1",  ["FERREYC1.LM"]),
    ("UNACEM Corp S.A.A.",                   "UNACEMC1",  ["UNACEMC1.LM"]),
    ("Alicorp S.A.A.",                       "ALICORC1",  ["ALICORC1.LM"]),
    ("Unión de Cervecerías Backus y Johnston", "BACKUSI1", ["BACKUSI1.LM"]),
    ("Banco de Crédito del Perú",            "CREDITC1",  ["CREDITC1.LM"]),
    ("Luz del Sur S.A.A.",                   "LUSURC1",   ["LUSURC1.LM"]),
    ("Banco BBVA Perú",                      "BBVAC1",    ["BBVAC1.LM"]),
    # --- RESERVAS (entran solo si algún titular falla) ---
    ("Orygen Perú (ex Engie)",               "ENGEPEC1",  ["ENGIEC1.LM"]),
    # Control: BVN debe fallar por brecha de dividendos 2020-2021
    ("Cía. de Minas Buenaventura",           "BVN",       ["BVN"]),
]

N_TITULARES = 10


# ----------------------------------------------------------------------------
# 3. FUNCIONES
# ----------------------------------------------------------------------------
def fin_exclusivo(fecha_corte):
    """yfinance trata end como exclusivo: se suma 1 día."""
    return (pd.Timestamp(fecha_corte) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def racha_maxima_igual(serie):
    """Mayor número de cierres consecutivos idénticos."""
    if serie.empty:
        return 0
    grupos = (serie != serie.shift()).cumsum()
    return int(serie.groupby(grupos).size().max())


def max_anios_seguidos_sin_div(anios_con_div, ini, fin):
    """Mayor tramo de años consecutivos sin ningún dividendo dentro del periodo."""
    mayor, actual = 0, 0
    for a in range(ini, fin + 1):
        if a in anios_con_div:
            actual = 0
        else:
            actual += 1
            mayor = max(mayor, actual)
    return mayor


def limpiar_dividendo(x):
    """Convierte un dividendo a número. Acepta números, None y texto
    como '0.09', '0,09' o 'PEN 0.09'. Devuelve 0.0 si está vacío y
    None si es texto que no se puede interpretar."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return 0.0 if pd.isna(x) else float(x)
    texto = str(x).strip()
    if texto == "" or texto.lower() in ("nan", "none"):
        return 0.0
    m = re.search(r"-?\d[\d.,]*", texto)
    if not m:
        return None
    n = m.group(0).rstrip(".,")
    if "," in n and "." in n:
        n = n.replace(",", "")          # coma como separador de miles
    elif "," in n:
        n = n.replace(",", ".")         # coma decimal
    try:
        return float(n)
    except ValueError:
        return None


def moneda_de(t):
    """Moneda de cotización según Yahoo (puede fallar: devuelve None)."""
    try:
        return t.fast_info["currency"]
    except Exception:
        return None


def evaluar_ticker(ticker):
    """Descarga datos diarios 2018-2025 y devuelve un diccionario de métricas."""
    res = {"ticker": ticker, "funciona": False, "error": ""}
    ini_anio = pd.Timestamp(FECHA_INICIO).year
    fin_anio = pd.Timestamp(FECHA_CORTE).year
    try:
        t = yf.Ticker(ticker)

        # Histórico diario del periodo de estudio (precios crudos + dividendos)
        h = t.history(start=FECHA_INICIO, end=fin_exclusivo(FECHA_CORTE),
                      interval="1d", auto_adjust=False, actions=True)
        if h is None or h.empty:
            res["error"] = "sin datos en el periodo (ticker inexistente o feed roto)"
            return res

        if getattr(h.index, "tz", None) is not None:
            h.index = h.index.tz_localize(None)

        # Diagnóstico: tipos originales (en algunos .LM llega texto)
        res["dtypes_originales"] = ", ".join(f"{c}:{h[c].dtype}" for c in h.columns)
        posibles = ["Open", "High", "Low", "Close", "Volume", "Stock Splits"]
        cols_num = [c for c in posibles if c in h.columns]
        antes_nan = int(h[cols_num].isna().sum().sum())
        for c in cols_num:
            h[c] = pd.to_numeric(h[c], errors="coerce")  # texto -> NaN
        res["celdas_no_numericas"] = int(h[cols_num].isna().sum().sum()) - antes_nan

        # Dividendos: en los .LM Yahoo los entrega como texto (dtype object)
        if "Dividends" in h.columns:
            crudo = h["Dividends"]
            es_texto = crudo.map(lambda v: isinstance(v, str))
            res["div_texto_n"] = int(es_texto.sum())
            res["div_texto_ejemplos"] = list(crudo[es_texto].astype(str).head(3))
            limpio = crudo.map(limpiar_dividendo)
            res["div_no_interpretables"] = int((es_texto & limpio.isna()).sum())
            h["Dividends"] = limpio.fillna(0.0)
        else:
            h["Dividends"] = 0.0
        if "Volume" not in h.columns:
            h["Volume"] = float("nan")

        h = h.dropna(subset=["Close"])
        if h.empty:
            res["error"] = "todas las filas de Close son NaN"
            return res

        # Primer dato disponible en toda la historia de Yahoo
        try:
            hm = t.history(period="max", interval="1mo", auto_adjust=False)
            desde = hm.index.min().year if not hm.empty else None
        except Exception:
            desde = None

        divs = h["Dividends"][h["Dividends"] > 0]
        anios = sorted(set(divs.index.year))

        res.update({
            "funciona": True,
            "moneda": moneda_de(t),
            "desde_anio_yahoo": desde,
            "obs": int(len(h)),
            "primera_fecha": h.index.min().date().isoformat(),
            "ultima_fecha": h.index.max().date().isoformat(),
            "n_pagos_div": int(len(divs)),
            "anios_con_div": anios,
            "n_anios_con_div": len(anios),
            "max_anios_sin_div": max_anios_seguidos_sin_div(
                set(anios), ini_anio, fin_anio),
            "pct_volumen_cero": round(float((h["Volume"] == 0).mean() * 100), 1),
            "racha_max_cierre_igual": racha_maxima_igual(h["Close"]),
        })
    except Exception as e:                       # cualquier fallo de red o de Yahoo
        linea = traceback.extract_tb(e.__traceback__)[-1].lineno
        res["error"] = f"{type(e).__name__}: {e} (línea {linea} del script)"
    return res


def cumple_criterios(r):
    """Devuelve (True/False, lista de motivos de rechazo)."""
    if not r.get("funciona"):
        return False, [r.get("error", "no funciona")]
    motivos = []
    if r["obs"] < MIN_OBS:
        motivos.append(f"obs {r['obs']} < {MIN_OBS}")
    if r["primera_fecha"] > MAX_ARRANQUE:
        motivos.append(f"empieza tarde ({r['primera_fecha']})")
    if r["ultima_fecha"] < MIN_ULTIMA:
        motivos.append(f"termina pronto ({r['ultima_fecha']})")
    if r["n_anios_con_div"] < MIN_ANIOS_CON_DIV:
        motivos.append(f"solo {r['n_anios_con_div']} años con dividendo")
    if r["max_anios_sin_div"] > MAX_ANIOS_SEGUIDOS_SIN_DIV:
        motivos.append(f"brecha de {r['max_anios_sin_div']} años sin dividendo")
    return (len(motivos) == 0), motivos


# ----------------------------------------------------------------------------
# 4. EJECUCIÓN
# ----------------------------------------------------------------------------
def imprimir_resultado(tk, r, ok, motivos):
    """Imprime el resultado de un ticker en líneas cortas."""
    if not r["funciona"]:
        print("     " + tk + "  -> NO FUNCIONA | " + str(r["error"]))
        return
    print("     " + tk + "  -> FUNCIONA")
    print("        obs:", r["obs"], "| desde:", r["primera_fecha"],
          "| hasta:", r["ultima_fecha"])
    print("        pagos de dividendo:", r["n_pagos_div"])
    print("        años con dividendo:", r["anios_con_div"])
    print("        moneda:", r["moneda"], "| datos Yahoo desde:",
          r["desde_anio_yahoo"])
    print("        volumen=0:", str(r["pct_volumen_cero"]) + "%",
          "| racha cierre igual:", r["racha_max_cierre_igual"])
    if r.get("celdas_no_numericas"):
        print("        AVISO: celdas no numéricas (precios/volumen):",
              r["celdas_no_numericas"])
    if r.get("div_texto_n"):
        print("        AVISO: dividendos como TEXTO:", r["div_texto_n"],
              "| ejemplos:", r["div_texto_ejemplos"])
        print("        no interpretables:", r["div_no_interpretables"],
              "| tipos originales:", r["dtypes_originales"])
    if ok:
        print("        CUMPLE: SI")
    else:
        print("        CUMPLE: NO ->", "; ".join(motivos))


def main():
    print("yfinance", yf.__version__, "| Python", sys.version.split()[0])
    print("Ventana:", FECHA_INICIO, "->", FECHA_CORTE)
    print("Corrida:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "\n")

    filas, elegidos = [], []
    for i, (nombre, nemonico, tickers) in enumerate(CANDIDATOS, start=1):
        rol = "TITULAR" if i <= N_TITULARES else "RESERVA"
        print("[" + str(i).zfill(2) + "]", rol, "·", nombre,
              "(BVL:", nemonico + ")")
        ganador = None
        for tk in tickers:
            r = evaluar_ticker(tk)
            ok, motivos = cumple_criterios(r)
            imprimir_resultado(tk, r, ok, motivos)
            r.update({"emisor": nombre, "nemonico_bvl": nemonico,
                      "rol": rol, "cumple": ok,
                      "motivos_rechazo": "; ".join(motivos)})
            filas.append(r)
            if ok and ganador is None:
                ganador = r
            time.sleep(PAUSA_SEG)
        if ganador:
            elegidos.append(ganador)
        print()

    # Selección final: titulares que cumplen + reservas hasta completar 10
    finales = elegidos[:N_TITULARES]
    total_obs = sum(r["obs"] for r in finales)
    print("=" * 70)
    print("EMISORES QUE CUMPLEN:", len(elegidos),
          "| SELECCIÓN FINAL:", len(finales), "de", N_TITULARES)
    for r in finales:
        print("  -", r["ticker"], "|", r["emisor"],
              "| obs:", r["obs"], "| pagos:", r["n_pagos_div"])
    completo = total_obs >= 15000 and len(finales) == N_TITULARES
    print("TOTAL DE OBSERVACIONES:", format(total_obs, ","),
          "(mínimo 15,000) ->", "OK" if completo else "REVISAR")
    print("Nota: volumen=0 alto o racha de cierres iguales larga = "
          "poca liquidez o dato congelado.")

    os.makedirs("salidas", exist_ok=True)
    ruta = os.path.join("salidas", "validacion_tickers.csv")
    pd.DataFrame(filas).to_csv(ruta, index=False, encoding="utf-8-sig")
    print("\nDetalle guardado en", ruta)


if __name__ == "__main__":
    main()
