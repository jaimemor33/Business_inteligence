"""REGCESS (Registro General de Centros, Servicios y Establecimientos Sanitarios) ↔ BORME, sector sanitario.

Fuentes que admite `load_snapshots` (una o varias "fotos" del registro):
- Descarga del Ministerio de Sanidad: https://regcess.mscbs.es/regcessWeb/inicioDescargarCentrosAction.do
  Excel por tipo de centro (C1 hospitales, C2 centros sin internamiento, C3 servicios sanitarios en
  organizaciones no sanitarias, E establecimientos). Las clínicas dentales son C.2.5.1, dentro del fichero C2.
  Periodicidad mensual según el Ministerio. NO VERIFICADO que se puedan bajar fotos de meses anteriores.
- Alternativa: "Centros, servicios y establecimientos sanitarios" de la Comunidad de Madrid
  (https://datos.comunidad.madrid/catalogo/dataset/centros_servicios_establecimientos_sanitarios), CSV/JSON diario.

Cómo se calcula la fecha de alta de cada centro:
- Con ≥ 2 fotos: primera foto en la que aparece el centro. Los centros que ya están en la primera foto
  quedan censurados: no se sabe cuándo entraron.
- Con 1 foto: el campo "Fecha Autorización de Funcionamiento" (definido en el manual del REGCESS). Si el
  centro ha renovado la autorización, puede ser la fecha de la última renovación; se avisa en el informe.

Emparejamiento sociedad del BORME -> centro:
- **alta**: titular del centro (o, si el fichero no trae titular, nombre del centro) igual a la denominación
  normalizada; o dirección igual (vía + número) con nombre ≥ 60.
- **media**: nombre ≥ 90 en el mismo municipio, comparando solo el núcleo distintivo (sin "CLINICA", "DENTAL"...).
- **baja**: solo dirección. Se informa aparte y no cuenta como emparejamiento.

ESQUEMA NO VALIDADO con el fichero real (la red estaba bloqueada): ALIAS se basa en los campos del
"Manual de definiciones" del REGCESS. Hay que revisarlo con la primera descarga real.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import norm_nombre, score_distintivo
from .common import address_key, norm, norm_key

log = logging.getLogger(__name__)

ALIAS: dict[str, list[str]] = {
    "codigo_centro": ["codigo_autonomico_del_centro", "codigo_autonomico", "codigo_centro", "cod_centro",
                      "codigo_regcess", "codigo", "id_centro", "nregistro", "numero_registro"],
    "nombre_centro": ["nombre_del_centro", "nombre_centro", "denominacion_centro", "denominacion", "centro", "nombre"],
    "titular": ["nombre_del_titular", "titular", "nombre_titular", "razon_social", "titularidad_nombre",
                "entidad_titular", "titular_del_centro"],
    "tipo_centro": ["tipo_de_centro", "tipo_centro", "clase_de_centro", "clase_centro", "desc_tipo_centro",
                    "tipo", "codigo_tipo_centro"],
    "oferta": ["oferta_asistencial", "ofertas_asistenciales", "unidades_asistenciales", "servicios", "oferta"],
    "direccion": ["direccion", "domicilio", "direccion_del_centro", "via", "calle", "direccion_centro"],
    "municipio": ["municipio", "localidad", "nombre_municipio", "desc_municipio", "poblacion"],
    "codigo_postal": ["codigo_postal", "cp", "cod_postal"],
    "provincia": ["provincia", "nombre_provincia", "desc_provincia"],
    "fecha_autorizacion": ["fecha_autorizacion_de_funcionamiento", "fecha_autorizacion_funcionamiento",
                           "fecha_autorizacion", "fecha_de_autorizacion", "fecha_alta", "fecha_inscripcion",
                           "fecha_funcionamiento"],
    "fecha_cierre": ["fecha_cierre", "fecha_de_cierre", "fecha_baja"],
    "estado": ["estado", "situacion", "estado_centro", "situacion_centro"],
}
RE_DENTAL = re.compile(r"DENTAL|ODONTOLOG|ESTOMATOLOG|C\.?\s?2\.?\s?5\.?\s?1\b|\bU\.?\s?(44|46)\b")
RE_FECHA_FICHERO = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])(?:[-_.]?(\d{2}))?")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    keys = {norm_key(c): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for canon, alts in ALIAS.items():
        col = next((keys[a] for a in alts if a in keys), None)
        out[canon] = df[col] if col is not None else None
    return out


def _read(path: Path) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf in (".xls", ".xlsx"):
        return pd.read_excel(path, dtype=str)
    if suf == ".json":
        return pd.json_normalize(pd.read_json(path).to_dict("records"))
    from .madrid_census import read_csv_flexible
    return read_csv_flexible(path)


def fecha_snapshot(path: Path) -> pd.Timestamp | None:
    m = RE_FECHA_FICHERO.search(path.stem)
    if not m:
        return None
    return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))


def load_snapshots(paths: list[Path]) -> pd.DataFrame:
    """Une las fotos del registro. Columna `snapshot` = fecha de la foto (del nombre del fichero)."""
    partes = []
    for p in sorted(paths):
        p = Path(p)
        d = normalize(_read(p))
        d["snapshot"] = fecha_snapshot(p)
        d["fichero"] = p.name
        partes.append(d)
    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=[*ALIAS, "snapshot", "fichero"])
    df["fecha_autorizacion"] = pd.to_datetime(df["fecha_autorizacion"], errors="coerce", dayfirst=True)
    df["fecha_cierre"] = pd.to_datetime(df["fecha_cierre"], errors="coerce", dayfirst=True)
    df["es_dental"] = [bool(RE_DENTAL.search(norm(f"{t} {o} {n}"))) for t, o, n in
                       zip(df["tipo_centro"], df["oferta"], df["nombre_centro"])]
    return df


def centros(df: pd.DataFrame, solo_dental: bool = True) -> tuple[pd.DataFrame, str]:
    """Una fila por centro con su fecha de alta. Devuelve (centros, método de fecha)."""
    d = df[df["es_dental"]] if solo_dental else df
    fotos = sorted(x for x in d["snapshot"].dropna().unique())
    key = d["codigo_centro"].fillna(d["nombre_centro"].astype(str) + "|" + d["direccion"].astype(str))
    d = d.assign(_k=key)
    g = d.sort_values("snapshot").groupby("_k")
    c = g.agg(nombre_centro=("nombre_centro", "last"), titular=("titular", "last"), direccion=("direccion", "last"),
              municipio=("municipio", "last"), tipo_centro=("tipo_centro", "last"),
              fecha_autorizacion=("fecha_autorizacion", "min"), fecha_cierre=("fecha_cierre", "max"),
              primera_foto=("snapshot", "min"), ultima_foto=("snapshot", "max")).reset_index()
    if len(fotos) >= 2:
        c["fecha_alta"] = c["primera_foto"].where(c["primera_foto"] > fotos[0])
        c["fecha_alta_censurada"] = c["primera_foto"] == fotos[0]
        metodo = f"primera aparición en {len(fotos)} fotos ({pd.Timestamp(fotos[0]).date()} a {pd.Timestamp(fotos[-1]).date()})"
    else:
        c["fecha_alta"] = c["fecha_autorizacion"]
        c["fecha_alta_censurada"] = False
        metodo = "campo Fecha Autorización de Funcionamiento (1 sola foto; puede ser la última renovación)"
    c["titular_norm"] = [norm_nombre(x) for x in c["titular"]]
    c["nombre_norm"] = [norm_nombre(x) for x in c["nombre_centro"]]
    c["addr_key"] = [address_key(x) if isinstance(x, str) else None for x in c["direccion"]]
    c["muni_norm"] = [norm(x) for x in c["municipio"]]
    return c, metodo


def cruzar(sl: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """Mejor centro para cada sociedad del BORME (`sl`: constituciones de un sector sanitario)."""
    by_addr: dict[str, list[int]] = {}
    for j, k in enumerate(c["addr_key"]):
        if k:
            by_addr.setdefault(k, []).append(j)
    tit = c["titular_norm"].tolist()
    nom = c["nombre_norm"].tolist()
    out = []
    for r in sl.to_dict("records"):
        n = norm_nombre(r.get("denominacion"))
        ak = address_key(r["domicilio"]) if isinstance(r.get("domicilio"), str) else None
        muni = norm(r.get("municipio"))
        best = None
        for j in range(len(c)):
            s_tit = 100.0 if n and tit[j] and n == tit[j] else score_distintivo(n, tit[j]) if tit[j] else 0.0
            s_nom = score_distintivo(n, nom[j]) if nom[j] else 0.0
            s = max(s_tit, s_nom)
            same_addr = bool(ak) and c.at[j, "addr_key"] == ak
            if s_tit == 100.0 or (same_addr and s >= 60):
                nivel = "alta"
            elif s >= 90 and (not muni or c.at[j, "muni_norm"] == muni):
                nivel = "media"
            elif same_addr:
                nivel = "baja"
            else:
                continue
            key = ({"alta": 0, "media": 1, "baja": 2}[nivel], -s)
            if best is None or key < best[0]:
                best = (key, j, nivel, s, "titular" if s_tit >= s_nom and tit[j] else "nombre_centro")
        rec = {"empresa_key": r.get("empresa_key"), "denominacion": r.get("denominacion"),
               "comienzo_operaciones": r.get("comienzo_operaciones"), "fecha_publicacion": r.get("fecha_publicacion")}
        if best:
            _, j, nivel, s, campo = best
            cc = c.iloc[j]
            rec.update(match_nivel=nivel, match_score=s, match_campo=campo, centro=cc["nombre_centro"],
                       titular=cc["titular"], fecha_alta=cc["fecha_alta"], fecha_alta_censurada=cc["fecha_alta_censurada"])
        else:
            rec.update(match_nivel="sin_match")
        out.append(rec)
    m = pd.DataFrame(out)
    for col in ("comienzo_operaciones", "fecha_publicacion", "fecha_alta"):
        m[col] = pd.to_datetime(m.get(col), errors="coerce")
    ref = m["comienzo_operaciones"].fillna(m["fecha_publicacion"])
    m["lag_escritura_regcess_dias"] = (m["fecha_alta"] - ref).dt.days
    m["lag_borme_regcess_dias"] = (m["fecha_alta"] - m["fecha_publicacion"]).dt.days
    return m


def resumen(m: pd.DataFrame, fecha_corte: pd.Timestamp, seguimiento_min_dias: int = 270) -> pd.DataFrame:
    """Métricas MEDIDAS. El % con centro autorizado se da para toda la cohorte y para las sociedades con al
    menos `seguimiento_min_dias` de seguimiento (las recientes no han tenido tiempo de autorizarse)."""
    ok = m["match_nivel"].isin(["alta", "media"])
    pub = pd.to_datetime(m["fecha_publicacion"], errors="coerce")
    madura = (fecha_corte - pub).dt.days >= seguimiento_min_dias
    lag = m.loc[ok & m["lag_escritura_regcess_dias"].notna(), "lag_escritura_regcess_dias"]
    lagb = m.loc[ok & m["lag_borme_regcess_dias"].notna(), "lag_borme_regcess_dias"]

    def q(s, p):
        return float(np.percentile(s, p)) if len(s) else np.nan

    return pd.DataFrame([{
        "n_sl": len(m), "n_match_alta": int((m["match_nivel"] == "alta").sum()),
        "n_match_media": int((m["match_nivel"] == "media").sum()), "n_solo_direccion": int((m["match_nivel"] == "baja").sum()),
        "pct_con_centro": ok.mean() if len(m) else np.nan,
        "n_sl_maduras": int(madura.sum()), "pct_con_centro_maduras": ok[madura].mean() if madura.any() else np.nan,
        "n_lag": len(lag), "lag_escritura_p25": q(lag, 25), "lag_escritura_mediana": q(lag, 50), "lag_escritura_p75": q(lag, 75),
        "lag_borme_p25": q(lagb, 25), "lag_borme_mediana": q(lagb, 50), "lag_borme_p75": q(lagb, 75),
        "pct_centro_antes_de_sl": float((lag < -30).mean()) if len(lag) else np.nan,
    }])
