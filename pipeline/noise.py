"""Filtro de ruido de la fase 1: separa las aperturas nuevas de las reestructuraciones o expansiones,
los holdings y las patrimoniales.

Entrada: todos los anuncios parseados y clasificados (borme_clasificado.csv). Cada anuncio trae
`admins_id` y `socio_unico_id`: seudónimo HMAC si es persona física, denominación si es persona jurídica.

Para cada constitución se calcula:
- `ruido_tipo`:
  - `holding_patrimonial`: sector 'ruido' (tenencia de participaciones, patrimonial, inversión, inmobiliaria).
  - `filial_de_grupo`: administrador o socio único persona jurídica (sociedad de un grupo o cadena).
  - `expansion_mismo_sector`: algún administrador administra OTRA sociedad del mismo sector en el histórico descargado.
  - `apertura_nueva`: el resto.
- `admin_otras_sociedades`: nº de otras sociedades (distinta hoja registral o denominación) que comparten
  administrador o socio único, en cualquier sector.

Limitación (MEDIDO solo dentro de la ventana): solo se ven las sociedades con algún acto publicado en el
periodo descargado. Una persona que administra desde 2015 otra sociedad sin actos recientes no aparece.
Por eso el % de expansiones es una COTA INFERIOR. Para afinarlo, descarga un histórico más largo (el XML
es ligero): `fetch --desde` 24-36 meses antes.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

NO_SECTOR = {"ruido", "otros", "generico", "sin_clasificar", None, ""}


def _true(v) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1")


def _ids(row) -> set[str]:
    out = set()
    for col in ("admins_id", "socio_unico_id"):
        v = row.get(col)
        if isinstance(v, str) and v:
            out.update(x for x in v.split("|") if x)
    return out


def _empresa_key(row) -> str:
    h = row.get("hoja_registral")
    return f"H:{h}" if isinstance(h, str) and h else f"D:{row.get('denominacion_base') or row.get('denominacion')}"


def sector_por_empresa(df: pd.DataFrame) -> dict[str, str]:
    """Sector más informativo de cada sociedad: el de su constitución o cambio de objeto si lo hay; si no,
    el de cualquier anuncio con sector distinto de 'sin_clasificar'."""
    prio = {"constitucion": 0, "cambio_objeto": 1, "ampliacion_objeto": 2}
    d = df.assign(_k=df.apply(_empresa_key, axis=1),
                  _p=df["evento_principal"].map(prio).fillna(9))
    d = d[d["sector"].notna() & (d["sector"] != "sin_clasificar")].sort_values("_p")
    return d.groupby("_k")["sector"].first().to_dict()


def marcar(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las constituciones con las columnas `empresa_key`, `admin_otras_sociedades`,
    `otras_mismo_sector` y `ruido_tipo`."""
    df = df.copy()
    for col in ("admins_id", "socio_unico_id", "hoja_registral", "denominacion_base",
                "admin_persona_juridica", "socio_unico_persona_juridica"):
        if col not in df.columns:
            df[col] = None
    df["empresa_key"] = df.apply(_empresa_key, axis=1)
    sect = sector_por_empresa(df)
    # índice persona/PJ -> sociedades en las que aparece como administrador o socio único
    por_id: dict[str, set[str]] = {}
    for row in df[["admins_id", "socio_unico_id", "empresa_key"]].to_dict("records"):
        for i in _ids(row):
            por_id.setdefault(i, set()).add(row["empresa_key"])

    const = df[df["evento_principal"] == "constitucion"].copy()
    otras, mismo, tipo = [], [], []
    for row in const.to_dict("records"):
        ids = _ids(row)
        emp = row["empresa_key"]
        rel = set().union(*(por_id.get(i, set()) for i in ids)) - {emp} if ids else set()
        s = row.get("sector")
        n_mismo = sum(1 for e in rel if sect.get(e) == s) if s not in NO_SECTOR else 0
        otras.append(len(rel))
        mismo.append(n_mismo)
        if s == "ruido":
            tipo.append("holding_patrimonial")
        elif _true(row.get("admin_persona_juridica")) or _true(row.get("socio_unico_persona_juridica")):
            tipo.append("filial_de_grupo")
        elif n_mismo > 0:
            tipo.append("expansion_mismo_sector")
        else:
            tipo.append("apertura_nueva")
    const["admin_otras_sociedades"] = otras
    const["otras_mismo_sector"] = mismo
    const["ruido_tipo"] = tipo
    log.info("Ruido: %s", const["ruido_tipo"].value_counts().to_dict())
    return const
