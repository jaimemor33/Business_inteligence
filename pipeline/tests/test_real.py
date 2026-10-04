"""Tests contra datos REALES del BOE (ver fixtures/real/README.md)."""
import datetime as dt
import json
import os
from pathlib import Path

import pytest

from pipeline import borme_parse as bp
from pipeline.borme_fetch import items_seccion_a

REAL = Path(__file__).parent / "fixtures" / "real"


def test_xml_oficial_seccion_a():
    an = bp.parse_file(REAL / "BORME-A-2026-189-28.xml")
    # Los anuncios del XML NO vienen ordenados por número: deben salir los 6.
    assert [a.num_anuncio for a in an] == [435794, 435804, 435791, 436108, 435833, 435924]
    assert all(a.provincia == "MADRID" and a.fecha_publicacion == dt.date(2026, 9, 30) for a in an)
    c = an[0]
    assert c.denominacion == "MA5 MAMEY SL" and c.evento_principal == "constitucion"
    assert c.objeto_social == "Restaurantes. Puestos de comida. Establecimientos de bebidas. Bar y cafetería"
    assert c.domicilio == "C/ LABRADOR 1 - LOCAL 7 Y 8 (NAVALCARNERO)" and c.municipio == "NAVALCARNERO"
    assert c.capital == 3000 and c.comienzo_operaciones == dt.date(2026, 8, 18)
    assert c.fecha_inscripcion == dt.date(2026, 9, 23)
    assert c.n_cargos_nombrados == 2 and len(c.admins_id.split("|")) == 1  # mismo texto anonimizado -> 1 seudónimo
    # Cada anuncio conserva su propia fecha de inscripción (antes se mezclaban).
    assert an[1].fecha_inscripcion == dt.date(2026, 9, 23) and an[2].fecha_inscripcion == dt.date(2025, 6, 9)


def test_sumario_real_url_xml():
    s = json.loads((REAL / "sumario_20260930.json").read_text())
    items = items_seccion_a(s, dt.date(2026, 9, 30))
    mad = [i for i in items if i.cod_provincia == "28"]
    assert len(mad) == 1 and mad[0].identificador == "BORME-A-2026-189-28"
    assert mad[0].url_xml == "https://www.boe.es/diario_borme/xml.php?id=BORME-A-2026-189-28"
    assert all(i.cod_provincia != "99" for i in items)  # el índice alfabético no es una provincia


@pytest.mark.skipif(not os.environ.get("BI_REAL_PDF"), reason="BI_REAL_PDF no definido (PDF real con datos personales)")
def test_pdf_real_2015():
    an = bp.parse_file(os.environ["BI_REAL_PDF"])
    assert len(an) == 30 and [a.num_anuncio for a in an] == list(range(57315, 57345))
    const = [a for a in an if a.evento_principal == "constitucion"]
    assert len(const) == 8 and all(a.objeto_social and a.capital and a.comienzo_operaciones for a in const)
    assert all(a.parse_ok for a in an)


def test_cli_fase1_oficial_con_xml_real(tmp_path, monkeypatch):
    """Humo: el comando completo corre sobre el XML real sin red (--sin-fetch) y escribe el informe."""
    import shutil
    from pipeline import cli
    monkeypatch.setenv("BI_HASH_KEY", "test")
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    d = tmp_path / "raw" / "borme" / "20260930"
    d.mkdir(parents=True)
    shutil.copy(REAL / "BORME-A-2026-189-28.xml", d)
    cli.main(["--data-dir", str(tmp_path), "fase1-oficial", "--desde", "2026-09-30", "--hasta", "2026-09-30",
              "--sin-fetch", "--sin-llm", "--research-dir", str(tmp_path / "research")])
    txt = (tmp_path / "research" / "BACKTEST.md").read_text()
    assert "REGCESS**: NO DISPONIBLE" in txt and "GOOGLE**: NO DISPONIBLE" in txt
