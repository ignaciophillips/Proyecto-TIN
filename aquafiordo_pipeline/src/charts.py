#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera las 3-5 visualizaciones para el componente E del informe.
Requiere haber corrido pipeline.py antes (lee output/*.csv)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config as C

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

AZUL = "#2b6cb0"
AZUL_CLARO = "#90cdf4"
ROJO = "#c53030"
GRIS = "#a0aec0"
VERDE = "#2f855a"
FUENTE = "Fuente: origen_acuicultura.sqlite + origen_costos_alimento.csv (AquaFiordo, 2025)"

plt.rcParams.update({
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def chart_costo_por_kilo():
    df = pd.read_csv(OUTPUT_DIR / "resumen_centro_fcr_mortalidad.csv")
    df = df.sort_values("costo_por_kilo_clp", ascending=True)
    colores = [ROJO if c == "Centro Cisnes" else AZUL_CLARO for c in df["nombre_centro"]]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(df["nombre_centro"], df["costo_por_kilo_clp"], color=colores)
    ax.set_xlabel("Costo de alimento por kilo producido (CLP/kg)")
    ax.set_title("Costo por kilo de salmón producido, por centro (2025)",
                  fontsize=13, fontweight="bold")
    for i, v in enumerate(df["costo_por_kilo_clp"]):
        ax.text(v + 15, i, f"${v:,.0f}", va="center", fontsize=9)
    fig.text(0.02, -0.02, FUENTE, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "01_costo_por_kilo_centro.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_fcr_dos_definiciones():
    df = pd.read_csv(OUTPUT_DIR / "resumen_centro_fcr_mortalidad.csv")
    df = df.sort_values("fcr_simple", ascending=True)
    x = range(len(df))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.38
    colores_a = [ROJO if c == "Centro Cisnes" else AZUL for c in df["nombre_centro"]]
    colores_b = [ROJO if c == "Centro Cisnes" else AZUL_CLARO for c in df["nombre_centro"]]
    ax.barh([i + w / 2 for i in x], df["fcr_simple"], height=w,
            label="FCR simple (alimento / crecimiento)", color=colores_a)
    ax.barh([i - w / 2 for i in x], df["fcr_corregido_mortalidad"], height=w,
            label="FCR corregido por mortalidad", color=colores_b, alpha=0.85)
    ax.set_yticks(list(x))
    ax.set_yticklabels(df["nombre_centro"])
    ax.set_xlabel("FCR (kg alimento / kg pez ganado)")
    ax.set_title("FCR por centro bajo las dos definiciones (2025)",
                  fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    fig.text(0.02, -0.02, FUENTE, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "02_fcr_dos_definiciones.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_descomposicion():
    df = pd.read_csv(OUTPUT_DIR / "descomposicion_sobrecosto_fcr_vs_mortalidad.csv")
    df = df[df["definicion_mortalidad"] == C.MORT_PRINCIPAL].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    x = range(len(df))
    fcr_millones = df["sobrecosto_fcr_clp"] / 1e6
    mort_millones = df["costo_mortalidad_evento_clp"] / 1e6
    ax.bar(x, fcr_millones, label="Explicado por FCR peor", color=AZUL)
    ax.bar(x, mort_millones, bottom=fcr_millones,
           label="Explicado por mortalidad atribuible al evento SRS", color=ROJO)
    ax.set_xticks(list(x))
    ax.set_xticklabels(["FCR simple", "FCR corregido\npor mortalidad"])
    ax.set_ylabel("Sobrecosto vs. promedio del resto de centros (MM CLP)")
    ax.set_title("Centro Cisnes: ¿por qué es el más caro? FCR vs. mortalidad",
                 fontsize=12.5, fontweight="bold")
    for i in x:
        total = fcr_millones.iloc[i] + mort_millones.iloc[i]
        pct_fcr = df["pct_fcr"].iloc[i]
        ax.text(i, total + 15, f"{pct_fcr:.0f}% FCR / {100-pct_fcr:.0f}% mortalidad",
                ha="center", fontsize=9, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8.5, frameon=False)
    fig.text(0.02, -0.02, FUENTE, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "03_descomposicion_sobrecosto.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_mortalidad_eventos():
    df = pd.read_csv(OUTPUT_DIR / "mortalidad_eventos_2_definiciones.csv")
    df = df.sort_values("mortalidad_total_periodo", ascending=True)
    x = range(len(df))
    etiquetas = [f"{c}\n({t})" for c, t in zip(df["nombre_centro"], df["tipo_evento"])]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.25
    ax.barh([i + w for i in x], df["mortalidad_declarada_json"], height=w,
            label="Declarada (JSON gerencia)", color=GRIS)
    ax.barh([i for i in x], df["mortalidad_total_periodo"], height=w,
            label="Mortalidad total del período del evento", color=AZUL_CLARO)
    ax.barh([i - w for i in x], df["mortalidad_atribuible"], height=w,
            label="Mortalidad atribuible (exceso sobre la basal)", color=ROJO)
    ax.set_yticks(list(x))
    ax.set_yticklabels(etiquetas, fontsize=9)
    ax.set_xlabel("Peces muertos (n)")
    ax.set_title("Mortalidad por evento sanitario: declarada vs. medida (2025)",
                  fontsize=12.5, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    fig.text(0.02, -0.02,
              "Fuente: origen_eventos_sanitarios.json + operacion_diaria (AquaFiordo, 2025)",
              fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "04_mortalidad_declarada_vs_medida.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_cobertura():
    df = pd.read_csv(OUTPUT_DIR / "cobertura_datos.csv")
    agg = df.groupby("fuente", as_index=False)["pct_excluido"].sum()
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.barh(agg["fuente"], agg["pct_excluido"], color=VERDE)
    ax.set_xlabel("% de registros excluidos del análisis")
    ax.set_title("Cobertura de datos por fuente (2025)", fontsize=12.5, fontweight="bold")
    for i, v in enumerate(agg["pct_excluido"]):
        ax.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=9)
    fig.text(0.02, -0.03, FUENTE, fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "05_cobertura_datos.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    chart_costo_por_kilo()
    chart_fcr_dos_definiciones()
    chart_descomposicion()
    chart_mortalidad_eventos()
    chart_cobertura()
    print(f"5 graficos guardados en: {CHARTS_DIR}")
