# Pipeline y prototipo AquaFiordo — Grupo Salmonera N°4 (Entrega 2)

Responde la **Pregunta 2**: en el centro con más costo, ¿la causa es la mortalidad de un
evento sanitario o un FCR peor, o ambas? ¿Se pueden separar? ¿Cuánto vale y cuánto cuesta actuar?

## Cómo instalar y correr (de cero)

Requiere Python 3.9+. Internet solo se usa para consultar la API del dólar (si no hay,
se usa el respaldo local y queda registrado).

```bash
cd aquafiordo_pipeline
python3 run_all.py        # Windows: python run_all.py   (también: bash run_all.sh)
```

Crea el ambiente virtual `.venv`, instala dependencias, corre el pipeline **con sus pruebas de
calidad** y genera los gráficos. Demora **menos de 1 minuto**. Si una prueba bloqueante falla, la
corrida se detiene (código de salida 1) y no calcula métricas.

Abrir el prototipo (después de correr la cadena):

```bash
.venv/bin/streamlit run app.py        # Windows: .venv\Scripts\streamlit run app.py
```

Se abre en el navegador (http://localhost:8501). **Se actualiza solo** cuando la cadena vuelve a
correr: basta recargar la página. Para forzar modo sin internet: `AQUAFIORDO_OFFLINE=1 python3 run_all.py`.

## Qué se espera ver al final

- `output/cifras_clave.csv`: **cada número citado en el informe** (FCR dentro/fuera del brote,
  costo por kg, sobrecostos, rango, auditoría…) con la función que lo calcula.
- `output/descomposicion_sobrecosto_fcr_vs_mortalidad.csv`: sobrecosto de Cisnes por causa, para las
  4 combinaciones (2 definiciones de FCR × 2 de mortalidad). La fila `es_referencia` es la cifra principal.
- `output/caso_negocio_auditoria.csv` y `auditoria_supuestos_costo.csv`: valor, costo, beneficio y
  punto de equilibrio de la auditoría de alimentación.
- `output/resumen_centro_fcr_mortalidad.csv`, `mortalidad_eventos_2_definiciones.csv`,
  `fcr_dentro_fuera_evento.csv`, `cobertura_datos.csv`.
- `output/calidad_pruebas.csv`: resultado de cada prueba en la última corrida.
- `output/corrida_metadata.json`: fecha de la corrida, estado de la API, resumen de pruebas y acuerdo de servicio.
- `output/charts/*.png`: 5 visualizaciones.

## Definiciones (una sola vez, en `src/config.py`)

| Nombre | Qué es |
|---|---|
| `fcr_simple` (principal) | alimento / crecimiento de biomasa (solo peces vivos) |
| `fcr_corregido_mortalidad` | alimento / (crecimiento + biomasa perdida por mortalidad) |
| `mortalidad_atribuible` (principal) | muertes de la ventana del evento sobre la mortalidad basal esperada |
| `mortalidad_total_periodo` | todas las muertes del centro en la ventana del evento (basal incluida) |

Sobrecosto = FCR + evento sanitario (mortalidad atribuible) + mortalidad basal (esta última solo
si se elige `mortalidad_total_periodo`). Siempre suma 100%.

## Arquitectura por capas

| Capa | Dónde | Qué hace |
|---|---|---|
| Orígenes | SQLite, CSV, JSON, API mindicador.cl | Fuentes del caso |
| Cruda | `data/raw/` | Copia sin tocar; la API se consulta en cada corrida y, si falla, se usa `dolar_2025.json` |
| Depurada | `src/pipeline.py` (limpieza) + `src/calidad.py` | Fechas/números/textos normalizados, duplicados y registros de prueba fuera, 20 pruebas de calidad |
| Modelo | `data/processed/hecho_*.csv` | Constelación de hechos (operación diaria, cosecha, evento sanitario, costo de alimento) según el DDL |
| Consumo | `output/` + `app.py` | Métricas, caso de negocio y prototipo; el prototipo solo lee `output/` |

Decisiones: **ETL** (se transforma en Python antes de cargar al modelo, porque las fuentes vienen sucias y el
modelo exige claves únicas); **carga completa** (el volumen es de ~14 mil filas y se recalcula entero en <1 min, lo
que evita duplicar o perder registros); **falla de la API** → respaldo local, aviso en consola, en
`calidad_pruebas.csv` y en el pie del prototipo.

## Linaje de la métrica principal (sobrecosto por FCR)

`operacion_diaria.alimento_kg`, `crecimiento_kg` (SQLite) → limpieza + sin duplicados → suma por centro →
`fcr_simple` (`calcular_metricas`) → FCR promedio del resto → `sobrecosto_fcr_clp` (`descomponer_sobrecosto`,
usa `costo_alimento_clp` = `alimento_kg` × precio mensual del CSV) → `descomposicion_sobrecosto_…csv` →
pantalla del prototipo ("Reparto por causa" y "¿Qué parte ataco y cuánto vale?").
`cosechas.kilos_producto` (SQLite, hecho_cosecha) → `costo_por_kilo_clp` → "Costo por kg por centro".

## Acuerdo de servicio (`hecho_operacion_diaria`)

Frescura: se actualiza al menos cada 30 días · Completitud: ≥ 98% de los registros esperados llega ·
Calidad: 100% de las pruebas bloqueantes en verde · Dueño: ver `DUENO_DATO` en `src/config.py`.
Los valores medidos en cada corrida quedan en `output/corrida_metadata.json`.

## Supuestos de limpieza (ver bitácora en el informe)

- Se excluyen 4 eventos con `centro_id` 90-93 (no existen en `centros`; datos de prueba).
- Se excluyen 6 cosechas con `lote_id` 77000-77005 (no existen en `lotes`; kilos incoherentes).
- Se excluyen 69 filas de `operacion_diaria` fechadas en 2026.
- Se excluyen 55 filas con mortalidad diaria > 5% de la población (todas superan el 100%: error de captura).
- Se eliminan 139 filas duplicadas de `operacion_diaria` (misma jaula-día con valores idénticos).
- `operacion_diaria` no trae `tipo_alimento`: el costo se estima con el precio mensual promedio de todos los tipos.
- La fila `TOTAL` y el encabezado repetido del CSV de costos no se cuentan como registros.
- Los supuestos del costo de la auditoría están en `src/config.py` (`AUDITORIA_SUPUESTOS`).
