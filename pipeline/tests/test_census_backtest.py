import pandas as pd
import pytest

from pipeline import cli
from pipeline.backtest import borme_candidatos, match, muestra_revision, nombre_score, norm_nombre, precision
from pipeline.borme_parse import parse_dir
from pipeline.classify import classify_frame
from pipeline.madrid_census import detect_aperturas, load_month, load_panel, normalize_columns
from pipeline.madrid_licencias import cruzar_aperturas, load_licencias


@pytest.fixture
def panel(fix):
    return load_panel(sorted((fix / "censo").glob("*.csv")))


def test_normalizacion_columnas_y_codificaciones(fix):
    meses = {}
    for f in sorted((fix / "censo").glob("*.csv")):
        d = load_month(f)
        meses[d["mes"].iloc[0]] = d
        assert d["id_local"].notna().all() and d["desc_situacion_local"].notna().all()
        assert d["coordenada_x_local"].between(430000, 460000).all()  # coma decimal convertida
    assert sorted(meses) == ["2026-06", "2026-07", "2026-08", "2026-09"]
    assert "PEÑA GORBEA" in set(meses["2026-08"]["desc_vial_edificio"])      # alias 'desc_vial'
    assert "ARGÜELLES" in set(meses["2026-06"]["desc_barrio_local"])          # latin-1 bien leído
    df = normalize_columns(pd.DataFrame(columns=["ID_LOCAL", "Situación local", "Rótulo", "Epígrafe"]))
    assert {"id_local", "desc_situacion_local", "rotulo", "id_epigrafe"} <= set(df.columns)


def test_aperturas(panel):
    ap = detect_aperturas(panel).set_index("id_local")
    assert ap.at["280001001", "tipo_apertura"] == "reapertura_actividad_nueva"   # obras -> abierto
    assert ap.at["280001002", "meses_previos_obras"] == 3 and bool(ap.at["280001002", "obras_censurado"])
    assert ap.at["280001005", "tipo_apertura"] == "nuevo_local" and ap.at["280001005", "mes_apertura"] == "2026-07"
    assert ap.at["280001006", "meses_previos_cerrado"] == 2
    assert ap.at["280001008", "lag_obras_apertura_meses"] == 2
    assert ap.at["280002002", "tipo_apertura"] == "cambio_actividad"
    assert ap.at["280002003", "tipo_apertura"] == "reapertura_misma_actividad"
    assert "280001009" not in ap.index                 # sigue en obras
    assert not any(i.startswith("2800030") for i in ap.index)  # locales estables o censurados
    assert ap.at["280001002", "sector"] == "dental" and ap.at["280001007", "sector"] == "centro_estetica"


def test_nombres():
    assert norm_nombre("SONRISAS PROSPERIDAD CLINICA DENTAL SOCIEDAD LIMITADA PROFESIONAL") == "SONRISAS PROSPERIDAD CLINICA DENTAL"
    assert norm_nombre("ABC, S.L.U.") == "ABC"
    assert nombre_score("FISIO VALLECAS", "FISIO VALLECAS") == 100
    assert nombre_score("PEPE", "GRUPO PEPE INVERSIONES") < 60


def test_backtest_matches_contra_verdad(panel, data_dir, fix):
    borme = classify_frame(parse_dir(data_dir / "raw"))
    ap = detect_aperturas(panel)
    ap = ap[ap.tipo_apertura.isin(["nuevo_local", "reapertura_actividad_nueva", "cambio_actividad"])].reset_index(drop=True)
    m = match(ap, borme_candidatos(borme))
    verdad = pd.read_csv(fix / "verdad_matches.csv", dtype=str).set_index("id_local")["num_anuncio"].to_dict()
    got = {r.id_local: str(int(r.borme_num_anuncio)) for r in m[m["match"]].itertuples()}
    assert got == verdad                              # 7/7 encontrados y ningún falso positivo
    r = m.set_index("id_local")
    assert r.at["280001004", "nivel_match"] == "C_nombre"      # domicilio social en otro sitio
    assert r.at["280001007", "nivel_match"] == "B_direccion"   # sin rótulo
    assert r.at["280001008", "lag_borme_apertura_dias"] == -1  # BORME publicado tras abrir
    assert not r.at["280002004", "match"]                       # rótulo genérico "BAR" no empareja
    # Muestra de revisión + tabla de precisión
    s = muestra_revision(m)
    assert set(s["nivel_match"]) == {"A_direccion_y_nombre", "B_direccion", "C_nombre"} and s["es_correcto"].eq("").all()
    s["es_correcto"] = [int(verdad.get(i) == str(int(n))) for i, n in zip(s["id_local"], m.set_index("id_local").loc[s["id_local"], "borme_num_anuncio"])]
    p = precision(s).set_index("nivel_match")
    assert p.at["TOTAL", "precision"] == 1.0


def test_licencias_300193(panel, fix):
    lic = load_licencias([fix / "licencias" / "licencias_2026.csv"])
    assert lic["fecha_dt"].notna().all() and lic["addr_key"].notna().all()
    assert lic["es_declaracion_responsable"].sum() == 3
    ap = detect_aperturas(panel)
    from pipeline.common import address_key
    ap["addr_key"] = [address_key(v, n) for v, n in zip(ap["desc_vial_edificio"], ap["num_edificio"])]
    x = cruzar_aperturas(ap, lic).set_index("id_local")
    assert x.at["280001001", "lic_match"] and x.at["280001001", "lag_licencia_apertura_dias"] == 47
    assert x.at["280001008", "lic_es_dr"] and x.at["280001008", "lag_licencia_apertura_dias"] == 31
    assert not x.at["280002001", "lic_match"]


def test_cli_extremo_a_extremo(data_dir, fix):
    d = str(data_dir)
    cli.main(["--data-dir", d, "parse"])
    cli.main(["--data-dir", d, "classify"])
    cli.main(["--data-dir", d, "metrics"])
    cli.main(["--data-dir", d, "backtest", "--censo", str(fix / "censo"),
              "--licencias", str(fix / "licencias" / "licencias_2026.csv")])
    out = data_dir / "output"
    for f in ("informe_borme.md", "informe_backtest.md", "metrics_sector_provincia_mes.csv", "backtest_resumen_sector.csv",
              "backtest_muestra_revision.csv", "backtest_aperturas.csv", "backtest_licencias_sector.csv"):
        assert (out / f).exists(), f
    res = pd.read_csv(out / "backtest_resumen_sector.csv").set_index("sector")
    assert res.at["dental", "pct_match"] == 100.0
    # Revisión manual simulada -> tabla de precisión
    s = pd.read_csv(out / "backtest_muestra_revision.csv")
    s["es_correcto"] = 1
    s.to_csv(data_dir / "revisado.csv", index=False)
    cli.main(["--data-dir", d, "backtest", "--censo", str(fix / "censo"), "--revisado", str(data_dir / "revisado.csv")])
    assert "TOTAL" in (out / "informe_backtest.md").read_text(encoding="utf-8")
