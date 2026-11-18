# -*- coding: utf-8 -*-
"""Configuracion central del pipeline AquaFiordo (Grupo Salmonera N4).

Aqui se escribe UNA sola vez: el nombre de cada definicion, los parametros
y los supuestos del caso de negocio. El pipeline, los graficos y el
prototipo leen estos valores; nadie los redefine.
"""

ANIO = 2025
UMBRAL_MORTALIDAD_DIARIA = 0.05   # >5% de la poblacion en un dia = error de captura
                                  # (las 55 filas excluidas superan el 100%)

# ---------------------------------------------------------------------
# Definiciones (nombres que dicen que son; sin letras A/B)
# ---------------------------------------------------------------------
FCR_SIMPLE = "fcr_simple"
FCR_CORREGIDO = "fcr_corregido_mortalidad"
MORT_ATRIBUIBLE = "mortalidad_atribuible"
MORT_TOTAL = "mortalidad_total_periodo"

# La principal de cada par es la usada como cifra de referencia.
FCR_PRINCIPAL = FCR_SIMPLE
MORT_PRINCIPAL = MORT_ATRIBUIBLE

DEFINICIONES_FCR = {
    FCR_SIMPLE: "FCR simple: alimento / crecimiento de biomasa (solo peces vivos)",
    FCR_CORREGIDO: "FCR corregido por mortalidad: alimento / (crecimiento + biomasa perdida por mortalidad)",
}
DEFINICIONES_MORTALIDAD = {
    MORT_ATRIBUIBLE: "Mortalidad atribuible: muertes en la ventana del evento sobre la mortalidad basal esperada",
    MORT_TOTAL: "Mortalidad total del periodo: todas las muertes del centro en la ventana del evento (basal incluida)",
}

# ---------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------
API_DOLAR_URL = f"https://mindicador.cl/api/dolar/{ANIO}"
API_TIMEOUT_SEG = 10

# ---------------------------------------------------------------------
# Acuerdo de servicio (tabla principal: hecho_operacion_diaria)
# ---------------------------------------------------------------------
SLA_FRESCURA_DIAS = 30          # se actualiza al menos cada 30 dias (cierre mensual)
SLA_COMPLETITUD_MIN_PCT = 98.0  # % de registros esperados que llegan a la tabla de hechos
SLA_CALIDAD_MIN_PCT = 100.0     # % de pruebas bloqueantes que deben estar en verde
DUENO_DATO = "Grupo Salmonera N°4 (equipo de datos); dueño de negocio: Gerencia de Producción de AquaFiordo"
CERTIFICA_DEFINICIONES = "Ignacio Phillips"   # certifica las definiciones que aparecen en el pie del prototipo

# ---------------------------------------------------------------------
# Caso de negocio: costo de la auditoria de alimentacion (SUPUESTOS)
# Cada fila debe tener dueño y fecha en la bitacora de supuestos del informe.
# (concepto, cantidad, unidad, costo_unitario_clp)
# ---------------------------------------------------------------------
AUDITORIA_SUPUESTOS = [
    ("Especialista en nutricion acuicola (honorario externo)", 5, "dias", 600_000),
    ("Traslado y estadia a Cisnes (Aysen) - 2 personas", 2, "personas", 1_200_000),
    ("Tiempo interno (jefe de produccion + analista)", 10, "dias-persona", 150_000),
    ("Muestreos de peso y calibracion de alimentadores", 1, "global", 3_000_000),
]
AUDITORIA_CONTINGENCIA_PCT = 20.0
CAPTURAS_BRECHA = [0.25, 0.50, 1.00]   # % de la brecha de FCR que se logra cerrar

# Regla de decision (prueba acida): si el sobrecosto atribuible a FCR de un centro
# supera este umbral en el periodo, la gerencia ordena auditar su alimentacion.
UMBRAL_AUDITORIA_CLP = 250_000_000
