"""Carga del censo de locales y actividades de Madrid (datos.madrid.es, dataset 200085) y
detección de aperturas entre ficheros mensuales.

Los ficheros cambian de nombres de columna, codificación y separador entre años; aquí se
normalizan a un esquema canónico. Un local puede tener varias filas por mes (una por actividad).
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import pandas as pd

from .classify import classify_text
from .common import norm, norm_key

log = logging.getLogger(__name__)

# Esquema canónico -> nombres alternativos (ya normalizados con norm_key) vistos o previsibles.
ALIAS: dict[str, list[str]] = {
    "id_local": ["id_local", "idlocal", "cod_local", "codigo_local", "id_local_censo"],
    "id_situacion_local": ["id_situacion_local", "cod_situacion_local", "id_situacion"],
    "desc_situacion_local": ["desc_situacion_local", "situacion_local", "desc_situacion", "situacion",
                             "estado_local", "estado", "descripcion_situacion_local"],
    "rotulo": ["rotulo", "rotulo_local", "desc_rotulo", "nombre_comercial", "rotulo_comercial"],
    "id_epigrafe": ["id_epigrafe", "epigrafe", "cod_epigrafe", "id_epigrafe_actividad", "codigo_epigrafe"],
    "desc_epigrafe": ["desc_epigrafe", "descripcion_epigrafe", "epigrafe_desc", "desc_epigrafe_actividad",
                      "nombre_epigrafe"],
    "id_seccion": ["id_seccion", "cod_seccion", "seccion"],
    "desc_seccion": ["desc_seccion", "descripcion_seccion"],
    "id_division": ["id_division", "cod_division", "division"],
    "desc_division": ["desc_division", "descripcion_division"],
    "coordenada_x_local": ["coordenada_x_local", "coordenada_x", "coord_x", "x_local", "utm_x", "x"],
    "coordenada_y_local": ["coordenada_y_local", "coordenada_y", "coord_y", "y_local", "utm_y", "y"],
    "clase_vial_edificio": ["clase_vial_edificio", "clase_vial", "tipo_via", "desc_clase_vial", "clase_via"],
    "desc_vial_edificio": ["desc_vial_edificio", "desc_vial", "nombre_via", "nom_vial", "vial", "via",
                           "desc_vial_acceso"],
    "num_edificio": ["num_edificio", "numero_edificio", "num_portal", "numero", "num", "nnum_edificio",
                     "num_acceso"],
    "cal_edificio": ["cal_edificio", "calificador", "cal_acceso"],
    "id_distrito_local": ["id_distrito_local", "cod_distrito", "id_distrito", "cod_distrito_local"],
    "desc_distrito_local": ["desc_distrito_local", "distrito", "desc_distrito", "nombre_distrito"],
    "id_barrio_local": ["id_barrio_local", "cod_barrio", "id_barrio", "cod_barrio_local"],
    "desc_barrio_local": ["desc_barrio_local", "barrio", "desc_barrio", "nombre_barrio"],
    "fx_carga": ["fx_carga", "fecha_carga", "fec_carga", "fecha_datos", "fx_datos_fin"],
}
CANON = list(ALIAS)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas al esquema canónico. Las desconocidas se conservan normalizadas."""
    keys = {c: norm_key(c) for c in df.columns}
    rename, usados = {}, set()
    for canon, alts in ALIAS.items():
        for alt in alts:  # el orden de ALIAS marca la preferencia
            hit = next((c for c, k in keys.items() if k == alt and c not in rename), None)
            if hit is not None and canon not in usados:
                rename[hit] = canon
                usados.add(canon)
                break
    for c, k in keys.items():
        rename.setdefault(c, k if k not in usados else f"{k}_orig")
    out = df.rename(columns=rename)
    for c in CANON:
        if c not in out:
            out[c] = None
    return out


def read_csv_flexible(path: Path) -> pd.DataFrame:
    """CSV con ';' (o ','), en UTF-8 (con o sin BOM) o latin-1/cp1252; todo como texto."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.split("\n", 1)[0]
    sep = ";" if first.count(";") >= first.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False, na_values=[""],
                       quotechar='"', skipinitialspace=True)


RE_MES = [re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])(?!\d)"), re.compile(r"(?<!\d)(0[1-9]|1[0-2])[-_.]?(20\d{2})")]


def mes_from_name(name: str) -> str | None:
    m = RE_MES[0].search(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = RE_MES[1].search(name)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    return None


def estado(desc: str | None) -> str:
    d = norm(desc)
    if "ABIERT" in d:
        return "abierto"
    if "OBRA" in d:
        return "obras"
    if "CERRAD" in d:
        return "cerrado"
    if "BAJA" in d:
        return "baja"
    return "otro" if d else "desconocido"


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
                         if s.astype(str).str.contains(",").any() else s, errors="coerce")


def load_month(path: Path, mes: str | None = None) -> pd.DataFrame:
    """Lee un fichero mensual y lo devuelve en esquema canónico con columnas 'mes' y 'estado'."""
    df = normalize_columns(read_csv_flexible(path))
    mes = mes or mes_from_name(Path(path).name)
    if mes is None and df["fx_carga"].notna().any():
        f = pd.to_datetime(df["fx_carga"].dropna().iloc[0], dayfirst=True, errors="coerce")
        mes = f.strftime("%Y-%m") if pd.notna(f) else None
    if mes is None:
        raise ValueError(f"No se puede deducir el mes de {path}; renómbralo con AAAA-MM o usa fx_carga")
    df["mes"] = mes
    df["id_local"] = df["id_local"].astype(str).str.strip()
    df["estado"] = [estado(x) for x in df["desc_situacion_local"]]
    for c in ("coordenada_x_local", "coordenada_y_local"):
        df[c] = _num(df[c])
    df["id_epigrafe"] = df["id_epigrafe"].astype("string").str.strip()
    return df


def load_panel(paths: list[Path]) -> pd.DataFrame:
    """Concatena N meses. Si un mes viene en varios ficheros (locales + actividades), se unen por id_local."""
    por_mes: dict[str, list[pd.DataFrame]] = {}
    for p in sorted(paths):
        d = load_month(p)
        por_mes.setdefault(d["mes"].iloc[0], []).append(d)
    meses = []
    for mes, partes in sorted(por_mes.items()):
        if len(partes) == 1:
            meses.append(partes[0])
            continue
        base = max(partes, key=lambda x: x["desc_situacion_local"].notna().sum())
        act = max(partes, key=lambda x: x["id_epigrafe"].notna().sum())
        if base is act:
            meses.append(pd.concat(partes, ignore_index=True))
        else:
            cols_act = ["id_local"] + [c for c in ("id_epigrafe", "desc_epigrafe", "id_seccion", "desc_seccion",
                                                   "id_division", "desc_division") if c in act]
            m = base.drop(columns=[c for c in cols_act if c != "id_local"]).merge(act[cols_act], on="id_local", how="left")
            meses.append(m)
    panel = pd.concat(meses, ignore_index=True)
    log.info("Censo: %d filas, %d locales, meses %s", len(panel), panel["id_local"].nunique(), sorted(panel["mes"].unique()))
    return panel


# --------------------------------------------------------------------------- sector por epígrafe

_sector_cache: dict[tuple, tuple[str, float]] = {}


def sector_epigrafe(id_epigrafe, desc_epigrafe, desc_division=None) -> tuple[str, float]:
    """Sector a partir del epígrafe del censo (los 4 primeros dígitos suelen ser la clase CNAE-2009)."""
    key = (id_epigrafe, desc_epigrafe, desc_division)
    if key not in _sector_cache:
        ide = re.sub(r"\D", "", str(id_epigrafe or ""))
        cnae = [ide[:4]] if len(ide) >= 4 else []
        texto = " ".join(str(x) for x in (desc_epigrafe, desc_division) if x and x == x)
        c = classify_text(texto, None, cnae)
        _sector_cache[key] = (c.sector, c.confianza)
    return _sector_cache[key]


# --------------------------------------------------------------------------- aperturas


def snapshot(panel: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (id_local, mes) con el conjunto de epígrafes y el sector principal."""
    sect = [sector_epigrafe(a, b, c) for a, b, c in
            zip(panel["id_epigrafe"], panel["desc_epigrafe"], panel["desc_division"])]
    p = panel.assign(sector=[s for s, _ in sect], conf_sector=[c for _, c in sect])
    p = p.sort_values(["id_local", "mes", "conf_sector"], ascending=[True, True, False])

    def first_valid(s):
        s = s.dropna()
        return s.iloc[0] if len(s) else None

    g = p.groupby(["id_local", "mes"], sort=True)
    snap = g.agg(
        estado=("estado", first_valid), rotulo=("rotulo", first_valid),
        epigrafes=("id_epigrafe", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        id_epigrafe=("id_epigrafe", first_valid), desc_epigrafe=("desc_epigrafe", first_valid),
        sector=("sector", first_valid), conf_sector=("conf_sector", "max"),
        clase_vial_edificio=("clase_vial_edificio", first_valid), desc_vial_edificio=("desc_vial_edificio", first_valid),
        num_edificio=("num_edificio", first_valid), desc_distrito_local=("desc_distrito_local", first_valid),
        desc_barrio_local=("desc_barrio_local", first_valid),
        coordenada_x_local=("coordenada_x_local", "first"), coordenada_y_local=("coordenada_y_local", "first"),
    ).reset_index()
    return snap


def _mes_idx(mes: str) -> int:
    y, m = mes.split("-")
    return int(y) * 12 + int(m) - 1


def detect_aperturas(panel: pd.DataFrame) -> pd.DataFrame:
    """Detecta aperturas en el panel mensual.

    Tipos:
    - nuevo_local: el local aparece por primera vez (no estaba en ningún mes anterior) y ya 'Abierto'.
    - reapertura_actividad_nueva: pasa de obras/cerrado/baja a 'Abierto' con un epígrafe distinto del
      último que tuvo abierto (o sin historial abierto).
    - cambio_actividad: sigue 'Abierto' pero aparece un epígrafe nuevo.
    - reapertura_misma_actividad: vuelve a 'Abierto' con la misma actividad (vacaciones, cierre
      temporal); se registra pero no cuenta como apertura en el backtest.
    El primer mes del panel está censurado (no se puede saber qué había antes) y no genera aperturas.
    Para cada apertura se cuentan los meses consecutivos previos en 'obras' y en 'cerrado'.
    """
    snap = snapshot(panel)
    meses = sorted(snap["mes"].unique())
    primer = meses[0]
    rows = []
    for id_local, g in snap.groupby("id_local", sort=False):
        recs = g.sort_values("mes").to_dict("records")
        ultimo_abierto_epi: set[str] | None = None
        for i, r in enumerate(recs):
            epis = set(filter(None, (r["epigrafes"] or "").split("|")))
            prev = recs[i - 1] if i else None
            tipo = None
            if r["estado"] == "abierto" and r["mes"] != primer:
                if prev is None:
                    tipo = "nuevo_local"
                elif prev["estado"] != "abierto":
                    nueva = ultimo_abierto_epi is None or not epis <= ultimo_abierto_epi
                    tipo = "reapertura_actividad_nueva" if nueva else "reapertura_misma_actividad"
                elif ultimo_abierto_epi is not None and epis and not epis <= ultimo_abierto_epi:
                    tipo = "cambio_actividad"
            if tipo:
                obras = cerrado = 0
                primer_obras = None
                for q in reversed(recs[:i]):
                    if q["estado"] == "abierto":
                        break
                    if q["estado"] == "obras":
                        obras += 1
                        primer_obras = q["mes"]
                    elif q["estado"] in ("cerrado", "baja"):
                        cerrado += 1
                rows.append({
                    **{k: r[k] for k in ("id_local", "mes", "rotulo", "id_epigrafe", "desc_epigrafe", "epigrafes",
                                         "sector", "conf_sector", "clase_vial_edificio", "desc_vial_edificio",
                                         "num_edificio", "desc_distrito_local", "desc_barrio_local",
                                         "coordenada_x_local", "coordenada_y_local")},
                    "tipo_apertura": tipo, "estado_previo": prev["estado"] if prev else None,
                    "meses_previos_obras": obras, "meses_previos_cerrado": cerrado,
                    "lag_obras_apertura_meses": (_mes_idx(r["mes"]) - _mes_idx(primer_obras)) if primer_obras else None,
                    "obras_censurado": bool(primer_obras and primer_obras == primer),
                })
            if r["estado"] == "abierto":
                ultimo_abierto_epi = epis or ultimo_abierto_epi
    out = pd.DataFrame(rows)
    if len(out):
        out = out.rename(columns={"mes": "mes_apertura"})
        out["fecha_apertura"] = pd.to_datetime(out["mes_apertura"] + "-01")
    return out
