# -*- coding: utf-8 -*-
"""Pruebas de calidad automatizadas: corren en CADA ejecucion del pipeline,
despues de limpiar/integrar y antes de calcular la metrica.

Cada prueba declara: que verifica, que pasa si falla ('bloquea' = el
pipeline se detiene y no calcula; 'avisa' = sigue y queda registrado) y su
resultado en la ultima corrida (OK / AVISO / FALLA) en output/calidad_pruebas.csv.
"""
import pandas as pd

import config as C


def ejecutar_pruebas(ctx):
    op, cos, costos = ctx["op"], ctx["cos"], ctx["costos"]
    eventos, dolar_m = ctx["eventos"], ctx["dolar_mensual"]
    tablas = ctx["tablas"]
    filas = []

    def prueba(nombre, fuente, que_verifica, si_falla, ok, detalle):
        resultado = "OK" if ok else ("FALLA" if si_falla == "bloquea" else "AVISO")
        filas.append({"prueba": nombre, "fuente": fuente, "que_verifica": que_verifica,
                      "si_falla": si_falla, "resultado": resultado, "detalle": detalle})

    # ---------------- SQLite: operacion_diaria -> hecho_operacion_diaria ----------------
    n_dup = int(op.duplicated(["jaula_id", "fecha"]).sum())
    prueba("unicidad_clave_hecho_operacion", "sqlite.operacion_diaria",
           "La clave (jaula_id, fecha) del hecho no se repite", "bloquea",
           n_dup == 0, f"{n_dup} claves repetidas")

    huerf = {
        "centro_id": int((~op["centro_id"].isin(tablas["centros"]["centro_id"])).sum()),
        "jaula_id": int((~op["jaula_id"].isin(tablas["jaulas"]["jaula_id"])).sum()),
        "lote_id": int((~op["lote_id"].isin(tablas["lotes"]["lote_id"])).sum()),
    }
    prueba("llaves_sin_huerfanos_operacion", "sqlite.operacion_diaria",
           "centro, jaula y lote del hecho existen en sus dimensiones", "bloquea",
           sum(huerf.values()) == 0, f"huerfanos: {huerf}")

    fuera = int(((op["fecha"].dt.year != C.ANIO)).sum())
    prueba("fechas_dentro_del_periodo", "sqlite.operacion_diaria",
           f"Todas las fechas del hecho caen en {C.ANIO}", "bloquea", fuera == 0,
           f"{fuera} filas fuera del periodo")

    malos = int(((op["alimento_kg"] <= 0) | (op["biomasa_kg"] <= 0) |
                 (op["crecimiento_kg"] < 0) | (op["mortalidad_n"] < 0)).sum())
    prueba("rangos_validos_operacion", "sqlite.operacion_diaria",
           "alimento y biomasa > 0; crecimiento y mortalidad >= 0", "bloquea",
           malos == 0, f"{malos} filas fuera de rango")

    tasa_max = float((op["mortalidad_n"] / op["poblacion"]).max())
    prueba("mortalidad_diaria_plausible", "sqlite.operacion_diaria",
           f"Mortalidad diaria <= {C.UMBRAL_MORTALIDAD_DIARIA:.0%} de la poblacion", "bloquea",
           tasa_max <= C.UMBRAL_MORTALIDAD_DIARIA, f"maximo observado {tasa_max:.2%}")

    sin_precio = int(op["costo_alimento_clp"].isna().sum())
    prueba("costo_alimento_calculado", "sqlite + csv",
           "Toda fila del hecho tiene precio mensual de alimento (el costo no queda nulo)",
           "bloquea", sin_precio == 0, f"{sin_precio} filas sin costo")

    completitud = 100 * len(op) / (ctx["total_op"] - ctx["det_op"]["duplicados_exactos_eliminados"])
    prueba("completitud_operacion", "sqlite.operacion_diaria",
           f"Llega al menos {C.SLA_COMPLETITUD_MIN_PCT:.0f}% de los registros esperados", "avisa",
           completitud >= C.SLA_COMPLETITUD_MIN_PCT, f"{completitud:.2f}% de los registros llegan")

    # ---------------- SQLite: cosechas -> hecho_cosecha ----------------
    d = int(cos["cosecha_id"].duplicated().sum())
    prueba("unicidad_clave_hecho_cosecha", "sqlite.cosechas",
           "cosecha_id no se repite", "bloquea", d == 0, f"{d} claves repetidas")

    h = {"centro_id": int((~cos["centro_id"].isin(tablas["centros"]["centro_id"])).sum()),
         "lote_id": int((~cos["lote_id"].isin(tablas["lotes"]["lote_id"])).sum())}
    prueba("llaves_sin_huerfanos_cosecha", "sqlite.cosechas",
           "centro y lote de la cosecha existen en sus dimensiones", "bloquea",
           sum(h.values()) == 0, f"huerfanos: {h}")

    mal = int(((cos["kilos_producto"] <= 0) | (cos["kilos_producto"] > cos["kilos_vivos"]) |
               cos[["kilos_vivos", "kilos_producto"]].isna().any(axis=1)).sum())
    prueba("rangos_validos_cosecha", "sqlite.cosechas",
           "0 < kilos_producto <= kilos_vivos (denominador del costo por kilo)", "bloquea",
           mal == 0, f"{mal} cosechas fuera de rango")

    fc = int((cos["fecha"].dt.year != C.ANIO).sum() + cos["fecha"].isna().sum())
    prueba("fechas_cosecha_en_periodo", "sqlite.cosechas",
           f"Fechas de cosecha validas y dentro de {C.ANIO}", "bloquea", fc == 0,
           f"{fc} fechas invalidas o fuera del periodo")

    sin_cos = sorted(set(op["centro_id"]) - set(cos["centro_id"]))
    prueba("cada_centro_tiene_cosechas", "sqlite.cosechas",
           "Todo centro con operacion tiene cosechas (si no, el costo por kilo es nulo)",
           "bloquea", not sin_cos, f"centros sin cosechas: {sin_cos}")

    # ---------------- CSV: costos de alimento ----------------
    pmin, pmax = float(costos["precio_clp_kg"].min()), float(costos["precio_clp_kg"].max())
    prueba("rango_precio_alimento", "csv.origen_costos_alimento",
           "Precio por kg > 0 y razonable (500-3.000 CLP)", "bloquea",
           pmin > 500 and pmax < 3000, f"min {pmin:,.0f} / max {pmax:,.0f}")

    meses = costos["mes"].nunique()
    prueba("cobertura_meses_precio", "csv.origen_costos_alimento",
           "Hay precio de alimento para los 12 meses", "bloquea", meses == 12,
           f"{meses} meses con precio")

    tipos = sorted(costos["tipo_alimento_norm"].dropna().unique())
    prueba("tipos_alimento_normalizados", "csv.origen_costos_alimento",
           "Las variantes de texto quedan en 3 codigos (ENG-100, ENG-200, PIG)", "avisa",
           set(tipos) == {"ENG-100", "ENG-200", "PIG"}, f"codigos: {tipos}")

    # ---------------- JSON: eventos sanitarios ----------------
    orden = int((eventos["fecha_fin"] < eventos["fecha_inicio"]).sum())
    fuera_ev = int(((eventos["fecha_inicio"].dt.year != C.ANIO) | (eventos["fecha_fin"].dt.year != C.ANIO)).sum())
    prueba("fechas_eventos_validas", "json.origen_eventos_sanitarios",
           "fecha_fin >= fecha_inicio y ambas dentro del periodo", "bloquea",
           orden == 0 and fuera_ev == 0, f"{orden} con fin<inicio, {fuera_ev} fuera del periodo")

    h = int((~eventos["centro_id"].isin(tablas["centros"]["centro_id"])).sum())
    prueba("eventos_con_centro_valido", "json.origen_eventos_sanitarios",
           "Todo evento retenido apunta a un centro existente (los 90-93 se excluyen en la limpieza)",
           "bloquea", h == 0, f"{h} eventos huerfanos")

    nm = int((eventos["mortalidad_asociada"] <= 0).sum())
    prueba("mortalidad_declarada_positiva", "json.origen_eventos_sanitarios",
           "mortalidad_asociada > 0", "avisa", nm == 0, f"{nm} eventos con mortalidad <= 0")

    # ---------------- API del dolar ----------------
    est = ctx["dolar_estado"]
    prueba("api_dolar_disponible", "api.mindicador.cl",
           "La API responde en esta corrida (si no, se usa el respaldo local y se avisa)",
           "avisa", est["fuente"] == "api", f"fuente usada: {est['fuente']} ({est['detalle']})")

    prueba("dolar_valido", "api.mindicador.cl (o respaldo)",
           "Dolar mensual > 0 y con los 12 meses del periodo", "bloquea",
           bool((dolar_m["dolar_obs_promedio_mes"] > 0).all()) and len(dolar_m) == 12,
           f"{len(dolar_m)} meses")

    out = pd.DataFrame(filas)
    out.insert(0, "fecha_ejecucion", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
    return out
