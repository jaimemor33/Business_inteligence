"""Fase 1 de extremo a extremo con respuestas de Places simuladas (sin red)."""
import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd

from pipeline import fase1, noise, places


def _anuncios():
    rows = []
    base = dict(provincia="MADRID", cod_provincia="28", municipio="MADRID", evento_principal="constitucion",
                admin_persona_juridica=False, socio_unico_persona_juridica=None, capital=3000.0)
    # 30 restaurantes nuevos con admins distintos
    for i in range(30):
        rows.append({**base, "denominacion": f"TABERNA NUM{i} SL", "denominacion_base": f"TABERNA NUM{i}",
                     "hoja_registral": f"M {1000 + i}", "sector": "hosteleria", "admins_id": f"p{i}",
                     "domicilio": f"C/ ALCALA {i + 1} BAJO (MADRID)", "objeto_social": "Restaurantes",
                     "fecha_publicacion": "2025-06-02", "comienzo_operaciones": "2025-05-10"})
    # expansión: p0 ya administra otro restaurante
    rows.append({**base, "denominacion": "OTRO REST SL", "denominacion_base": "OTRO REST", "hoja_registral": "M 9",
                 "sector": "hosteleria", "admins_id": "p0", "evento_principal": "nombramientos",
                 "fecha_publicacion": "2025-07-01"})
    rows.append({**base, "denominacion": "MEGA HOLDING SL", "denominacion_base": "MEGA HOLDING", "hoja_registral": "M 7",
                 "sector": "ruido", "admins_id": "q1", "fecha_publicacion": "2025-06-02"})
    rows.append({**base, "denominacion": "FILIAL SL", "denominacion_base": "FILIAL", "hoja_registral": "M 8",
                 "sector": "hosteleria", "admins_id": "GRUPO X SL", "admin_persona_juridica": True,
                 "fecha_publicacion": "2025-06-02"})
    rows.append({**base, "denominacion": "MULTI SL", "denominacion_base": "MULTI", "hoja_registral": "M 6",
                 "sector": "generico", "admins_id": "q2", "fecha_publicacion": "2025-06-02"})
    return pd.DataFrame(rows)


class FakeHTTP:
    """Places simulado: las tabernas pares existen (≤5 reseñas, abiertas 60 días después del BORME)."""
    def __init__(self):
        self.posts = self.gets = 0

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts += 1
        q = json["textQuery"]
        num = q.split("NUM")[1].split()[0] if "NUM" in q else None
        places_ = []
        if num is not None and int(num) % 2 == 0:
            places_ = [{"id": f"pl{num}", "displayName": {"text": f"Taberna Num{num}"},
                        "formattedAddress": f"C. de Alcalá, {int(num) + 1}, 28014 Madrid",
                        "types": ["restaurant", "food"], "businessStatus": "OPERATIONAL"}]
        return SimpleNamespace(status_code=200, json=lambda: {"places": places_}, text="")

    def get(self, url, params=None, headers=None, timeout=None):
        self.gets += 1
        d = {"userRatingCount": 3, "businessStatus": "OPERATIONAL",
             "reviews": [{"publishTime": "2025-08-01T10:00:00Z"}, {"publishTime": "2025-09-01T10:00:00Z"},
                         {"publishTime": "2025-10-01T10:00:00Z"}]}
        return SimpleNamespace(status_code=200, json=lambda: d, text="")


def test_noise():
    c = noise.marcar(_anuncios())
    t = dict(zip(c["denominacion"], c["ruido_tipo"]))
    assert t["TABERNA NUM0 SL"] == "expansion_mismo_sector"
    assert t["TABERNA NUM1 SL"] == "apertura_nueva"
    assert t["MEGA HOLDING SL"] == "holding_patrimonial" and t["FILIAL SL"] == "filial_de_grupo"


def test_nombre_limpio_y_puntuacion():
    assert places.nombre_limpio("MA5 MAMEY RESTAURACION 2025 SL") == "MA5 MAMEY RESTAURACION"
    sc, _ = places.puntuar({"displayName": {"text": "Taberna Num4"}, "formattedAddress": "C. de Alcalá, 5, Madrid",
                            "types": ["restaurant"]}, "TABERNA NUM4", "C/ ALCALA 5 BAJO (MADRID)", "hosteleria")
    assert places.nivel(sc) == "alta"


def test_fase1_end_to_end(tmp_path):
    const = fase1.preparar(noise.marcar(_anuncios()))
    cands = fase1.muestra(const, por_celda=100)
    assert set(cands["ruido_tipo"]) == {"apertura_nueva"} and len(cands) == 29
    http = FakeHTTP()
    pl, gasto = places.run(cands, tmp_path, presupuesto_usd=10, session=http, api_key="x")
    assert len(pl) == 29
    # 14 tabernas pares localizables (la 0 es expansión, no entra en la muestra)
    assert int(pl["localizable"].sum()) == 14 and pl["fecha_apertura_exacta"].sum() == 14
    T = fase1.tablas(const, pl)
    ld = T["localizable_desfase"].set_index("sector").loc["hosteleria"]
    assert abs(ld["pct_localizable"] - 14 / 29) < 1e-9
    assert ld["lag_mediana_dias"] == (dt.date(2025, 8, 1) - dt.date(2025, 6, 2)).days
    crit = fase1.criterios(T).set_index("sector").loc["hosteleria"]
    # 29 aperturas nuevas/mes × 48 % localizable = 14 aperturas reales/mes < 20 -> descarta por volumen
    assert crit["c1_localizable"] == "PASA" and crit["c3_desfase"] == "PASA"
    assert crit["c2_volumen"] == "DESCARTA" and crit["veredicto"] == "DESCARTAR"
    assert abs(crit["aperturas_reales_mes_est"] - 29 * 14 / 29) < 1e-9
    p = fase1.informe(T, fase1.criterios(T), gasto, {"desde": "2025-06-01", "hasta": "2025-07-31"}, tmp_path)
    txt = p.read_text()
    assert "BACKTEST" in txt and "hosteleria" in txt and (tmp_path / "backtest" / "criterios.csv").exists()
    cal = T["calidad_ciudad"].set_index("ciudad").loc["MADRID"]
    assert cal["genericos"] == 1


def test_tope_presupuesto(tmp_path):
    const = fase1.preparar(noise.marcar(_anuncios()))
    cands = fase1.muestra(const, por_celda=100)
    http = FakeHTTP()
    # 0,10 USD: 3 búsquedas (0,032 c/u) y ninguna llamada más
    pl, gasto = places.run(cands, tmp_path, presupuesto_usd=0.10, session=http, api_key="x")
    assert gasto.usd <= 0.10 and http.posts + http.gets == gasto.llamadas_search + gasto.llamadas_details
    assert json.loads((tmp_path / "places_ledger.json").read_text())["usd_precio_lista"] <= 0.10
    # una 2.ª ejecución reutiliza la caché y no gasta más
    antes = gasto.usd
    places.run(cands.head(1), tmp_path, presupuesto_usd=0.10, session=http, api_key="x")
    assert json.loads((tmp_path / "places_ledger.json").read_text())["usd_precio_lista"] == round(antes, 4)
