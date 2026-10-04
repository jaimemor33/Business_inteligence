import datetime as dt
import textwrap

import pandas as pd
import pytest

from pipeline.borme_parse import (forma_juridica, parse_anuncio, parse_cargos, parse_cnae, parse_dir, parse_file,
                                  pdf_to_text, segment, to_frame, xml_to_text)

EJEMPLO = ("412345 - EJEMPLO RESTAURACION 2026 SL. Constitución. Comienzo de operaciones: 15.07.26. Objeto social: "
           "La explotación de bares, restaurantes y cafeterías. CNAE 5610. Domicilio: C/ ALCALA 123 BAJO (MADRID). "
           "Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: PEREZ GARCIA JUAN. Datos registrales. S 8 , H M "
           "812345, I/A 1 (02.09.26).")


def test_ejemplo_del_enunciado():
    a = parse_anuncio(412345, EJEMPLO, {"fecha_publicacion": dt.date(2026, 9, 2), "provincia": "MADRID"})
    assert a.denominacion == "EJEMPLO RESTAURACION 2026 SL" and a.forma_juridica == "SL"
    assert a.evento_principal == "constitucion"
    assert a.tipos_acto == "constitucion|nombramientos|datos_registrales"
    assert a.objeto_social.startswith("La explotación de bares") and a.cnae == "5610"
    assert a.domicilio == "C/ ALCALA 123 BAJO (MADRID)" and a.municipio == "MADRID"
    assert a.capital == 3000.0
    assert a.comienzo_operaciones == dt.date(2026, 7, 15)
    assert a.fecha_inscripcion == dt.date(2026, 9, 2)
    assert a.hoja_registral == "M-812345"
    assert a.n_cargos_nombrados == 1 and not a.admin_persona_juridica


def test_otros_actos():
    t = ("9 - X SL(R.M. ALCALA DE HENARES). Cambio de denominación social. NUEVA X SL. Cambio de domicilio social. "
         "AVDA DE AMERICA 4 PLANTA 3 (MADRID). Ampliación de capital. Capital: 1.000,00 Euros. Resultante Suscrito: "
         "4.000,00 Euros. Declaración de unipersonalidad. Socio único: HOLDING Y SA. Ceses/Dimisiones. Adm. Solid.: "
         "A B C;D E F. Nombramientos. Adm. Unico: GRUPO ZETA SL. Datos registrales. T 1 , F 2, S 8, H M 1, I/A 5 (28.08.26).")
    a = parse_anuncio(9, t)
    assert a.registro_mercantil == "ALCALA DE HENARES"
    assert a.nueva_denominacion == "NUEVA X SL"
    assert a.evento_principal == "cambio_domicilio" and a.domicilio.startswith("AVDA DE AMERICA 4")
    assert a.capital == 1000.0 and a.capital_tipo == "ampliacion"
    assert a.n_cargos_cesados == 2 and a.n_cargos_nombrados == 1
    assert a.admin_persona_juridica and a.socio_unico_persona_juridica


def test_utilidades():
    assert forma_juridica("CLINICA X SOCIEDAD LIMITADA PROFESIONAL") == ("CLINICA X", "SLP")
    assert forma_juridica("ABC S.L.U.")[1] == "SLU"
    assert forma_juridica("COOPERATIVA DEL CAMPO S. COOP.")[1] == "COOP"
    assert parse_cnae("Actividad principal C.N.A.E.: 56.10 y CNAE 5630") == ["5610", "5630"]
    assert [pj for _, pj in parse_cargos("Adm. Unico: PEREZ X. Apoderado: A SL;GOMEZ Y. Apo.Manc.: Z Z")] == [False, True, False, False]


def test_segmentacion_robusta(fix):
    txt = (fix / "borme_txt/20260602/BORME-A-2026-103-28.txt").read_text(encoding="utf-8")
    seg = segment(txt)
    assert [n for n, _ in seg] == list(range(230101, 230111))
    by = dict(seg)
    assert "hostelería" in by[230101]                     # palabra partida con guion re-unida
    assert "BOLETÍN" not in by[230105] and "cve:" not in by[230105]  # salto de página dentro del anuncio
    assert "(MADRID). Datos registrales" in by[230105]
    # Línea del cuerpo que empieza por número no crea un anuncio nuevo
    assert len(segment("100 - A SL. Extinción. Datos registrales. (1.1.26).\n5 - texto suelto\n101 - B SL. Extinción.")) == 2


def test_rgpd_sin_nombres_de_personas(data_dir):
    df = parse_dir(data_dir / "raw")
    csv = df.to_csv(index=False)
    for nombre in ("FERNANDEZ RUIZ LUCIA", "MARTIN SOTO ELENA", "GIL PARDO ANDRES", "NAVARRO GIL PABLO", "PEREZ GARCIA JUAN",
                   "VEGA LOPEZ MARIO", "MORENO DIAZ JOSE", "GOMEZ ARIAS EVA"):
        assert nombre not in csv
    r = df.set_index("num_anuncio")
    assert r.at[230102, "n_cargos_nombrados"] == 2
    assert bool(r.at[230103, "admin_persona_juridica"]) and bool(r.at[230103, "socio_unico_persona_juridica"])


def test_parse_dir_formatos_y_filtros(data_dir):
    df = parse_dir(data_dir / "raw")
    assert len(df) == 20 and df["parse_ok"].all()
    assert set(df["fuente"]) == {"txt", "xml"}
    assert set(df.loc[df["fuente"].eq("xml"), "num_anuncio"]) == {260201, 260202, 260203}
    solo_bcn = parse_dir(data_dir / "raw", provincias={"08"})
    assert set(solo_bcn["provincia"]) == {"BARCELONA"} and len(solo_bcn) == 3
    rango = parse_dir(data_dir / "raw", desde=dt.date(2026, 7, 1), hasta=dt.date(2026, 7, 31))
    assert set(pd.to_datetime(rango["fecha_publicacion"]).dt.month) == {7}


def test_xml_por_lineas(tmp_path):
    p = tmp_path / "BORME-A-2026-200-28.xml"
    p.write_text(f"<doc><p><b>412345 - EJEMPLO RESTAURACION 2026 SL.</b> {EJEMPLO.split('SL. ', 1)[1]}</p></doc>",
                 encoding="utf-8")
    assert segment(xml_to_text(p))[0][0] == 412345
    (a,) = parse_file(p)
    assert a.capital == 3000.0 and a.comienzo_operaciones == dt.date(2026, 7, 15)


# --------------------------------------------------------------------------- PDF sintético (dos columnas)


def _anuncios_madrid():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("make_fixtures", Path(__file__).parent / "fixtures" / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.BORMES[("20260602", 103, "28")]


def _pdf(path, anuncios, columnas=2):
    """Maqueta los anuncios en un PDF de 1 o 2 columnas con cabecera y pie, al estilo del BORME."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    W, H = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    ancho = 52 if columnas == 2 else 110
    lines = [l for a in anuncios for l in textwrap.wrap(a, ancho)]
    xs = [40, W / 2 + 12] if columnas == 2 else [40]
    per_col, i, pag = 62, 0, 1
    while i < len(lines):
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(W / 2, H - 40, "BOLETÍN OFICIAL DEL REGISTRO MERCANTIL")
        c.setFont("Helvetica", 7)
        c.drawString(40, H - 55, f"Núm. 168 Miércoles 2 de septiembre de 2026 Pág. {41000 + pag}")
        for x in xs:
            y = H - 90
            for line in lines[i:i + per_col]:
                c.drawString(x, y, line)
                y -= 10
            i += per_col
        c.drawString(40, 30, "cve: BORME-A-2026-168-28")
        c.drawString(W - 200, 30, "Verificable en https://www.boe.es")
        c.showPage()
        pag += 1
    c.save()


@pytest.mark.parametrize("columnas", [1, 2])
def test_pdf_columnas(tmp_path, columnas):
    pytest.importorskip("reportlab")
    d = tmp_path / "20260902"
    d.mkdir()
    pdf = d / "BORME-A-2026-168-28.pdf"
    _pdf(pdf, _anuncios_madrid(), columnas)
    txt = pdf_to_text(pdf)
    assert "Datos registrales" in txt
    df = to_frame(parse_file(pdf))
    assert list(df["num_anuncio"]) == list(range(230101, 230111))
    assert df["parse_ok"].all()
    r = df.set_index("num_anuncio")
    assert r.at[230101, "capital"] == 3000.0 and r.at[230108, "domicilio"].startswith("CALLE SAN BERNARDO 70")
    assert r.at[230104, "comienzo_operaciones"] == dt.date(2026, 5, 2)
    assert r.at[230101, "fecha_publicacion"] == dt.date(2026, 9, 2)  # desde la ruta AAAAMMDD
    # pypdf como respaldo también produce anuncios (sin detección de columnas)
    assert "230101 - LA TABERNA" in pdf_to_text(pdf, engine="pypdf")
