# -*- coding: utf-8 -*-
"""Prototipo AquaFiordo: ¿el sobrecosto de alimentacion del centro mas caro es
por FCR o por mortalidad? Lee SOLO los archivos que produce el pipeline
(output/*.csv, corrida_metadata.json); no recalcula ninguna formula.

Abrir:  streamlit run app.py   (desde esta carpeta)
Se actualiza solo cuando la cadena vuelve a correr (python src/pipeline.py).

Pantalla 1 "Respuesta": la pregunta, la cifra clave, su explicacion y la decision.
Pantalla 2 "Definiciones y detalle": para quien necesite discutir la definicion o el valor exacto.
"""
import json
import sys
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
sys.path.insert(0, str(BASE / "src"))
import config as C  # noqa: E402  (definiciones y supuestos escritos una sola vez)

st.set_page_config(page_title="AquaFiordo · Sobrecosto de alimentación", layout="wide")

ARCHIVOS = ["resumen_centro_fcr_mortalidad.csv", "descomposicion_sobrecosto_fcr_vs_mortalidad.csv",
            "mortalidad_eventos_2_definiciones.csv", "fcr_dentro_fuera_evento.csv",
            "caso_negocio_auditoria.csv", "auditoria_supuestos_costo.csv",
            "cobertura_datos.csv", "calidad_pruebas.csv", "corrida_metadata.json"]

faltan = [a for a in ARCHIVOS if not (OUT / a).exists()]
if faltan:
    st.error("Faltan resultados del pipeline. Corre primero `python src/pipeline.py` "
             f"(o `python run_all.py`). Faltan: {', '.join(faltan)}")
    st.stop()


def firma_archivos():
    """Cambia cuando el pipeline vuelve a correr -> invalida el cache."""
    return tuple((a, (OUT / a).stat().st_mtime_ns) for a in ARCHIVOS)


@st.cache_data
def cargar(firma):
    d = {a[:-4]: pd.read_csv(OUT / a) for a in ARCHIVOS if a.endswith(".csv")}
    with open(OUT / "corrida_metadata.json", encoding="utf-8") as f:
        meta = json.load(f)
    return d, meta


datos, meta = cargar(firma_archivos())
resumen = datos["resumen_centro_fcr_mortalidad"]
descomp = datos["descomposicion_sobrecosto_fcr_vs_mortalidad"]
mort_ev = datos["mortalidad_eventos_2_definiciones"]
fcr_df = datos["fcr_dentro_fuera_evento"]
caso = datos["caso_negocio_auditoria"]
supuestos = datos["auditoria_supuestos_costo"]
pruebas = datos["calidad_pruebas"]
cob = datos["cobertura_datos"]

CENTRO = descomp["centro"].iloc[0]
CENTRO_CORTO = CENTRO.replace("Centro ", "")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_corta(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def mm(x):
    """Millones de CLP con formato chileno."""
    return f"${x / 1e6:,.0f}".replace(",", ".") + " millones"


def num(x, dec=0):
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


PERIODO = f"{fecha_corta(meta['periodo_datos']['inicio'])} – {fecha_corta(meta['periodo_datos']['fin'])}"

# ---------- TITULO, PERIODO Y FILTROS ----------
st.title(f"¿El sobrecosto de alimentación de {CENTRO_CORTO} es por FCR o por mortalidad?")
st.caption(f"{CENTRO} · Período de los datos: {PERIODO} (todo lo disponible) · "
           "Audiencia: gerente general · Revisión mensual o al cierre de cada evento sanitario")

f1, f2 = st.columns(2)
def_fcr = f1.selectbox("Definición de FCR", list(C.DEFINICIONES_FCR),
                       index=list(C.DEFINICIONES_FCR).index(C.FCR_PRINCIPAL),
                       format_func=lambda k: C.DEFINICIONES_FCR[k])
def_mort = f2.selectbox("Definición de mortalidad (basal)", list(C.DEFINICIONES_MORTALIDAD),
                        index=list(C.DEFINICIONES_MORTALIDAD).index(C.MORT_PRINCIPAL),
                        format_func=lambda k: C.DEFINICIONES_MORTALIDAD[k])

fila = descomp[(descomp.definicion_fcr == def_fcr) & (descomp.definicion_mortalidad == def_mort)].iloc[0]
ref = descomp[descomp.es_referencia].iloc[0]
total = fila["sobrecosto_total_clp"]
minimo, maximo = descomp["sobrecosto_total_clp"].min(), descomp["sobrecosto_total_clp"].max()
brecha = fila["sobrecosto_fcr_clp"]
costo_aud = caso["costo_auditoria_clp"].iloc[0]

tab_resp, tab_det = st.tabs(["Respuesta", "Definiciones y detalle"])

# =====================================================================
# PANTALLA 1: RESPUESTA
# =====================================================================
with tab_resp:
    # ---------- CIFRA CLAVE CON SU COMPARACION ----------
    k1, k2, k3 = st.columns([2, 1, 1])
    k1.metric(f"Sobrecosto de {CENTRO_CORTO} vs. operar como el resto de centros", mm(total),
              delta=f"equivale al {100 * total / fila['costo_alimento_real_clp']:.0f}% de su costo de alimento ({mm(fila['costo_alimento_real_clp'])})",
              delta_color="off")
    k2.metric("Cifra de referencia", mm(ref["sobrecosto_total_clp"]),
              help=f"{C.FCR_PRINCIPAL} + {C.MORT_PRINCIPAL}")
    k3.metric("Rango (4 combinaciones)", f"{mm(minimo).replace(' millones', '')} a {mm(maximo)}",
              help="Mínimo y máximo según la definición de FCR y de mortalidad")

 # ---------- GRAFICO QUE EXPLICA LA CIFRA: reparto por causa (suma 100%) ----------
    st.subheader("¿De dónde viene? Reparto del sobrecosto por causa")
    reparto = pd.DataFrame({
        "Causa": ["Alimentación ineficiente (FCR)", "Evento sanitario (mortalidad atribuible)",
                  "Mortalidad basal (solo con mortalidad total del período)"],
        "Monto (millones CLP)": [fila["sobrecosto_fcr_clp"] / 1e6, fila["costo_mortalidad_evento_clp"] / 1e6,
                                 fila["costo_mortalidad_basal_clp"] / 1e6],
        "Porcentaje": [fila["pct_fcr"], fila["pct_evento"], fila["pct_basal"]],
    })
    nombres = ["Alimentación ineficiente (FCR)", "Evento sanitario", "Mortalidad basal"]
    reparto["Causa"] = [f"{n}: {m:,.0f} M ({p:.1f}%)".replace(",", ".")
                        for n, m, p in zip(nombres, reparto["Monto (millones CLP)"], reparto["Porcentaje"])]
    orden = list(reparto["Causa"])
    
    # Capa base
    base = alt.Chart(reparto).encode(
        y=alt.Y("Causa:N", sort=orden, title=None, 
                axis=alt.Axis(labelLimit=600, labelFontSize=13, labelOverlap=False)),
        x=alt.X("Monto (millones CLP):Q", title="Millones de CLP")
    )

    # Capa de barras con colores
    barras = base.mark_bar().encode(
        color=alt.Color("Causa:N", sort=orden, legend=None, 
                        scale=alt.Scale(range=["#D9694F", "#9A918A", "#C7B9AE"])),
        tooltip=["Causa", alt.Tooltip("Monto (millones CLP):Q", format=",.0f")]
    )

    # Capa de texto al final de la barra
    texto = base.mark_text(align='left', baseline='middle', dx=3, fontSize=12).encode(
        text=alt.Text("Monto (millones CLP):Q", format=",.0f")
    )

    # Combinar y aplicar altura fija
    graf = (barras + texto).properties(height=170)
    st.altair_chart(graf, use_container_width=True)
    
    st.caption("Evento sanitario = mortalidad atribuible al brote. Mortalidad basal = muertes normales de la ventana "
               "(solo cuenta si eliges «mortalidad total del período»).")
    fc = fcr_df[fcr_df["nombre_centro"] == CENTRO].iloc[0]
    st.caption(f"Las tres causas suman el 100%. El FCR malo no es culpa del brote: "
               f"{num(fc['fcr_fuera_evento'], 3)} fuera del brote vs. {num(fc['fcr_dentro_evento'], 3)} durante el brote "
               f"(resto de centros: {num(fila['fcr_promedio_resto'], 2)}).")

    # ---------- DECISION: cuanto vale y cuanto cuesta ----------
    st.subheader("¿Qué hago? Auditar la alimentación")
    d1, d2, d3 = st.columns(3)
    d1.metric("Vale (ahorro anual en margen)", mm(brecha),
              help="Si el FCR del centro llega al del resto de centros")
    d2.metric("Cuesta (auditoría)", mm(costo_aud), help="Supuestos en la pestaña «Definiciones y detalle»")
    d3.metric("Se paga cerrando", f"{num(100 * costo_aud / brecha, 1)}% de la brecha")
    regla = "SÍ cumple" if brecha > C.UMBRAL_AUDITORIA_CLP else "NO cumple"
    st.info(f"**Regla de decisión:** si el sobrecosto por FCR de un centro supera {mm(C.UMBRAL_AUDITORIA_CLP)}, "
            f"el gerente general ordena auditar su alimentación dentro de 15 días del cierre. "
            f"{CENTRO_CORTO} {regla} ({mm(brecha)}).")

    # ---------- CORTE POR DIMENSION PRINCIPAL ----------
    st.subheader("Costo de alimento por kilo producido, por centro")
    rc = resumen.assign(Destacado=resumen["nombre_centro"] == CENTRO)
    rc["Centro"] = [f"{n}: ${num(v)}" for n, v in zip(rc["nombre_centro"], rc["costo_por_kilo_clp"])]
    barras = alt.Chart(rc).mark_bar().encode(
        y=alt.Y("Centro:N", sort=alt.SortField("costo_por_kilo_clp", order="descending"), title=None,
                axis=alt.Axis(labelLimit=600, labelFontSize=13)),
        x=alt.X("costo_por_kilo_clp:Q", title="CLP por kg de producto cosechado"),
        color=alt.condition(alt.datum.Destacado, alt.value("#c53030"), alt.value("#90cdf4")),
        tooltip=["Centro", alt.Tooltip("costo_por_kilo_clp:Q", format=",.0f")])
    st.altair_chart(barras, width="stretch")

# =====================================================================
# PANTALLA 2: DEFINICIONES Y DETALLE
# =====================================================================
with tab_det:
    st.subheader("Definiciones")
    for k, v in {**C.DEFINICIONES_FCR, **C.DEFINICIONES_MORTALIDAD}.items():
        principal = " (principal)" if k in (C.FCR_PRINCIPAL, C.MORT_PRINCIPAL) else ""
        st.markdown(f"- **{k}**{principal}: {v}")

    st.subheader("Mortalidad: declarada vs. medida")
    fm = mort_ev[mort_ev["nombre_centro"] == CENTRO].iloc[0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Declarada por la gerencia", num(fm["mortalidad_declarada_json"]))
    m2.metric("Total del período del evento", num(fm[C.MORT_TOTAL]))
    m3.metric("Basal esperada en la ventana", num(fm["mortalidad_basal_esperada"]))
    m4.metric("Atribuible al evento", num(fm[C.MORT_ATRIBUIBLE]))
    st.caption("La gerencia declaró casi todas las muertes de la ventana como causadas por el brote. Descontando la "
               "mortalidad basal (la que habría ocurrido igual), el exceso atribuible es menor.")

    st.subheader("Valor de la auditoría según cuánta brecha se cierre")
    tab = caso[caso.definicion_fcr == def_fcr][["pct_brecha_capturada", "valor_anual_margen_clp",
                                                "costo_auditoria_clp", "beneficio_neto_clp", "beneficio_sobre_costo"]].copy()
    for col in ["valor_anual_margen_clp", "costo_auditoria_clp", "beneficio_neto_clp"]:
        tab[col] = (tab[col] / 1e6).round(1)
    tab.columns = ["% de la brecha que se cierra", "Valor anual en margen (M CLP)", "Costo auditoría (M CLP)",
                   "Beneficio neto (M CLP)", "Beneficio / costo (veces)"]
    st.dataframe(tab, hide_index=True, width="stretch")
    st.caption("Supuestos del equipo, a validar con AquaFiordo. El valor es ahorro directo de alimento (margen, no venta) "
               "y supone que el volumen del período se repite en el próximo ciclo.")
    with st.expander("Supuestos del costo de la auditoría"):
        st.dataframe(supuestos, hide_index=True, width="stretch")

    st.subheader("Detalle por centro")
    det = resumen[["nombre_centro", "costo_por_kilo_clp", C.FCR_SIMPLE, C.FCR_CORREGIDO, "mortalidad_n_total"]].copy()
    det.columns = ["Centro", "Costo por kg (CLP)", "FCR simple", "FCR corregido por mortalidad", "Mortalidad total (peces)"]
    st.dataframe(det.round(3), hide_index=True, width="stretch")

    with st.expander("Cobertura de datos y pruebas de calidad"):
        st.dataframe(cob[["fuente", "excluidos", "total", "pct_excluido", "motivo"]], hide_index=True, width="stretch")
        st.dataframe(pruebas[["prueba", "fuente", "que_verifica", "si_falla", "resultado", "detalle"]],
                     hide_index=True, width="stretch")

# =====================================================================
# PIE: fuente, fecha, dueño, calidad (visible en ambas pantallas)
# =====================================================================
filas_op = cob[cob.fuente == "operacion_diaria"]
sla = meta["sla"]
cert = C.CERTIFICA_DEFINICIONES or "pendiente de certificar (ver src/config.py)"
st.divider()
st.caption(
    f"Fuente: SQLite + CSV + JSON + API mindicador.cl (dólar: {meta['dolar_fuente'].replace('_', ' ')}) · "
    f"Última actualización: {meta['fecha_corrida_local']} · Dueño del dato: {C.DUENO_DATO} · "
    f"Definiciones certificadas por: {cert}")
st.caption(
    f"Cobertura: {int(filas_op['excluidos'].sum())} de {int(filas_op['total'].iloc[0])} registros de operación diaria "
    f"fuera ({100 * filas_op['excluidos'].sum() / filas_op['total'].iloc[0]:.2f}%) · "
    f"Calidad de la última corrida: {meta['pruebas_ok']}/{meta['pruebas_total']} pruebas OK, "
    f"{meta['pruebas_aviso']} aviso(s), {meta['pruebas_falla']} falla(s) · "
    f"Acuerdo de servicio: frescura ≤ {sla['frescura_objetivo_dias']} días, completitud {sla['completitud_pct']}% "
    f"(mín. {sla['completitud_min_pct']:.0f}%), calidad {sla['calidad_pct']}% de pruebas bloqueantes en verde.")
