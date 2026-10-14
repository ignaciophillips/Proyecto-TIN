#!/usr/bin/env bash
# Corre toda la cadena de cero: limpieza + integracion + metricas + graficos.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
MPLBACKEND=Agg .venv/bin/python src/pipeline.py
MPLBACKEND=Agg .venv/bin/python src/charts.py
echo ""
echo "Listo. Revisa la carpeta output/ (tablas) y output/charts/ (graficos)."
