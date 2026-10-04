"""Descarga automática de las fuentes oficiales de la fase 1 (sin pasos manuales).

- Portales CKAN (datos.madrid.es y datos.comunidad.madrid): `package_show` da la lista de recursos y se bajan
  los CSV, XLS y JSON. Si la API no responde, se buscan enlaces de descarga en la página HTML del dataset.
- REGCESS: la página del área de descarga del Ministerio se recorre en busca de enlaces a ficheros Excel.
  Si la descarga exige un formulario con sesión y no hay enlaces directos, se registra como NO AUTOMATIZABLE
  y la pipeline usa la alternativa diaria de la Comunidad de Madrid.

NO PROBADO CONTRA LOS PORTALES REALES (red bloqueada en el desarrollo). Cada descarga queda anotada en
data/raw/descargas_manifest.csv con la URL, el tamaño y la fecha.
"""
from __future__ import annotations

import csv
import datetime as dt
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

from .common import ensure

log = logging.getLogger(__name__)

DATASETS = {
    # nombre lógico: (base CKAN, id del dataset, subcarpeta en data/raw)
    "censo_historico": ("https://datos.madrid.es", "209548-0-censo-locales-historico", "censo"),
    "censo_actual": ("https://datos.madrid.es", "200085-0-censo-locales", "censo"),
    "licencias_urbanisticas": ("https://datos.madrid.es", "300193-0-licencias-urbanisticas", "licencias"),
    "centros_sanitarios_cam": ("https://datos.comunidad.madrid", "centros_servicios_establecimientos_sanitarios", "regcess"),
}
REGCESS_URL = "http://regcess.mscbs.es/regcessWeb/inicioDescargarCentrosAction.do"
EXT = (".csv", ".xls", ".xlsx", ".json", ".zip")


def _session(session=None):
    if session is not None:
        return session
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "BusinessIntelligence-research/1.0 (datos abiertos; contacto en el repositorio)"
    return s


def _manifest(raw: Path, filas: list[dict]):
    f = ensure(raw) / "descargas_manifest.csv"
    nuevo = not f.exists()
    with f.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["fecha", "fuente", "url", "fichero", "bytes", "estado"])
        if nuevo:
            w.writeheader()
        w.writerows(filas)


def _bajar(s, url: str, destino: Path, pausa: float) -> tuple[str, int]:
    if destino.exists() and destino.stat().st_size > 0:
        return "cache", destino.stat().st_size
    r = s.get(url, timeout=120)
    time.sleep(pausa)
    if r.status_code != 200 or not r.content:
        return f"http_{r.status_code}", 0
    tmp = destino.with_suffix(destino.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.rename(destino)
    return "ok", len(r.content)


def recursos_ckan(s, base: str, dataset: str) -> list[str]:
    """URLs de recursos descargables de un dataset CKAN (API y, si falla, HTML)."""
    urls: list[str] = []
    try:
        r = s.get(f"{base}/api/3/action/package_show", params={"id": dataset}, timeout=60)
        if r.status_code == 200 and r.json().get("success"):
            urls = [x.get("url") for x in r.json()["result"].get("resources", []) if x.get("url")]
    except Exception as e:  # API no disponible o no es CKAN
        log.info("CKAN %s/%s: %s; se prueba el HTML", base, dataset, e)
    if not urls:
        r = s.get(f"{base}/dataset/{dataset}", timeout=60)
        if r.status_code == 200:
            urls = [urljoin(base, u) for u in re.findall(r'href="([^"]+)"', r.text)]
    return sorted({u for u in urls if u.lower().split("?")[0].endswith(EXT) or "/download" in u.lower()})


def descargar_ckan(nombre: str, raw: Path, session=None, pausa: float = 1.0) -> list[Path]:
    base, ds, sub = DATASETS[nombre]
    s = _session(session)
    d = ensure(Path(raw) / sub)
    hoy = dt.date.today().isoformat()
    out, filas = [], []
    for u in recursos_ckan(s, base, ds):
        nombre_f = re.sub(r"[^\w.\-]", "_", u.rstrip("/").split("/")[-1].split("?")[0]) or "recurso"
        if not nombre_f.lower().endswith(EXT):
            nombre_f += ".csv"
        if sub == "regcess":  # foto diaria: la fecha en el nombre sirve para la "primera aparición"
            nombre_f = f"{Path(nombre_f).stem}_{hoy}{Path(nombre_f).suffix}"
        dest = d / nombre_f
        estado, n = _bajar(s, u, dest, pausa)
        filas.append({"fecha": hoy, "fuente": nombre, "url": u, "fichero": str(dest), "bytes": n, "estado": estado})
        if estado in ("ok", "cache"):
            out.append(dest)
    _manifest(Path(raw), filas)
    log.info("%s: %d ficheros", nombre, len(out))
    return out


def descargar_regcess(raw: Path, session=None, pausa: float = 1.0) -> list[Path]:
    """Intenta bajar los Excel del área de descarga del REGCESS. Lista vacía = no automatizable con GET."""
    s = _session(session)
    d = ensure(Path(raw) / "regcess")
    hoy = dt.date.today().isoformat()
    r = s.get(REGCESS_URL, timeout=60)
    links = [urljoin(REGCESS_URL, u) for u in re.findall(r'href="([^"]+)"', r.text or "")] if r.status_code == 200 else []
    links = [u for u in links if re.search(r"\.(xlsx?|zip)(\?|$)|descarga", u, re.I) and "Manual" not in u]
    out, filas = [], []
    for u in links:
        slug = re.sub(r"[^\w]", "_", u.split("/")[-1])[:60]
        dest = d / f"regcess_{slug}_{hoy}.xlsx"
        estado, n = _bajar(s, u, dest, pausa)
        if estado == "ok" and dest.read_bytes()[:4] not in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0"):
            dest.unlink()  # era una página HTML, no un Excel
            estado = "no_excel"
        filas.append({"fecha": hoy, "fuente": "regcess", "url": u, "fichero": str(dest), "bytes": n, "estado": estado})
        if estado in ("ok", "cache"):
            out.append(dest)
    if not out:
        filas.append({"fecha": hoy, "fuente": "regcess", "url": REGCESS_URL, "fichero": "", "bytes": 0,
                      "estado": "NO_AUTOMATIZABLE_CON_GET"})
        log.warning("REGCESS: sin enlaces directos a Excel; usar la alternativa de la Comunidad de Madrid")
    _manifest(Path(raw), filas)
    return out


def descargar_todo(raw: Path, session=None) -> dict[str, list[Path]]:
    res = {k: descargar_ckan(k, raw, session) for k in DATASETS}
    res["regcess_ministerio"] = descargar_regcess(raw, session)
    return res


def separar_censo(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    """Separa los ficheros del censo en (locales/actividades mensuales, licencias). Descarta terrazas."""
    censo, lic = [], []
    for p in paths:
        n = p.name.upper()
        if "TERRAZ" in n or "HORARIO" in n:
            continue
        (lic if "LICENC" in n else censo).append(p)
    return censo, lic
