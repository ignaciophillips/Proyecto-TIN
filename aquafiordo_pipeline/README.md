# Pipeline AquaFiordo — Grupo Salmonera N°4

Cadena de datos ejecutable para la Entrega 1 (componente B). Responde la
**Pregunta 2**: en el centro con más costo, ¿la causa es la mortalidad de un
evento sanitario o un FCR peor, o ambas?

## Cómo instalar y correr

Requiere Python 3.9+ y conexión a internet solo si se quiere volver a
descargar el dólar observado (ya viene guardado en `data/raw/dolar_2025.json`,
así que no es necesario).

```bash
cd aquafiordo_pipeline
bash run_all.sh
```

Esto instala las dependencias (`pandas`, `numpy`, `matplotlib`), corre el
pipeline de limpieza e integración, calcula las métricas y genera los 5
gráficos. Demora menos de 1 minuto en un computador normal.

Si prefieres correr los pasos por separado:

```bash
pip install -r requirements.txt
python3 src/pipeline.py   # limpieza, integración, métricas -> output/*.csv
python3 src/charts.py     # gráficos -> output/charts/*.png
```

## Qué vas a ver al final

- `output/resumen_centro_fcr_mortalidad.csv`: costo por kilo, FCR (2
  definiciones) y mortalidad total por los 7 centros.
- `output/mortalidad_eventos_2_definiciones.csv`: mortalidad declarada por la
  gerencia vs. medida (total del período y atribuible/exceso sobre la
  basal), por evento sanitario.
- `output/descomposicion_sobrecosto_fcr_vs_mortalidad.csv`: cuánto del
  sobrecosto del centro más caro (Centro Cisnes) se explica por FCR y
  cuánto por mortalidad, bajo las dos definiciones de FCR.
- `output/cobertura_datos.csv`: % de registros excluidos del análisis, por
  fuente y motivo.
- `output/charts/*.png`: las 5 visualizaciones.

## Fuentes que lee

1. `data/raw/origen_acuicultura.sqlite` (tablas: centros, zonas, jaulas,
   lotes, especies, operacion_diaria, cosechas)
2. `data/raw/origen_costos_alimento.csv`
3. `data/raw/origen_eventos_sanitarios.json`
4. `data/raw/dolar_2025.json` (snapshot de `mindicador.cl/api/dolar/2025`,
   guardado localmente para que el pipeline corra sin depender de la API
   en el momento de la entrega)

## Decisiones de definición (ver ficha de la métrica en el informe)

- **FCR, denominador (2 definiciones)**: (A) simple = alimento total /
  crecimiento registrado; (B) corregido = alimento total / (crecimiento +
  biomasa perdida por mortalidad), porque los peces que murieron también
  comieron antes de morir.
- **Mortalidad basal vs. atribuible (2 definiciones)**: (A) toda la
  mortalidad del centro durante las fechas del evento; (B) solo el exceso
  sobre la mortalidad basal (promedio diario del centro fuera de eventos).

## Supuestos de limpieza (ver bitácora completa en el informe)

- Se excluyen 4 eventos sanitarios con `centro_id` 90-93 (no existen en la
  tabla `centros`; se asumen registros de prueba).
- Se excluyen 69 filas de `operacion_diaria` fechadas en 2026 (fuera del
  período 2025 que pide la gerencia).
- Se excluyen 55 filas de `operacion_diaria` donde la mortalidad diaria
  supera el 5% de la población de la jaula en un solo día (error de
  captura: implicaría que la jaula casi se vacía en un día, lo cual no se
  refleja en la población del día siguiente).
- `operacion_diaria` no trae `tipo_alimento`, así que el costo de alimento
  por jaula se estima con el precio promedio mensual de todos los tipos
  (ver nota en el DDL del modelo dimensional, sección 4a).
