"""Agregados del BORME clasificado por sector x provincia x mes, y un informe markdown."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .common import ensure, md_table, norm

# --------------------------------------------------------------------------- tipo de domicilio

RE_LOCAL = re.compile(
    r"\b(?:BAJOS?|BJ|LOCAL(?:ES)?|PLANTA BAJA|PLANTA 0|PL\.? ?0|PB|NAVES?)\b|\bLOC\.|\bNAV\.")
RE_PISO = re.compile(
    r"(\d\s*[ºª°]|\b(PISO|PLANTA [1-9]\d?|PL\.? ?[1-9]\d?\b|OFICINA|OFIC?\.|OF\b|PUERTA ?\d|PTA\.? ?\d|"
    r"ESC(ALERA|\.)?\s?[A-Z0-9]\b|ENTREPLANTA|ENTLO|ATICO|DESPACHO|DPCHO|DCHA|IZDA|IZQ(UIERDA)?|DERECHA)\b)")


def tipo_domicilio(dom: str | None) -> str:
    """'local' (bajo/local/nave), 'piso_oficina' (º, piso, planta 1-9, oficina, puerta n...) o 'indeterminado'.

    Si aparecen ambos tipos de marca (p. ej. 'LOCAL 2 PLANTA 1' en un centro comercial) se da
    prioridad a 'local'.
    """
    d = norm(dom)
    if not d:
        return "indeterminado"
    d = re.sub(r"\([^)]*\)\s*\.?$", "", d)  # quita el municipio entre paréntesis
    if RE_LOCAL.search(d):
        return "local"
    if RE_PISO.search(d):
        return "piso_oficina"
    return "indeterminado"


# --------------------------------------------------------------------------- utilidades

PCTS = (10, 25, 50, 75, 90)


def _pcts(s: pd.Series, prefix: str) -> dict:
    s = pd.to_numeric(s, errors="coerce").dropna()
    out = {f"{prefix}_n": int(len(s))}
    for p in PCTS:
        out[f"{prefix}_p{p}"] = float(np.percentile(s, p)) if len(s) else np.nan
    return out


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"cod_provincia": str, "cnae": str, "codigo_postal": str})
    for c in ("fecha_publicacion", "comienzo_operaciones", "fecha_inscripcion"):
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mes"] = df["fecha_publicacion"].dt.strftime("%Y-%m")
    df["tipo_domicilio"] = [tipo_domicilio(x) if isinstance(x, str) else "indeterminado" for x in df["domicilio"]]
    df["lag_comienzo_pub_dias"] = (df["fecha_publicacion"] - df["comienzo_operaciones"]).dt.days
    df["lag_inscripcion_pub_dias"] = (df["fecha_publicacion"] - df["fecha_inscripcion"]).dt.days
    # Fechas absurdas (errores de OCR/parseo): fuera de [-30, 730] días se anulan.
    for c in ("lag_comienzo_pub_dias", "lag_inscripcion_pub_dias"):
        df.loc[(df[c] < -30) | (df[c] > 730), c] = np.nan
    df["es_ruido"] = df["sector"].eq("ruido")
    return df


# --------------------------------------------------------------------------- agregados


def actos_por_tipo(df: pd.DataFrame) -> pd.DataFrame:
    """nº de actos por sector x provincia x mes x tipo_acto."""
    x = df[["sector", "provincia", "mes", "tipos_acto"]].copy()
    x["tipo_acto"] = x["tipos_acto"].fillna("").str.split("|")
    x = x.explode("tipo_acto")
    x = x[x["tipo_acto"].ne("") & x["tipo_acto"].ne("datos_registrales")]
    return (x.groupby(["sector", "provincia", "mes", "tipo_acto"]).size().rename("n").reset_index()
            .sort_values(["provincia", "mes", "sector", "n"], ascending=[True, True, True, False]))


def _resumen_grupo(g: pd.DataFrame) -> dict:
    tipos = g["tipos_acto"].fillna("")
    const = g[tipos.str.contains(r"\bconstitucion\b")]
    con_dom = g[tipos.str.contains(r"\bconstitucion\b|\bcambio_domicilio\b")]
    cap = const["capital"].dropna()
    td = con_dom["tipo_domicilio"].value_counts()
    n_dom = len(con_dom)
    row = {
        "n_anuncios": len(g),
        "n_constitucion": int(tipos.str.contains(r"\bconstitucion\b").sum()),
        "n_cambio_domicilio": int(tipos.str.contains(r"\bcambio_domicilio\b").sum()),
        "n_cambio_objeto": int(tipos.str.contains(r"\bcambio_objeto\b|\bampliacion_objeto\b").sum()),
        "n_cambio_denominacion": int(tipos.str.contains(r"\bcambio_denominacion\b").sum()),
        "n_ampliacion_capital": int(tipos.str.contains(r"\bampliacion_capital\b").sum()),
        "n_extincion_disolucion": int(tipos.str.contains(r"\bextincion\b|\bdisolucion\b").sum()),
        "capital_medio": float(cap.mean()) if len(cap) else np.nan,
        "capital_mediano": float(cap.median()) if len(cap) else np.nan,
        "n_domicilios": n_dom,
        "pct_local": 100 * td.get("local", 0) / n_dom if n_dom else np.nan,
        "pct_piso_oficina": 100 * td.get("piso_oficina", 0) / n_dom if n_dom else np.nan,
        "pct_indeterminado": 100 * td.get("indeterminado", 0) / n_dom if n_dom else np.nan,
        "confianza_media": float(g["confianza"].mean()) if "confianza" in g else np.nan,
    }
    row.update(_pcts(const["lag_comienzo_pub_dias"], "lag_comienzo_pub"))
    row.update(_pcts(g["lag_inscripcion_pub_dias"], "lag_inscripcion_pub"))
    return row


def resumen(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for keys, g in df.groupby(by, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        rows.append({**dict(zip(by, keys)), **_resumen_grupo(g)})
    return pd.DataFrame(rows)


def ruido_por_provincia_mes(df: pd.DataFrame) -> pd.DataFrame:
    """% de ruido sobre constituciones y sobre todos los anuncios con objeto social."""
    con_obj = df[df["objeto_social"].notna()]
    g = con_obj.groupby(["provincia", "mes"])
    out = pd.DataFrame({"n_con_objeto": g.size(), "n_ruido": g["es_ruido"].sum(),
                        "n_sin_clasificar": g["sector"].apply(lambda s: s.eq("sin_clasificar").sum())}).reset_index()
    out["pct_ruido"] = 100 * out["n_ruido"] / out["n_con_objeto"]
    out["pct_sin_clasificar"] = 100 * out["n_sin_clasificar"] / out["n_con_objeto"]
    return out


# --------------------------------------------------------------------------- informe


def informe(df: pd.DataFrame, res_sector: pd.DataFrame, ruido: pd.DataFrame) -> str:
    fmin, fmax = df["fecha_publicacion"].min(), df["fecha_publicacion"].max()
    provs = ", ".join(sorted(df["provincia"].dropna().unique()))
    n_const = int(df["tipos_acto"].fillna("").str.contains(r"\bconstitucion\b").sum())
    con_obj = df[df["objeto_social"].notna()]
    pct_ruido = 100 * con_obj["es_ruido"].mean() if len(con_obj) else float("nan")
    parse_ok = 100 * df["parse_ok"].mean() if "parse_ok" in df and len(df) else float("nan")
    lag_all = _pcts(df.loc[df["tipos_acto"].fillna("").str.contains("constitucion"), "lag_comienzo_pub_dias"], "x")
    lag_ins = _pcts(df["lag_inscripcion_pub_dias"], "x")
    met = df["metodo"].value_counts(normalize=True).mul(100).round(1) if "metodo" in df else pd.Series(dtype=float)

    cols = ["sector", "n_constitucion", "n_cambio_domicilio", "n_cambio_objeto", "capital_mediano", "pct_local",
            "pct_piso_oficina", "lag_comienzo_pub_p10", "lag_comienzo_pub_p50", "lag_comienzo_pub_p90",
            "lag_inscripcion_pub_p50", "confianza_media"]
    tabla = res_sector.sort_values("n_constitucion", ascending=False)[[c for c in cols if c in res_sector]]

    def f(v):
        return "n/d" if v != v else f"{v:.0f}"

    return f"""# Informe BORME sección A: actos por sector

Fuente: BORME sección A ([datos abiertos del BOE](https://www.boe.es/datosabiertos/)), cálculo propio
con el pipeline `pipeline/`. Generado el {dt.date.today().isoformat()}.
Todas las cifras de este informe son **[DATO]** derivados del BORME, con los sesgos de parseo y
clasificación descritos al final.

## Cobertura
- Periodo de publicación: {fmin:%Y-%m-%d} a {fmax:%Y-%m-%d}
- Provincias: {provs}
- Anuncios parseados: {len(df)} ({parse_ok:.1f} % sin avisos de parseo)
- Constituciones: {n_const}
- Ruido (holding, patrimonial, inversión, consultoría genérica, online...): {pct_ruido:.1f} % de los anuncios con objeto social
- Método de clasificación: {", ".join(f"{k} {v} %" for k, v in met.items())}

## Retrasos de publicación (días)
| Retraso | n | p10 | p25 | mediana | p75 | p90 |
|---|---|---|---|---|---|---|
| Comienzo de operaciones -> publicación (constituciones) | {lag_all['x_n']} | {f(lag_all['x_p10'])} | {f(lag_all['x_p25'])} | {f(lag_all['x_p50'])} | {f(lag_all['x_p75'])} | {f(lag_all['x_p90'])} |
| Inscripción -> publicación (todos los anuncios) | {lag_ins['x_n']} | {f(lag_ins['x_p10'])} | {f(lag_ins['x_p25'])} | {f(lag_ins['x_p50'])} | {f(lag_ins['x_p75'])} | {f(lag_ins['x_p90'])} |

## Por sector (todo el periodo y todas las provincias)
`pct_local` = % de domicilios (constituciones y traslados) con marca de local a pie de calle o nave
(BAJO, LOCAL, PB, PLANTA BAJA, NAVE...); `pct_piso_oficina` = marca de piso u oficina (º, PISO,
PLANTA 1-9, OFICINA, PUERTA n...). El resto es indeterminado.

{md_table(tabla)}
## Ruido por provincia y mes
{md_table(ruido.sort_values(["provincia", "mes"]))}
## Limitaciones
- Solo sociedades mercantiles: los autónomos (empresarios individuales) no aparecen en el BORME.
- El domicilio social no siempre es el local de la actividad (muchas SL se domicilian en casa del socio
  o en la gestoría); `pct_local` es un indicador, no un censo de locales.
- "Comienzo de operaciones" es normalmente la fecha de la escritura, no la de apertura.
- La clasificación por reglas tiene errores en objetos sociales "cajón de sastre"; revisar `regla` y `confianza`.
- El texto de los PDF puede romperse por columnas y saltos de página; ver `parse_warnings`.
"""


def run(clasificado_csv: Path, out_dir: Path) -> dict[str, Path]:
    out_dir = ensure(Path(out_dir))
    df = prepare(load(clasificado_csv))
    paths = {
        "actos": out_dir / "metrics_actos_por_tipo.csv",
        "resumen": out_dir / "metrics_sector_provincia_mes.csv",
        "sector": out_dir / "metrics_sector.csv",
        "ruido": out_dir / "metrics_ruido_provincia_mes.csv",
        "informe": out_dir / "informe_borme.md",
    }
    actos_por_tipo(df).to_csv(paths["actos"], index=False)
    resumen(df, ["sector", "provincia", "mes"]).to_csv(paths["resumen"], index=False, float_format="%.2f")
    res_sector = resumen(df, ["sector"])
    res_sector.to_csv(paths["sector"], index=False, float_format="%.2f")
    ruido = ruido_por_provincia_mes(df)
    ruido.to_csv(paths["ruido"], index=False, float_format="%.2f")
    paths["informe"].write_text(informe(df, res_sector, ruido), encoding="utf-8")
    return paths
