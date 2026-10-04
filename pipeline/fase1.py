"""Fase 1: métricas reales por sector y ciudad y evaluación de los criterios de descarte.

Encadena: constituciones clasificadas -> filtro de ruido -> muestra estratificada -> Google Places -> informe.
Escribe research/BACKTEST.md y research/backtest/*.csv.

Etiquetas del informe:
- MEDIDO: contado directamente sobre los datos (BORME o respuesta de Places).
- MEDIDO (muestra): proporción medida en una muestra aleatoria, con su intervalo de confianza al 95 % (Wilson).
- ESTIMADO: combinación de medidas (p. ej. constituciones/mes × % localizable).
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .common import ensure, md_table, norm

log = logging.getLogger(__name__)

NO_OBJETIVO = {"ruido", "otros", "generico", "sin_clasificar"}
CIUDADES = {("28", "MADRID"): "MADRID", ("08", "BARCELONA"): "BARCELONA"}
MIN_N = 15  # por debajo, la proporción se marca como muestra insuficiente

CRITERIOS = {
    "localizable_min": 0.30,     # < 30 % de sociedades con local real -> sin señal
    "aperturas_mes_min": 20,     # < 20 aperturas reales/mes por sector y ciudad -> sin volumen
    "lag_mediana_min_dias": 21,  # mediana BORME -> apertura < 3 semanas -> tarde para el capex
}


def ciudad(row) -> str:
    cod = str(row.get("cod_provincia") or "").zfill(2)
    return CIUDADES.get((cod, norm(row.get("municipio"))), f"RESTO_{row.get('provincia') or cod}")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def preparar(const: pd.DataFrame) -> pd.DataFrame:
    c = const.copy()
    c["ciudad"] = c.apply(ciudad, axis=1)
    c["fecha_publicacion"] = pd.to_datetime(c["fecha_publicacion"], errors="coerce")
    c["comienzo_operaciones"] = pd.to_datetime(c["comienzo_operaciones"], errors="coerce")
    c["mes"] = c["fecha_publicacion"].dt.to_period("M").astype(str)
    c["objetivo"] = ~c["sector"].isin(NO_OBJETIVO)
    return c


def muestra(c: pd.DataFrame, por_celda: int, ciudades=("MADRID", "BARCELONA"), sectores=None,
            seed: int = 7) -> pd.DataFrame:
    """Muestra aleatoria estratificada de aperturas nuevas por sector × ciudad (tope `por_celda` por celda)."""
    base = c[c["objetivo"] & (c["ruido_tipo"] == "apertura_nueva") & c["ciudad"].isin(ciudades)]
    if sectores:
        base = base[base["sector"].isin(sectores)]
    partes = [g.sample(min(len(g), por_celda), random_state=seed) for _, g in base.groupby(["sector", "ciudad"])]
    return pd.concat(partes) if partes else base.head(0)


def _pct(x) -> str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.1f} %"


def tablas(c: pd.DataFrame, pl: pd.DataFrame | None, ciudades=("MADRID", "BARCELONA")) -> dict[str, pd.DataFrame]:
    cc = c[c["ciudad"].isin(ciudades)]
    n_meses = max(1, cc["mes"].nunique())
    T: dict[str, pd.DataFrame] = {}

    # 1. Volumen mensual (MEDIDO)
    vol = (cc.groupby(["ciudad", "sector", "mes"])
             .agg(constituciones=("denominacion", "size"),
                  aperturas_nuevas=("ruido_tipo", lambda s: int((s == "apertura_nueva").sum())))
             .reset_index())
    T["volumen_mensual"] = vol
    res = (cc.groupby(["ciudad", "sector"])
             .agg(constituciones=("denominacion", "size"),
                  aperturas_nuevas=("ruido_tipo", lambda s: int((s == "apertura_nueva").sum())),
                  expansion=("ruido_tipo", lambda s: int((s == "expansion_mismo_sector").sum())),
                  filial_grupo=("ruido_tipo", lambda s: int((s == "filial_de_grupo").sum())),
                  holding=("ruido_tipo", lambda s: int((s == "holding_patrimonial").sum())),
                  capital_mediano=("capital", "median"))
             .reset_index())
    res["meses"] = n_meses
    res["constituciones_mes"] = res["constituciones"] / n_meses
    res["aperturas_nuevas_mes"] = res["aperturas_nuevas"] / n_meses
    res["pct_reestructuracion"] = (res["expansion"] + res["filial_grupo"]) / res["constituciones"]
    T["resumen_sector"] = res

    # 2. Genéricos y ruido por ciudad (MEDIDO)
    g = (cc.groupby("ciudad")
           .agg(constituciones=("denominacion", "size"),
                genericos=("sector", lambda s: int((s == "generico").sum())),
                sin_clasificar=("sector", lambda s: int((s == "sin_clasificar").sum())),
                holding_patrimonial=("ruido_tipo", lambda s: int((s == "holding_patrimonial").sum())),
                expansion=("ruido_tipo", lambda s: int((s == "expansion_mismo_sector").sum())),
                filial_grupo=("ruido_tipo", lambda s: int((s == "filial_de_grupo").sum())))
           .reset_index())
    for k in ("genericos", "sin_clasificar", "holding_patrimonial", "expansion", "filial_grupo"):
        g[f"pct_{k}"] = g[k] / g["constituciones"]
    T["calidad_ciudad"] = g

    # 3. Localizable y desfase (MEDIDO en muestra)
    if pl is not None and len(pl):
        m = pl.merge(cc[["empresa_key", "ciudad", "sector", "fecha_publicacion", "comienzo_operaciones"]],
                     on="empresa_key", how="left")
        m["primera_resena"] = pd.to_datetime(m["primera_resena"], errors="coerce")
        m["lag_borme_dias"] = (m["primera_resena"] - m["fecha_publicacion"]).dt.days
        m["lag_escritura_dias"] = (m["primera_resena"] - m["comienzo_operaciones"]).dt.days
        T["places_detalle"] = m
        filas = []
        for (ci, se), d in m.groupby(["ciudad", "sector"]):
            n = len(d)
            k = int(d["localizable"].fillna(False).astype(bool).sum())
            lo, hi = wilson(k, n)
            ex = d[d["localizable"].fillna(False).astype(bool) & d["fecha_apertura_exacta"].fillna(False).astype(bool)
                   & d["lag_borme_dias"].notna()]
            todos = d[d["localizable"].fillna(False).astype(bool) & d["lag_borme_dias"].notna()]
            q = ex["lag_borme_dias"].quantile([.25, .5, .75]) if len(ex) else pd.Series([np.nan] * 3, index=[.25, .5, .75])
            filas.append({
                "ciudad": ci, "sector": se, "n_muestra": n, "n_localizable": k,
                "pct_localizable": k / n if n else np.nan, "ic95_inf": lo, "ic95_sup": hi,
                "pct_confianza_alta": float((d["confianza"] == "alta").mean()) if n else np.nan,
                "pct_negocio_previo": float(d["negocio_previo"].fillna(False).astype(bool).mean()) if n else np.nan,
                "pct_cerrado": float(d["business_status"].isin(["CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"]).mean()) if n else np.nan,
                "n_fecha_exacta": len(ex),
                "lag_p25_dias": q[.25], "lag_mediana_dias": q[.5], "lag_p75_dias": q[.75],
                "pct_abierto_antes_borme": float((ex["lag_borme_dias"] < 0).mean()) if len(ex) else np.nan,
                "lag_mediana_escritura_dias": ex["lag_escritura_dias"].median() if len(ex) else np.nan,
                "lag_mediana_cota_dias": todos["lag_borme_dias"].median() if len(todos) else np.nan,
            })
        T["localizable_desfase"] = pd.DataFrame(filas)
    return T


def criterios(T: dict[str, pd.DataFrame]) -> pd.DataFrame:
    res = T["resumen_sector"]
    ld = T.get("localizable_desfase", pd.DataFrame(columns=["ciudad", "sector"]))
    m = res.merge(ld, on=["ciudad", "sector"], how="left")
    out = []
    for r in m.to_dict("records"):
        n = r.get("n_muestra") or 0
        loc = r.get("pct_localizable")
        ab_mes = r["aperturas_nuevas_mes"] * loc if loc is not None and not pd.isna(loc) else np.nan
        lag = r.get("lag_mediana_dias")
        nex = r.get("n_fecha_exacta") or 0
        c1 = "SIN DATOS" if n < MIN_N else ("DESCARTA" if loc < CRITERIOS["localizable_min"] else "PASA")
        c2 = "SIN DATOS" if n < MIN_N else ("DESCARTA" if ab_mes < CRITERIOS["aperturas_mes_min"] else "PASA")
        c3 = ("SIN DATOS" if nex < 10 else
              ("SOLO RECURRENTES" if lag < CRITERIOS["lag_mediana_min_dias"] else "PASA"))
        if "DESCARTA" in (c1, c2):
            ver = "DESCARTAR"
        elif "SIN DATOS" in (c1, c2):
            ver = "SIN DATOS SUFICIENTES"
        elif c3 == "SOLO RECURRENTES":
            ver = "SEGUIR (solo servicios recurrentes)"
        else:
            ver = "SEGUIR"
        out.append({"ciudad": r["ciudad"], "sector": r["sector"],
                    "constituciones_mes": r["constituciones_mes"], "aperturas_nuevas_mes": r["aperturas_nuevas_mes"],
                    "n_muestra": n, "pct_localizable": loc, "aperturas_reales_mes_est": ab_mes,
                    "lag_mediana_dias": lag, "n_fecha_exacta": nex,
                    "c1_localizable": c1, "c2_volumen": c2, "c3_desfase": c3, "veredicto": ver})
    return pd.DataFrame(out).sort_values(["ciudad", "aperturas_nuevas_mes"], ascending=[True, False])


def informe(T: dict[str, pd.DataFrame], crit: pd.DataFrame, gasto, meta: dict, research_dir: Path) -> Path:
    out_csv = ensure(Path(research_dir) / "backtest")
    for k, v in {**T, "criterios": crit}.items():
        v.to_csv(out_csv / f"{k}.csv", index=False)
    fmt = crit.copy()
    for col in ("pct_localizable",):
        fmt[col] = fmt[col].map(_pct)
    for col in ("constituciones_mes", "aperturas_nuevas_mes", "aperturas_reales_mes_est", "lag_mediana_dias"):
        fmt[col] = fmt[col].map(lambda x: "" if pd.isna(x) else f"{x:.1f}")
    cal = T["calidad_ciudad"].copy()
    for col in [c for c in cal.columns if c.startswith("pct_")]:
        cal[col] = cal[col].map(_pct)
    L = [
        "# BACKTEST: fase 1 con datos reales",
        "",
        f"*Generado automáticamente el {dt.date.today().isoformat()} por `python -m pipeline.cli fase1`.*",
        "",
        "## Parámetros",
        "",
        f"- **Periodo BORME**: {meta.get('desde')} a {meta.get('hasta')} ({meta.get('meses')} meses con datos). Provincias: {meta.get('provincias')}.",
        f"- **Constituciones parseadas**: {meta.get('n_const')}. **Clasificación**: {meta.get('clasif')}.",
        f"- **Google Places**: {meta.get('n_places')} sociedades consultadas (muestra aleatoria de hasta {meta.get('por_celda')} por sector y ciudad).",
        f"  - Llamadas: {getattr(gasto, 'llamadas_search', 0)} Text Search y {getattr(gasto, 'llamadas_details', 0)} Place Details.",
        f"  - **Coste: {getattr(gasto, 'usd', 0):.2f} USD** a precio de lista, sin descontar el tramo gratuito, así que es una cota superior. Tope: {getattr(gasto, 'presupuesto_usd', 0):.0f} USD.",
        "",
        "## Veredicto por criterio (sector × ciudad)",
        "",
        "Criterios de descarte:",
        "- **c1, señal**: menos del 30 % de las sociedades termina en un local real localizable.",
        "- **c2, volumen**: menos de 20 aperturas reales al mes.",
        "- **c3, desfase**: mediana BORME → apertura de menos de 21 días. En ese caso el lead solo sirve para servicios recurrentes.",
        "",
        "Etiquetas:",
        "- `constituciones_mes` y `aperturas_nuevas_mes`: MEDIDO.",
        "- `pct_localizable` y `lag_mediana_dias`: MEDIDO en la muestra.",
        "- `aperturas_reales_mes_est`: ESTIMADO (aperturas nuevas/mes × % localizable).",
        "- SIN DATOS: muestra de menos de 15 sociedades, o menos de 10 fechas de apertura exactas.",
        "",
        md_table(fmt),
        "",
        "## Calidad de la señal por ciudad (MEDIDO)",
        "",
        md_table(cal),
        "",
        "## Localizable y desfase (MEDIDO en la muestra)",
        "",
        "Cómo leer las columnas:",
        "- `lag_*`: días entre la publicación en el BORME y la reseña más antigua en Google. Solo cuenta los lugares cuya fecha es exacta (≤ 5 reseñas en total).",
        "- `lag_mediana_cota_dias`: incluye también los lugares con más reseñas, donde la fecha es una cota superior.",
        "- `pct_abierto_antes_borme`: % que ya tenía reseñas antes de salir en el BORME, es decir, lead tardío.",
        "",
        md_table(T["localizable_desfase"]) if "localizable_desfase" in T else "*(sin datos de Places)*",
        "",
        "## Limitaciones de la medida",
        "",
        "- **Reseña más antigua ≠ apertura.** La primera reseña llega días o semanas después de abrir, así que el desfase real BORME → apertura es algo MENOR que el medido. Solo se usan las fechas exactas (lugares con ≤ 5 reseñas), lo que sesga la muestra hacia negocios con poca actividad.",
        "- **Emparejamiento automático.** Las coincidencias de confianza media pueden ser falsos positivos, y los nombres comerciales muy distintos de la denominación pueden no encontrarse (falsos negativos). La 2.ª búsqueda por dirección y tipo mitiga este segundo problema.",
        "- **Expansión.** Solo se detecta dentro del periodo descargado, así que es una cota inferior.",
        "- **Autónomos.** No aparecen en el BORME. Este backtest mide el universo de sociedades, no todo el mercado.",
    ]
    p = Path(research_dir) / "BACKTEST.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p
