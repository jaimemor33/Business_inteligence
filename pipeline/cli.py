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
            hits = [str(x) for x in Path(p).iterdir() if x.suffix.lower() in (".csv", ".xls", ".xlsx")]
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
        df = apply_llm(df, P["interim"] / "llm_cache.jsonl", umbral=args.umbral, max_filas=args.max_llm)
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
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    args.func(args)


if __name__ == "__main__":
    main()
