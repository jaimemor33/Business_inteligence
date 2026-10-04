"""Fase 4: backtest del timing BORME -> apertura con el censo de locales de Madrid.

1. Detecta aperturas en el panel mensual del censo (madrid_census.detect_aperturas).
2. Empareja cada apertura con constituciones o cambios de domicilio previos de la provincia de
   Madrid por (i) similitud rótulo ~ denominación (rapidfuzz) y (ii) dirección normalizada.
3. Resume por sector: % de aperturas con match, lag BORME -> apertura, lag obras -> apertura, y
   precisión de los matches (con una muestra para revisión manual).
4. Opcional: cruza con licencias urbanísticas / declaraciones responsables (dataset 300193).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from .common import address_key, ensure, md_table, norm
from .madrid_census import detect_aperturas, load_panel

log = logging.getLogger(__name__)

FORMAS = r"\b(SOCIEDAD LIMITADA( UNIPERSONAL| PROFESIONAL| LABORAL| NUEVA EMPRESA)?|SOCIEDAD ANONIMA( UNIPERSONAL)?|" \
         r"S\.?\s?L\.?\s?[UPL]?\.?|S\.?\s?A\.?\s?U?\.?|SLU|SLP|SLL|SLNE|SAU|UNIPERSONAL|SOCIEDAD|LIMITADA|S\.?\s?COOP\.?)$"
GENERICOS = {"BAR", "RESTAURANTE", "CAFETERIA", "PELUQUERIA", "FARMACIA", "LOCUTORIO", "ALIMENTACION", "FRUTERIA",
             "TALLER", "OPTICA", "CLINICA DENTAL", "CLINICA", "GIMNASIO", "SUPERMERCADO", "ESTANCO", "BAZAR",
             "TIENDA", "MODA", "ACADEMIA", "ESCUELA INFANTIL", "CENTRO DE ESTETICA", "LAVANDERIA", "HOTEL"}
UMBRAL_NOMBRE_SOLO = 90   # match solo por nombre
UMBRAL_NOMBRE_CON_DIR = 60
MAX_CANDIDATOS_DIR = 3    # más sociedades en la misma dirección -> probable gestoría/centro de negocios


def norm_nombre(s: str | None) -> str:
    """Normaliza rótulo o denominación: sin forma jurídica, signos ni artículos sueltos."""
    s = norm(s)
    s = re.sub(r"[.,;:\"'`´()\-/&+]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(2):
        s = re.sub(FORMAS, "", s).strip()
    toks = [t for t in s.split() if t not in {"S", "L", "A", "U", "Y", "E"}]
    return " ".join(toks)


# Palabras de sector que no distinguen un negocio de otro ("CLINICA DENTAL X" vs "CLINICA DENTAL Y").
PALABRAS_SECTOR = {"CLINICA", "CLINICAS", "DENTAL", "DENTALES", "ODONTOLOGIA", "ODONTOLOGICA", "ODONTOLOGICO",
                   "CENTRO", "CENTROS", "MEDICO", "MEDICA", "MEDICOS", "ESTETICA", "SALUD", "POLICLINICA",
                   "RESTAURANTE", "RESTAURACION", "BAR", "CAFETERIA", "CAFE", "ASADOR", "TABERNA", "CERVECERIA",
                   "PELUQUERIA", "GIMNASIO", "FITNESS", "ESTUDIO", "ACADEMIA", "ESCUELA", "INFANTIL", "GRUPO",
                   "SERVICIOS", "GESTION", "Y", "DE", "DEL", "LA", "EL", "LOS", "LAS"}


def nucleo(nombre: str) -> str:
    """Parte distintiva de un nombre normalizado: sin palabras genéricas de sector."""
    return " ".join(t for t in (nombre or "").split() if t not in PALABRAS_SECTOR)


def score_distintivo(a: str, b: str) -> float:
    """Similitud 0-100 sobre el núcleo distintivo. 0 si alguno no tiene núcleo."""
    ca, cb = nucleo(a), nucleo(b)
    return nombre_score(ca, cb) if ca and cb else 0.0


def nombre_score(a: str, b: str) -> float:
    """Similitud 0-100. token_set_ratio salvo que el más corto tenga una sola palabra (evita que
    'PEPE' empareje con cualquier 'GRUPO PEPE ...')."""
    if not a or not b:
        return 0.0
    if min(len(a.split()), len(b.split())) == 1:
        return float(max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b)))
    return float(fuzz.token_set_ratio(a, b))


# --------------------------------------------------------------------------- BORME


def borme_candidatos(borme: pd.DataFrame, municipio: str = "MADRID") -> pd.DataFrame:
    """Constituciones y cambios de domicilio de la provincia de Madrid (municipio Madrid o sin dato)."""
    b = borme.copy()
    b["fecha_publicacion"] = pd.to_datetime(b["fecha_publicacion"], errors="coerce")
    b["comienzo_operaciones"] = pd.to_datetime(b.get("comienzo_operaciones"), errors="coerce")
    tipos = b["tipos_acto"].fillna("")
    mask = (b["cod_provincia"].astype(str).str.zfill(2).eq("28") | b["provincia"].fillna("").str.upper().eq("MADRID")) \
        & tipos.str.contains(r"\bconstitucion\b|\bcambio_domicilio\b")
    if municipio:
        mask &= b["municipio"].isna() | b["municipio"].fillna("").str.contains(municipio)
    b = b[mask].reset_index(drop=True)
    b["evento"] = np.where(tipos[mask].str.contains(r"\bconstitucion\b").values, "constitucion", "cambio_domicilio")
    nombres = b["nueva_denominacion"].where(b.get("nueva_denominacion").notna(), b["denominacion"]) \
        if "nueva_denominacion" in b else b["denominacion"]
    b["nombre_norm"] = [norm_nombre(x) for x in nombres]
    b["addr_key"] = [address_key(x) if isinstance(x, str) else None for x in b["domicilio"]]
    return b


# --------------------------------------------------------------------------- emparejamiento


def match(aperturas: pd.DataFrame, borme: pd.DataFrame, dias_antes: int = 730, dias_despues: int = 62,
          chunk: int = 500) -> pd.DataFrame:
    """Mejor candidato del BORME para cada apertura.

    Ventana: publicación en el BORME entre `dias_antes` antes y `dias_despues` después del mes de
    apertura (el censo es mensual y el BORME puede publicarse después de abrir).
    Niveles: A = dirección + nombre >= 60; B = solo dirección (<= 3 sociedades en esa dirección);
    C = solo nombre >= 90.
    """
    ap = aperturas.reset_index(drop=True).copy()
    ap["rotulo_norm"] = [norm_nombre(x) for x in ap["rotulo"]]
    ap["addr_key"] = [address_key(v, n) if isinstance(v, str) else None
                      for v, n in zip(ap["desc_vial_edificio"], ap["num_edificio"])]
    by_addr: dict[str, list[int]] = {}
    for j, k in enumerate(borme["addr_key"]):
        if k:
            by_addr.setdefault(k, []).append(j)
    fpub = borme["fecha_publicacion"].values.astype("datetime64[D]")
    names = borme["nombre_norm"].tolist()

    # Candidatos por nombre (vectorizado por bloques con rapidfuzz).
    cand_nombre: dict[int, list[int]] = {}
    valid = [i for i, r in enumerate(ap["rotulo_norm"]) if len(r) >= 4 and r not in GENERICOS]
    for s in range(0, len(valid), chunk):
        idx = valid[s:s + chunk]
        if not names:
            break
        m = process.cdist([ap.at[i, "rotulo_norm"] for i in idx], names, scorer=fuzz.token_set_ratio,
                          score_cutoff=UMBRAL_NOMBRE_CON_DIR, workers=-1, dtype=np.uint8)
        for row, i in enumerate(idx):
            js = np.nonzero(m[row])[0]
            if len(js):
                cand_nombre[i] = js.tolist()

    out = []
    for i, a in ap.iterrows():
        fap = np.datetime64(a["fecha_apertura"].date(), "D")
        cands = set(cand_nombre.get(i, [])) | set(by_addr.get(a["addr_key"], []) if a["addr_key"] else [])
        best = None
        for j in cands:
            lag = int((fap - fpub[j]).astype(int)) if not np.isnat(fpub[j]) else None
            if lag is None or lag > dias_antes or lag < -dias_despues:
                continue
            same_addr = bool(a["addr_key"]) and borme.at[j, "addr_key"] == a["addr_key"]
            n_addr = len(by_addr.get(a["addr_key"], [])) if same_addr else 0
            ns = nombre_score(a["rotulo_norm"], names[j]) if a["rotulo_norm"] not in GENERICOS else 0.0
            if same_addr and ns >= UMBRAL_NOMBRE_CON_DIR:
                nivel = "A_direccion_y_nombre"
            elif same_addr and n_addr <= MAX_CANDIDATOS_DIR:
                nivel = "B_direccion"
            elif ns >= UMBRAL_NOMBRE_SOLO:
                nivel = "C_nombre"
            else:
                continue
            key = (nivel, -ns, abs(lag) if lag >= 0 else 10**6 + abs(lag))
            if best is None or key < best[0]:
                best = (key, j, nivel, ns, lag)
        if best:
            _, j, nivel, ns, lag = best
            b = borme.loc[j]
            lag_com = (fap - np.datetime64(b["comienzo_operaciones"].date(), "D")).astype(int) \
                if pd.notna(b.get("comienzo_operaciones")) else None
            out.append({"match": True, "nivel_match": nivel, "score_nombre": ns, "borme_denominacion": b["denominacion"],
                        "borme_evento": b["evento"], "borme_fecha_publicacion": b["fecha_publicacion"],
                        "borme_domicilio": b["domicilio"], "borme_sector": b.get("sector"),
                        "borme_num_anuncio": b.get("num_anuncio"), "borme_id": b.get("borme_id"),
                        "lag_borme_apertura_dias": lag,
                        "lag_comienzo_apertura_dias": int(lag_com) if lag_com is not None else None})
        else:
            out.append({"match": False, "nivel_match": None})
    res = pd.concat([ap, pd.DataFrame(out)], axis=1)
    res["match"] = res["match"].fillna(False).astype(bool)
    return res


# --------------------------------------------------------------------------- resúmenes

APERTURAS_VALIDAS = ("nuevo_local", "reapertura_actividad_nueva", "cambio_actividad")


def _q(s: pd.Series, p: int):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(np.percentile(s, p)) if len(s) else np.nan


def resumen_sector(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sector, g in m.groupby("sector"):
        mm = g[g["match"]]
        lag = mm["lag_borme_apertura_dias"]
        obras = g.loc[g["meses_previos_obras"] > 0, "lag_obras_apertura_meses"]
        rows.append({
            "sector": sector, "n_aperturas": len(g), "n_match": len(mm), "pct_match": 100 * len(mm) / len(g),
            "pct_match_A": 100 * g["nivel_match"].eq("A_direccion_y_nombre").mean(),
            "pct_match_B": 100 * g["nivel_match"].eq("B_direccion").mean(),
            "pct_match_C": 100 * g["nivel_match"].eq("C_nombre").mean(),
            "pct_borme_antes_apertura": 100 * (lag > 0).mean() if len(lag) else np.nan,
            **{f"lag_borme_apertura_p{p}": _q(lag, p) for p in (10, 25, 50, 75, 90)},
            "pct_con_obras_previas": 100 * (g["meses_previos_obras"] > 0).mean(),
            **{f"lag_obras_apertura_meses_p{p}": _q(obras, p) for p in (25, 50, 75)},
        })
    return pd.DataFrame(rows).sort_values("n_aperturas", ascending=False)


def muestra_revision(m: pd.DataFrame, n_por_nivel: int = 30, seed: int = 42) -> pd.DataFrame:
    """Muestra estratificada por nivel para revisar a mano (rellenar 'es_correcto' con 1/0)."""
    cols = ["id_local", "mes_apertura", "sector", "rotulo", "desc_vial_edificio", "num_edificio", "nivel_match",
            "score_nombre", "borme_denominacion", "borme_domicilio", "borme_evento", "borme_fecha_publicacion",
            "lag_borme_apertura_dias"]
    mm = m[m["match"]]
    partes = [g.sample(min(len(g), n_por_nivel), random_state=seed) for _, g in mm.groupby("nivel_match")]
    s = pd.concat(partes) if partes else mm.head(0)
    s = s[[c for c in cols if c in s]].copy()
    s["es_correcto"] = ""
    return s


def precision(revisado: pd.DataFrame) -> pd.DataFrame:
    """Precisión por nivel a partir de la muestra revisada (es_correcto = 1/0)."""
    r = revisado.copy()
    r["es_correcto"] = pd.to_numeric(r["es_correcto"], errors="coerce")
    r = r.dropna(subset=["es_correcto"])
    if not len(r):
        return pd.DataFrame(columns=["nivel_match", "n_revisados", "n_correctos", "precision"])
    g = r.groupby("nivel_match")["es_correcto"]
    out = pd.DataFrame({"n_revisados": g.size(), "n_correctos": g.sum()}).reset_index()
    out["precision"] = out["n_correctos"] / out["n_revisados"]
    tot = pd.DataFrame([{"nivel_match": "TOTAL", "n_revisados": len(r), "n_correctos": r["es_correcto"].sum(),
                         "precision": r["es_correcto"].mean()}])
    return pd.concat([out, tot], ignore_index=True)


def informe(ap: pd.DataFrame, m: pd.DataFrame, res: pd.DataFrame, prec: pd.DataFrame | None,
            lic_res: pd.DataFrame | None) -> str:
    meses = sorted(ap["mes_apertura"].unique()) if len(ap) else []
    tipos = ap["tipo_apertura"].value_counts() if len(ap) else pd.Series(dtype=int)
    prec_txt = md_table(prec, floatfmt="{:.2f}") if prec is not None and len(prec) else \
        "_Precisión pendiente: rellenar `es_correcto` en `backtest_muestra_revision.csv` y volver a ejecutar con `--revisado`._\n"
    lic_txt = ("\n## Licencias urbanísticas y declaraciones responsables (dataset 300193, NO VALIDADO)\n"
               + md_table(lic_res)) if lic_res is not None and len(lic_res) else ""
    return f"""# Backtest: BORME -> apertura en el censo de locales de Madrid

Fuentes: [censo de locales y actividades de Madrid](https://datos.madrid.es) (dataset 200085) y BORME
sección A. Cálculo propio con `pipeline/backtest.py`. Todas las cifras son **[DATO]** derivados de
esas fuentes, sujetos a las limitaciones de emparejamiento descritas abajo.

## Aperturas detectadas
- Meses con aperturas: {", ".join(meses) or "ninguno"} (el primer mes del panel está censurado).
- Por tipo: {", ".join(f"{k} {v}" for k, v in tipos.items())}.
- Se usan en el backtest: {", ".join(APERTURAS_VALIDAS)} ({len(m)} aperturas).

## Por sector
`lag_borme_apertura` en días (positivo = el BORME se publicó antes de la apertura). La apertura se
fecha el día 1 del primer mes en que el local figura como "Abierto" (resolución de un mes).
`lag_obras_apertura_meses`: meses desde el primer mes en "obras" consecutivo previo a la apertura.

{md_table(res)}
## Precisión de los matches
Niveles: A = misma dirección y nombre >= {UMBRAL_NOMBRE_CON_DIR}; B = misma dirección (como mucho
{MAX_CANDIDATOS_DIR} sociedades en esa dirección); C = solo nombre >= {UMBRAL_NOMBRE_SOLO}.

{prec_txt}{lic_txt}
## Limitaciones
- El rótulo del censo falta a menudo y rara vez coincide con la denominación social.
- El domicilio social de muchas SL no es el local (gestoría, casa del socio): el cruce por dirección
  pierde esas aperturas y el nivel B puede emparejar sociedades distintas en el mismo edificio.
- Los autónomos (sin SL) no aparecen en el BORME: el % de match es una cota inferior de la cobertura.
- Con pocos meses de censo, los lags largos (obras de más de N-1 meses) quedan censurados.
"""


def run(censo_files: list[Path], borme_csv: Path, out_dir: Path, revisado: Path | None = None,
        licencias_files: list[Path] | None = None) -> dict[str, Path]:
    out_dir = ensure(Path(out_dir))
    panel = load_panel(censo_files)
    ap = detect_aperturas(panel)
    if not len(ap):
        raise SystemExit("No se detectaron aperturas: hacen falta al menos 2 meses de censo.")
    validas = ap[ap["tipo_apertura"].isin(APERTURAS_VALIDAS)].reset_index(drop=True)
    borme = borme_candidatos(pd.read_csv(borme_csv, dtype={"cod_provincia": str, "cnae": str}))
    m = match(validas, borme)
    res = resumen_sector(m)
    paths = {"aperturas": out_dir / "backtest_aperturas.csv", "resumen": out_dir / "backtest_resumen_sector.csv",
             "muestra": out_dir / "backtest_muestra_revision.csv", "informe": out_dir / "informe_backtest.md"}
    ap.to_csv(out_dir / "censo_aperturas_todas.csv", index=False)
    res.to_csv(paths["resumen"], index=False, float_format="%.2f")
    muestra_revision(m).to_csv(paths["muestra"], index=False)
    prec = None
    if revisado and Path(revisado).exists():
        prec = precision(pd.read_csv(revisado))
        paths["precision"] = out_dir / "backtest_precision.csv"
        prec.to_csv(paths["precision"], index=False, float_format="%.3f")
    lic_res = None
    if licencias_files:
        from .madrid_licencias import cruzar_aperturas, load_licencias, resumen_por_sector
        lic = load_licencias(licencias_files)
        m = cruzar_aperturas(m, lic)
        lic_res = resumen_por_sector(m)
        paths["licencias"] = out_dir / "backtest_licencias_sector.csv"
        lic_res.to_csv(paths["licencias"], index=False, float_format="%.2f")
    m.to_csv(paths["aperturas"], index=False)
    paths["informe"].write_text(informe(ap, m, res, prec, lic_res), encoding="utf-8")
    return paths
