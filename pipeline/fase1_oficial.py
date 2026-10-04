"""Fase 1 con fuentes oficiales primero y Google solo como último recurso. Ámbito: Madrid.

Orden de verificación de cada sociedad constituida:
1. **REGCESS** (sectores sanitarios; dental primero): ¿tiene un centro autorizado?, ¿cuándo?
2. **Censo de locales de Madrid**: ¿hay un local con su rótulo o dirección?, ¿cuándo pasa a "Obras" y a "Abierto"?
3. **Google Places** (modo básico: ID y campos básicos, sin reseñas; tope de 20 USD), solo para las sociedades
   sin emparejar en 1 ni en 2.

Cada métrica del informe lleva su fuente (BORME, REGCESS, CENSO, GOOGLE) y la marca MEDIDO o ESTIMADO.
Barcelona queda fuera hasta encontrar una fuente de locales o actividades con actualización frecuente
(ver research/FUENTES_FASE1.md).
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .common import ensure, md_table
from .fase1 import CRITERIOS, MIN_N, NO_OBJETIVO, wilson

log = logging.getLogger(__name__)

SANITARIOS_REGCESS = {"dental"}  # ampliable: medicina_estetica, fisioterapia, podologia...


def _q(s: pd.Series, p: float) -> float:
    s = pd.Series(s).dropna()
    return float(s.quantile(p)) if len(s) else np.nan


def _f(x, pct=False, dec=1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)) or (x is pd.NaT):
        return "—"
    return f"{100 * x:.{dec}f} %" if pct else f"{x:.{dec}f}" if isinstance(x, float) else str(x)


def volumen(const: pd.DataFrame, ambito: str = "MADRID") -> pd.DataFrame:
    """BORME, MEDIDO: constituciones/mes y aperturas nuevas/mes por sector (municipio de Madrid)."""
    c = const[const["ciudad"] == ambito]
    if c.empty:
        return pd.DataFrame(columns=["sector", "constituciones", "aperturas_nuevas", "reestructuracion", "holding",
                                     "meses", "constituciones_mes", "aperturas_nuevas_mes", "pct_reestructuracion"])
    meses = max(1, c["mes"].nunique())
    v = (c.groupby("sector")
           .agg(constituciones=("denominacion", "size"),
                aperturas_nuevas=("ruido_tipo", lambda s: int((s == "apertura_nueva").sum())),
                reestructuracion=("ruido_tipo", lambda s: int(s.isin(["expansion_mismo_sector", "filial_de_grupo"]).sum())),
                holding=("ruido_tipo", lambda s: int((s == "holding_patrimonial").sum())))
           .reset_index())
    v["meses"] = meses
    v["constituciones_mes"] = v["constituciones"] / meses
    v["aperturas_nuevas_mes"] = v["aperturas_nuevas"] / meses
    v["pct_reestructuracion"] = v["reestructuracion"] / v["constituciones"]
    return v.sort_values("constituciones", ascending=False)


def combinar(vol: pd.DataFrame, m_reg: pd.DataFrame | None, m_censo: pd.DataFrame | None,
             pl: pd.DataFrame | None, base: pd.DataFrame) -> pd.DataFrame:
    """Une las fuentes por sociedad (`base` = aperturas nuevas objetivo del municipio de Madrid)."""
    b = base[["empresa_key", "sector", "fecha_publicacion"]].copy()
    b["ok_regcess"] = False
    b["ok_censo"] = False
    b["ok_google"] = np.nan  # NaN = no consultado
    if m_reg is not None and len(m_reg):
        ok = set(m_reg.loc[m_reg["match_nivel"].isin(["alta", "media"]), "empresa_key"])
        b["ok_regcess"] = b["empresa_key"].isin(ok)
    if m_censo is not None and len(m_censo):
        ok = set(m_censo.loc[m_censo["match"].fillna(False).astype(bool), "empresa_key"])
        b["ok_censo"] = b["empresa_key"].isin(ok)
    if pl is not None and len(pl):
        g = pl.set_index("empresa_key")["localizable"].astype(float)
        b["ok_google"] = b["empresa_key"].map(g)
    b["ok_oficial"] = b["ok_regcess"] | b["ok_censo"]
    return b


def criterios(vol: pd.DataFrame, comb: pd.DataFrame, m_censo: pd.DataFrame | None,
              m_reg: pd.DataFrame | None) -> pd.DataFrame:
    filas = []
    for r in vol.to_dict("records"):
        s = r["sector"]
        if s in NO_OBJETIVO:
            continue
        d = comb[comb["sector"] == s]
        n = len(d)
        k_of = int(d["ok_oficial"].sum())
        pct_of = k_of / n if n else np.nan
        sin = d[~d["ok_oficial"]]
        g = sin["ok_google"].dropna()
        pct_g = g.mean() if len(g) else np.nan
        # ESTIMADO: % oficial + (1 - % oficial) × % Google en las no emparejadas
        pct_tot = pct_of + (1 - pct_of) * pct_g if len(g) >= MIN_N else np.nan
        loc = pct_tot if not math.isnan(pct_tot) else pct_of
        ab_mes = r["aperturas_nuevas_mes"] * loc if not math.isnan(loc) else np.nan
        lag = np.nan
        fuente_lag = "—"
        if m_censo is not None and len(m_censo):
            l = m_censo.loc[(m_censo["sector"] == s) & m_censo["match"].fillna(False).astype(bool), "lag_borme_abierto_dias"].dropna()
            if len(l) >= 10:
                lag, fuente_lag = float(l.median()), f"CENSO (n={len(l)})"
        if s in SANITARIOS_REGCESS and m_reg is not None and len(m_reg):
            l = m_reg.loc[m_reg["match_nivel"].isin(["alta", "media"]), "lag_borme_regcess_dias"].dropna()
            if len(l) >= 10 and math.isnan(lag):
                lag, fuente_lag = float(l.median()), f"REGCESS (n={len(l)})"
        c1 = "SIN DATOS" if n < MIN_N else ("DESCARTA" if loc < CRITERIOS["localizable_min"] else "PASA")
        c2 = "SIN DATOS" if n < MIN_N else ("DESCARTA" if ab_mes < CRITERIOS["aperturas_mes_min"] else "PASA")
        c3 = "SIN DATOS" if math.isnan(lag) else ("SOLO RECURRENTES" if lag < CRITERIOS["lag_mediana_min_dias"] else "PASA")
        ver = ("DESCARTAR" if "DESCARTA" in (c1, c2) else "SIN DATOS SUFICIENTES" if "SIN DATOS" in (c1, c2)
               else "SEGUIR (solo servicios recurrentes)" if c3 == "SOLO RECURRENTES" else "SEGUIR")
        lo, hi = wilson(k_of, n)
        filas.append({"sector": s, "aperturas_nuevas_mes [BORME·MEDIDO]": r["aperturas_nuevas_mes"],
                      "n": n, "pct_local_oficial [REGCESS+CENSO·MEDIDO]": pct_of, "ic95": f"{_f(lo, True)}–{_f(hi, True)}",
                      "pct_google_no_emparejadas [GOOGLE·MEDIDO muestra]": pct_g, "n_google": len(g),
                      "pct_local_total [ESTIMADO]": pct_tot,
                      "aperturas_reales_mes [ESTIMADO]": ab_mes,
                      "lag_mediana_borme_apertura_dias [MEDIDO]": lag, "fuente_lag": fuente_lag,
                      "c1": c1, "c2": c2, "c3": c3, "veredicto": ver})
    return pd.DataFrame(filas)


def informe(out: dict, meta: dict, research_dir: Path) -> Path:
    d = ensure(Path(research_dir) / "backtest")
    for k, v in out.items():
        if isinstance(v, pd.DataFrame):
            v.to_csv(d / f"{k}.csv", index=False)

    def tabla(df, pct_cols=(), num_cols=()):
        if df is None or not len(df):
            return "*(sin datos: fuente no disponible en esta ejecución)*"
        t = df.copy()
        for c in t.columns:
            if c in pct_cols or c.startswith("pct_"):
                t[c] = t[c].map(lambda x: _f(x, True))
            elif t[c].dtype.kind == "f":
                t[c] = t[c].map(_f)
        return md_table(t)

    L = ["# BACKTEST: fase 1 con fuentes oficiales (Madrid)", "",
         f"*Generado el {dt.date.today().isoformat()} por `python -m pipeline.cli fase1-oficial`.*", "",
         "Convenciones: cada métrica lleva su **fuente** (BORME, REGCESS, CENSO, GOOGLE) y la marca **MEDIDO** "
         "(contado sobre los datos) o **ESTIMADO** (combinación de medidas). Barcelona está excluida: "
         "ver `research/FUENTES_FASE1.md`.", "",
         "## Fuentes de esta ejecución", ""]
    for k, v in meta.get("fuentes", {}).items():
        L.append(f"- **{k}**: {v}")
    L += ["", "## 1. Volumen en el BORME (municipio de Madrid) [BORME · MEDIDO]", "",
          tabla(out.get("volumen")), "",
          f"- % de objetos sociales genéricos sobre todas las constituciones de Madrid: **{_f(meta.get('pct_generico'), True)}** [BORME · MEDIDO; clasificación: {meta.get('clasif')}]", "",
          "## 2. Dental × REGCESS (Comunidad de Madrid) [REGCESS · MEDIDO]", "",
          f"Método de fecha de alta del centro: {meta.get('regcess_metodo', '—')}.", "",
          tabla(out.get("regcess_resumen")), "",
          "Cómo leer la tabla:",
          "- `pct_con_centro_maduras`: solo sociedades con ≥ 270 días desde la publicación, para no penalizar a las recientes.",
          "- `lag_*`: días desde la escritura (o desde el BORME) hasta el alta del centro en el REGCESS.",
          "- `pct_centro_antes_de_sl`: centros autorizados antes de que existiera la sociedad. Suele ser un cambio de titular o un traspaso, no una apertura.", "",
          "## 3. Censo de locales de Madrid ↔ sociedades del BORME [CENSO · MEDIDO]", "",
          tabla(out.get("censo_resumen")), "",
          "Calidad del emparejamiento:",
          "- **A** dirección + rótulo: más fiable.",
          "- **B** solo dirección.",
          "- **C** solo rótulo.",
          "- Hay una muestra para revisar en `research/backtest/censo_muestra_revision.csv`.", "",
          "## 4. Señal temprana: «Obras» + licencia «En tramitación» [CENSO · MEDIDO]", "",
          tabla(out.get("senal_resumen")), "",
          "## 5. Google Places para las sociedades sin emparejar [GOOGLE · MEDIDO en muestra]", "",
          f"- Consultadas: {meta.get('n_google', 0)}. Coste: **{_f(meta.get('google_usd'), dec=2)} USD** a precio de lista (cota superior; tope {meta.get('google_tope')} USD).",
          "- Solo ID y campos básicos, sin reseñas: Google confirma que el local existe, no cuándo abrió.", "",
          "## 6. Criterios de descarte por sector (municipio de Madrid)", "",
          "Criterios:",
          "- **c1**: < 30 % de las sociedades con un local real.",
          "- **c2**: < 20 aperturas reales al mes.",
          "- **c3**: mediana del desfase BORME → apertura < 21 días (solo sirve para servicios recurrentes).",
          "",
          "Si Google se ha consultado en menos de 15 sociedades sin emparejar, `pct_local_total` no se calcula y se usa el % oficial. Ese % es una cota inferior, porque solo cuenta lo que las fuentes oficiales confirman.", "",
          tabla(out.get("criterios")), "",
          "## Limitaciones", "",
          "- **Esquemas no validados.** Los del REGCESS, el fichero de licencias del censo y el histórico del censo no se han comprobado con ficheros reales en el desarrollo; ver los avisos de carga en el log de la ejecución.",
          "- **El censo es mensual.** Los desfases tienen una resolución de unos 30 días.",
          "- **Autónomos.** No aparecen en el BORME. Todo el backtest mide el universo de sociedades.",
          ]
    p = Path(research_dir) / "BACKTEST.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


def resumen_censo(m: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for s, d in m.groupby("sector"):
        ok = d["match"].fillna(False).astype(bool)
        filas.append({"sector": s, "n_sl": len(d), "pct_match": ok.mean(),
                      "pct_A": (d["nivel_match"] == "A_direccion_y_rotulo").mean(),
                      "pct_B": (d["nivel_match"] == "B_direccion").mean(),
                      "pct_C": (d["nivel_match"] == "C_rotulo").mean(),
                      "n_lag_obras": int(d["lag_borme_obras_dias"].notna().sum()),
                      "lag_obras_mediana": _q(d["lag_borme_obras_dias"], .5),
                      "n_lag_abierto": int(d["lag_borme_abierto_dias"].notna().sum()),
                      "lag_abierto_p25": _q(d["lag_borme_abierto_dias"], .25),
                      "lag_abierto_mediana": _q(d["lag_borme_abierto_dias"], .5),
                      "lag_abierto_p75": _q(d["lag_borme_abierto_dias"], .75)})
    return pd.DataFrame(filas).sort_values("n_sl", ascending=False) if filas else pd.DataFrame()
