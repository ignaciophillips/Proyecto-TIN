#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AquaFiordo - Pipeline BI - Grupo Salmonera N4
Pregunta 2: En el centro con mas costo, la causa es la mortalidad de un
evento sanitario o un FCR peor, o ambas?

Capas (ver README):
  1. cruda    : data/raw        (SQLite, CSV, JSON, API del dolar con respaldo)
  2. depurada : limpieza en memoria + pruebas de calidad (src/calidad.py)
  3. modelo   : data/processed  (hechos segun el DDL del equipo)
  4. consumo  : output/         (metricas, caso de negocio, cifras del informe)

Uso:
    python3 src/pipeline.py
"""
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
from calidad import ejecutar_pruebas

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 30)


# =====================================================================
# 0. UTILIDADES DE LIMPIEZA
# =====================================================================

def parse_fecha_mixta(valor):
    """Parsea fechas en formatos mixtos: '17/09/2025', '22-09-25',
    '28-jul-2025', '2025-10-20', '14/09/2025'."""
    if pd.isna(valor):
        return pd.NaT
    s = str(valor).strip()
    formatos = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y", "%d-%b-%Y",
                "%d-%b-%y", "%d/%m/%y"]
    meses_es = {"ene": "jan", "abr": "apr", "ago": "aug", "dic": "dec"}
    s_norm = s.lower()
    for es, en in meses_es.items():
        s_norm = s_norm.replace(es, en)
    for fmt in formatos:
        try:
            return pd.to_datetime(s_norm, format=fmt)
        except (ValueError, TypeError):
            continue
    try:
        return pd.to_datetime(s, dayfirst=True, errors="coerce")
    except Exception:
        return pd.NaT


def parse_numero_sucio(valor):
    """Parsea numeros en texto con formatos chilenos/mixtos:
    '246.597' (miles), '203152' (sin separador), '10,4' (coma decimal),
    '$1.050', '993,00', '-' (nulo)."""
    if pd.isna(valor):
        return np.nan
    s = str(valor).strip()
    if s in ("-", "", "nan", "NaN", "None"):
        return np.nan
    s = s.replace("$", "").strip()
    has_comma = "," in s
    has_dot = "." in s
    if has_comma and has_dot:
        s = s.replace(".", "").replace(",", ".")
    elif has_comma and not has_dot:
        s = s.replace(",", ".")
    elif has_dot and not has_comma:
        partes = s.split(".")
        if len(partes[-1]) == 3 and len(partes) > 1:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def normaliza_tipo_alimento(valor):
    """Normaliza variantes a un codigo unico: 'ENG-100' / 'engorda100' /
    'Engorda 100' -> 'ENG-100'; 'pigmentado' / 'PIG' -> 'PIG'."""
    if pd.isna(valor):
        return None
    s = str(valor).strip().upper().replace(" ", "").replace("-", "")
    if s.startswith("PIG"):
        return "PIG"
    m = re.search(r"(\d+)", s)
    return f"ENG-{m.group(1)}" if m else None


# =====================================================================
# 1. EXTRACCION (capa cruda)
# =====================================================================

def obtener_dolar():
    """Dolar observado: intenta la API de mindicador.cl en CADA corrida y,
    si falla, usa el respaldo local (data/raw/dolar_2025.json). Devuelve
    (json, estado) para que quede registrado de donde salio el dato."""
    motivo = "modo offline forzado (AQUAFIORDO_OFFLINE=1)"
    if os.environ.get("AQUAFIORDO_OFFLINE") != "1":
        try:
            req = urllib.request.Request(C.API_DOLAR_URL,
                                         headers={"User-Agent": "aquafiordo-pipeline"})
            with urllib.request.urlopen(req, timeout=C.API_TIMEOUT_SEG) as r:
                data = json.loads(r.read().decode("utf-8"))
            if not data.get("serie"):
                raise ValueError("respuesta de la API sin 'serie'")
            with open(PROCESSED_DIR / "dolar_api_ultima.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return data, {"fuente": "api", "detalle": C.API_DOLAR_URL,
                          "n_registros": len(data["serie"])}
        except Exception as e:  # red caida, timeout, JSON invalido, etc.
            motivo = f"{type(e).__name__}: {e}"
    with open(RAW_DIR / "dolar_2025.json", encoding="utf-8") as f:
        data = json.load(f)
    print(f"   [AVISO] API del dolar no disponible ({motivo}); se usa el respaldo local.")
    return data, {"fuente": "respaldo_local", "detalle": motivo,
                  "n_registros": len(data["serie"])}


def extraer():
    con = sqlite3.connect(RAW_DIR / "origen_acuicultura.sqlite")
    tablas = {}
    for t in ["zonas", "centros", "jaulas", "especies", "lotes",
              "operacion_diaria", "cosechas"]:
        tablas[t] = pd.read_sql(f"SELECT * FROM {t}", con)
    con.close()

    # CSV de alimento: separador ';', latin-1, con un encabezado duplicado a
    # mitad de archivo y una fila 'TOTAL' vacia al final: ninguna es un registro.
    costos_raw = pd.read_csv(RAW_DIR / "origen_costos_alimento.csv", sep=";",
                             dtype=str, encoding="latin-1")
    es_basura = costos_raw["tipo_alimento"].str.strip().str.upper().isin(
        ["TIPO_ALIMENTO", "TOTAL"])
    costos_raw = costos_raw[~es_basura].copy()

    with open(RAW_DIR / "origen_eventos_sanitarios.json", encoding="utf-8") as f:
        eventos_raw = json.load(f)

    dolar_raw, dolar_estado = obtener_dolar()
    return tablas, costos_raw, eventos_raw, dolar_raw, dolar_estado


# =====================================================================
# 2. LIMPIEZA (capa depurada)
# =====================================================================

# Centro Skyring (centro_id 7) viene con zona_id 7, que no existe en zonas
# (solo 1-3). Skyring esta en Magallanes -> zona_id 3 (supuesto en bitacora).
CORRECCION_ZONA_CENTRO = {7: 3}


def limpiar_centros(centros, zonas):
    df = centros.copy()
    zona_invalida = ~df["zona_id"].isin(zonas["zona_id"])
    corregir = zona_invalida & df["centro_id"].isin(CORRECCION_ZONA_CENTRO)
    df.loc[corregir, "zona_id"] = df.loc[corregir, "centro_id"].map(CORRECCION_ZONA_CENTRO)
    return df, int(corregir.sum()), len(df)


def limpiar_operacion_diaria(df):
    df = df.copy()
    df["fecha"] = df["fecha"].apply(parse_fecha_mixta)
    for col in ["alimento_kg", "mortalidad_n", "biomasa_kg",
                "crecimiento_kg", "temperatura_agua"]:
        df[col] = df[col].apply(parse_numero_sucio)
    total = len(df)

    mask_incompleto = df[["fecha", "alimento_kg", "biomasa_kg",
                          "crecimiento_kg", "poblacion"]].isna().any(axis=1)

    # 69 filas fechadas en 2026, fuera del periodo declarado (2025).
    mask_fuera_de_2025 = (df["fecha"].dt.year != C.ANIO).fillna(False)

    # mortalidad diaria biologicamente imposible: > 5% de la poblacion de la
    # jaula en un dia (las 55 filas detectadas superan el 100% de la poblacion).
    tasa = df["mortalidad_n"] / df["poblacion"]
    mask_mortalidad_imposible = (tasa > C.UMBRAL_MORTALIDAD_DIARIA).fillna(False)

    mask_excluir = mask_incompleto | mask_fuera_de_2025 | mask_mortalidad_imposible
    df_limpio = df.loc[~mask_excluir].copy()

    # Duplicados: la misma jaula-dia con exactamente los mismos valores (57
    # literales + 82 que solo difieren en el formato de fecha). El grano del
    # hecho es 1 jaula en 1 dia, asi que se conserva una sola fila.
    n_antes = len(df_limpio)
    df_limpio = df_limpio.drop_duplicates()
    n_dup = n_antes - len(df_limpio)

    detalle = {
        "incompleto_no_parseable": int(mask_incompleto.sum()),
        "fuera_de_2025": int(mask_fuera_de_2025.sum()),
        "mortalidad_diaria_imposible_mayor_5pct": int(mask_mortalidad_imposible.sum()),
        "duplicados_exactos_eliminados": int(n_dup),
    }
    return df_limpio, int(mask_excluir.sum()), total, detalle


def limpiar_cosechas(df, lotes_validos):
    """Excluye cosechas de lotes que no existen en la tabla lotes (lote_id
    77000-77005: 6 registros de prueba con kilos incoherentes, p. ej. producto
    > vivos). Cada centro tiene 6 cosechas reales; sin esta exclusion el
    denominador del costo por kilo queda inflado/distorsionado."""
    df = df.copy()
    df["fecha"] = df["fecha"].apply(parse_fecha_mixta)
    df["kilos_vivos"] = df["kilos_vivos"].apply(parse_numero_sucio)
    df["kilos_producto"] = df["kilos_producto"].apply(parse_numero_sucio)
    huerfana = ~df["lote_id"].isin(lotes_validos)
    return df.loc[~huerfana].copy(), int(huerfana.sum()), len(df)


def limpiar_costos_alimento(df):
    df = df.copy()
    df["precio_clp_kg"] = df["precio_clp_kg"].apply(parse_numero_sucio)
    df["tipo_alimento_norm"] = df["tipo_alimento"].apply(normaliza_tipo_alimento)
    antes = len(df)
    df_validos = df.dropna(subset=["precio_clp_kg"])
    return df, df_validos, antes - len(df_validos)


def limpiar_eventos(eventos_raw, centros_validos):
    eventos = eventos_raw["eventos"]
    filas, excluidos = [], 0
    for ev in eventos:
        if ev["centro_id"] not in centros_validos:
            excluidos += 1
            continue
        mort = ev["mortalidad_asociada"]
        mort = float(mort) if not isinstance(mort, (int, float)) else mort
        filas.append({
            "evento_id": ev["evento_id"],
            "centro_id": ev["centro_id"],
            "tipo_evento": ev["tipo"],
            "fecha_inicio": parse_fecha_mixta(ev["fecha_inicio"]),
            "fecha_fin": parse_fecha_mixta(ev["fecha_fin"]),
            "mortalidad_asociada": mort,
            "tratamiento": ev["tratamiento"],
            "jaulas_afectadas": ev["jaulas_afectadas"],
        })
    return pd.DataFrame(filas), excluidos, len(eventos)


def limpiar_dolar(dolar_raw):
    df = pd.DataFrame(dolar_raw["serie"])
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.tz_localize(None).dt.normalize()
    df["anio_mes"] = df["fecha"].dt.strftime("%Y-%m")
    mensual = df.groupby("anio_mes", as_index=False)["valor"].mean()
    mensual = mensual.rename(columns={"valor": "dolar_obs_promedio_mes"})
    return df, mensual


# =====================================================================
# 3. INTEGRACION (capa modelo)
# =====================================================================

def construir_modelo(tablas, op_diaria, cosechas, costos_validos, eventos, dolar_mensual):
    centros = tablas["centros"].merge(tablas["zonas"], on="zona_id", how="left")
    centros = centros.rename(columns={"nombre": "nombre_centro", "zona": "nombre_zona"})

    op = op_diaria.merge(centros[["centro_id", "nombre_centro", "nombre_zona"]],
                         on="centro_id", how="left")
    op["anio_mes"] = op["fecha"].dt.strftime("%Y-%m")

    cos = cosechas.merge(centros[["centro_id", "nombre_centro", "nombre_zona"]],
                         on="centro_id", how="left")

    # precio mensual promedio de alimento (todos los tipos/proveedores), porque
    # operacion_diaria no trae tipo_alimento (brecha del DDL, seccion 4a).
    precio_mensual = (costos_validos.groupby("mes", as_index=False)["precio_clp_kg"]
                      .mean().rename(columns={"mes": "anio_mes",
                                              "precio_clp_kg": "precio_prom_clp_kg"}))

    op = op.merge(precio_mensual, on="anio_mes", how="left")
    op = op.merge(dolar_mensual, on="anio_mes", how="left")
    op["costo_alimento_clp"] = op["alimento_kg"] * op["precio_prom_clp_kg"]

    ev = eventos.merge(centros[["centro_id", "nombre_centro"]], on="centro_id", how="left")
    return op, cos, ev, precio_mensual


# =====================================================================
# 4. METRICAS (capa consumo): FCR y mortalidad, dos definiciones cada una
# =====================================================================

def _mask_ventana(op, centro_id, fecha_inicio, fecha_fin):
    return ((op["centro_id"] == centro_id) &
            (op["fecha"] >= fecha_inicio) & (op["fecha"] <= fecha_fin))


def calcular_metricas(op, cos, ev):
    resumen = (op.groupby(["centro_id", "nombre_centro"])
               .agg(alimento_kg_total=("alimento_kg", "sum"),
                    crecimiento_kg_total=("crecimiento_kg", "sum"),
                    mortalidad_n_total=("mortalidad_n", "sum"),
                    costo_alimento_clp_total=("costo_alimento_clp", "sum"),
                    biomasa_kg_promedio=("biomasa_kg", "mean"),
                    poblacion_promedio=("poblacion", "mean"))
               .reset_index())

    resumen["peso_prom_kg"] = resumen["biomasa_kg_promedio"] / resumen["poblacion_promedio"]
    resumen["mortalidad_kg_total"] = resumen["mortalidad_n_total"] * resumen["peso_prom_kg"]

    # FCR simple = alimento / crecimiento registrado
    resumen[C.FCR_SIMPLE] = resumen["alimento_kg_total"] / resumen["crecimiento_kg_total"]
    # FCR corregido por mortalidad = alimento / (crecimiento + biomasa perdida
    # por mortalidad): los peces que murieron tambien comieron antes de morir.
    resumen[C.FCR_CORREGIDO] = resumen["alimento_kg_total"] / (
        resumen["crecimiento_kg_total"] + resumen["mortalidad_kg_total"])

    # costo por kilo producido (hecho_cosecha aporta el denominador)
    cos_centro = cos.groupby("centro_id", as_index=False).agg(
        kilos_producto_total=("kilos_producto", "sum"),
        kilos_vivos_total=("kilos_vivos", "sum"))
    resumen = resumen.merge(cos_centro, on="centro_id", how="left")
    resumen["costo_por_kilo_clp"] = (resumen["costo_alimento_clp_total"] /
                                     resumen["kilos_producto_total"])

    # Mortalidad por evento: total del periodo vs atribuible (sobre la basal)
    filas = []
    for _, row in ev.iterrows():
        mask_ev = _mask_ventana(op, row["centro_id"], row["fecha_inicio"], row["fecha_fin"])
        total_ev = op.loc[mask_ev, "mortalidad_n"].sum()
        mask_basal = (op["centro_id"] == row["centro_id"]) & (~mask_ev)
        tasa_basal = op.loc[mask_basal, "mortalidad_n"].mean()      # muertes por jaula-dia
        jaula_dias = int(mask_ev.sum())
        basal_esperada = tasa_basal * jaula_dias
        atribuible = max(total_ev - basal_esperada, 0)
        filas.append({
            "evento_id": row["evento_id"],
            "centro_id": row["centro_id"],
            "nombre_centro": row["nombre_centro"],
            "tipo_evento": row["tipo_evento"],
            "mortalidad_declarada_json": row["mortalidad_asociada"],
            C.MORT_TOTAL: total_ev,
            "mortalidad_basal_esperada": round(basal_esperada, 1),
            C.MORT_ATRIBUIBLE: round(atribuible, 1),
        })
    return resumen, pd.DataFrame(filas)


def calcular_fcr_dentro_fuera_evento(op, ev):
    """FCR simple del centro dentro vs fuera de la ventana del evento: separa
    'consecuencia del evento' de 'problema estructural del centro'."""
    filas = []
    for _, row in ev.iterrows():
        mask_ev = _mask_ventana(op, row["centro_id"], row["fecha_inicio"], row["fecha_fin"])
        mask_fuera = (op["centro_id"] == row["centro_id"]) & (~mask_ev)
        dentro, fuera = op.loc[mask_ev], op.loc[mask_fuera]
        filas.append({
            "evento_id": row["evento_id"],
            "centro_id": row["centro_id"],
            "nombre_centro": row["nombre_centro"],
            "tipo_evento": row["tipo_evento"],
            "fcr_dentro_evento": round(dentro["alimento_kg"].sum() / dentro["crecimiento_kg"].sum(), 3),
            "fcr_fuera_evento": round(fuera["alimento_kg"].sum() / fuera["crecimiento_kg"].sum(), 3),
            "jaula_dias_evento": int(mask_ev.sum()),
        })
    return pd.DataFrame(filas)


# =====================================================================
# 4b. DESCOMPOSICION DEL SOBRECOSTO (2 FCR x 2 mortalidad = 4 combinaciones)
# =====================================================================

def descomponer_sobrecosto(resumen, mortalidad_eventos, precio_mensual):
    """Sobrecosto del centro mas caro vs el promedio simple de los demas,
    repartido por causa y que suma:
      - FCR (eficiencia de alimentacion)
      - evento sanitario (mortalidad atribuible)
      - mortalidad basal (solo si se elige 'mortalidad total del periodo':
        el resto de las muertes de la ventana, que no es exceso)."""
    precio_prom_global = precio_mensual["precio_prom_clp_kg"].mean()
    top = resumen.sort_values("costo_por_kilo_clp", ascending=False).iloc[0]
    otros = resumen[resumen["centro_id"] != top["centro_id"]]
    mort = mortalidad_eventos[mortalidad_eventos["centro_id"] == top["centro_id"]]
    n_atrib = mort[C.MORT_ATRIBUIBLE].sum()
    n_total = mort[C.MORT_TOTAL].sum()

    filas = []
    for def_fcr in [C.FCR_SIMPLE, C.FCR_CORREGIDO]:
        fcr_resto = otros[def_fcr].mean()
        fcr_real = top[def_fcr]
        kg_base = top["crecimiento_kg_total"] + (
            top["mortalidad_kg_total"] if def_fcr == C.FCR_CORREGIDO else 0)
        # Precio consistente con el costo real (mensual): se escala el gasto
        # real por la reduccion proporcional de alimento (supuesto en bitacora).
        factor = (fcr_resto * kg_base) / top["alimento_kg_total"]
        costo_contrafactual = factor * top["costo_alimento_clp_total"]
        sobre_fcr = top["costo_alimento_clp_total"] - costo_contrafactual

        def costo_muertes(n):  # alimento ya invertido en los peces muertos, al FCR del resto
            return n * top["peso_prom_kg"] * fcr_resto * precio_prom_global

        for def_mort in [C.MORT_ATRIBUIBLE, C.MORT_TOTAL]:
            n_evento = n_atrib
            n_basal = (n_total - n_atrib) if def_mort == C.MORT_TOTAL else 0.0
            c_evento, c_basal = costo_muertes(n_evento), costo_muertes(n_basal)
            total = sobre_fcr + c_evento + c_basal
            filas.append({
                "definicion_fcr": def_fcr,
                "definicion_mortalidad": def_mort,
                "es_referencia": def_fcr == C.FCR_PRINCIPAL and def_mort == C.MORT_PRINCIPAL,
                "centro": top["nombre_centro"],
                "fcr_centro": round(fcr_real, 3),
                "fcr_promedio_resto": round(fcr_resto, 3),
                "costo_alimento_real_clp": round(top["costo_alimento_clp_total"], 0),
                "costo_alimento_si_fcr_resto_clp": round(costo_contrafactual, 0),
                "sobrecosto_fcr_clp": round(sobre_fcr, 0),
                "mortalidad_evento_n": round(n_evento, 0),
                "mortalidad_basal_n": round(n_basal, 0),
                "costo_mortalidad_evento_clp": round(c_evento, 0),
                "costo_mortalidad_basal_clp": round(c_basal, 0),
                "sobrecosto_total_clp": round(total, 0),
                "pct_fcr": round(100 * sobre_fcr / total, 1),
                "pct_evento": round(100 * c_evento / total, 1),
                "pct_basal": round(100 * c_basal / total, 1),
            })
    return pd.DataFrame(filas), top["nombre_centro"]


# =====================================================================
# 4c. CASO DE NEGOCIO: valor vs costo de la auditoria de alimentacion
# =====================================================================

def calcular_caso_negocio(descomp):
    """Valor (margen: ahorro directo de alimento) vs costo de la auditoria.
    El valor es el sobrecosto por FCR de 2025 (supuesto: el mismo volumen se
    repite en el proximo ciclo). Los costos son SUPUESTOS de config.py."""
    sup = pd.DataFrame(C.AUDITORIA_SUPUESTOS,
                       columns=["concepto", "cantidad", "unidad", "costo_unitario_clp"])
    sup["costo_total_clp"] = sup["cantidad"] * sup["costo_unitario_clp"]
    subtotal = sup["costo_total_clp"].sum()
    conting = subtotal * C.AUDITORIA_CONTINGENCIA_PCT / 100
    costo_aud = subtotal + conting
    sup = pd.concat([sup, pd.DataFrame([
        {"concepto": f"Contingencia ({C.AUDITORIA_CONTINGENCIA_PCT:.0f}%)", "cantidad": 1,
         "unidad": "global", "costo_unitario_clp": conting, "costo_total_clp": conting},
        {"concepto": "TOTAL auditoria", "cantidad": 1, "unidad": "global",
         "costo_unitario_clp": costo_aud, "costo_total_clp": costo_aud}])], ignore_index=True)

    base = descomp[descomp["definicion_mortalidad"] == C.MORT_PRINCIPAL]
    filas = []
    for _, r in base.iterrows():
        brecha = r["sobrecosto_fcr_clp"]
        for cap in C.CAPTURAS_BRECHA:
            valor = brecha * cap
            filas.append({
                "definicion_fcr": r["definicion_fcr"],
                "brecha_fcr_clp": round(brecha, 0),
                "pct_brecha_capturada": int(round(cap * 100)),
                "valor_anual_margen_clp": round(valor, 0),
                "costo_auditoria_clp": round(costo_aud, 0),
                "beneficio_neto_clp": round(valor - costo_aud, 0),
                "beneficio_sobre_costo": round(valor / costo_aud, 1),
                "punto_equilibrio_pct_brecha": round(100 * costo_aud / brecha, 2),
            })
    return pd.DataFrame(filas), sup, costo_aud


# =====================================================================
# 5. COBERTURA Y CIFRAS CLAVE
# =====================================================================

def calcular_cobertura(total_op, det, excl_cos, total_cos, excl_evt, total_evt, excl_precio, total_costos,
                       centros_corregidos, total_centros):
    def fila(fuente, n, total, motivo):
        return {"fuente": fuente, "excluidos": n, "total": total,
                "pct_excluido": round(100 * n / total, 2), "motivo": motivo}
    filas = [
        fila("operacion_diaria", det["incompleto_no_parseable"], total_op,
             "fecha o valores numericos no parseables tras limpieza"),
        fila("operacion_diaria", det["fuera_de_2025"], total_op,
             "fecha fuera del periodo declarado (anio != 2025)"),
        fila("operacion_diaria", det["mortalidad_diaria_imposible_mayor_5pct"], total_op,
             "mortalidad_n > 5% de la poblacion en un dia (las 55 filas superan el 100%: error de captura)"),
        fila("operacion_diaria", det["duplicados_exactos_eliminados"], total_op,
             "misma jaula-dia repetida con valores identicos (grano = 1 jaula en 1 dia)"),
        fila("sqlite.cosechas", excl_cos, total_cos,
             "lote_id 77000-77005 no existe en lotes y kilos incoherentes (dato de prueba)"),
        fila("origen_eventos_sanitarios.json", excl_evt, total_evt,
             "centro_id 90-93 no existe en la tabla centros (dato de prueba)"),
        fila("origen_costos_alimento.csv", excl_precio, total_costos,
             "precio_clp_kg nulo ('-'); se excluyen antes del conteo la fila TOTAL y el encabezado repetido"),
        {"fuente": "origen_acuicultura.sqlite (centros)", "excluidos": 0, "total": total_centros,
         "pct_excluido": 0.0,
         "motivo": f"{centros_corregidos} centro(s) corregido(s), no excluido(s): Centro Skyring con "
                   "zona_id 7 inexistente -> Magallanes (zona_id 3) (supuesto documentado)"},
    ]
    return pd.DataFrame(filas)


def exportar_cifras_clave(resumen, mortalidad_eventos, fcr_df, descomp, caso, costo_aud,
                          cobertura, centro_top):
    """Cada numero citado en el informe y el prototipo sale de aqui."""
    top = resumen[resumen["nombre_centro"] == centro_top].iloc[0]
    otros = resumen[resumen["nombre_centro"] != centro_top]
    fcr_top = fcr_df[fcr_df["nombre_centro"] == centro_top].iloc[0]
    mort = mortalidad_eventos[mortalidad_eventos["nombre_centro"] == centro_top]
    ref = descomp[descomp["es_referencia"]].iloc[0]
    sim = descomp[(descomp.definicion_fcr == C.FCR_SIMPLE) & (descomp.definicion_mortalidad == C.MORT_ATRIBUIBLE)].iloc[0]
    cor = descomp[(descomp.definicion_fcr == C.FCR_CORREGIDO) & (descomp.definicion_mortalidad == C.MORT_ATRIBUIBLE)].iloc[0]
    cn = caso[caso.pct_brecha_capturada == 100]
    cn_s = cn[cn.definicion_fcr == C.FCR_SIMPLE].iloc[0]
    cn_c = cn[cn.definicion_fcr == C.FCR_CORREGIDO].iloc[0]

    items = [
        ("centro_mas_caro", "Centro con mayor costo por kilo", centro_top, "texto", "calcular_metricas"),
        ("costo_kg_centro", "Costo de alimento por kg producto, centro mas caro", top["costo_por_kilo_clp"], "CLP/kg", "calcular_metricas"),
        ("costo_kg_otros_min", "Costo por kg minimo del resto", otros["costo_por_kilo_clp"].min(), "CLP/kg", "calcular_metricas"),
        ("costo_kg_otros_max", "Costo por kg maximo del resto", otros["costo_por_kilo_clp"].max(), "CLP/kg", "calcular_metricas"),
        ("pct_mas_caro_vs_max_resto", "Cuanto mas caro que el centro mas caro del resto", 100 * (top["costo_por_kilo_clp"] / otros["costo_por_kilo_clp"].max() - 1), "%", "calcular_metricas"),
        ("pct_mas_caro_vs_min_resto", "Cuanto mas caro que el centro mas barato", 100 * (top["costo_por_kilo_clp"] / otros["costo_por_kilo_clp"].min() - 1), "%", "calcular_metricas"),
        ("fcr_simple_centro", "FCR simple del centro mas caro", top[C.FCR_SIMPLE], "ratio", "calcular_metricas"),
        ("fcr_simple_resto", "FCR simple, promedio del resto", otros[C.FCR_SIMPLE].mean(), "ratio", "descomponer_sobrecosto"),
        ("fcr_corregido_centro", "FCR corregido por mortalidad del centro", top[C.FCR_CORREGIDO], "ratio", "calcular_metricas"),
        ("fcr_corregido_resto", "FCR corregido, promedio del resto", otros[C.FCR_CORREGIDO].mean(), "ratio", "descomponer_sobrecosto"),
        ("fcr_fuera_evento", "FCR simple del centro fuera del brote", fcr_top["fcr_fuera_evento"], "ratio", "calcular_fcr_dentro_fuera_evento"),
        ("fcr_dentro_evento", "FCR simple del centro durante el brote", fcr_top["fcr_dentro_evento"], "ratio", "calcular_fcr_dentro_fuera_evento"),
        ("mortalidad_declarada", "Mortalidad declarada por la gerencia (JSON)", mort["mortalidad_declarada_json"].sum(), "peces", "limpiar_eventos"),
        ("mortalidad_total_periodo", "Mortalidad total del periodo del evento", mort[C.MORT_TOTAL].sum(), "peces", "calcular_metricas"),
        ("mortalidad_basal_esperada", "Mortalidad basal esperada en la ventana", mort["mortalidad_basal_esperada"].sum(), "peces", "calcular_metricas"),
        ("mortalidad_atribuible", "Mortalidad atribuible al evento", mort[C.MORT_ATRIBUIBLE].sum(), "peces", "calcular_metricas"),
        ("sobrecosto_fcr_simple", "Sobrecosto atribuible a FCR (FCR simple)", sim["sobrecosto_fcr_clp"], "CLP", "descomponer_sobrecosto"),
        ("sobrecosto_fcr_corregido", "Sobrecosto atribuible a FCR (FCR corregido)", cor["sobrecosto_fcr_clp"], "CLP", "descomponer_sobrecosto"),
        ("sobrecosto_total_referencia", "Sobrecosto total, cifra de referencia (FCR simple + mortalidad atribuible)", ref["sobrecosto_total_clp"], "CLP", "descomponer_sobrecosto"),
        ("sobrecosto_total_min", "Sobrecosto total, minimo de las 4 combinaciones", descomp["sobrecosto_total_clp"].min(), "CLP", "descomponer_sobrecosto"),
        ("sobrecosto_total_max", "Sobrecosto total, maximo de las 4 combinaciones", descomp["sobrecosto_total_clp"].max(), "CLP", "descomponer_sobrecosto"),
        ("pct_fcr_simple_atrib", "% del sobrecosto explicado por FCR (FCR simple, mort. atribuible)", sim["pct_fcr"], "%", "descomponer_sobrecosto"),
        ("pct_fcr_corregido_atrib", "% del sobrecosto explicado por FCR (FCR corregido, mort. atribuible)", cor["pct_fcr"], "%", "descomponer_sobrecosto"),
        ("costo_auditoria", "Costo estimado de la auditoria (con contingencia)", costo_aud, "CLP", "calcular_caso_negocio"),
        ("valor_auditoria_simple_100", "Valor anual si se cierra 100% de la brecha (FCR simple)", cn_s["valor_anual_margen_clp"], "CLP", "calcular_caso_negocio"),
        ("valor_auditoria_corregido_100", "Valor anual si se cierra 100% de la brecha (FCR corregido)", cn_c["valor_anual_margen_clp"], "CLP", "calcular_caso_negocio"),
        ("punto_equilibrio_simple_pct", "% de la brecha que hay que cerrar para pagar la auditoria (FCR simple)", cn_s["punto_equilibrio_pct_brecha"], "%", "calcular_caso_negocio"),
        ("punto_equilibrio_corregido_pct", "% de la brecha que hay que cerrar para pagar la auditoria (FCR corregido)", cn_c["punto_equilibrio_pct_brecha"], "%", "calcular_caso_negocio"),
    ]
    for _, r in cobertura.iterrows():
        items.append((f"cobertura_{r['fuente']}_{r['motivo'][:25]}".replace(" ", "_"),
                      f"% excluido - {r['fuente']}: {r['motivo']}", r["pct_excluido"], "%", "calcular_cobertura"))
    return pd.DataFrame(items, columns=["cifra_id", "descripcion", "valor", "unidad", "calculado_en"])


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("1/6 Extrayendo datos crudos (SQLite, CSV, JSON, API dolar)...")
    tablas, costos_raw, eventos_raw, dolar_raw, dolar_estado = extraer()
    print(f"   dolar: {dolar_estado['fuente']}")

    print("2/6 Limpiando...")
    tablas["centros"], centros_corregidos, total_centros = limpiar_centros(
        tablas["centros"], tablas["zonas"])
    op_diaria, excl_op, total_op, det_op = limpiar_operacion_diaria(tablas["operacion_diaria"])
    cosechas, excl_cos, total_cos = limpiar_cosechas(tablas["cosechas"], set(tablas["lotes"]["lote_id"]))
    costos_todos, costos_validos, excl_precio = limpiar_costos_alimento(costos_raw)
    centros_validos = set(tablas["centros"]["centro_id"].tolist())
    eventos, excl_evt, total_evt = limpiar_eventos(eventos_raw, centros_validos)
    dolar_diario, dolar_mensual = limpiar_dolar(dolar_raw)

    print("3/6 Integrando segun el modelo dimensional...")
    op, cos, ev, precio_mensual = construir_modelo(
        tablas, op_diaria, cosechas, costos_validos, eventos, dolar_mensual)

    print("4/6 Pruebas de calidad (bloquean la carga si fallan)...")
    contexto = {"tablas": tablas, "op": op, "cos": cos, "costos": costos_validos,
                "eventos": eventos, "dolar_mensual": dolar_mensual,
                "dolar_estado": dolar_estado, "total_op": total_op, "det_op": det_op}
    pruebas = ejecutar_pruebas(contexto)
    pruebas.to_csv(OUTPUT_DIR / "calidad_pruebas.csv", index=False)
    print(pruebas[["prueba", "fuente", "resultado"]].to_string(index=False))
    if (pruebas["resultado"] == "FALLA").any():
        print("\nERROR: fallaron pruebas bloqueantes; no se calculan metricas. "
              "Ver output/calidad_pruebas.csv")
        sys.exit(1)

    print("5/6 Calculando metricas, caso de negocio y cifras clave...")
    resumen, mortalidad_eventos = calcular_metricas(op, cos, ev)
    descomp, centro_top = descomponer_sobrecosto(resumen, mortalidad_eventos, precio_mensual)
    fcr_df = calcular_fcr_dentro_fuera_evento(op, ev)
    caso, auditoria_sup, costo_aud = calcular_caso_negocio(descomp)
    cobertura = calcular_cobertura(total_op, det_op, excl_cos, total_cos, excl_evt, total_evt, excl_precio,
                                   len(costos_todos), centros_corregidos, total_centros)
    cifras = exportar_cifras_clave(resumen, mortalidad_eventos, fcr_df, descomp, caso,
                                   costo_aud, cobertura, centro_top)

    print("6/6 Guardando resultados...")
    op.to_csv(PROCESSED_DIR / "hecho_operacion_diaria.csv", index=False)
    cos.to_csv(PROCESSED_DIR / "hecho_cosecha.csv", index=False)
    ev.to_csv(PROCESSED_DIR / "hecho_evento_sanitario.csv", index=False)
    costos_validos.to_csv(PROCESSED_DIR / "hecho_costo_alimento.csv", index=False)
    dolar_mensual.to_csv(PROCESSED_DIR / "dim_dolar_mensual.csv", index=False)

    resumen.sort_values("costo_por_kilo_clp", ascending=False).to_csv(
        OUTPUT_DIR / "resumen_centro_fcr_mortalidad.csv", index=False)
    mortalidad_eventos.to_csv(OUTPUT_DIR / "mortalidad_eventos_2_definiciones.csv", index=False)
    descomp.to_csv(OUTPUT_DIR / "descomposicion_sobrecosto_fcr_vs_mortalidad.csv", index=False)
    fcr_df.to_csv(OUTPUT_DIR / "fcr_dentro_fuera_evento.csv", index=False)
    caso.to_csv(OUTPUT_DIR / "caso_negocio_auditoria.csv", index=False)
    auditoria_sup.to_csv(OUTPUT_DIR / "auditoria_supuestos_costo.csv", index=False)
    cobertura.to_csv(OUTPUT_DIR / "cobertura_datos.csv", index=False)
    cifras.to_csv(OUTPUT_DIR / "cifras_clave.csv", index=False)

    # Registro de la corrida + acuerdo de servicio (tabla hecho_operacion_diaria)
    n_esperados = total_op - det_op["duplicados_exactos_eliminados"]
    completitud = round(100 * len(op) / n_esperados, 2)
    bloq = pruebas[pruebas["si_falla"] == "bloquea"]
    calidad = round(100 * (bloq["resultado"] == "OK").mean(), 1)
    ahora = datetime.now(timezone.utc)
    meta = {
        "fecha_corrida_utc": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "fecha_corrida_local": datetime.now().astimezone().strftime("%d-%m-%Y %H:%M"),
        "periodo_datos": {"inicio": op["fecha"].min().strftime("%Y-%m-%d"),
                          "fin": op["fecha"].max().strftime("%Y-%m-%d")},
        "dolar_fuente": dolar_estado["fuente"],
        "dolar_detalle": dolar_estado["detalle"],
        "filas_hecho_operacion_diaria": int(len(op)),
        "pruebas_total": int(len(pruebas)),
        "pruebas_ok": int((pruebas["resultado"] == "OK").sum()),
        "pruebas_aviso": int((pruebas["resultado"] == "AVISO").sum()),
        "pruebas_falla": int((pruebas["resultado"] == "FALLA").sum()),
        "sla": {
            "tabla": "hecho_operacion_diaria",
            "frescura_objetivo_dias": C.SLA_FRESCURA_DIAS,
            "completitud_pct": float(completitud), "completitud_min_pct": C.SLA_COMPLETITUD_MIN_PCT,
            "completitud_cumple": bool(completitud >= C.SLA_COMPLETITUD_MIN_PCT),
            "calidad_pct": float(calidad), "calidad_min_pct": C.SLA_CALIDAD_MIN_PCT,
            "calidad_cumple": bool(calidad >= C.SLA_CALIDAD_MIN_PCT),
            "dueno": C.DUENO_DATO,
        },
    }
    with open(OUTPUT_DIR / "corrida_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n=== CENTRO MAS CARO: {centro_top} ===")
    print(resumen.sort_values("costo_por_kilo_clp", ascending=False)[
        ["nombre_centro", "costo_por_kilo_clp", C.FCR_SIMPLE, C.FCR_CORREGIDO]].to_string(index=False))
    print("\n=== MORTALIDAD POR EVENTO ===")
    print(mortalidad_eventos.to_string(index=False))
    print("\n=== DESCOMPOSICION DEL SOBRECOSTO (4 combinaciones) ===")
    print(descomp[["definicion_fcr", "definicion_mortalidad", "sobrecosto_fcr_clp",
                   "sobrecosto_total_clp", "pct_fcr", "pct_evento", "pct_basal"]].to_string(index=False))
    print("\n=== FCR DENTRO vs FUERA DEL EVENTO ===")
    print(fcr_df.to_string(index=False))
    print("\n=== CASO DE NEGOCIO (auditoria) ===")
    print(caso.to_string(index=False))
    print(f"\nListo. Resultados en: {OUTPUT_DIR}")
    return resumen, mortalidad_eventos, cobertura, descomp


if __name__ == "__main__":
    main()
