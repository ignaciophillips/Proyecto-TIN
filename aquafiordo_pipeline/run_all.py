#!/usr/bin/env python3
"""Corre la cadena completa de cero, en cualquier sistema (Windows, Mac, Linux):
crea el ambiente virtual, instala dependencias, corre el pipeline (con sus pruebas
de calidad) y genera los graficos. Uso:  python run_all.py   (o: bash run_all.sh)
Con --app abre ademas el prototipo."""
import subprocess
import sys
import venv
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / ".venv"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*args):
    subprocess.run([str(PY), *args], cwd=BASE, check=True,
                   env={**__import__("os").environ, "MPLBACKEND": "Agg"})


if not VENV.exists():
    print("Creando ambiente virtual...")
    venv.create(VENV, with_pip=True)
print("Instalando dependencias...")
run("-m", "pip", "install", "--quiet", "--upgrade", "pip")
run("-m", "pip", "install", "--quiet", "-r", "requirements.txt")
run("src/pipeline.py")
run("src/charts.py")
print("\nListo. Tablas en output/, graficos en output/charts/.")
print("Para abrir el prototipo:  .venv/bin/streamlit run app.py   (Windows: .venv\\Scripts\\streamlit run app.py)")
if "--app" in sys.argv:
    run("-m", "streamlit", "run", "app.py")
