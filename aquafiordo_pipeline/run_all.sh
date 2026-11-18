#!/usr/bin/env bash
# Corre toda la cadena de cero: limpieza + pruebas de calidad + metricas + graficos.
# Equivale a: python3 run_all.py   (que tambien funciona en Windows)
set -e
cd "$(dirname "$0")"
exec python3 run_all.py "$@"
