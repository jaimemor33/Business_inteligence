import datetime as dt
import json

import pytest

from pipeline.borme_fetch import BoeClient, fetch, items_seccion_a
from pipeline.common import address_key, parse_fecha, parse_importe, parse_provincias, provincia_code


def test_fechas_e_importes():
    assert parse_fecha("15.07.26") == dt.date(2026, 7, 15)
    assert parse_fecha("1.9.2026") == dt.date(2026, 9, 1)
    assert parse_fecha("15/07/2026") == dt.date(2026, 7, 15)
    assert parse_fecha("3 de marzo de 2026") == dt.date(2026, 3, 3)
    assert parse_fecha("32.13.26") is None
    assert parse_importe("3.000,00 Euros") == 3000.0
    assert parse_importe("1.500.000,50 Euros") == 1500000.5
    assert parse_importe("500.000 Ptas") == pytest.approx(3005.06, abs=0.01)


def test_provincias():
    assert provincia_code("Madrid") == "28"
    assert provincia_code("ALICANTE/ALACANT") == "03"
    assert provincia_code("8") == "08"
    assert parse_provincias("MADRID,BARCELONA") == {"28", "08"}
    assert parse_provincias(None) is None
    with pytest.raises(ValueError):
        parse_provincias("ATLANTIDA")


def test_address_key():
    assert address_key("C/ ALCALA 123 BAJO (MADRID)") == "ALCALA|123"
    assert address_key("ALCALA", "123") == "ALCALA|123"
    assert address_key("PLAZA DE OLAVIDE 3 PB (MADRID)") == address_key("OLAVIDE", "3")
    assert address_key("AVDA DE LA ALBUFERA 200 1º A (MADRID)") == "ALBUFERA|200"


# --------------------------------------------------------------------------- fetch con HTTP simulado


class FakeResp:
    def __init__(self, status, content=b"", data=None):
        self.status_code, self.content, self._data, self.headers = status, content, data, {}

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, fix, fail_first=0):
        self.fix, self.calls, self.headers, self.fail_first = fix, [], {}, fail_first

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        if self.fail_first:
            self.fail_first -= 1
            return FakeResp(503)
        if "/sumario/" in url:
            f = self.fix / "sumarios" / f"{url.rsplit('/', 1)[1]}.json"
            if not f.exists():
                return FakeResp(404, data={"status": {"code": "404", "text": "No se encontraron datos"}})
            return FakeResp(200, data=json.loads(f.read_text(encoding="utf-8")))
        if url.endswith(".pdf"):
            return FakeResp(200, content=b"%PDF-1.4 sintetico")
        if "xml.php" in url:
            return FakeResp(200, content=b"<?xml version='1.0'?><documento/>")
        return FakeResp(404)


def test_items_seccion_a_defensivo(fix):
    s = json.loads((fix / "sumarios" / "20260602.json").read_text(encoding="utf-8"))
    items = items_seccion_a(s, dt.date(2026, 6, 2))
    assert [i.identificador for i in items] == ["BORME-A-2026-103-08", "BORME-A-2026-103-28"]  # sin índice (99) ni B/C
    assert items[1].provincia == "MADRID" and items[1].url_pdf.endswith("BORME-A-2026-103-28.pdf")
    # Ítem único como dict (no lista) y url_xml (API v2.0)
    s2 = json.loads((fix / "sumarios" / "20260715.json").read_text(encoding="utf-8"))
    (it,) = items_seccion_a(s2, dt.date(2026, 7, 15))
    assert it.cod_provincia == "28" and "xml.php" in it.url_xml
    # Claves renombradas: se recurre a la búsqueda de URLs en el JSON serializado
    raw = {"x": {"y": ["https://www.boe.es/borme/dias/2026/06/02/pdfs/BORME-A-2026-103-46.pdf"]}}
    (it2,) = items_seccion_a(raw, dt.date(2026, 6, 2))
    assert it2.cod_provincia == "46"


def test_fetch_cache_idempotente(fix, tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    sess = FakeSession(fix, fail_first=1)  # primer intento 503 -> reintento
    client = BoeClient(tmp_path / "raw", min_interval=0, session=sess)
    items = fetch(dt.date(2026, 6, 1), dt.date(2026, 6, 7), {"28"}, tmp_path / "raw", client=client)
    assert [i.identificador for i in items] == ["BORME-A-2026-103-28"]
    assert (tmp_path / "raw/borme/20260602/BORME-A-2026-103-28.pdf").exists()
    assert (tmp_path / "raw/sumarios/20260601.none").exists()          # día sin BORME (404) cacheado
    assert not (tmp_path / "raw/sumarios/20260606.none").exists()      # fines de semana no se piden
    assert (tmp_path / "raw/borme/manifest.csv").read_text().count(",BORME-A-2026-103-28,") == 1
    n = len(sess.calls)
    fetch(dt.date(2026, 6, 1), dt.date(2026, 6, 7), {"28"}, tmp_path / "raw", client=client)
    assert len(sess.calls) == n  # segunda pasada: todo sale de la caché


def test_fetch_descarga_xml(fix, tmp_path):
    client = BoeClient(tmp_path / "raw", min_interval=0, session=FakeSession(fix))
    (it,) = fetch(dt.date(2026, 7, 15), dt.date(2026, 7, 15), None, tmp_path / "raw", client=client)
    assert it.path_xml.endswith("BORME-A-2026-133-28.xml") and not it.path  # por defecto, PDF solo si falla el XML
    (it,) = fetch(dt.date(2026, 7, 15), dt.date(2026, 7, 15), None, tmp_path / "raw", client=client, formato="ambos")
    assert it.path_xml.endswith("BORME-A-2026-133-28.xml") and it.path.endswith(".pdf")
