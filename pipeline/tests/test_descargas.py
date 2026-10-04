"""Descargas automáticas con portales simulados (sin red)."""
from types import SimpleNamespace

from pipeline import descargas


class FakeS:
    def __init__(self):
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        if url.endswith("/api/3/action/package_show"):
            res = [{"url": "https://datos.madrid.es/f/Actividades_202505.csv"},
                   {"url": "https://datos.madrid.es/f/Terrazas_202505.csv"},
                   {"url": "https://datos.madrid.es/f/Licencias_202505.csv"},
                   {"url": "https://datos.madrid.es/f/estructura.pdf"}]
            return SimpleNamespace(status_code=200, json=lambda: {"success": True, "result": {"resources": res}}, text="")
        if "regcess" in url and url.endswith(".do"):
            return SimpleNamespace(status_code=200, text='<a href="descargarFichero.do?tipo=C2">C2</a>', content=b"")
        if "descargarFichero" in url:
            return SimpleNamespace(status_code=200, content=b"PK\x03\x04xlsx", text="")
        return SimpleNamespace(status_code=200, content=b"id_local;rotulo\n1;X\n", text="")


def test_ckan_y_separacion(tmp_path):
    s = FakeS()
    fs = descargas.descargar_ckan("censo_historico", tmp_path, session=s, pausa=0)
    assert sorted(p.name for p in fs) == ["Actividades_202505.csv", "Licencias_202505.csv", "Terrazas_202505.csv"]
    censo, lic = descargas.separar_censo(fs)
    assert [p.name for p in censo] == ["Actividades_202505.csv"] and [p.name for p in lic] == ["Licencias_202505.csv"]
    n = len(s.urls)
    descargas.descargar_ckan("censo_historico", tmp_path, session=s, pausa=0)  # 2.ª vez: caché
    assert len(s.urls) == n + 1  # solo la llamada a la API
    assert (tmp_path / "descargas_manifest.csv").exists()


def test_regcess_excel_directo(tmp_path):
    fs = descargas.descargar_regcess(tmp_path, session=FakeS(), pausa=0)
    assert len(fs) == 1 and fs[0].read_bytes().startswith(b"PK")
