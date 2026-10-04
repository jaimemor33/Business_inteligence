"""Descarga de sumarios del BORME (API de datos abiertos del BOE) y PDF de la sección A.

- Sumario:  GET https://www.boe.es/datosabiertos/api/borme/sumario/AAAAMMDD  (Accept: application/json)
- PDF:      la URL que indique el sumario (url_pdf) para cada provincia de la sección A.

Caché en disco (idempotente):
    data/raw/sumarios/AAAAMMDD.json         (o AAAAMMDD.none si ese día no hay BORME)
    data/raw/borme/AAAAMMDD/BORME-A-AAAA-NNN-PP.pdf
    data/raw/borme/manifest.csv             (una fila por PDF descargado)

El parseo del sumario es defensivo: recorre el JSON entero buscando ítems con un identificador
BORME-A-... y una URL de PDF, en lugar de depender de rutas de claves concretas.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .common import daterange, ensure, norm, provincia_code, provincia_name

log = logging.getLogger(__name__)

API_SUMARIO = "https://www.boe.es/datosabiertos/api/borme/sumario/{fecha}"
BASE = "https://www.boe.es"
USER_AGENT = "bi-pipeline/0.1 (investigacion de datos abiertos; contacto en README)"
RE_ID_A = re.compile(r"BORME-A-(\d{4})-(\d{1,4})-(\d{2})")


@dataclass
class ItemA:
    """Un PDF de la sección A (una provincia, un día)."""
    fecha: str              # AAAA-MM-DD (fecha de publicación)
    identificador: str      # BORME-A-2026-187-28
    cod_provincia: str      # '28'
    provincia: str          # 'MADRID'
    url_pdf: str
    path: str = ""          # ruta local una vez descargado
    url_xml: str = ""       # API v2.0 (28-05-2026): XML/HTML de la sección primera, si el sumario lo trae
    url_html: str = ""
    path_xml: str = ""


# --------------------------------------------------------------------------- cliente HTTP


class BoeClient:
    """Cliente con reintentos (backoff exponencial), caché en disco y rate limit."""

    def __init__(self, raw_dir: Path, min_interval: float = 1.0, retries: int = 4,
                 timeout: float = 60.0, session=None):
        self.raw_dir = Path(raw_dir)
        self.min_interval = min_interval
        self.retries = retries
        self.timeout = timeout
        self._last = 0.0
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _wait(self):
        delta = time.monotonic() - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()

    def get(self, url: str, accept: str | None = None):
        """GET con reintentos en 429/5xx/errores de red. Devuelve la respuesta (también si es 404)."""
        headers = {"Accept": accept} if accept else {}
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait()
            try:
                r = self.session.get(url, headers=headers, timeout=self.timeout)
            except Exception as e:  # requests.ConnectionError, Timeout...
                last_exc = e
                log.warning("Error de red en %s (%s), intento %d", url, e, attempt + 1)
            else:
                if r.status_code in (429, 500, 502, 503, 504):
                    ra = r.headers.get("Retry-After") if hasattr(r, "headers") else None
                    wait = float(ra) if ra and str(ra).isdigit() else 2 ** attempt * 2
                    log.warning("HTTP %s en %s; reintento en %.0fs", r.status_code, url, wait)
                    time.sleep(min(wait, 120))
                    last_exc = RuntimeError(f"HTTP {r.status_code}")
                    continue
                return r
            time.sleep(min(2 ** attempt * 2, 60))
        raise RuntimeError(f"No se pudo descargar {url}: {last_exc}")

    # ------------------------------------------------------------------ sumario

    def sumario(self, fecha: dt.date, refresh: bool = False) -> dict | None:
        """Sumario del día (dict) o None si no hay BORME ese día. Cacheado en data/raw/sumarios/."""
        d = ensure(self.raw_dir / "sumarios")
        key = fecha.strftime("%Y%m%d")
        fjson, fnone = d / f"{key}.json", d / f"{key}.none"
        if not refresh:
            if fjson.exists():
                return json.loads(fjson.read_text(encoding="utf-8"))
            if fnone.exists():
                return None
        r = self.get(API_SUMARIO.format(fecha=key), accept="application/json")
        if r.status_code == 404:
            fnone.write_text("404", encoding="utf-8")
            return None
        if r.status_code != 200:
            raise RuntimeError(f"Sumario {key}: HTTP {r.status_code}")
        data = r.json()
        status = str(_dig(data, "status", "code") or "200")
        if status == "404":
            fnone.write_text("404", encoding="utf-8")
            return None
        fjson.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data

    # ------------------------------------------------------------------ xml (API v2.0)

    def xml(self, item: ItemA, refresh: bool = False) -> Path | None:
        """Descarga el XML de la sección A si el sumario trae url_xml. No validado con datos reales."""
        if not item.url_xml:
            return None
        d = ensure(self.raw_dir / "borme" / item.fecha.replace("-", ""))
        out = d / f"{item.identificador}.xml"
        if out.exists() and out.stat().st_size > 0 and not refresh:
            return out
        r = self.get(item.url_xml, accept="application/xml")
        if r.status_code != 200 or not r.content.lstrip()[:1] == b"<":
            log.warning("XML %s: HTTP %s o contenido no XML; se usará el PDF", item.url_xml, r.status_code)
            return None
        tmp = out.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(out)
        return out

    # ------------------------------------------------------------------ pdf

    def pdf(self, item: ItemA, refresh: bool = False) -> Path:
        d = ensure(self.raw_dir / "borme" / item.fecha.replace("-", ""))
        out = d / f"{item.identificador}.pdf"
        if out.exists() and out.stat().st_size > 0 and not refresh:
            return out
        r = self.get(item.url_pdf, accept="application/pdf")
        if r.status_code != 200:
            raise RuntimeError(f"PDF {item.url_pdf}: HTTP {r.status_code}")
        content = r.content
        if not content.startswith(b"%PDF"):
            raise RuntimeError(f"{item.url_pdf} no devolvió un PDF")
        tmp = out.with_suffix(".part")
        tmp.write_bytes(content)
        tmp.replace(out)  # escritura atómica: no deja PDF a medias si se interrumpe
        return out


# --------------------------------------------------------------------------- parseo del sumario


def _dig(d: Any, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _walk(node: Any, ctx: dict):
    """Recorre el JSON y emite (item_dict, ctx) para cada dict que parezca un ítem con PDF."""
    if isinstance(node, dict):
        ctx = dict(ctx)
        # Contexto de sección: 'codigo' / 'nombre' de la sección que contiene los ítems.
        for k in ("codigo", "código", "code"):
            if k in node and isinstance(node[k], str) and len(node[k]) <= 3:
                ctx["seccion_codigo"] = node[k]
        nombre = node.get("nombre") or node.get("titulo_seccion")
        if isinstance(nombre, str) and "SECCI" in norm(nombre):
            ctx["seccion_nombre"] = nombre
        if any(k in node for k in ("url_pdf", "urlPdf", "url")) and any(
                k in node for k in ("identificador", "id", "titulo", "title")):
            yield node, ctx
        for v in node.values():
            yield from _walk(v, ctx)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, ctx)


def _url_of(item: dict, keys=("url_pdf", "urlPdf", "url")) -> str | None:
    u = next((item[k] for k in keys if item.get(k)), None)
    if isinstance(u, dict):  # {"szBytes":..., "texto": "https://..."}
        u = u.get("texto") or u.get("text") or u.get("#text") or u.get("url") or u.get("href")
    if not isinstance(u, str) or not u.strip():
        return None
    u = u.strip()
    return u if u.startswith("http") else BASE + ("" if u.startswith("/") else "/") + u


def items_seccion_a(sumario: dict, fecha: dt.date) -> list[ItemA]:
    """Extrae los PDF de la sección A (uno por provincia) de un sumario, de forma defensiva.

    Un ítem es de la sección A si su identificador/URL contiene 'BORME-A-' o si cuelga de una
    sección con código 'A' o nombre 'SECCIÓN PRIMERA'. Se descartan los PDF que no
    correspondan a una provincia (p. ej. índices).
    """
    out: dict[str, ItemA] = {}
    for it, ctx in _walk(sumario, {}):
        url = _url_of(it)
        ident = str(it.get("identificador") or it.get("id") or "")
        m = RE_ID_A.search(ident) or (RE_ID_A.search(url) if url else None)
        otra = re.search(r"BORME-([A-Z])-", ident + " " + (url or ""))
        if otra and otra.group(1) != "A":  # sección B (otros actos), C (anuncios), S (sumario)...
            continue
        cod_sec = ctx.get("seccion_codigo")
        en_seccion_a = cod_sec == "A" or (cod_sec is None and "ACTOS INSCRITOS" in norm(ctx.get("seccion_nombre", "")))
        if not url or not (m or en_seccion_a) or not url.lower().endswith(".pdf"):
            continue
        titulo = str(it.get("titulo") or it.get("title") or "")
        cod = m.group(3) if m else provincia_code(titulo)
        if cod is None or provincia_name(cod) is None:
            continue
        ident = m.group(0) if m else Path(url).stem
        out[ident] = ItemA(fecha=fecha.isoformat(), identificador=ident, cod_provincia=cod,
                           provincia=provincia_name(cod) or norm(titulo), url_pdf=url,
                           url_xml=_url_of(it, ("url_xml", "urlXml", "xml", "url_XML")) or "",
                           url_html=_url_of(it, ("url_html", "urlHtml", "html", "url_HTML")) or "")
    if not out:  # último recurso: buscar URLs de PDF de la sección A en el JSON serializado
        raw = json.dumps(sumario, ensure_ascii=False)
        for u in set(re.findall(r"(?:https?://www\.boe\.es)?/borme/dias/[\w/]+/BORME-A-\d{4}-\d+-\d{2}\.pdf", raw)):
            m = RE_ID_A.search(u)
            if m and provincia_name(m.group(3)):
                out[m.group(0)] = ItemA(fecha.isoformat(), m.group(0), m.group(3), provincia_name(m.group(3)),
                                        u if u.startswith("http") else BASE + u)
    return sorted(out.values(), key=lambda x: x.identificador)


# --------------------------------------------------------------------------- orquestación

MANIFEST_FIELDS = list(ItemA.__dataclass_fields__)


def _append_manifest(raw_dir: Path, items: Iterable[ItemA]):
    path = ensure(raw_dir / "borme") / "manifest.csv"
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            existing = {r["identificador"]: r for r in csv.DictReader(f)}
    for it in items:
        existing[it.identificador] = asdict(it)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        for k in sorted(existing):
            w.writerow({c: existing[k].get(c, "") for c in MANIFEST_FIELDS})


def fetch(desde: dt.date, hasta: dt.date, provincias: set[str] | None, raw_dir: Path,
          client: BoeClient | None = None, refresh: bool = False, solo_sumarios: bool = False,
          formato: str = "xml") -> list[ItemA]:
    """Descarga sumarios y XML/PDF de la sección A para el rango y provincias (códigos INE) dados.

    formato='xml' (por defecto): XML oficial y el PDF solo si el XML falla; 'ambos': los dos.
    """
    client = client or BoeClient(raw_dir)
    done: list[ItemA] = []
    for fecha in daterange(desde, hasta):
        try:
            s = client.sumario(fecha, refresh=refresh)
        except Exception as e:
            log.error("Sumario %s: %s", fecha, e)
            continue
        if s is None:
            log.info("%s: sin BORME", fecha)
            continue
        items = [i for i in items_seccion_a(s, fecha) if provincias is None or i.cod_provincia in provincias]
        log.info("%s: %d PDF de la sección A seleccionados", fecha, len(items))
        if solo_sumarios:
            continue
        for it in items:
            try:
                px = client.xml(it, refresh=refresh)
                it.path_xml = str(px) if px else ""
            except Exception as e:
                log.warning("XML %s: %s", it.identificador, e)
            if formato == "ambos" or not it.path_xml:
                try:
                    it.path = str(client.pdf(it, refresh=refresh))
                except Exception as e:
                    log.error("PDF %s: %s", it.identificador, e)
            if it.path or it.path_xml:
                done.append(it)
        _append_manifest(raw_dir, done)
    return done
