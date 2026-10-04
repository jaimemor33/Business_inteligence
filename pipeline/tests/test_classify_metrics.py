import json
from types import SimpleNamespace

import pandas as pd
import pytest

from pipeline import classify as C
from pipeline.borme_parse import parse_dir
from pipeline.metrics import prepare, resumen, run as run_metrics, tipo_domicilio


@pytest.mark.parametrize("objeto,den,cnae,esperado", [
    ("La explotación de bares, restaurantes y cafeterías. CNAE 5610", None, "5610", "hosteleria"),
    ("Servicios de odontología y ortodoncia", None, None, "dental"),
    ("Tratamientos de medicina estética y cirugía estética", None, None, "medicina_estetica"),
    ("Centro de estética, manicura, pedicura y depilación", None, None, "centro_estetica"),
    ("Actividades de fisioterapia y osteopatía", None, "8690", "fisioterapia"),
    ("Consulta de podología y quiropodia", None, None, "podologia"),
    ("Gabinete de psicología y psicoterapia", None, None, "psicologia"),
    ("Venta de gafas y lentes de contacto, optometría", None, None, "optica"),
    ("Venta y adaptación de audífonos, audiología", None, None, "audiologia"),
    ("Clínica veterinaria y venta de piensos", None, None, "veterinaria"),
    ("Centro de diagnóstico por imagen, resonancia magnética", None, None, "imagen_diagnostica"),
    ("Clínica de reproducción asistida y fertilidad", None, None, "fertilidad"),
    ("Laboratorio de análisis clínicos", None, None, "laboratorio"),
    ("Peluquería y barbería", None, None, "peluqueria"),
    ("Explotación de spa, sauna y circuito de aguas", None, None, "spa"),
    ("Explotación de gimnasios e instalaciones deportivas", None, None, "gimnasio"),
    ("Estudio de pilates, yoga y entrenamiento personal", None, None, "boutique_fitness"),
    ("Escuela infantil de primer ciclo de educación infantil", None, None, "escuela_infantil"),
    ("Academia de clases particulares y refuerzo escolar", None, None, "academia"),
    ("Centro de formación profesional para el empleo", None, None, "formacion"),
    ("Colegio privado de educación primaria, secundaria y bachillerato", None, None, "colegio"),
    ("Residencia para personas mayores", None, None, "residencia"),
    ("Centro de día para mayores", None, None, "centro_dia"),
    ("Explotación de hoteles y hostales", None, None, "hotel"),
    ("Explotación de apartamentos turísticos y viviendas de uso turístico", None, None, "apartamentos_turisticos"),
    ("Explotación de espacios de coliving", None, None, "coliving"),
    ("Explotación de supermercados", None, None, "supermercado"),
    ("Oficina de farmacia", None, None, "farmacia"),
    ("Floristería y venta al público de plantas", None, None, "retail"),
    ("Taller mecánico, chapa y pintura", None, None, "taller"),
    ("Lavandería autoservicio y tintorería", None, None, "lavanderia"),
    ("Explotación de espacios de coworking", None, None, "coworking"),
    ("Operador logístico, almacenaje y última milla", None, None, "logistica"),
    ("Fabricación de productos alimenticios y platos preparados", None, None, "industria_alimentaria"),
    ("La tenencia de participaciones sociales", "X HOLDING SL", None, "ruido"),
    ("Arrendamiento de bienes inmuebles por cuenta propia", None, "6820", "ruido"),
    ("Comercio electrónico y venta online", None, None, "ruido"),
])
def test_reglas_por_sector(objeto, den, cnae, esperado):
    c = C.classify_text(objeto, den, cnae)
    assert c.sector == esperado, c
    assert 0 <= c.confianza <= 1 and c.regla


def test_baja_confianza_en_cajon_de_sastre():
    c = C.classify_text("La compraventa de inmuebles, la construcción, las reformas, el transporte de mercancías, "
                        "la hostelería y la formación")
    assert c.confianza < 0.6
    assert C.classify_text("Prestación de servicios").sector == "sin_clasificar"


# --------------------------------------------------------------------------- LLM (cliente simulado)


def _msg(d):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(d))])


class FakeMessages:
    def __init__(self):
        self.calls = []
        self.batches = FakeBatches(self)

    def create(self, **params):
        self.calls.append(params)
        assert params["model"] == C.LLM_MODEL
        assert params["output_config"]["format"]["type"] == "json_schema"
        return _msg({"sector": "hosteleria", "confianza": 0.83, "justificacion": "Objeto centrado en bares."})


class FakeBatches:
    def __init__(self, parent):
        self.parent, self.reqs = parent, None

    def create(self, requests):
        self.reqs = requests
        return SimpleNamespace(id="batch_1", processing_status="in_progress")

    def retrieve(self, _id):
        return SimpleNamespace(id=_id, processing_status="ended")

    def results(self, _id):
        for r in reversed(self.reqs):  # orden distinto al de envío
            yield SimpleNamespace(custom_id=r["custom_id"], result=SimpleNamespace(
                type="succeeded", message=_msg({"sector": "academia", "confianza": 1.4, "justificacion": "x"})))


def test_llm_sincrono_y_cache(tmp_path):
    fake = SimpleNamespace(messages=FakeMessages())
    df = pd.DataFrame({"denominacion": ["MULTI SL", "BAR PEPE SL"],
                       "objeto_social": ["Construcción, hostelería, formación y transporte", "Explotación de bares"],
                       "cnae": [None, None]})
    df = C.classify_frame(df)
    out = C.apply_llm(df, tmp_path / "cache.jsonl", umbral=0.6, client=fake)
    assert out.at[0, "metodo"] == "llm" and out.at[0, "sector"] == "hosteleria"
    assert out.at[0, "justificacion_llm"] and out.at[0, "objeto_social"].startswith("Construcción")
    assert len(fake.messages.calls) == 1  # solo la fila de baja confianza
    C.apply_llm(df, tmp_path / "cache.jsonl", umbral=0.6, client=fake)
    assert len(fake.messages.calls) == 1  # segunda vez desde la caché


def test_llm_batch(tmp_path):
    fake = SimpleNamespace(messages=FakeMessages())
    rows = [{"idx": i, "denominacion": f"S{i} SL", "objeto_social": f"actividad {i}"} for i in range(5)]
    res = C.classify_llm(rows, tmp_path / "c.jsonl", client=fake, batch_threshold=2, poll_seconds=0)
    assert set(res) == set(range(5)) and all(r["confianza"] == 1.0 for r in res.values())  # recortada a [0, 1]
    assert fake.messages.calls == []


def test_llm_desactivado_sin_clave(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    df = C.classify_frame(pd.DataFrame({"denominacion": ["X"], "objeto_social": ["algo indefinido"], "cnae": [None]}))
    assert C.apply_llm(df, tmp_path / "c.jsonl").equals(df)


# --------------------------------------------------------------------------- métricas


@pytest.mark.parametrize("dom,tipo", [
    ("C/ ALCALA 123 BAJO (MADRID)", "local"), ("CALLE MAYOR 5 LOCAL 2 (MADRID)", "local"),
    ("CALLE ATOCHA 10 PB (MADRID)", "local"), ("POL IND X NAVE 12 (GETAFE)", "local"),
    ("CALLE SAN BERNARDO 70 PLANTA BAJA (MADRID)", "local"), ("PZA ESPAÑA 1 LOC. 3 (MADRID)", "local"),
    ("CALLE SERRANO 50 3º B (MADRID)", "piso_oficina"), ("PASEO CASTELLANA 95 PLANTA 15 OFICINA 3 (MADRID)", "piso_oficina"),
    ("AVDA DIAGONAL 600 PL 4 PTA 2 (BARCELONA)", "piso_oficina"),
    ("CALLE FUENCARRAL 100 (MADRID)", "indeterminado"), ("CALLE PUERTA DEL SOL 3 (MADRID)", "indeterminado"),
    ("CALLE LOCALIDAD 5 (X)", "indeterminado"),
])
def test_tipo_domicilio(dom, tipo):
    assert tipo_domicilio(dom) == tipo


def test_metricas_e_informe(data_dir, tmp_path):
    df = C.classify_frame(parse_dir(data_dir / "raw"))
    p = tmp_path / "clasificado.csv"
    df.to_csv(p, index=False)
    paths = run_metrics(p, tmp_path / "out")
    res = pd.read_csv(paths["resumen"])
    assert {"sector", "provincia", "mes", "n_constitucion", "capital_mediano", "pct_local",
            "lag_comienzo_pub_p50", "lag_inscripcion_pub_p90"} <= set(res.columns)
    hb = res[(res.sector == "hosteleria") & (res.provincia == "BARCELONA") & (res.mes == "2026-06")].iloc[0]
    assert hb.n_constitucion == 1 and hb.pct_local == 100.0 and hb.capital_mediano == 3000
    assert hb.lag_comienzo_pub_p50 == 23  # 10.05.26 -> 2.06.26
    assert hb.lag_inscripcion_pub_p50 == 7  # 26.05.26 -> 2.06.26
    actos = pd.read_csv(paths["actos"])
    assert actos.loc[actos.tipo_acto.eq("constitucion"), "n"].sum() == 15
    ruido = pd.read_csv(paths["ruido"])
    assert ruido.loc[ruido.provincia.eq("BARCELONA"), "pct_ruido"].iloc[0] == pytest.approx(100 / 3, 0.01)
    md = paths["informe"].read_text(encoding="utf-8")
    assert "Retrasos de publicación" in md and "| hosteleria |" in md
    allp = resumen(prepare(pd.read_csv(p, parse_dates=["fecha_publicacion", "comienzo_operaciones", "fecha_inscripcion"])), ["sector"])
    assert allp["n_anuncios"].sum() == len(df)
