"""Línea de comandos del pipeline.

    python -m pipeline.cli fetch    --desde 2026-04-01 --hasta 2026-09-30 --provincias MADRID,BARCELONA
    python -m pipeline.cli parse    --desde 2026-04-01 --hasta 2026-09-30 --provincias MADRID
    python -m pipeline.cli classify [--llm] [--umbral 0.6]
    python -m pipeline.cli metrics
    python -m pipeline.cli backtest --censo data/raw/censo/*.csv [--revisado muestra.csv] [--licencias data/raw/licencias/*.csv]
    python -m pipeline.cli all      --desde ... --hasta ... --provincias ...   (fetch+parse+classify+metrics)
"""
from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

from .common import data_dir, ensure, parse_iso, parse_provincias

log = logging.getLogger("pipeline")


def _paths(args) -> dict[str, Path]:
    d = data_dir(args.data_dir)
    return {"raw": d / "raw", "interim": d / "interim", "processed": d / "processed", "output": d / "output"}


def _expand(patterns: list[str] | None) -> list[Path]:
    out: list[Path] = []
    for p in patterns or []:
        if Path(p).is_dir():
            hits = [str(x) for x in Path(p).iterdir() if x.suffix.lower() in (".csv", ".xls", ".xlsx", ".json")]
        else:
            hits = glob.glob(p)
        out.extend(Path(h) for h in hits)
    return sorted(set(out))


def cmd_fetch(args):
    from .borme_fetch import BoeClient, fetch
    P = _paths(args)
    client = BoeClient(P["raw"], min_interval=args.pausa)
    items = fetch(parse_iso(args.desde), parse_iso(args.hasta), parse_provincias(args.provincias), P["raw"],
                  client=client, refresh=args.refresh, solo_sumarios=args.solo_sumarios)
    print(f"Descargados/en caché: {len(items)} BORME de la sección A en {P['raw'] / 'borme'}")


def cmd_parse(args):
    from .borme_parse import parse_dir
    P = _paths(args)
    df = parse_dir(P["raw"], parse_iso(args.desde) if args.desde else None, parse_iso(args.hasta) if args.hasta else None,
                   parse_provincias(args.provincias), engine=args.engine)
    out = ensure(P["processed"]) / "borme_actos.csv"
    df.to_csv(out, index=False)
    ok = 100 * df["parse_ok"].mean() if len(df) else 0
    print(f"{len(df)} anuncios -> {out} ({ok:.1f} % sin avisos)")


def cmd_classify(args):
    from .classify import apply_llm, classify_frame
    P = _paths(args)
    df = pd.read_csv(P["processed"] / "borme_actos.csv", dtype={"cod_provincia": str, "cnae": str, "codigo_postal": str})
    df = classify_frame(df)
    if args.llm:
        df = apply_llm(df, P["interim"] / "llm_cache.jsonl", umbral=args.umbral, max_filas=args.max_llm,
                       todos=getattr(args, "llm_todo", False))
    out = P["processed"] / "borme_clasificado.csv"
    df.to_csv(out, index=False)
    print(f"Clasificados {len(df)} -> {out}")
    print(df["sector"].value_counts().head(15).to_string())


def cmd_metrics(args):
    from .metrics import run
    P = _paths(args)
    paths = run(P["processed"] / "borme_clasificado.csv", P["output"])
    print("\n".join(f"{k}: {v}" for k, v in paths.items()))


def cmd_backtest(args):
    from .backtest import run
    P = _paths(args)
    censo = _expand(args.censo) or _expand([str(P["raw"] / "censo")])
    if len(censo) < 2:
        sys.exit("Hacen falta al menos 2 ficheros mensuales del censo (--censo).")
    lic = _expand(args.licencias) if args.licencias else None
    paths = run(censo, Path(args.borme) if args.borme else P["processed"] / "borme_clasificado.csv", P["output"],
                revisado=Path(args.revisado) if args.revisado else None, licencias_files=lic)
    print("\n".join(f"{k}: {v}" for k, v in paths.items()))


def _borme_constituciones(args):
    """Descarga (XML), parsea, clasifica (Claude en constituciones si hay clave) y marca el ruido.
    Devuelve (constituciones preparadas, texto de método de clasificación)."""
    import os
    from . import fase1, noise
    from .borme_fetch import BoeClient, fetch
    from .borme_parse import parse_dir
    from .classify import LLM_MODEL, apply_llm, classify_frame
    P = _paths(args)
    provs = parse_provincias(args.provincias)
    desde, hasta = parse_iso(args.desde), parse_iso(args.hasta)
    if not args.sin_fetch:
        fetch(desde, hasta, provs, P["raw"], client=BoeClient(P["raw"], min_interval=args.pausa), formato="xml")
    df = parse_dir(P["raw"], desde, hasta, provs)
    if df.empty:
        sys.exit("No hay anuncios parseados: revisa la descarga (¿acceso a www.boe.es?).")
    ensure(P["processed"])
    df.to_csv(P["processed"] / "borme_actos.csv", index=False)
    df = classify_frame(df)
    clasif = "reglas (CNAE + palabras clave)"
    es_const = df["evento_principal"] == "constitucion"
    if not args.sin_llm and os.environ.get("ANTHROPIC_API_KEY"):
        sub = apply_llm(df[es_const], P["interim"] / "llm_cache.jsonl", todos=True, max_filas=args.max_llm)
        for col in sub.columns:
            df.loc[sub.index, col] = sub[col]
        clasif = f"Claude ({LLM_MODEL}) sobre todas las constituciones; reglas para el resto de actos"
    elif not args.sin_llm:
        clasif += " (ANTHROPIC_API_KEY no definida: sin LLM, sin categoría 'generico')"
    df.to_csv(P["processed"] / "borme_clasificado.csv", index=False)
    const = fase1.preparar(noise.marcar(df))
    const.to_csv(P["processed"] / "constituciones_fase1.csv", index=False)
    return const, clasif


def cmd_fase1(args):
    """Fase 1 (variante Google con reseñas): BORME -> clasificación -> ruido -> Places -> research/BACKTEST.md."""
    import os
    from . import fase1, places
    P = _paths(args)
    const, clasif = _borme_constituciones(args)
    pl, gasto = None, None
    sectores = args.sectores.split(",") if args.sectores else None
    cands = fase1.muestra(const, args.muestra_por_celda, sectores=sectores)
    if os.environ.get("GOOGLE_PLACES_API_KEY") or os.environ.get("GOOGLE_MAPS_API_KEY"):
        pl, gasto = places.run(cands, P["interim"], args.places_presupuesto)
        pl.to_csv(P["processed"] / "places_backtest.csv", index=False)
    else:
        log.warning("GOOGLE_PLACES_API_KEY no definida: se omite el backtest de Places")
    T = fase1.tablas(const, pl)
    crit = fase1.criterios(T)
    meta = {"desde": args.desde, "hasta": args.hasta, "provincias": args.provincias, "meses": const["mes"].nunique(),
            "n_const": len(const), "clasif": clasif, "n_places": 0 if pl is None else len(pl),
            "por_celda": args.muestra_por_celda}
    p = fase1.informe(T, crit, gasto, meta, Path(args.research_dir))
    print(f"Informe: {p}")
    print(crit[["ciudad", "sector", "aperturas_nuevas_mes", "pct_localizable", "lag_mediana_dias", "veredicto"]]
          .head(40).to_string(index=False))


def cmd_fase1_oficial(args):
    """Fase 1 con fuentes oficiales primero: BORME -> REGCESS (dental) -> censo de Madrid -> Google (básico)."""
    import os
    from . import censo_borme, fase1_oficial as F, places, regcess
    from .madrid_census import load_panel
    P = _paths(args)
    if not args.sin_fetch and not (args.regcess or args.censo):
        from .descargas import descargar_todo, separar_censo
        d = descargar_todo(P["raw"])
        cen_files, lic_files = separar_censo(d["censo_historico"] + d["censo_actual"])
        args.censo = [str(x) for x in cen_files]
        args.licencias_censo = args.licencias_censo or [str(x) for x in lic_files]
        args.regcess = [str(x) for x in d["regcess_ministerio"] + d["centros_sanitarios_cam"]]
    const, clasif = _borme_constituciones(args)
    fuentes = {"BORME": f"{const['mes'].nunique()} meses, {len(const)} constituciones (provincias {args.provincias})"}
    mad = const[const["ciudad"] == "MADRID"]
    base = mad[mad["objetivo"] & (mad["ruido_tipo"] == "apertura_nueva")]
    out = {"volumen": F.volumen(const)}
    meta = {"clasif": clasif, "pct_generico": float((mad["sector"] == "generico").mean()) if len(mad) else float("nan"),
            "google_tope": args.google_tope}
    # 1. REGCESS (dental, toda la Comunidad de Madrid)
    m_reg = None
    reg_files = _expand(args.regcess) if args.regcess else []
    if reg_files:
        snaps = regcess.load_snapshots(reg_files)
        cen, metodo = regcess.centros(snaps)
        sl = const[(const["cod_provincia"].astype(str).str.zfill(2) == "28") & (const["sector"] == "dental")
                   & (const["ruido_tipo"] == "apertura_nueva")]
        m_reg = regcess.cruzar(sl, cen)
        corte = snaps["snapshot"].max() if snaps["snapshot"].notna().any() else pd.Timestamp.today()
        out["regcess_resumen"], out["regcess_detalle"] = regcess.resumen(m_reg, corte), m_reg
        meta["regcess_metodo"] = metodo
        fuentes["REGCESS"] = f"{len(reg_files)} fichero(s), {len(cen)} centros dentales; {metodo}"
    else:
        fuentes["REGCESS"] = "NO DISPONIBLE en esta ejecución (pasar --regcess)"
    # 2. Censo de locales + licencias (municipio de Madrid)
    m_c = None
    censo_files = _expand(args.censo) if args.censo else []
    if len(censo_files) >= 2:
        panel = load_panel(censo_files)
        hist = censo_borme.historia_locales(panel)
        m_c = censo_borme.cruzar_sl(base, hist)
        out["censo_resumen"], out["censo_detalle"] = F.resumen_censo(m_c), m_c
        ok = m_c[m_c["match"].fillna(False).astype(bool)]
        out["censo_muestra_revision"] = ok.groupby("nivel_match", group_keys=False).apply(
            lambda g: g.sample(min(len(g), 30), random_state=42))
        fuentes["CENSO"] = f"{panel['mes'].nunique()} meses ({panel['mes'].min()} a {panel['mes'].max()}), {len(hist)} locales"
        lic_files = _expand(args.licencias_censo) if args.licencias_censo else []
        if lic_files:
            lic = censo_borme.load_licencias_censo(lic_files)
            out["senales"], out["senal_resumen"] = censo_borme.senal_temprana(panel, lic, m_c)
            fuentes["CENSO-LICENCIAS"] = f"{len(lic)} licencias, {int(lic['en_tramitacion'].sum())} en tramitación"
        else:
            fuentes["CENSO-LICENCIAS"] = "NO DISPONIBLE (pasar --licencias-censo)"
    else:
        fuentes["CENSO"] = "NO DISPONIBLE (hacen falta ≥ 2 meses en --censo)"
    # 3. Google solo para las no emparejadas
    comb = F.combinar(out["volumen"], m_reg, m_c, None, base)
    pl = None
    if os.environ.get("GOOGLE_PLACES_API_KEY") or os.environ.get("GOOGLE_MAPS_API_KEY"):
        sin = base[base["empresa_key"].isin(comb.loc[~comb["ok_oficial"], "empresa_key"])]
        partes = [g.sample(min(len(g), args.google_por_sector), random_state=7) for _, g in sin.groupby("sector")]
        cands = pd.concat(partes) if partes else sin.head(0)
        pl, gasto = places.run(cands, P["interim"], args.google_tope, basico=True)
        out["google_detalle"] = pl
        meta.update(n_google=len(pl), google_usd=gasto.usd)
        fuentes["GOOGLE"] = f"{len(pl)} sociedades sin emparejar consultadas (básico, sin reseñas)"
    else:
        fuentes["GOOGLE"] = "NO DISPONIBLE (GOOGLE_PLACES_API_KEY no definida)"
    comb = F.combinar(out["volumen"], m_reg, m_c, pl, base)
    out["combinado"] = comb
    out["criterios"] = F.criterios(out["volumen"], comb, m_c, m_reg)
    meta["fuentes"] = fuentes
    p = F.informe(out, meta, Path(args.research_dir))
    print(f"Informe: {p}")
    if len(out["criterios"]):
        print(out["criterios"][["sector", "veredicto"]].to_string(index=False))


def cmd_descargar(args):
    from .descargas import descargar_todo
    res = descargar_todo(_paths(args)["raw"])
    for k, v in res.items():
        print(f"{k}: {len(v)} ficheros")


def cmd_all(args):
    for f in (cmd_fetch, cmd_parse, cmd_classify, cmd_metrics):
        f(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline", description="BORME-A + censo de locales de Madrid")
    p.add_argument("--data-dir", default=None, help="directorio de datos (por defecto ./data o $BI_DATA_DIR)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def fechas(sp, required):
        sp.add_argument("--desde", required=required, help="AAAA-MM-DD")
        sp.add_argument("--hasta", required=required, help="AAAA-MM-DD")
        sp.add_argument("--provincias", default=None, help="MADRID,BARCELONA o códigos INE (28,08); por defecto todas")

    sp = sub.add_parser("fetch", help="descarga sumarios y PDF/XML de la sección A")
    fechas(sp, True)
    sp.add_argument("--refresh", action="store_true", help="ignora la caché")
    sp.add_argument("--solo-sumarios", action="store_true")
    sp.add_argument("--pausa", type=float, default=1.0, help="segundos mínimos entre peticiones (rate limit)")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("parse", help="PDF/XML -> data/processed/borme_actos.csv")
    fechas(sp, False)
    sp.add_argument("--engine", choices=["auto", "pdfplumber", "pypdf"], default="auto")
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("classify", help="clasificación sectorial (reglas + LLM opcional)")
    sp.add_argument("--llm", action="store_true", help="usar Claude para los casos de baja confianza (requiere ANTHROPIC_API_KEY)")
    sp.add_argument("--umbral", type=float, default=0.6)
    sp.add_argument("--max-llm", type=int, default=None, help="límite de filas enviadas al LLM")
    sp.add_argument("--llm-todo", action="store_true", help="clasificar con Claude todas las filas (no solo las dudosas)")
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("metrics", help="agregados e informe markdown")
    sp.set_defaults(func=cmd_metrics)

    sp = sub.add_parser("backtest", help="cruce con el censo de locales de Madrid")
    sp.add_argument("--censo", nargs="+", help="ficheros CSV mensuales (o un directorio)")
    sp.add_argument("--borme", default=None, help="CSV clasificado (por defecto data/processed/borme_clasificado.csv)")
    sp.add_argument("--revisado", default=None, help="muestra de revisión con es_correcto rellenado")
    sp.add_argument("--licencias", nargs="+", default=None, help="ficheros del dataset 300193 (opcional, no validado)")
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("all", help="fetch + parse + classify + metrics")
    fechas(sp, True)
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument("--solo-sumarios", action="store_true")
    sp.add_argument("--pausa", type=float, default=1.0)
    sp.add_argument("--engine", choices=["auto", "pdfplumber", "pypdf"], default="auto")
    sp.add_argument("--llm", action="store_true")
    sp.add_argument("--umbral", type=float, default=0.6)
    sp.add_argument("--max-llm", type=int, default=None)
    sp.set_defaults(func=cmd_all)
    sp = sub.add_parser("fase1", help="fase 1 completa con datos reales -> research/BACKTEST.md")
    fechas(sp, True)
    sp.set_defaults(provincias="MADRID,BARCELONA")
    sp.add_argument("--sin-fetch", action="store_true", help="usar solo lo ya descargado")
    sp.add_argument("--pausa", type=float, default=1.0)
    sp.add_argument("--sin-llm", action="store_true")
    sp.add_argument("--max-llm", type=int, default=None)
    sp.add_argument("--places-presupuesto", type=float, default=100.0, help="tope duro de gasto en Places (USD)")
    sp.add_argument("--muestra-por-celda", type=int, default=60, help="sociedades por sector × ciudad en Places")
    sp.add_argument("--sectores", default=None, help="limitar el backtest de Places a estos sectores (coma)")
    sp.add_argument("--research-dir", default="research")
    sp.set_defaults(func=cmd_fase1)

    sp = sub.add_parser("descargar", help="descarga REGCESS, centros sanitarios CAM, censo y licencias de Madrid")
    sp.set_defaults(func=cmd_descargar)

    sp = sub.add_parser("fase1-oficial", help="fase 1 con REGCESS + censo de Madrid + Google (básico) -> research/BACKTEST.md")
    fechas(sp, True)
    sp.set_defaults(provincias="MADRID")
    sp.add_argument("--sin-fetch", action="store_true")
    sp.add_argument("--pausa", type=float, default=1.0)
    sp.add_argument("--sin-llm", action="store_true")
    sp.add_argument("--max-llm", type=int, default=None)
    sp.add_argument("--regcess", nargs="*", help="ficheros o carpeta con las descargas del REGCESS / CAM (xlsx, csv, json)")
    sp.add_argument("--censo", nargs="*", help="CSV mensuales del censo de locales (histórico 209548)")
    sp.add_argument("--licencias-censo", nargs="*", help="fichero(s) de locales con información de licencias")
    sp.add_argument("--google-tope", type=float, default=20.0, help="tope duro de gasto en Google Places (USD)")
    sp.add_argument("--google-por-sector", type=int, default=40)
    sp.add_argument("--research-dir", default="research")
    sp.set_defaults(func=cmd_fase1_oficial)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    args.func(args)


if __name__ == "__main__":
    main()
