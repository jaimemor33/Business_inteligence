"""Genera los fixtures SINTÉTICOS del pipeline (no son datos reales).

    python pipeline/tests/fixtures/make_fixtures.py

Crea:
  sumarios/AAAAMMDD.json               sumarios con la estructura documentada de la API del BORME
  borme_txt/AAAAMMDD/BORME-A-*.txt     texto "como si" se hubiera extraído del PDF (cabeceras, saltos
                                       de página, guiones de partición de palabra, nombres en 2 líneas)
  borme_txt/AAAAMMDD/BORME-A-*.xml     XML hipotético de la API v2.0 (estructura inventada)
  censo/*.csv                          4 meses del censo de locales de Madrid con esquemas y
                                       codificaciones distintos entre meses
  licencias/licencias_2026.csv         licencias/declaraciones responsables (dataset 300193, esquema supuesto)
  verdad_matches.csv                   verdad de referencia: id_local -> nº de anuncio del BORME

Las personas físicas de los fixtures son nombres inventados.
"""
from __future__ import annotations

import csv
import json
import textwrap
from pathlib import Path

HERE = Path(__file__).parent

# --------------------------------------------------------------------------- BORME

BORMES = {
    # fecha, nº BORME, provincia (código), anuncios
    ("20260602", 103, "28"): [
        "230101 - LA TABERNA DE LUCIA SL. Constitución. Comienzo de operaciones: 5.05.26. Objeto social: La explotación "
        "de bares, restaurantes, cafeterías y establecimientos de hostelería en general. CNAE 5610. Domicilio: C/ "
        "ARGANZUELA 12 BAJO (MADRID). Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: FERNANDEZ RUIZ LUCIA. "
        "Datos registrales. S 8 , H M 801001, I/A 1 (26.05.26).",
        "230102 - SONRISAS PROSPERIDAD CLINICA DENTAL SOCIEDAD LIMITADA PROFESIONAL. Constitución. Comienzo de "
        "operaciones: 12.05.26. Objeto social: La prestación de servicios de odontología, estomatología, ortodoncia e "
        "implantología a través de profesionales colegiados. Domicilio: CALLE LOPEZ DE HOYOS 140 LOCAL 2 (MADRID). "
        "Capital: 6.000,00 Euros. Nombramientos. Adm. Solid.: MARTIN SOTO ELENA;GIL PARDO ANDRES. Datos "
        "registrales. S 8 , H M 801002, I/A 1 (27.05.26).",
        "230103 - INVERSIONES PATRIMONIALES ROBLEDO SL. Constitución. Comienzo de operaciones: 30.04.26. Objeto "
        "social: La tenencia de participaciones sociales, la gestión de su patrimonio y el arrendamiento de bienes "
        "inmuebles. Domicilio: CALLE SERRANO 50 3º B (MADRID). Capital: 60.000,00 Euros. Declaración de "
        "unipersonalidad. Socio único: ROBLEDO HOLDING FAMILIAR SL. Nombramientos. Adm. Unico: ROBLEDO HOLDING "
        "FAMILIAR SL. Datos registrales. S 8 , H M 801003, I/A 1 (25.05.26).",
        "230104 - FISIO VALLECAS SL. Constitución. Comienzo de operaciones: 2.05.26. Objeto social: Actividades de "
        "fisioterapia, osteopatía y rehabilitación. CNAE 8690. Domicilio: AVDA DE LA ALBUFERA 200 1º A (MADRID). "
        "Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: NAVARRO GIL PABLO. Datos registrales. S 8 , H M "
        "801004, I/A 1 (26.05.26).",
        "230105 - GIMNASIOS ATLAS CENTRO SL. Cambio de domicilio social. CALLE TOLEDO 80 BAJO (MADRID). Datos "
        "registrales. T 40001 , F 10, S 8, H M 700105, I/A 7 (21.05.26).",
        "230106 - CONSTRUCCIONES HERMANOS VEGA SA. Ampliación de capital. Capital: 100.000,00 Euros. Resultante "
        "Suscrito: 160.000,00 Euros. Ceses/Dimisiones. Consejero: VEGA LOPEZ MARIO. Nombramientos. Consejero: "
        "VEGA PRIETO SARA. Datos registrales. T 30123 , F 55, S 8, H M 500106, I/A 22 (20.05.26).",
        "230107 - GRUPO MULTISERVICIOS SURESTE SL. Constitución. Comienzo de operaciones: 7.05.26. Objeto social: La "
        "compraventa de inmuebles, la construcción, las reformas, el transporte de mercancías, la hostelería y la "
        "formación. Domicilio: CALLE ALCALA 400 (MADRID). Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: "
        "ORTIZ CANO LUIS. Datos registrales. S 8 , H M 801007, I/A 1 (27.05.26).",
        "230108 - RESIDENCIAS COMPARTIDAS PARA JOVENES PROFESIONALES Y ESTUDIANTES DEL BARRIO DE MALASAÑA SL. "
        "Constitución. Comienzo de operaciones: 1.04.26. Objeto social: La explotación de espacios de coliving y "
        "residencias de estudiantes, así como la prestación de servicios complementarios de limpieza y "
        "mantenimiento. Domicilio: CALLE SAN BERNARDO 70 PLANTA BAJA (MADRID). Capital: 10.000,00 Euros. "
        "Nombramientos. Adm. Mancom.: CRUZ PEÑA ANA;PEÑA ROMERO JORGE. Datos registrales. S 8 , H M 801008, I/A 1 "
        "(28.05.26).",
        "230109 - TRANSPORTES ANTIGUOS MORENO SL. Disolución. Voluntaria. Extinción. Ceses/Dimisiones. Adm. Unico: "
        "MORENO DIAZ JOSE. Datos registrales. T 12000 , F 200, S 8, H M 222109, I/A 30 (19.05.26).",
        "230110 - TECH SOLUTIONS DIGITAL SL. Constitución. Comienzo de operaciones: 3.05.26. Objeto social: El "
        "desarrollo de software, el comercio electrónico y la venta online de productos. Domicilio: PASEO DE LA "
        "CASTELLANA 95 PLANTA 15 OFICINA 3 (MADRID). Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: "
        "LOPEZ RIVAS MARTA. Datos registrales. S 8 , H M 801010, I/A 1 (25.05.26).",
    ],
    ("20260602", 103, "08"): [
        "150201 - CAFETERIA LA RAMBLA 2026 SL. Constitución. Comienzo de operaciones: 10.05.26. Objeto social: "
        "Explotación de cafeterías y restaurantes. Domicilio: CALLE MALLORCA 200 BAJOS (BARCELONA). Capital: "
        "3.000,00 Euros. Nombramientos. Adm. Unico: PUIG SERRA JORDI. Datos registrales. S 8 , H B 600201, I/A 1 "
        "(26.05.26).",
        "150202 - OPTICA GRACIA VISIO SL. Constitución. Comienzo de operaciones: 4.05.26. Objeto social: Comercio al "
        "por menor de artículos de óptica, gafas y lentes de contacto, y servicios de optometría. Domicilio: CALLE "
        "GRAN DE GRACIA 150 (BARCELONA). Capital: 5.000,00 Euros. Nombramientos. Adm. Unico: VIDAL ROCA MONTSE. "
        "Datos registrales. S 8 , H B 600202, I/A 1 (27.05.26).",
        "150203 - PATRIMONIAL DIAGONAL 2026 SL. Constitución. Comienzo de operaciones: 2.05.26. Objeto social: "
        "Tenencia de acciones y participaciones, inversión en valores y gestión de patrimonio. Domicilio: AVDA "
        "DIAGONAL 600 PL 4 PTA 2 (BARCELONA). Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: SOLER MAS "
        "PERE. Datos registrales. S 8 , H B 600203, I/A 1 (25.05.26).",
    ],
    ("20260902", 168, "28"): [
        "300301 - EJEMPLO RESTAURACION 2026 SL. Constitución. Comienzo de operaciones: 15.07.26. Objeto social: La "
        "explotación de bares, restaurantes y cafeterías. CNAE 5610. Domicilio: C/ ALCALA 123 BAJO (MADRID). "
        "Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: PEREZ GARCIA JUAN. Datos registrales. S 8 , H M "
        "812345, I/A 1 (02.09.26).",
        "300302 - PEQUEÑOS EXPLORADORES ESCUELA INFANTIL SL. Constitución. Comienzo de operaciones: 20.07.26. Objeto "
        "social: Centro de educación infantil de primer ciclo y ludoteca. Domicilio: CALLE IBIZA 20 LOCAL (MADRID). "
        "Capital: 12.000,00 Euros. Nombramientos. Adm. Unico: SANZ MORA LAURA. Datos registrales. S 8 , H M 812346, "
        "I/A 1 (25.08.26).",
        "300303 - CAFE DEL RETIRO SL. Cambio de denominación social. LA ESQUINA DEL RETIRO SL. Cambio de objeto "
        "social. Explotación de cafeterías y bares. Datos registrales. T 41000 , F 5, S 8, H M 711303, I/A 4 "
        "(20.08.26).",
        "300304 - ACADEMIA BRIDGE IDIOMAS SL. Cambio de objeto social. La enseñanza de idiomas, clases particulares y "
        "refuerzo escolar. Revocaciones. Apoderado: GOMEZ ARIAS EVA. Datos registrales. T 40500 , F 77, S 8, H M "
        "690304, I/A 9 (21.08.26).",
    ],
}
# BORME de julio solo en XML (estructura hipotética de la API v2.0).
XML_JULIO = ("20260715", 133, "28", [
    ("260201", "PANADERIA OBRADOR CHAMBERI SL",
     "Constitución. Comienzo de operaciones: 10.06.26. Objeto social: Elaboración de pan, bollería y pastelería en "
     "obrador propio y su venta al público. Domicilio: CALLE FUENCARRAL 100 (MADRID). Capital: 3.500,00 Euros. "
     "Nombramientos. Adm. Unico: RIOS VEGA CARMEN. Datos registrales. S 8 , H M 805001, I/A 1 (07.07.26)."),
    ("260202", "ESTETICA BELLA LUNA SL",
     "Constitución. Comienzo de operaciones: 15.06.26. Objeto social: Centro de estética, tratamientos de belleza, "
     "manicura y depilación. Domicilio: PLAZA DE OLAVIDE 3 PB (MADRID). Capital: 3.000,00 Euros. Nombramientos. "
     "Adm. Unico: LUNA CASTRO SOFIA. Datos registrales. S 8 , H M 805002, I/A 1 (08.07.26)."),
    ("260203", "BAR CENTRAL SL",
     "Constitución. Comienzo de operaciones: 16.06.26. Objeto social: Explotación de bares. Domicilio: CALLE "
     "BRAVO MURILLO 300 (MADRID). Capital: 3.000,00 Euros. Nombramientos. Adm. Unico: CENTRAL GRUPO HOSTELERO SL. "
     "Datos registrales. S 8 , H M 805003, I/A 1 (08.07.26)."),
])

CABECERA = ["BOLETÍN OFICIAL DEL REGISTRO MERCANTIL", "Núm. {num} {dia} Pág. {pag}", "SECCIÓN PRIMERA",
            "Empresarios", "Actos inscritos", "{prov}"]
PIE = ["cve: BORME-A-{year}-{num}-{cod}", "Verificable en https://www.boe.es"]
DIAS = {"20260602": "Martes 2 de junio de 2026", "20260715": "Miércoles 15 de julio de 2026",
        "20260902": "Miércoles 2 de septiembre de 2026"}
PROV = {"28": "MADRID", "08": "BARCELONA"}


def _hyphenate(lines: list[str], every: int = 6) -> list[str]:
    """Parte con guion la última palabra larga de algunas líneas, como hace la maquetación del PDF."""
    out = []
    for i, line in enumerate(lines):
        words = line.split(" ")
        last = words[-1] if words else ""
        if i % every == 3 and len(last) >= 8 and last.isalpha() and last.islower():
            cut = len(last) // 2
            out.append(" ".join(words[:-1] + [last[:cut] + "-"]))
            out.append("\x00" + last[cut:])  # se pegará al principio de la línea siguiente
        else:
            out.append(line)
    res = []
    for line in out:
        if res and res[-1].startswith("\x00"):
            res[-1] = res[-1][1:] + " " + line
        else:
            res.append(line)
    return [x.lstrip("\x00") for x in res]


def borme_text(fecha: str, num: int, cod: str, anuncios: list[str], lineas_por_pagina: int = 22, ancho: int = 92) -> str:
    lines: list[str] = []
    for a in anuncios:
        lines.extend(_hyphenate(textwrap.wrap(a, ancho)))
    pages, pag = [], 25000 + num
    for k in range(0, len(lines), lineas_por_pagina):
        cab = [c.format(num=num, dia=DIAS[fecha], pag=pag + k // lineas_por_pagina, prov=PROV[cod]) for c in CABECERA]
        if k:  # en las páginas siguientes no se repite el bloque de sección
            cab = cab[:2]
        pie = [p.format(year=fecha[:4], num=num, cod=cod) for p in PIE]
        pages.append("\n".join(cab + lines[k:k + lineas_por_pagina] + pie))
    return "\n".join(pages) + "\n"


def borme_xml(fecha, num, cod, anuncios) -> str:
    items = "\n".join(
        f'  <anuncio numero="{n}">\n    <denominacion>{d}.</denominacion>\n    <texto>{t}</texto>\n  </anuncio>'
        for n, d, t in anuncios)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<documento id="BORME-A-{fecha[:4]}-{num}-{cod}" '
            f'fecha="{fecha}">\n  <provincia>{PROV[cod]}</provincia>\n{items}\n</documento>\n')


def sumario(fecha: str, num: int, items_a: list[tuple[str, str]], xml: bool = False, single: bool = False) -> dict:
    y, m, d = fecha[:4], fecha[4:6], fecha[6:]
    base = f"https://www.boe.es/borme/dias/{y}/{m}/{d}/pdfs"
    items = []
    for cod, titulo in items_a:
        ident = f"BORME-A-{y}-{num}-{cod}"
        it = {"identificador": ident, "titulo": titulo,
              "url_pdf": {"szBytes": "123456", "szKBytes": "121", "texto": f"{base}/{ident}.pdf"}}
        if xml:
            it["url_xml"] = f"https://www.boe.es/diario_borme/xml.php?id={ident}"
        items.append(it)
    return {
        "status": {"code": "200", "text": "ok"},
        "data": {"sumario": {
            "metadatos": {"publicacion": "BORME", "fecha_publicacion": fecha},
            "diario": [{
                "numero": str(num),
                "sumario_diario": {"identificador": f"BORME-S-{y}-{num}",
                                   "url_pdf": {"szBytes": "9999", "szKBytes": "10", "texto": f"{base}/BORME-S-{y}-{num}.pdf"}},
                "seccion": [
                    {"codigo": "A", "nombre": "SECCIÓN PRIMERA. Empresarios. Actos inscritos",
                     "item": items[0] if single and len(items) == 1 else items},
                    {"codigo": "B", "nombre": "SECCIÓN PRIMERA. Empresarios. Otros actos publicados en el Registro Mercantil",
                     "item": [{"identificador": f"BORME-B-{y}-{num}-28", "titulo": "MADRID",
                               "url_pdf": {"texto": f"{base}/BORME-B-{y}-{num}-28.pdf"}}]},
                    {"codigo": "C", "nombre": "SECCIÓN SEGUNDA. Anuncios y avisos legales",
                     "apartado": [{"nombre": "FUSIONES Y ABSORCIONES DE EMPRESAS",
                                   "item": {"identificador": f"BORME-C-{y}-1{num}", "titulo": "EMPRESA X SA",
                                            "url_pdf": {"texto": f"{base}/BORME-C-{y}-1{num}.pdf"}}}]},
                ],
            }],
        }},
    }


# --------------------------------------------------------------------------- censo de Madrid

# id_local -> {mes: (situacion, rotulo, [(id_epigrafe, desc_epigrafe, id_division, desc_division)])}, dirección
HOST = ("561001", "RESTAURANTE", "56", "SERVICIOS DE COMIDAS Y BEBIDAS")
BAR = ("563001", "BAR CAFETERIA", "56", "SERVICIOS DE COMIDAS Y BEBIDAS")
DENT = ("862301", "ACTIVIDADES ODONTOLOGICAS", "86", "ACTIVIDADES SANITARIAS")
FISIO = ("869004", "ACTIVIDADES DE FISIOTERAPIA", "86", "ACTIVIDADES SANITARIAS")
GYM = ("931301", "GIMNASIOS", "93", "ACTIVIDADES DEPORTIVAS, RECREATIVAS Y DE ENTRETENIMIENTO")
PAN = ("107101", "FABRICACION DE PAN Y PRODUCTOS FRESCOS DE PANADERIA Y PASTELERIA", "10", "INDUSTRIA DE LA ALIMENTACION")
ROPA = ("477101", "COMERCIO AL POR MENOR DE PRENDAS DE VESTIR", "47", "COMERCIO AL POR MENOR")
EST = ("960202", "CENTRO DE ESTETICA", "96", "OTROS SERVICIOS PERSONALES")
PELU = ("960201", "PELUQUERIA", "96", "OTROS SERVICIOS PERSONALES")
FARMA = ("477301", "FARMACIA", "47", "COMERCIO AL POR MENOR")
SUPER = ("471101", "SUPERMERCADO", "47", "COMERCIO AL POR MENOR")
INF = ("851001", "EDUCACION INFANTIL PRIMER CICLO", "85", "EDUCACION")

M = ["2026-06", "2026-07", "2026-08", "2026-09"]
LOCALES = {
    # Aperturas con constitución previa en el BORME (verdad de referencia en VERDAD).
    "280001001": (("CALLE", "ARGANZUELA", "12", "ARGANZUELA", "IMPERIAL"),
                  {"2026-07": ("En obras", None, [HOST]), "2026-08": ("Abierto", "TABERNA DE LUCIA", [HOST]),
                   "2026-09": ("Abierto", "TABERNA DE LUCIA", [HOST])}),
    "280001002": (("CALLE", "LOPEZ DE HOYOS", "140", "CHAMARTIN", "PROSPERIDAD"),
                  {"2026-06": ("Obras", None, [DENT]), "2026-07": ("Obras", None, [DENT]),
                   "2026-08": ("Obras", None, [DENT]), "2026-09": ("Abierto", "SONRISAS PROSPERIDAD", [DENT])}),
    "280001004": (("CALLE", "PEÑA GORBEA", "5", "PUENTE DE VALLECAS", "SAN DIEGO"),
                  {"2026-08": ("Abierto", "FISIO VALLECAS", [FISIO]), "2026-09": ("Abierto", "FISIO VALLECAS", [FISIO])}),
    "280001005": (("CALLE", "TOLEDO", "80", "CENTRO", "EMBAJADORES"),
                  {"2026-07": ("Abierto", "ATLAS GIMNASIOS", [GYM]), "2026-08": ("Abierto", "ATLAS GIMNASIOS", [GYM]),
                   "2026-09": ("Abierto", "ATLAS GIMNASIOS", [GYM])}),
    "280001006": (("CALLE", "FUENCARRAL", "100", "CENTRO", "UNIVERSIDAD"),
                  {"2026-06": ("Abierto", "MODAS LOLA", [ROPA]), "2026-07": ("Cerrado", "MODAS LOLA", [ROPA]),
                   "2026-08": ("Cerrado", None, [ROPA]), "2026-09": ("Abierto", "OBRADOR CHAMBERI", [PAN])}),
    "280001007": (("PLAZA", "OLAVIDE", "3", "CHAMBERI", "TRAFALGAR"),
                  {"2026-07": ("En obras", None, [EST]), "2026-08": ("Abierto", None, [EST]),
                   "2026-09": ("Abierto", None, [EST])}),
    "280001008": (("CALLE", "ALCALA", "123", "SALAMANCA", "GOYA"),
                  {"2026-06": ("Cerrado", None, [BAR]), "2026-07": ("Obras", None, [HOST]),
                   "2026-08": ("Obras", None, [HOST]), "2026-09": ("Abierto", "RESTAURANTE EJEMPLO", [HOST])}),
    "280001009": (("CALLE", "IBIZA", "20", "RETIRO", "IBIZA"),
                  {"2026-08": ("Obras", None, [INF]), "2026-09": ("En obras", None, [INF])}),
    # Aperturas sin BORME (autónomos o sociedades antiguas).
    "280002001": (("CALLE", "ATOCHA", "45", "CENTRO", "EMBAJADORES"),
                  {"2026-08": ("Abierto", "PELUQUERIA MARI", [PELU]), "2026-09": ("Abierto", "PELUQUERIA MARI", [PELU])}),
    "280002002": (("CALLE", "GOYA", "10", "SALAMANCA", "GOYA"),
                  {"2026-06": ("Abierto", "BOUTIQUE ANA", [ROPA]), "2026-07": ("Abierto", "BOUTIQUE ANA", [ROPA]),
                   "2026-08": ("Abierto", "BAR GOYA", [BAR]), "2026-09": ("Abierto", "BAR GOYA", [BAR])}),
    "280002003": (("CALLE", "PRINCESA", "30", "MONCLOA-ARAVACA", "ARGÜELLES"),
                  {"2026-06": ("Abierto", "FARMACIA PRINCESA", [FARMA]), "2026-07": ("Cerrado", "FARMACIA PRINCESA", [FARMA]),
                   "2026-08": ("Abierto", "FARMACIA PRINCESA", [FARMA]), "2026-09": ("Abierto", "FARMACIA PRINCESA", [FARMA])}),
    "280002004": (("CALLE", "BRAVO MURILLO", "120", "TETUAN", "CUATRO CAMINOS"),
                  {"2026-09": ("Abierto", "BAR", [BAR])}),
    # Locales estables (sin aperturas).
    **{f"28000300{i}": (("CALLE", "MAYOR", str(10 + i), "CENTRO", "SOL"),
                        {m: ("Abierto", f"COMERCIO MAYOR {i}", [SUPER if i % 2 else ROPA, ROPA]) for m in M})
       for i in range(1, 6)},
    "280003009": (("CALLE", "ARENAL", "9", "CENTRO", "SOL"),
                  {m: ("Cerrado", None, [ROPA]) for m in M}),
}
VERDAD = {"280001001": "230101", "280001002": "230102", "280001004": "230104", "280001005": "230105",
          "280001006": "260201", "280001007": "260202", "280001008": "300301"}

SCHEMAS = {
    # mes: (nombre de fichero, codificación, columnas -> nombre en el fichero, coma decimal)
    "2026-06": ("Actividades_202606.csv", "latin-1", None, False),
    "2026-07": ("ACTIVIDADES_07_2026.csv", "utf-8-sig", "upper", True),
    "2026-08": ("locales_actividades_2026-08.csv", "utf-8", {
        "id_local": "id_local", "desc_situacion_local": "situacion_local", "rotulo": "rotulo_local",
        "id_epigrafe": "epigrafe", "desc_epigrafe": "descripcion_epigrafe", "desc_vial_edificio": "desc_vial",
        "clase_vial_edificio": "clase_vial", "num_edificio": "numero", "desc_distrito_local": "distrito",
        "desc_barrio_local": "barrio", "coordenada_x_local": "coordenada_x", "coordenada_y_local": "coordenada_y"}, False),
    "2026-09": ("Actividades_202609.csv", "utf-8", None, False),
}
COLS = ["id_local", "id_distrito_local", "desc_distrito_local", "desc_barrio_local", "coordenada_x_local",
        "coordenada_y_local", "id_situacion_local", "desc_situacion_local", "clase_vial_edificio", "desc_vial_edificio",
        "num_edificio", "rotulo", "id_seccion", "desc_seccion", "id_division", "desc_division", "id_epigrafe",
        "desc_epigrafe", "fx_carga"]


def censo_rows(mes: str) -> list[dict]:
    rows = []
    for i, (idl, (dire, meses)) in enumerate(sorted(LOCALES.items())):
        if mes not in meses:
            continue
        sit, rot, epis = meses[mes]
        clase, via, num, dist, barrio = dire
        for e in epis:
            rows.append({"id_local": idl, "id_distrito_local": str(1 + i % 21), "desc_distrito_local": dist,
                         "desc_barrio_local": barrio, "coordenada_x_local": 440000.5 + 37 * i,
                         "coordenada_y_local": 4474000.25 + 41 * i, "id_situacion_local": {"Abierto": "1"}.get(sit, "2"),
                         "desc_situacion_local": sit, "clase_vial_edificio": clase, "desc_vial_edificio": via,
                         "num_edificio": num, "rotulo": rot or "", "id_seccion": "I", "desc_seccion": "SECCION",
                         "id_division": e[2], "desc_division": e[3], "id_epigrafe": e[0], "desc_epigrafe": e[1],
                         "fx_carga": f"01/{mes[5:]}/{mes[:4]}"})
    return rows


def write_censo(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for mes, (fname, enc, cols, coma) in SCHEMAS.items():
        rows = censo_rows(mes)
        if cols == "upper":
            mapping = {c: c.upper() for c in COLS}
        elif isinstance(cols, dict):
            mapping = {c: cols.get(c, c) for c in COLS}
        else:
            mapping = {c: c for c in COLS}
        with (out / fname).open("w", encoding=enc, newline="") as f:
            w = csv.writer(f, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            w.writerow([mapping[c] for c in COLS])
            for r in rows:
                vals = []
                for c in COLS:
                    v = r[c]
                    if isinstance(v, float):
                        v = f"{v:.2f}".replace(".", ",") if coma else f"{v:.2f}"
                    vals.append(v)
                w.writerow(vals)


def write_licencias(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        ["110/2026/01001", "15/06/2026", "Declaración responsable", "Implantación de actividad de restaurante con obras de acondicionamiento",
         "Terciario recreativo", "Acondicionamiento general", "CALLE ARGANZUELA 12", "440010,5", "4474010,2"],
        ["110/2026/01002", "20/05/2026", "Licencia urbanística procedimiento ordinario", "Clínica dental: obras y actividad",
         "Dotacional sanitario", "Reestructuración", "CALLE LOPEZ DE HOYOS, 140", "441000,0", "4476000,0"],
        ["110/2026/01003", "01/08/2026", "Declaración responsable", "Restaurante", "Terciario recreativo",
         "Acondicionamiento puntual", "C/ ALCALA, 123", "442000,0", "4475000,0"],
        ["110/2026/01004", "03/03/2026", "Declaración responsable", "Vivienda: reforma interior", "Residencial",
         "Reforma", "CALLE SERRANO 50", "441500,0", "4475500,0"],
    ]
    with (out / "licencias_2026.csv").open("w", encoding="latin-1", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Nº Expediente", "Fecha concesión", "Tipo de procedimiento", "Objeto de la licencia",
                    "Régimen de uso", "Obras", "Emplazamiento", "Coordenada X", "Coordenada Y"])
        w.writerows(rows)


def main():
    sdir, bdir = HERE / "sumarios", HERE / "borme_txt"
    sdir.mkdir(exist_ok=True)
    for (fecha, num, cod), anuncios in BORMES.items():
        d = bdir / fecha
        d.mkdir(parents=True, exist_ok=True)
        (d / f"BORME-A-{fecha[:4]}-{num}-{cod}.txt").write_text(borme_text(fecha, num, cod, anuncios), encoding="utf-8")
    fecha, num, cod, an = XML_JULIO
    (bdir / fecha).mkdir(parents=True, exist_ok=True)
    (bdir / fecha / f"BORME-A-{fecha[:4]}-{num}-{cod}.xml").write_text(borme_xml(fecha, num, cod, an), encoding="utf-8")

    (sdir / "20260602.json").write_text(json.dumps(sumario("20260602", 103, [("28", "MADRID"), ("08", "BARCELONA"), ("99", "ÍNDICE ALFABÉTICO DE SOCIEDADES")]), ensure_ascii=False, indent=1), encoding="utf-8")
    (sdir / "20260715.json").write_text(json.dumps(sumario("20260715", 133, [("28", "MADRID")], xml=True, single=True), ensure_ascii=False, indent=1), encoding="utf-8")
    (sdir / "20260902.json").write_text(json.dumps(sumario("20260902", 168, [("28", "MADRID"), ("08", "BARCELONA")]), ensure_ascii=False, indent=1), encoding="utf-8")

    write_censo(HERE / "censo")
    write_licencias(HERE / "licencias")
    with (HERE / "verdad_matches.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id_local", "num_anuncio"])
        w.writerows(sorted(VERDAD.items()))
    print("Fixtures sintéticos generados en", HERE)


if __name__ == "__main__":
    main()
