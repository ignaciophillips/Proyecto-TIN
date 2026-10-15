#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AquaFiordo - Pipeline BI - Grupo Salmonera N4
Pregunta 2: En el centro con mas costo, la causa es la mortalidad de un
evento sanitario o un FCR peor, o ambas?

Lee las 4 fuentes (SQLite, CSV, JSON, API dolar), limpia los datos sucios,
integra segun el modelo dimensional del equipo (ddl_modelo_dimensional_aquafiordo.sql)
y calcula la metrica bajo dos definiciones distintas.

Uso:
    python3 src/pipeline.py

Requiere: pandas, numpy (ver requirements.txt)
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)


# =====================================================================
# 0. UTILIDADES DE LIMPIEZA
# =====================================================================

def parse_fecha_mixta(valor):
    """Parsea fechas en formatos mixtos: '17/09/2025', '22-09-25',
    '28-jul-2025', '2025-10-20', '14/09/2025'."""
    if pd.isna(valor):
        return pd.NaT
    s = str(valor).strip()
    formatos = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y", "%d-%b-%Y",
        "%d-%b-%y", "%d/%m/%y",
    ]
    # meses en español abreviados -> ingles para strptime
    meses_es = {
        "ene": "jan", "abr": "apr", "ago": "aug", "dic": "dec",
    }
    s_norm = s.lower()
    for es, en in meses_es.items():
        s_norm = s_norm.replace(es, en)
    for fmt in formatos:
        try:
            return pd.to_datetime(s_norm, format=fmt)
        except (ValueError, TypeError):
            continue
    # ultimo intento: dejar que pandas infiera
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
        # formato chileno: punto de miles, coma decimal -> '1.050,00'
        s = s.replace(".", "").replace(",", ".")
    elif has_comma and not has_dot:
        # coma como decimal: '10,4' o '993,00'
        s = s.replace(",", ".")
    elif has_dot and not has_comma:
        # punto puede ser miles ('246.597') o decimal ('203.5')
        partes = s.split(".")
        if len(partes[-1]) == 3 and len(partes) > 1:
            # 3 digitos tras el punto -> separador de miles
            s = s.replace(".", "")
        # si no, se deja como decimal normal
    try:
        return float(s)
    except ValueError:
        return np.nan


def normaliza_tipo_alimento(valor):
    """Normaliza 'ENG-100' / 'engorda100' / 'Engorda 100' -> 'ENG-100'."""
    if pd.isna(valor):
        return None
    s = str(valor).strip().upper().replace(" ", "").replace("-", "")
    m = re.search(r"(\d+)", s)
    numero = m.group(1) if m else "000"
    return f"ENG-{numero}"


# =====================================================================
# 1. EXTRACCION
# =====================================================================

def extraer():
    con = sqlite3.connect(RAW_DIR / "origen_acuicultura.sqlite")
    tablas = {}
    for t in ["zonas", "centros", "jaulas", "especies", "lotes",
              "operacion_diaria", "cosechas"]:
        tablas[t] = pd.read_sql(f"SELECT * FROM {t}", con)
    con.close()

    # CSV de alimento: separador ';', con una fila de encabezado duplicada
    # a mitad de archivo -> se detecta y descarta.
    # el CSV viene en latin-1 (acentos como pigmentación), no utf-8
    costos_raw = pd.read_csv(RAW_DIR / "origen_costos_alimento.csv", sep=";",
                              dtype=str, encoding="latin-1")
    costos_raw = costos_raw[costos_raw["tipo_alimento"] != "tipo_alimento"].copy()

    with open(RAW_DIR / "origen_eventos_sanitarios.json", encoding="utf-8") as f:
        eventos_raw = json.load(f)

    with open(RAW_DIR / "dolar_2025.json", encoding="utf-8") as f:
        dolar_raw = json.load(f)

    return tablas, costos_raw, eventos_raw, dolar_raw


# =====================================================================
# 2. LIMPIEZA Y STAGING
# =====================================================================

# Centro Skyring (centro_id 7) viene con zona_id 7, que no existe en la tabla
# zonas (solo 1-3). Skyring esta en Magallanes -> se asigna zona_id 3
# (supuesto documentado en cobertura_datos.csv).
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

    # a) filas con campos no parseables (fecha o numeros invalidos)
    mask_incompleto = df[["fecha", "alimento_kg", "biomasa_kg",
                           "crecimiento_kg", "poblacion"]].isna().any(axis=1)

    # b) ANALISIS DE COBERTURA: 69 filas estan fechadas en 2026, fuera del
    #    periodo declarado por la empresa ("anio": 2025 en el JSON, y el
    #    README dice "durante 2025"). Se excluyen del analisis del año 2025.
    mask_fuera_de_2025 = df["fecha"].dt.year != 2025
    mask_fuera_de_2025 = mask_fuera_de_2025.fillna(False)

    # c) ANOMALIA DE MORTALIDAD: hay filas donde mortalidad_n es casi igual
    #    a la poblacion completa de la jaula (ej. 86.767 muertes de una
    #    poblacion de 83.806 en un solo dia), lo que es biologicamente
    #    imposible sin que la poblacion del dia siguiente caiga a cero.
    #    Se trata como error de captura y se excluye: mortalidad_n no puede
    #    superar el 5% de la poblacion de esa jaula en un solo dia
    #    (supuesto documentado en la bitacora).
    tasa_mortalidad_diaria = df["mortalidad_n"] / df["poblacion"]
    mask_mortalidad_imposible = tasa_mortalidad_diaria > 0.05
    mask_mortalidad_imposible = mask_mortalidad_imposible.fillna(False)

    mask_excluir = mask_incompleto | mask_fuera_de_2025 | mask_mortalidad_imposible
    df_limpio = df.loc[~mask_excluir].copy()

    detalle_exclusion = {
        "incompleto_no_parseable": int(mask_incompleto.sum()),
        "fuera_de_2025": int(mask_fuera_de_2025.sum()),
        "mortalidad_diaria_imposible_mayor_5pct": int(mask_mortalidad_imposible.sum()),
    }
    excluidos = int(mask_excluir.sum())
    return df_limpio, excluidos, total, detalle_exclusion


def limpiar_cosechas(df):
    df = df.copy()
    df["fecha"] = df["fecha"].apply(parse_fecha_mixta)
    df["kilos_vivos"] = df["kilos_vivos"].apply(parse_numero_sucio)
    df["kilos_producto"] = df["kilos_producto"].apply(parse_numero_sucio)
    return df


def limpiar_costos_alimento(df):
    df = df.copy()
    df["precio_clp_kg"] = df["precio_clp_kg"].apply(parse_numero_sucio)
    df["tipo_alimento_norm"] = df["tipo_alimento"].apply(normaliza_tipo_alimento)
    antes = len(df)
    df_validos = df.dropna(subset=["precio_clp_kg"])
    excluidos_precio_nulo = antes - len(df_validos)
    return df, df_validos, excluidos_precio_nulo


def limpiar_eventos(eventos_raw, centros_validos):
    eventos = eventos_raw["eventos"]
    filas = []
    excluidos_centro_invalido = 0
    for ev in eventos:
        centro_id = ev["centro_id"]
        if centro_id not in centros_validos:
            excluidos_centro_invalido += 1
            continue
        mort = ev["mortalidad_asociada"]
        mort = float(mort) if not isinstance(mort, (int, float)) else mort
        filas.append({
            "evento_id": ev["evento_id"],
            "centro_id": centro_id,
            "tipo_evento": ev["tipo"],
            "fecha_inicio": parse_fecha_mixta(ev["fecha_inicio"]),
            "fecha_fin": parse_fecha_mixta(ev["fecha_fin"]),
            "mortalidad_asociada": mort,
            "tratamiento": ev["tratamiento"],
            "jaulas_afectadas": ev["jaulas_afectadas"],
        })
    return pd.DataFrame(filas), excluidos_centro_invalido, len(eventos)


def limpiar_dolar(dolar_raw):
    df = pd.DataFrame(dolar_raw["serie"])
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.tz_localize(None).dt.normalize()
    df["anio_mes"] = df["fecha"].dt.strftime("%Y-%m")
    mensual = df.groupby("anio_mes", as_index=False)["valor"].mean()
    mensual = mensual.rename(columns={"valor": "dolar_obs_promedio_mes"})
    return df, mensual


# =====================================================================
# 3. INTEGRACION (segun el modelo dimensional del equipo)
# =====================================================================

def construir_modelo(tablas, op_diaria, cosechas, costos_validos, eventos, dolar_mensual):
    centros = tablas["centros"].merge(tablas["zonas"], on="zona_id", how="left")
    centros = centros.rename(columns={"nombre": "nombre_centro", "zona": "nombre_zona"})

    op = op_diaria.merge(centros[["centro_id", "nombre_centro", "nombre_zona"]],
                          on="centro_id", how="left")
    op["anio_mes"] = op["fecha"].dt.strftime("%Y-%m")

    cos = cosechas.merge(centros[["centro_id", "nombre_centro", "nombre_zona"]],
                          on="centro_id", how="left")

    # precio mensual promedio de alimento (todos los tipos/proveedores),
    # para estimar costo cuando operacion_diaria no trae tipo_alimento
    # (brecha de datos documentada en el DDL del equipo, seccion 4a).
    precio_mensual = (costos_validos.groupby("mes", as_index=False)["precio_clp_kg"]
                       .mean().rename(columns={"mes": "anio_mes",
                                                "precio_clp_kg": "precio_prom_clp_kg"}))

    op = op.merge(precio_mensual, on="anio_mes", how="left")
    op = op.merge(dolar_mensual, on="anio_mes", how="left")
    op["costo_alimento_clp"] = op["alimento_kg"] * op["precio_prom_clp_kg"]

    ev = eventos.merge(centros[["centro_id", "nombre_centro"]], on="centro_id", how="left")

    return op, cos, ev, precio_mensual


# =====================================================================
# 4. METRICA: FCR y mortalidad, dos definiciones
# =====================================================================

def calcular_metricas(op, cos, ev):
    resumen_centro = (op.groupby(["centro_id", "nombre_centro"])
                       .agg(alimento_kg_total=("alimento_kg", "sum"),
                            crecimiento_kg_total=("crecimiento_kg", "sum"),
                            mortalidad_n_total=("mortalidad_n", "sum"),
                            costo_alimento_clp_total=("costo_alimento_clp", "sum"),
                            biomasa_kg_promedio=("biomasa_kg", "mean"),
                            poblacion_promedio=("poblacion", "mean"))
                       .reset_index())

    # peso promedio del pez por centro (para convertir mortalidad en kg)
    resumen_centro["peso_prom_kg"] = (resumen_centro["biomasa_kg_promedio"] /
                                       resumen_centro["poblacion_promedio"])
    resumen_centro["mortalidad_kg_total"] = (resumen_centro["mortalidad_n_total"] *
                                              resumen_centro["peso_prom_kg"])

    # --- FCR Definicion A: "simple" = alimento / crecimiento registrado ---
    resumen_centro["FCR_def_A_simple"] = (resumen_centro["alimento_kg_total"] /
                                           resumen_centro["crecimiento_kg_total"])

    # --- FCR Definicion B: "corregido por mortalidad" = alimento /
    #     (crecimiento + biomasa perdida por mortalidad). Los peces que
    #     murieron tambien comieron antes de morir, asi que se les
    #     devuelve al denominador para no castigar el FCR por mortalidad. ---
    resumen_centro["FCR_def_B_corregido"] = (
        resumen_centro["alimento_kg_total"] /
        (resumen_centro["crecimiento_kg_total"] + resumen_centro["mortalidad_kg_total"])
    )

    # --- costo por kilo producido (cosecha), proxy de "costo" para P1/P2 ---
    cos_centro = cos.groupby(["centro_id", "nombre_centro"], as_index=False).agg(
        kilos_producto_total=("kilos_producto", "sum"),
        kilos_vivos_total=("kilos_vivos", "sum"))
    resumen_centro = resumen_centro.merge(
        cos_centro[["centro_id", "kilos_producto_total", "kilos_vivos_total"]],
        on="centro_id", how="left")
    resumen_centro["costo_por_kilo_clp"] = (resumen_centro["costo_alimento_clp_total"] /
                                             resumen_centro["kilos_producto_total"])

    # --- mortalidad: Definicion A = toda la mortalidad del centro durante
    #     las fechas de sus eventos sanitarios (verbalizado por la contraparte:
    #     "se distingue caso a caso"). Definicion B = exceso sobre la
    #     mortalidad basal (promedio diario del centro fuera de eventos). ---
    mort_rows = []
    for _, row in ev.iterrows():
        centro_id = row["centro_id"]
        mask_evento = ((op["centro_id"] == centro_id) &
                        (op["fecha"] >= row["fecha_inicio"]) &
                        (op["fecha"] <= row["fecha_fin"]))
        mort_evento_total = op.loc[mask_evento, "mortalidad_n"].sum()

        mask_basal = (op["centro_id"] == centro_id) & (~mask_evento)
        tasa_basal_diaria = op.loc[mask_basal, "mortalidad_n"].mean()
        duracion = (row["fecha_fin"] - row["fecha_inicio"]).days + 1
        mortalidad_basal_esperada = tasa_basal_diaria * int(mask_evento.sum())
        mortalidad_atribuible = max(mort_evento_total - mortalidad_basal_esperada, 0)

        mort_rows.append({
            "evento_id": row["evento_id"],
            "centro_id": centro_id,
            "nombre_centro": row["nombre_centro"],
            "tipo_evento": row["tipo_evento"],
            "mortalidad_declarada_json": row["mortalidad_asociada"],
            "mortalidad_def_A_total_periodo": mort_evento_total,
            "mortalidad_basal_esperada": round(mortalidad_basal_esperada, 1),
            "mortalidad_def_B_atribuible": round(mortalidad_atribuible, 1),
        })
    mortalidad_eventos = pd.DataFrame(mort_rows)

    return resumen_centro, mortalidad_eventos


# =====================================================================
# 4b. DESCOMPOSICION DEL SOBRECOSTO: FCR vs MORTALIDAD (componente D)
# =====================================================================

def descomponer_sobrecosto(resumen_centro, mortalidad_eventos, precio_mensual):
    precio_prom_global = precio_mensual["precio_prom_clp_kg"].mean()

    centro_top = resumen_centro.sort_values(
        "costo_por_kilo_clp", ascending=False).iloc[0]
    otros = resumen_centro[resumen_centro["centro_id"] != centro_top["centro_id"]]

    # Para cada definicion de FCR, calculamos cuanto alimento (y costo)
    # se habria usado en el centro top si hubiera tenido el FCR promedio
    # del resto de los centros, dado su crecimiento real.
    resultados = []
    for definicion, col_fcr in [("A_simple", "FCR_def_A_simple"),
                                 ("B_corregido", "FCR_def_B_corregido")]:
        fcr_baseline = otros[col_fcr].mean()
        fcr_real = centro_top[col_fcr]
        kg_base = centro_top["crecimiento_kg_total"] + (centro_top["mortalidad_kg_total"] if definicion == "B_corregido" else 0)
        alimento_contrafactual = fcr_baseline * kg_base
        costo_contrafactual = alimento_contrafactual * precio_prom_global
        sobrecosto_por_fcr = centro_top["costo_alimento_clp_total"] - costo_contrafactual

        # mortalidad atribuible al/los evento(s) sanitario(s) de este centro
        mort_centro = mortalidad_eventos[mortalidad_eventos["centro_id"] ==
                                          centro_top["centro_id"]]
        mortalidad_atribuible_total = mort_centro["mortalidad_def_B_atribuible"].sum()
        peso_prom = centro_top["peso_prom_kg"]
        kg_perdidos_por_mortalidad = mortalidad_atribuible_total * peso_prom
        # kilos que NO se cosecharon por la mortalidad atribuible al evento,
        # expresados como costo-oportunidad: el alimento ya invertido en esos
        # peces que murieron, valorizado al FCR baseline (lo que "debieron"
        # costar si hubiesen sobrevivido y se hubiesen cosechado)
        costo_mortalidad_alimento_perdido = (kg_perdidos_por_mortalidad *
                                              fcr_baseline * precio_prom_global)

        costo_total_real = centro_top["costo_alimento_clp_total"]
        costo_baseline_total = costo_contrafactual

        resultados.append({
            "definicion_FCR": definicion,
            "centro": centro_top["nombre_centro"],
            "FCR_centro_top": round(fcr_real, 3),
            "FCR_promedio_resto": round(fcr_baseline, 3),
            "costo_alimento_real_clp": round(costo_total_real, 0),
            "costo_alimento_si_FCR_baseline_clp": round(costo_baseline_total, 0),
            "sobrecosto_atribuible_a_FCR_clp": round(sobrecosto_por_fcr, 0),
            "mortalidad_atribuible_evento_n": round(mortalidad_atribuible_total, 0),
            "kg_biomasa_perdida_por_mortalidad": round(kg_perdidos_por_mortalidad, 0),
            "costo_alimento_perdido_en_mortalidad_clp": round(costo_mortalidad_alimento_perdido, 0),
            "pct_sobrecosto_explicado_por_FCR": round(
                100 * sobrecosto_por_fcr /
                (sobrecosto_por_fcr + costo_mortalidad_alimento_perdido), 1)
            if (sobrecosto_por_fcr + costo_mortalidad_alimento_perdido) > 0 else None,
        })

    return pd.DataFrame(resultados), centro_top["nombre_centro"]


# =====================================================================
# 5. COBERTURA DE DATOS
# =====================================================================

def calcular_cobertura(excl_op, total_op, detalle_excl_op, excl_centro_evt, total_evt,
                        excl_precio, total_costos, centros_zona_corregida, total_centros):
    filas = [
        {"fuente": "operacion_diaria", "excluidos": detalle_excl_op["incompleto_no_parseable"],
         "total": total_op,
         "pct_excluido": round(100 * detalle_excl_op["incompleto_no_parseable"] / total_op, 2),
         "motivo": "fecha o valores numericos no parseables tras limpieza"},
        {"fuente": "operacion_diaria", "excluidos": detalle_excl_op["fuera_de_2025"],
         "total": total_op,
         "pct_excluido": round(100 * detalle_excl_op["fuera_de_2025"] / total_op, 2),
         "motivo": "fecha fuera del periodo declarado (anio != 2025)"},
        {"fuente": "operacion_diaria",
         "excluidos": detalle_excl_op["mortalidad_diaria_imposible_mayor_5pct"],
         "total": total_op,
         "pct_excluido": round(100 * detalle_excl_op["mortalidad_diaria_imposible_mayor_5pct"]
                                / total_op, 2),
         "motivo": "mortalidad_n > 5% de la poblacion en un solo dia (error de captura, supuesto documentado)"},
        {"fuente": "origen_eventos_sanitarios.json", "excluidos": excl_centro_evt,
         "total": total_evt, "pct_excluido": round(100 * excl_centro_evt / total_evt, 2),
         "motivo": "centro_id 90-93 no existe en la tabla centros (dato de prueba)"},
        {"fuente": "origen_costos_alimento.csv", "excluidos": excl_precio,
         "total": total_costos, "pct_excluido": round(100 * excl_precio / total_costos, 2),
         "motivo": "precio_clp_kg nulo ('-') tras limpieza"},
        {"fuente": "origen_acuicultura.sqlite (centros)", "excluidos": 0,
         "total": total_centros, "pct_excluido": 0.0,
         "motivo": f"{centros_zona_corregida} centro(s) corregido(s), no excluido(s): "
                   "Centro Skyring con zona_id 7 inexistente -> asignado a Magallanes "
                   "(zona_id 3) segun su ubicacion geografica (supuesto documentado)"},
    ]
    return pd.DataFrame(filas)


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("1/5 Extrayendo datos crudos...")
    tablas, costos_raw, eventos_raw, dolar_raw = extraer()

    print("2/5 Limpiando...")
    tablas["centros"], centros_zona_corregida, total_centros = limpiar_centros(
        tablas["centros"], tablas["zonas"])
    op_diaria, excl_op, total_op, detalle_excl_op = limpiar_operacion_diaria(
        tablas["operacion_diaria"])
    cosechas = limpiar_cosechas(tablas["cosechas"])
    costos_raw_limpio, costos_validos, excl_precio = limpiar_costos_alimento(costos_raw)
    centros_validos = set(tablas["centros"]["centro_id"].tolist())
    eventos, excl_centro_evt, total_evt = limpiar_eventos(eventos_raw, centros_validos)
    dolar_diario, dolar_mensual = limpiar_dolar(dolar_raw)

    print("3/5 Integrando segun el modelo dimensional...")
    op, cos, ev, precio_mensual = construir_modelo(
        tablas, op_diaria, cosechas, costos_validos, eventos, dolar_mensual)

    print("4/5 Calculando metricas (FCR y mortalidad, 2 definiciones)...")
    resumen_centro, mortalidad_eventos = calcular_metricas(op, cos, ev)
    descomposicion, centro_top_nombre = descomponer_sobrecosto(
        resumen_centro, mortalidad_eventos, precio_mensual)
    descomposicion.to_csv(OUTPUT_DIR / "descomposicion_sobrecosto_fcr_vs_mortalidad.csv",
                           index=False)

    print("5/5 Calculando cobertura de datos y guardando resultados...")
    cobertura = calcular_cobertura(excl_op, total_op, detalle_excl_op, excl_centro_evt,
                                    total_evt, excl_precio, len(costos_raw_limpio),
                                    centros_zona_corregida, total_centros)

    # Guardar processed
    op.to_csv(PROCESSED_DIR / "hecho_operacion_diaria.csv", index=False)
    cos.to_csv(PROCESSED_DIR / "hecho_cosecha.csv", index=False)
    ev.to_csv(PROCESSED_DIR / "hecho_evento_sanitario.csv", index=False)
    costos_validos.to_csv(PROCESSED_DIR / "hecho_costo_alimento.csv", index=False)
    dolar_mensual.to_csv(PROCESSED_DIR / "dim_dolar_mensual.csv", index=False)

    # Guardar output (lo que va al informe)
    resumen_centro_out = resumen_centro.sort_values("costo_por_kilo_clp", ascending=False)
    resumen_centro_out.to_csv(OUTPUT_DIR / "resumen_centro_fcr_mortalidad.csv", index=False)
    mortalidad_eventos.to_csv(OUTPUT_DIR / "mortalidad_eventos_2_definiciones.csv", index=False)
    cobertura.to_csv(OUTPUT_DIR / "cobertura_datos.csv", index=False)

    print("\n=== CENTRO CON MAYOR COSTO POR KILO ===")
    print(resumen_centro_out[["nombre_centro", "costo_por_kilo_clp",
                               "FCR_def_A_simple", "FCR_def_B_corregido",
                               "mortalidad_n_total"]].to_string(index=False))

    print("\n=== MORTALIDAD POR EVENTO: DEFINICION A vs B ===")
    print(mortalidad_eventos[["nombre_centro", "tipo_evento",
                               "mortalidad_declarada_json",
                               "mortalidad_def_A_total_periodo",
                               "mortalidad_def_B_atribuible"]].to_string(index=False))

    print("\n=== COBERTURA DE DATOS ===")
    print(cobertura.to_string(index=False))

    print(f"\n=== DESCOMPOSICION DEL SOBRECOSTO: {centro_top_nombre} ===")
    print(descomposicion.to_string(index=False))

    print(f"\nListo. Resultados en: {OUTPUT_DIR}")
    return resumen_centro_out, mortalidad_eventos, cobertura, descomposicion


if __name__ == "__main__":
    main()
