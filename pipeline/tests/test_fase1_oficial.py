"""Fase 1 con fuentes oficiales (REGCESS + censo + licencias + Google básico) con datos SINTÉTICOS
en el formato documentado de cada fuente."""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from pipeline import censo_borme, fase1, fase1_oficial as F, noise, places, regcess
from pipeline.madrid_census import load_panel

N = ["ALBA", "BRISA", "CUMBRE", "DUNA", "ESTRELLA", "FARO", "GIRASOL", "HELECHO", "IRIS", "JAZMIN", "LAUREL",
     "MAGNOLIA", "NARDO", "OLIVO", "PALMERA", "QUIMERA", "ROBLE", "SAUCE", "TULIPAN", "VIOLETA"]


def _const():
    rows = []
    base = dict(provincia="MADRID", cod_provincia="28", municipio="MADRID", evento_principal="constitucion",
                admin_persona_juridica=False, socio_unico_persona_juridica=None, capital=3000.0)
    for i in range(20):  # 20 clínicas dentales nuevas
        rows.append({**base, "denominacion": f"CLINICA DENTAL {N[i]} SLP", "denominacion_base": f"CLINICA DENTAL {N[i]}",
                     "hoja_registral": f"M {100 + i}", "sector": "dental", "admins_id": f"d{i}",
                     "domicilio": f"C/ GOYA {i + 1} BAJO (MADRID)", "fecha_publicacion": "2025-05-05",
                     "comienzo_operaciones": "2025-04-10"})
    for i in range(20):  # 20 restaurantes nuevos
        rows.append({**base, "denominacion": f"ASADOR {N[i]} SL", "denominacion_base": f"ASADOR {N[i]}",
                     "hoja_registral": f"M {500 + i}", "sector": "hosteleria", "admins_id": f"r{i}",
                     "domicilio": f"C/ PRINCESA {i + 1} LOCAL (MADRID)", "fecha_publicacion": "2025-05-05",
                     "comienzo_operaciones": "2025-04-10"})
    rows.append({**base, "denominacion": "CUALQUIER COSA SL", "denominacion_base": "CUALQUIER COSA", "hoja_registral": "M 9",
                 "sector": "generico", "admins_id": "g", "fecha_publicacion": "2025-05-05"})
    return fase1.preparar(noise.marcar(pd.DataFrame(rows)))


def _regcess(tmp: Path) -> list[Path]:
    """Dos fotos (C2): las clínicas pares aparecen en la de 2025-09; la 0 ya estaba en la primera (censurada)."""
    cols = ["Código Autonómico del Centro", "Nombre del Centro", "Nombre del Titular", "Tipo de Centro",
            "Dirección", "Municipio", "Fecha Autorización de Funcionamiento"]
    def fila(i):
        return [f"CS{i}", f"Clínica {N[i].title()}", f"CLINICA DENTAL {N[i]} S.L.P.", "C.2.5.1 Clínicas dentales",
                f"Calle Goya {i + 1}", "Madrid", "15/08/2025"]
    f1 = tmp / "regcess_C2_2025-06-01.csv"
    f2 = tmp / "regcess_C2_2025-09-01.csv"
    pd.DataFrame([fila(0), ["X1", "Hospital X", "OTRO SA", "C.1.1", "Calle Y 1", "Madrid", "01/01/2000"]],
                 columns=cols).to_csv(f1, sep=";", index=False)
    pd.DataFrame([fila(i) for i in range(0, 20, 2)], columns=cols).to_csv(f2, sep=";", index=False)
    return [f1, f2]


def _censo(tmp: Path) -> list[Path]:
    """3 meses: los restaurantes 0-9 aparecen en obras en 2025-06 y abiertos en 2025-08."""
    out = []
    for mes, est in (("2025-05", None), ("2025-06", "Obras"), ("2025-08", "Abierto")):
        rows = [{"id_local": 9999, "desc_situacion_local": "Abierto", "rotulo": "BAR VIEJO", "id_epigrafe": "561001",
                 "desc_epigrafe": "RESTAURANTE", "desc_division": "SERVICIOS DE COMIDAS Y BEBIDAS",
                 "desc_vial_edificio": "SERRANO", "num_edificio": 1}]
        if est:
            rows += [{"id_local": 1000 + i, "desc_situacion_local": est, "rotulo": f"ASADOR {N[i]}",
                      "id_epigrafe": "561001", "desc_epigrafe": "RESTAURANTE", "desc_division": "SERVICIOS DE COMIDAS Y BEBIDAS",
                      "desc_vial_edificio": "PRINCESA", "num_edificio": i + 1} for i in range(10)]
        p = tmp / f"Actividades_{mes.replace('-', '')}.csv"
        pd.DataFrame(rows).to_csv(p, sep=";", index=False)
        out.append(p)
    return out


def test_regcess_dental(tmp_path):
    const = _const()
    snaps = regcess.load_snapshots(_regcess(tmp_path))
    assert snaps["es_dental"].sum() == 11  # el hospital no es dental
    cen, metodo = regcess.centros(snaps)
    assert "primera aparición en 2 fotos" in metodo
    sl = const[const["sector"] == "dental"]
    m = regcess.cruzar(sl, cen)
    assert (m["match_nivel"] == "alta").sum() == 10 and (m["match_nivel"] == "sin_match").sum() == 10
    r = regcess.resumen(m, pd.Timestamp("2025-09-01")).iloc[0]
    assert r["pct_con_centro"] == 0.5
    # fecha de alta = foto 2025-09-01 (la 0 está censurada) -> desde la escritura 2025-04-10: 144 días
    assert r["n_lag"] == 9 and r["lag_escritura_mediana"] == (dt.date(2025, 9, 1) - dt.date(2025, 4, 10)).days


def test_regcess_una_foto_usa_fecha_autorizacion(tmp_path):
    f = _regcess(tmp_path)[1]
    cen, metodo = regcess.centros(regcess.load_snapshots([f]))
    assert "Fecha Autorización" in metodo and cen["fecha_alta"].iloc[0] == pd.Timestamp("2025-08-15")


def test_censo_y_senal(tmp_path):
    const = _const()
    panel = load_panel(_censo(tmp_path))
    hist = censo_borme.historia_locales(panel)
    base = const[(const["sector"] == "hosteleria")]
    m = censo_borme.cruzar_sl(base, hist)
    assert m["match"].sum() == 10 and set(m.loc[m["match"], "nivel_match"]) == {"A_direccion_y_rotulo"}
    lag = m.loc[m["match"], "lag_borme_abierto_dias"]
    assert (lag == (dt.date(2025, 8, 1) - dt.date(2025, 5, 5)).days).all()
    lic = pd.DataFrame({"id_local": [1000 + i for i in range(5)], "desc_tipo_situacion_licencia": ["En tramitación"] * 5,
                        "desc_tipo_licencia": ["Declaración responsable"] * 5})
    lp = tmp_path / "licencias.csv"
    lic.to_csv(lp, sep=";", index=False)
    s, res = censo_borme.senal_temprana(panel, censo_borme.load_licencias_censo([lp]), m, ventana_meses=2)
    assert len(s) == 5 and (s["meses_hasta_apertura"] == 2).all() and s["borme_antes_de_senal"].all()
    assert res.iloc[0]["pct_abren_12m"] == 1.0


class FakeHTTP:
    def __init__(self):
        self.posts = self.gets = 0

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts += 1
        q = json["textQuery"]
        w = next((x for x in N if x in q), None)
        pl = [{"id": f"p{w}", "displayName": {"text": f"Asador {w.title()}"}, "formattedAddress": "Calle Princesa, Madrid",
               "types": ["restaurant"]}] if w and N.index(w) % 2 == 0 and "ASADOR" in q else []
        return SimpleNamespace(status_code=200, json=lambda: {"places": pl}, text="")

    def get(self, *a, **k):
        self.gets += 1
        raise AssertionError("el modo básico no debe llamar a Place Details")


def test_end_to_end_oficial(tmp_path):
    const = _const()
    mad = const[const["ciudad"] == "MADRID"]
    base = mad[mad["objetivo"] & (mad["ruido_tipo"] == "apertura_nueva")]
    cen, _ = regcess.centros(regcess.load_snapshots(_regcess(tmp_path)))
    m_reg = regcess.cruzar(base[base["sector"] == "dental"], cen)
    m_c = censo_borme.cruzar_sl(base, censo_borme.historia_locales(load_panel(_censo(tmp_path))))
    vol = F.volumen(const)
    comb = F.combinar(vol, m_reg, m_c, None, base)
    sin = base[base["empresa_key"].isin(comb.loc[~comb["ok_oficial"], "empresa_key"])]
    assert len(sin) == 20  # 10 dentales + 10 restaurantes sin emparejar en fuentes oficiales
    http = FakeHTTP()
    pl, gasto = places.run(sin, tmp_path, presupuesto_usd=20, session=http, api_key="x", basico=True)
    assert http.gets == 0 and gasto.llamadas_details == 0 and gasto.usd <= 20
    comb = F.combinar(vol, m_reg, m_c, pl, base)
    crit = F.criterios(vol, comb, m_c, m_reg).set_index("sector")
    h = crit.loc["hosteleria"]
    assert h["pct_local_oficial [REGCESS+CENSO·MEDIDO]"] == 0.5
    assert h["fuente_lag"].startswith("CENSO") and h["c2"] == "DESCARTA"  # 20 aperturas/mes × ~75 % < 20
    d = crit.loc["dental"]
    assert d["pct_local_oficial [REGCESS+CENSO·MEDIDO]"] == 0.5 and d["n_google"] == 10
    p = F.informe({"volumen": vol, "criterios": crit.reset_index(), "censo_resumen": F.resumen_censo(m_c)},
                  {"fuentes": {"REGCESS": "test"}, "pct_generico": 1 / 41}, tmp_path)
    t = p.read_text()
    assert "[REGCESS · MEDIDO]" in t and "[CENSO · MEDIDO]" in t and "GOOGLE" in t and "ESTIMADO" in t
