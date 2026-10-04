"""Censo de locales de Madrid (histórico mensual) ↔ BORME, desde el lado de la sociedad, y señal temprana.

1. **Emparejamiento sociedad -> local**: para cada constitución del municipio de Madrid se busca en el panel
   del censo un local cuyo rótulo y/o dirección coincida y que aparezca (en cualquier situación) desde 60 días
   antes de la publicación en el BORME. Niveles, iguales que en `backtest.match`:
   - **A**: dirección + rótulo ≥ 60.
   - **B**: solo dirección, con un máximo de 3 sociedades en esa dirección.
   - **C**: solo rótulo ≥ 90 sobre el núcleo distintivo (sin "BAR", "CLINICA"...) y con un sector compatible
     con el del epígrafe; los rótulos genéricos se excluyen.

   La calidad se mide como el % por nivel, más una muestra para revisión.
2. **Desfases**: publicación en el BORME -> primer mes en "Obras" y -> primer mes "Abierto" del local emparejado.
3. **Señal temprana**: un local en situación "Obras" con una licencia o declaración responsable "En tramitación"
   en el fichero de licencias del censo. Se mide qué % de esas señales acaba "Abierto", con qué desfase, y
   si la sociedad ya había salido en el BORME antes de la señal.

Fuente: https://datos.madrid.es (200085 censo actual; 209548 histórico mensual desde 2014; fichero de locales
con información de licencias). El esquema del fichero de licencias NO SE HA VALIDADO con datos reales.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import (GENERICOS, MAX_CANDIDATOS_DIR, UMBRAL_NOMBRE_CON_DIR, UMBRAL_NOMBRE_SOLO, norm_nombre,
                       score_distintivo)
from .common import address_key, norm, norm_key
from .madrid_census import _mes_idx, read_csv_flexible, snapshot

log = logging.getLogger(__name__)

ALIAS_LIC: dict[str, list[str]] = {
    "id_local": ["id_local", "idlocal", "cod_local"],
    "ref_licencia": ["ref_licencia", "referencia_licencia", "num_expediente", "expediente", "id_licencia"],
    "tipo_licencia": ["desc_tipo_licencia", "tipo_licencia", "id_tipo_licencia", "tipo_tramite"],
    "situacion_licencia": ["desc_tipo_situacion_licencia", "desc_situacion_licencia", "situacion_licencia",
                           "estado_licencia", "id_tipo_situacion_licencia", "situacion"],
    "fecha_licencia": ["fecha_dec_lic", "fecha_licencia", "fecha_concesion", "fecha_solicitud", "fecha"],
}


def load_licencias_censo(paths: list[Path]) -> pd.DataFrame:
    partes = []
    for p in paths:
        raw = read_csv_flexible(Path(p))
        keys = {norm_key(c): c for c in raw.columns}
        d = pd.DataFrame(index=raw.index)
        for canon, alts in ALIAS_LIC.items():
            col = next((keys[a] for a in alts if a in keys), None)
            d[canon] = raw[col] if col is not None else None
        partes.append(d)
    lic = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=list(ALIAS_LIC))
    lic["id_local"] = pd.to_numeric(lic["id_local"], errors="coerce")
    lic["fecha_licencia"] = pd.to_datetime(lic["fecha_licencia"], errors="coerce", dayfirst=True)
    lic["en_tramitacion"] = [("TRAMIT" in norm(s)) for s in lic["situacion_licencia"]]
    return lic.drop_duplicates()


def historia_locales(panel: pd.DataFrame) -> pd.DataFrame:
    """Una fila por local con el primer mes visto, el primer mes en obras y el primer mes abierto tras obras."""
    snap = snapshot(panel)
    rows = []
    for id_local, g in snap.groupby("id_local", sort=False):
        g = g.sort_values("mes")
        meses = g["mes"].tolist()
        est = g["estado"].tolist()
        p_obras = next((m for m, e in zip(meses, est) if e == "obras"), None)
        p_abierto_tras = None
        if p_obras:
            p_abierto_tras = next((m for m, e in zip(meses, est) if e == "abierto" and m > p_obras), None)
        last = g.iloc[-1]
        rows.append({"id_local": id_local, "primer_mes": meses[0], "primer_obras": p_obras,
                     "primer_abierto_tras_obras": p_abierto_tras,
                     "primer_abierto": next((m for m, e in zip(meses, est) if e == "abierto"), None),
                     "rotulo": next((r for r in reversed(g["rotulo"].tolist()) if isinstance(r, str) and r.strip()), None),
                     "sector_censo": last["sector"],
                     "addr_key": address_key(last["desc_vial_edificio"], last["num_edificio"])
                     if isinstance(last["desc_vial_edificio"], str) else None})
    h = pd.DataFrame(rows)
    h["rotulo_norm"] = [norm_nombre(x) for x in h["rotulo"]]
    return h


INDETERMINADOS = {None, "", "otros", "sin_clasificar", "generico", "ruido"}


def _sector_compatible(a, b) -> bool:
    """Un emparejamiento solo por rótulo exige el mismo sector (o alguno indeterminado)."""
    a = a if isinstance(a, str) else None
    b = b if isinstance(b, str) else None
    return a in INDETERMINADOS or b in INDETERMINADOS or a == b


def _mes_ts(m):
    return pd.Timestamp(f"{m}-01") if isinstance(m, str) else pd.NaT


def cruzar_sl(sl: pd.DataFrame, hist: pd.DataFrame, dias_antes: int = 60) -> pd.DataFrame:
    """Mejor local del censo para cada sociedad del municipio de Madrid."""
    from rapidfuzz import fuzz, process
    by_addr: dict[str, list[int]] = {}
    for j, k in enumerate(hist["addr_key"]):
        if k:
            by_addr.setdefault(k, []).append(j)
    names = hist["rotulo_norm"].fillna("").tolist()
    sl = sl.reset_index(drop=True).copy()
    sl["nombre_norm"] = [norm_nombre(x) for x in sl["denominacion"]]
    sl["addr_key"] = [address_key(x) if isinstance(x, str) else None for x in sl["domicilio"]]
    cand: dict[int, list[int]] = {}
    valid = [i for i, n in enumerate(sl["nombre_norm"]) if len(n) >= 4]
    if valid and names:
        mat = process.cdist([sl.at[i, "nombre_norm"] for i in valid], names, scorer=fuzz.token_set_ratio,
                            score_cutoff=UMBRAL_NOMBRE_CON_DIR, workers=-1, dtype=np.uint8)
        for row, i in enumerate(valid):
            js = np.nonzero(mat[row])[0]
            if len(js):
                cand[i] = js.tolist()
    n_sl_addr: dict[str, int] = sl["addr_key"].value_counts().to_dict()
    pub = pd.to_datetime(sl["fecha_publicacion"], errors="coerce")
    out = []
    for i, r in sl.iterrows():
        best = None
        for j in set(cand.get(i, [])) | set(by_addr.get(r["addr_key"], []) if r["addr_key"] else []):
            h = hist.iloc[j]
            # el local debe "vivir" después de (o poco antes de) la publicación
            ultimo = max(filter(None, [h["primer_abierto"], h["primer_obras"], h["primer_mes"]]))
            if pd.notna(pub[i]) and _mes_ts(ultimo) < pub[i] - pd.Timedelta(days=dias_antes):
                continue
            same = bool(r["addr_key"]) and h["addr_key"] == r["addr_key"]
            rot = h["rotulo_norm"] or ""
            ns = score_distintivo(r["nombre_norm"], rot) if rot and rot not in GENERICOS else 0.0
            if same and ns >= UMBRAL_NOMBRE_CON_DIR:
                nivel = "A_direccion_y_rotulo"
            elif same and n_sl_addr.get(r["addr_key"], 0) <= MAX_CANDIDATOS_DIR:
                nivel = "B_direccion"
            elif ns >= UMBRAL_NOMBRE_SOLO and _sector_compatible(r.get("sector"), h["sector_censo"]):
                nivel = "C_rotulo"
            else:
                continue
            key = (nivel, -ns)
            if best is None or key < best[0]:
                best = (key, j, nivel, ns)
        rec = {"empresa_key": r.get("empresa_key"), "denominacion": r["denominacion"], "sector": r.get("sector"),
               "fecha_publicacion": pub[i]}
        if best:
            _, j, nivel, ns = best
            h = hist.iloc[j]
            rec.update(match=True, nivel_match=nivel, score_rotulo=ns, id_local=h["id_local"], rotulo=h["rotulo"],
                       primer_obras=_mes_ts(h["primer_obras"]),
                       primer_abierto=_mes_ts(h["primer_abierto_tras_obras"] or h["primer_abierto"]))
        else:
            rec.update(match=False, nivel_match=None)
        out.append(rec)
    m = pd.DataFrame(out)
    for col in ("primer_obras", "primer_abierto"):
        if col not in m:
            m[col] = pd.NaT
        m[col] = pd.to_datetime(m[col], errors="coerce")
    m["lag_borme_obras_dias"] = (m["primer_obras"] - m["fecha_publicacion"]).dt.days
    m["lag_borme_abierto_dias"] = (m["primer_abierto"] - m["fecha_publicacion"]).dt.days
    return m


def senal_temprana(panel: pd.DataFrame, lic: pd.DataFrame, m_sl: pd.DataFrame | None = None,
                   ventana_meses: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Señal = primer mes en que un local está en 'Obras' y tiene alguna licencia 'En tramitación'.

    Devuelve (señales, resumen por sector). Una señal se cuenta como abierta si el local pasa a 'Abierto'
    dentro de `ventana_meses`. Solo se evalúan las señales con ventana completa dentro del panel.
    """
    snap = snapshot(panel)
    tram = set(pd.to_numeric(lic.loc[lic["en_tramitacion"], "id_local"], errors="coerce").dropna().astype(int))
    snap["id_local"] = pd.to_numeric(snap["id_local"], errors="coerce")
    ultimo = max(_mes_idx(x) for x in snap["mes"].unique())
    rows = []
    for id_local, g in snap[snap["id_local"].isin(tram)].groupby("id_local"):
        g = g.sort_values("mes")
        o = g[g["estado"] == "obras"]
        if o.empty:
            continue
        m0 = o.iloc[0]["mes"]
        ab = g[(g["estado"] == "abierto") & (g["mes"] > m0)]
        m1 = ab.iloc[0]["mes"] if len(ab) else None
        rows.append({"id_local": int(id_local), "mes_senal": m0, "sector_censo": o.iloc[0]["sector"],
                     "mes_apertura": m1, "meses_hasta_apertura": (_mes_idx(m1) - _mes_idx(m0)) if m1 else None,
                     "ventana_completa": ultimo - _mes_idx(m0) >= ventana_meses})
    s = pd.DataFrame(rows, columns=["id_local", "mes_senal", "sector_censo", "mes_apertura", "meses_hasta_apertura",
                                    "ventana_completa"])
    if m_sl is not None and len(s) and "id_local" in m_sl:
        mm = m_sl[m_sl["match"].fillna(False)].dropna(subset=["id_local"])
        mm = mm.assign(id_local=pd.to_numeric(mm["id_local"], errors="coerce"))
        s = s.merge(mm[["id_local", "fecha_publicacion", "denominacion"]], on="id_local", how="left")
        s["borme_antes_de_senal"] = s["fecha_publicacion"] < s["mes_senal"].map(_mes_ts)
    v = s[s["ventana_completa"]]
    if v.empty:
        return s, pd.DataFrame()
    res = (v.groupby("sector_censo")
             .agg(senales=("id_local", "size"),
                  abiertas_12m=("meses_hasta_apertura", lambda x: int((x.notna() & (x <= ventana_meses)).sum())),
                  meses_mediana=("meses_hasta_apertura", "median"),
                  meses_p25=("meses_hasta_apertura", lambda x: x.quantile(.25)),
                  meses_p75=("meses_hasta_apertura", lambda x: x.quantile(.75)))
             .reset_index())
    res["pct_abren_12m"] = res["abiertas_12m"] / res["senales"]
    return s, res
