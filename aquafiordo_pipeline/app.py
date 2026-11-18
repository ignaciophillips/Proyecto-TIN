# app.py — Prototipo AquaFiordo: Centro Cisnes, FCR vs. mortalidad
import pandas as pd
import streamlit as st

st.set_page_config(page_title="AquaFiordo · Sobrecosto Centro Cisnes", layout="wide")

OUT = "output"

@st.cache_data
def cargar_datos():
    resumen = pd.read_csv(f"{OUT}/resumen_centro_fcr_mortalidad.csv")
    descomp = pd.read_csv(f"{OUT}/descomposicion_sobrecosto_fcr_vs_mortalidad.csv")
    mort_ev = pd.read_csv(f"{OUT}/mortalidad_eventos_2_definiciones.csv")
    fcr_df = pd.read_csv(f"{OUT}/fcr_dentro_fuera_evento.csv")
    return resumen, descomp, mort_ev, fcr_df

resumen, descomp, mort_ev, fcr_df = cargar_datos()

CENTRO = "Centro Cisnes"
NOMBRES_DEF = {"A_simple": "FCR simple (solo peces vivos)",
               "B_corregido": "FCR corregido por mortalidad"}

# ---------- TÍTULO Y PREGUNTA ----------
st.title("¿El sobrecosto de alimentación de Cisnes es por FCR o por mortalidad?")
st.caption("Centro Cisnes · Año 2025 · Respuesta a la Pregunta 2 de la gerencia")

# ---------- FILTRO: definición seleccionable ----------
col_filtro, _ = st.columns([1, 2])
with col_filtro:
    definicion = st.selectbox(
        "Definición de FCR (selecciona la alternativa)",
        options=list(NOMBRES_DEF.keys()),
        format_func=lambda k: NOMBRES_DEF[k],
    )

fila = descomp[descomp["definicion_FCR"] == definicion].iloc[0]
sobrecosto_fcr = fila["sobrecosto_atribuible_a_FCR_clp"]
sobrecosto_mort = fila["costo_alimento_perdido_en_mortalidad_clp"]
total = sobrecosto_fcr + sobrecosto_mort
pct_fcr = fila["pct_sobrecosto_explicado_por_FCR"]

otra_def = "B_corregido" if definicion == "A_simple" else "A_simple"
fila_otra = descomp[descomp["definicion_FCR"] == otra_def].iloc[0]
total_otra = fila_otra["sobrecosto_atribuible_a_FCR_clp"] + fila_otra["costo_alimento_perdido_en_mortalidad_clp"]

# ---------- CIFRA CLAVE ----------
st.header(f"${total/1e6:,.0f} millones de sobrecosto en 2025".replace(",", "."))
def monto_mm(valor_clp):
    """Formatea millones en estilo chileno, sin tocar el resto del texto."""
    return f"{valor_clp/1e6:,.0f}".replace(",", ".")

...

st.markdown(
    f"Con **{NOMBRES_DEF[definicion]}**. Con la definición alternativa "
    f"(*{NOMBRES_DEF[otra_def]}*), el total sería **${monto_mm(total_otra)} millones** "
    f"— el rango real es **${monto_mm(min(total, total_otra))}–{monto_mm(max(total, total_otra))} millones**, "
    f"no un número único."
)

# ---------- GRÁFICO: reparto que suma ----------
st.subheader("Reparto del sobrecosto por causa")
reparto = pd.DataFrame({
    "Causa": ["FCR (alimentación ineficiente)", "Mortalidad (brote SRS)"],
    "Monto (CLP)": [sobrecosto_fcr, sobrecosto_mort],
})
st.bar_chart(reparto.set_index("Causa"))
st.caption(f"FCR explica el {pct_fcr:.1f}% del sobrecosto; mortalidad el {100-pct_fcr:.1f}%. Suman el 100% del total.")

# ---------- EVIDENCIA: no es culpa del brote ----------
st.subheader("¿El FCR malo lo causó el brote?")
fcr_cisnes = fcr_df[fcr_df["nombre_centro"] == CENTRO].iloc[0]
c1, c2 = st.columns(2)
c1.metric("FCR fuera del brote", f"{fcr_cisnes['FCR_fuera_evento']:.3f}")
c2.metric("FCR durante el brote", f"{fcr_cisnes['FCR_dentro_evento']:.3f}")
st.caption("Son prácticamente iguales: el FCR malo es un problema estructural del centro, no una consecuencia del SRS.")

# ---------- CORTE POR DIMENSIÓN PRINCIPAL ----------
st.subheader("Costo por kilo producido, por centro")
st.bar_chart(resumen.set_index("nombre_centro")["costo_por_kilo_clp"])

# ---------- BRECHA DE MORTALIDAD ----------
st.subheader("Mortalidad: declarada vs. atribuible al brote")
fila_mort = mort_ev[mort_ev["nombre_centro"] == CENTRO].iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("Declarada por la gerencia", f"{fila_mort['mortalidad_declarada_json']:,.0f}".replace(",", "."))
c2.metric("Total del período", f"{fila_mort['mortalidad_def_A_total_periodo']:,.0f}".replace(",", "."))
c3.metric("Atribuible al brote (usada)", f"{fila_mort['mortalidad_def_B_atribuible']:,.0f}".replace(",", "."))
st.caption(
    "La gerencia declaró casi todas las muertes del período como causadas por el brote. "
    "Nosotros descontamos la mortalidad basal (la que habría ocurrido igual sin brote), "
    "por eso la cifra atribuible es menor."
)

# ---------- DETALLE EN TABLA ----------
st.subheader("Detalle por centro")
st.dataframe(resumen[["nombre_centro", "costo_por_kilo_clp", "FCR_def_A_simple",
                       "FCR_def_B_corregido", "mortalidad_n_total"]])

# ---------- PIE ----------
st.caption(
    "Fuente: pipeline AquaFiordo (SQLite + CSV + JSON + API mindicador.cl) · "
    "Última actualización: corrida local del equipo · Dueño del dato: Grupo Salmonera N°4"
)