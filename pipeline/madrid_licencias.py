"""Carga opcional de "Licencias urbanísticas otorgadas y declaraciones responsables" de Madrid
(datos.madrid.es, dataset 300193; mensual, CSV o XLS).

NO VALIDADO CONTRA DATOS REALES: el esquema real no se ha podido descargar (red bloqueada). La
normalización de columnas es flexible y se basa en los campos descritos en la ficha del dataset
(objeto de la licencia, tipo de procedimiento, emplazamiento/dirección, régimen de uso, obras y
geolocalización). Revisar ALIAS con el primer fichero real.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .common import address_key, norm_key
from .madrid_census import read_csv_flexible

log = logging.getLogger(__name__)

ALIAS: dict[str, list[str]] = {
    "fecha": ["fecha_concesion", "fecha_otorgamiento", "fecha_resolucion", "fecha_de_concesion",
              "fecha_presentacion", "fecha_entrada", "fecha_declaracion", "fecha_alta", "fecha"],
    "tipo_procedimiento": ["tipo_procedimiento", "procedimiento", "tipo_de_procedimiento", "tipo_tramitacion",
                           "tramitacion", "tipo_expediente", "tipo"],
    "objeto": ["objeto_licencia", "objeto", "objeto_de_la_licencia", "descripcion", "finalidad", "actuacion",
               "descripcion_actuacion"],
    "uso": ["regimen_uso", "uso", "regimen_de_uso", "uso_principal", "actividad", "desc_uso"],
    "obras": ["obras", "tipo_obra", "tipo_obras", "desc_obras", "clase_obra"],
    "clase_vial": ["clase_vial", "tipo_via", "clase_via"],
    "via": ["nombre_via", "via", "desc_vial", "calle", "nom_via", "vial"],
    "numero": ["numero", "num", "num_portal", "numero_via", "num_edificio"],
    "direccion": ["emplazamiento", "direccion", "ubicacion", "localizacion", "domicilio"],
    "expediente": ["expediente", "num_expediente", "n_expediente", "id_expediente", "numero_expediente"],
    "x": ["coordenada_x", "utm_x", "x", "longitud", "lon"],
    "y": ["coordenada_y", "utm_y", "y", "latitud", "lat"],
    "distrito": ["distrito", "desc_distrito", "nombre_distrito"],
}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    keys = {c: norm_key(c) for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for canon, alts in ALIAS.items():
        hit = next((c for alt in alts for c, k in keys.items() if k == alt), None)
        if hit is None:  # coincidencia parcial: 'fecha_concesion_licencia' -> fecha
            hit = next((c for alt in alts for c, k in keys.items() if len(alt) > 4 and alt in k), None)
        out[canon] = df[hit] if hit is not None else None
    return out


def read_any(path: Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xls", ".xlsx"):
        return pd.read_excel(path, dtype=str)  # requiere xlrd (xls) u openpyxl (xlsx)
    return read_csv_flexible(path)


def load_licencias(paths: list[Path]) -> pd.DataFrame:
    """Concatena los ficheros, normaliza columnas y calcula fecha y clave de dirección."""
    frames = [normalize(read_any(p)).assign(fichero=Path(p).name) for p in sorted(paths)]
    if not frames:
        return pd.DataFrame(columns=list(ALIAS) + ["fichero", "fecha_dt", "addr_key", "es_declaracion_responsable"])
    df = pd.concat(frames, ignore_index=True)
    df["fecha_dt"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce", format="mixed")
    keys = []
    for via, num, dire in zip(df["via"], df["numero"], df["direccion"]):
        k = address_key(via, num) if isinstance(via, str) and via.strip() else None
        keys.append(k or (address_key(dire) if isinstance(dire, str) else None))
    df["addr_key"] = keys
    proc = df["tipo_procedimiento"].fillna("").astype(str) + " " + df["objeto"].fillna("").astype(str)
    df["es_declaracion_responsable"] = proc.str.upper().str.contains(r"DECLARACI[OÓ]N RESPONSABLE|\bDR\b", regex=True)
    log.info("Licencias/DR: %d filas, %d con dirección normalizada", len(df), df["addr_key"].notna().sum())
    return df


def cruzar_aperturas(aperturas: pd.DataFrame, lic: pd.DataFrame, max_dias: int = 730) -> pd.DataFrame:
    """Para cada apertura, la licencia/DR más reciente en la misma dirección y anterior a la apertura
    (como mucho `max_dias` antes, y hasta 31 días después por la resolución mensual del censo)."""
    lic = lic.dropna(subset=["addr_key", "fecha_dt"])
    by_key = {k: g.sort_values("fecha_dt") for k, g in lic.groupby("addr_key")}
    rows = []
    for _, a in aperturas.iterrows():
        g = by_key.get(a.get("addr_key"))
        res = {"lic_match": False, "lic_fecha": pd.NaT, "lic_tipo": None, "lic_es_dr": None, "lag_licencia_apertura_dias": None}
        if g is not None:
            lag = (a["fecha_apertura"] - g["fecha_dt"]).dt.days
            ok = g[(lag >= -31) & (lag <= max_dias)]
            if len(ok):
                best = ok.iloc[-1]
                res = {"lic_match": True, "lic_fecha": best["fecha_dt"], "lic_tipo": best["tipo_procedimiento"],
                       "lic_es_dr": bool(best["es_declaracion_responsable"]),
                       "lag_licencia_apertura_dias": int((a["fecha_apertura"] - best["fecha_dt"]).days)}
        rows.append(res)
    return pd.concat([aperturas.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def resumen_por_sector(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sector, g in df.groupby("sector"):
        lags = pd.to_numeric(g.loc[g["lic_match"], "lag_licencia_apertura_dias"], errors="coerce").dropna()
        rows.append({"sector": sector, "n_aperturas": len(g), "n_con_licencia_o_dr": int(g["lic_match"].sum()),
                     "pct_con_licencia_o_dr": 100 * g["lic_match"].mean(),
                     "pct_dr_sobre_match": 100 * g.loc[g["lic_match"], "lic_es_dr"].mean() if g["lic_match"].any() else None,
                     **{f"lag_lic_apertura_p{p}": (lags.quantile(p / 100) if len(lags) else None) for p in (10, 25, 50, 75, 90)}})
    return pd.DataFrame(rows)
