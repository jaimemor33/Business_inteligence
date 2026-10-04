"""Parseo de los PDF de la sección A del BORME.

PDF -> texto (pdfplumber, con detección de dos columnas; pypdf de respaldo) -> limpieza de
cabeceras/pies -> segmentación en anuncios ("^NNNNNN - DENOMINACION.") -> actos -> campos.

Minimización RGPD: los nombres de personas (administradores, apoderados, socios únicos...) se
leen solo para contarlos y para saber si el cargo lo ocupa una persona jurídica; NUNCA se
escriben en la salida. Tampoco se guarda el texto íntegro del anuncio.

Las palabras clave de actos y el patrón de "Datos registrales" siguen el conocimiento del
formato recogido en bormeparser (Pablo Castellano, GPLv3); el código es una reimplementación.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .common import MESES, norm, parse_fecha, parse_importe, provincia_name, strip_accents

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- actos
# Texto exacto en el BORME -> tipo normalizado.
ACTOS: dict[str, str] = {
    "Constitución": "constitucion",
    "Cambio de objeto social": "cambio_objeto",
    "Ampliacion del objeto social": "ampliacion_objeto",
    "Ampliación del objeto social": "ampliacion_objeto",
    "Cambio de domicilio social": "cambio_domicilio",
    "Cambio de denominación social": "cambio_denominacion",
    "Ampliación de capital": "ampliacion_capital",
    "Reducción de capital": "reduccion_capital",
    "Desembolso de dividendos pasivos": "desembolso",
    "Nombramientos": "nombramientos",
    "Reelecciones": "reelecciones",
    "Revocaciones": "revocaciones",
    "Ceses/Dimisiones": "ceses_dimisiones",
    "Cancelaciones de oficio de nombramientos": "cancelacion_nombramientos",
    "Modificación de poderes": "modificacion_poderes",
    "Declaración de unipersonalidad": "declaracion_unipersonalidad",
    "Sociedad unipersonal": "sociedad_unipersonal",
    "Pérdida del caracter de unipersonalidad": "perdida_unipersonalidad",
    "Pérdida del carácter de unipersonalidad": "perdida_unipersonalidad",
    "Disolución": "disolucion",
    "Extinción": "extincion",
    "Fusión por absorción": "fusion",
    "Fusión por unión": "fusion",
    "Escisión parcial": "escision",
    "Escisión total": "escision",
    "Segregación": "escision",
    "Cesión global de activo y pasivo": "cesion_global",
    "Transformación de sociedad": "transformacion",
    "Modificaciones estatutarias": "modificaciones_estatutarias",
    "Modificación de duración": "modificacion_duracion",
    "Situación concursal": "situacion_concursal",
    "Apertura de sucursal": "apertura_sucursal",
    "Sucursal": "apertura_sucursal",
    "Cierre de Sucursal": "cierre_sucursal",
    "Primera sucursal de sociedad extranjera": "apertura_sucursal",
    "Empresario Individual": "empresario_individual",
    "Página web de la sociedad": "pagina_web",
    "Otros conceptos": "otros_conceptos",
    "Fe de erratas": "fe_erratas",
    "Reapertura hoja registral": "reapertura_hoja",
    "Reactivación de la sociedad (Art. 242 del Reglamento del Registro Mercantil)": "reactivacion",
    "Adaptación Ley 2/95": "adaptacion",
    "Adaptación Ley 44/2015": "adaptacion",
    "Adaptación de sociedad": "adaptacion",
    "Crédito incobrable": "credito_incobrable",
    "Emisión de obligaciones": "emision_obligaciones",
    "Articulo 378.5 del Reglamento del Registro Mercantil": "art_378_5",
    "Cierre provisional hoja registral por baja en el índice de Entidades Jurídicas": "cierre_provisional",
    "Cierre provisional de la hoja registral por revocación del NIF": "cierre_provisional",
    "Cierre provisional hoja registral art. 137.2 Ley 43/1995 Impuesto de Sociedades": "cierre_provisional",
    "Acuerdo de ampliación de capital social sin ejecutar. Importe del acuerdo": "acuerdo_ampliacion_capital",
    "Primera inscripcion (O.M. 10/6/1.997)": "primera_inscripcion",
    "Datos registrales": "datos_registrales",
}
# Prioridad para el "evento principal" del anuncio (de más a menos relevante para el negocio).
PRIORIDAD = ["constitucion", "cambio_domicilio", "cambio_objeto", "ampliacion_objeto", "apertura_sucursal",
             "cambio_denominacion", "ampliacion_capital", "fusion", "escision", "transformacion",
             "declaracion_unipersonalidad", "disolucion", "extincion", "situacion_concursal",
             "nombramientos", "ceses_dimisiones", "revocaciones", "reelecciones"]
ACTOS_CON_CARGOS = {"nombramientos", "reelecciones", "revocaciones", "ceses_dimisiones",
                    "cancelacion_nombramientos", "modificacion_poderes", "declaracion_unipersonalidad",
                    "sociedad_unipersonal", "constitucion"}


def _kw_regex() -> re.Pattern:
    kws = sorted(ACTOS, key=len, reverse=True)
    alt = "|".join(re.escape(k) for k in kws)
    # Un acto empieza al principio del cuerpo o tras ". ", y va seguido de "." o ":".
    return re.compile(rf"(?:^|(?<=\.)\s+)({alt})(?=\s*[.:](?:\s|$))")


RE_ACTO = _kw_regex()
RE_ANUNCIO = re.compile(r"^\s*(\d{1,7})\s+-\s+(\S.*)$")
RE_REGISTRO = re.compile(r"\(R\.\s?M\.\s*([^)]+)\)")
SUB_CONSTITUCION = ["Comienzo de operaciones", "Objeto social", "Domicilio", "Capital suscrito",
                    "Desembolsado", "Capital", "Duración"]
RE_SUB = re.compile(r"(?:^|(?<=[.\s]))(" + "|".join(re.escape(k) for k in SUB_CONSTITUCION) + r")\s*:\s*")
RE_CNAE = re.compile(r"C\.?\s?N\.?\s?A\.?\s?E\.?(?:\s*-?\s*20(?:09|25))?\s*[:.]?\s*((?:\d{2}\.?\d{1,2}(?:\s*[,;y/]\s*)?)+)", re.I)
RE_CP = re.compile(r"(?<!\d)(0[1-9]\d{3}|[1-4]\d{4}|5[0-2]\d{3})(?!\d)")
RE_DATOS_FECHA = re.compile(r"\(\s*(\d{1,2}\.\d{1,2}\.\d{2,4})\s*\)")
RE_HOJA = re.compile(r"\bH\s+([A-Z]{1,3})\s*(\d+)")
# Etiqueta de cargo: uno o más tokens con alguna minúscula ("Adm. Unico", "Apo.Manc.", "Socio único")
# seguidos de ":". Los nombres en el BORME van en mayúsculas, así que no se confunden con etiquetas.
RE_ETIQUETA_CARGO = re.compile(r"(?:(?<=\s)|^)((?:\S*[a-záéíóúñº]\S*\s+)*?\S*[a-záéíóúñº][^\s:]*)\s*:\s*")

SIGLAS_FORMA = [  # (regex sobre el final de la denominación, forma normalizada)
    (r"SOCIEDAD LIMITADA PROFESIONAL|S\.?L\.?P\.?", "SLP"),
    (r"SOCIEDAD LIMITADA LABORAL|S\.?L\.?L\.?", "SLL"),
    (r"SOCIEDAD LIMITADA NUEVA EMPRESA|S\.?L\.?N\.?E\.?", "SLNE"),
    (r"SOCIEDAD LIMITADA UNIPERSONAL|S\.?L\.?U\.?|SL UNIPERSONAL", "SLU"),
    (r"SOCIEDAD DE RESPONSABILIDAD LIMITADA|S\.?R\.?L\.?", "SRL"),
    (r"SOCIEDAD LIMITADA|S\.?\s?L\.?", "SL"),
    (r"SOCIEDAD ANONIMA UNIPERSONAL|S\.?A\.?U\.?", "SAU"),
    (r"SOCIEDAD ANONIMA LABORAL|S\.?A\.?L\.?", "SAL"),
    (r"SOCIEDAD ANONIMA|S\.?\s?A\.?", "SA"),
    (r"SOCIEDAD COOPERATIVA(?: [A-Z ]+)?|S\.? ?COOP\.?(?: [A-Z.]+)?|COOP\.?", "COOP"),
    (r"SOCIEDAD CIVIL PROFESIONAL|S\.?C\.?P\.?", "SCP"),
    (r"SOCIEDAD COMANDITARIA(?: [A-Z ]+)?|S\.? ?COM\.?(?: ?P\.? ?A\.?)?", "SCOM"),
    (r"AGRUPACION DE INTERES ECONOMICO|A\.?I\.?E\.?", "AIE"),
    (r"SICAV|S\.?I\.?C\.?A\.?V\.?(?: SA)?", "SICAV"),
    (r"LIMITED|LTD\.?", "LTD"),
    (r"B\.?V\.?", "BV"),
    (r"GMBH", "GMBH"),
]
RE_FORMA = [(re.compile(rf"[\s,]+(?:{p})\s*$"), f) for p, f in SIGLAS_FORMA]
RE_PERSONA_JURIDICA = re.compile(
    r"(\bS\.?\s?L\.?U?\.?|\bS\.?\s?A\.?U?\.?|\bSLP\b|\bSOCIEDAD\b|\bLIMITED\b|\bLTD\b|\bGMBH\b|\bB\.?V\.?\b|"
    r"\bS\.?\s?COOP|\bCOOPERATIVA\b|\bFUNDACION\b|\bASOCIACION\b|\bAYUNTAMIENTO\b|\bS\.?\s?A\.?S\.?\b|\bSARL\b|"
    r"\bINC\.?\b|\bLLC\b|\bS\.?\s?R\.?\s?L\.?\b|\bS\.?\s?P\.?\s?A\.?\b|\bAIE\b)\s*\.?$")

# Líneas de cabecera/pie de página del PDF del BORME que hay que descartar.
RUIDO_LINEAS = [re.compile(p, re.I) for p in (
    r"^BOLET[IÍ]N OFICIAL(?: DEL)?(?: REGISTRO MERCANTIL)?$", r"^(?:DEL )?REGISTRO MERCANTIL$", r"^BORME$",
    r"^N[uú]m\.\s*\d+\s", r"^N[uú]m\.\s*\d+$", r"^P[aá]g\.\s*\d+$", r"^cve:\s*BORME", r"Verificable en https?://",
    r"^SECCI[OÓ]N PRIMERA$", r"^SECCI[OÓ]N PRIMERA\b.*Actos inscritos", r"^Empresarios$", r"^Actos inscritos$",
    r"^Empresarios\s+Actos inscritos$", r"^D\.\s?L\.:?\s*M-\d", r"^ISSN", r"^https?://www\.boe\.es",
    r"^(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bado|Domingo)\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}",
)]
RE_CABECERA_NUM = re.compile(r"N[uú]m\.\s*(\d+)\s+(?:Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bado|Domingo)\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.I)


# --------------------------------------------------------------------------- PDF -> texto


def _page_text(page) -> str:
    """Texto de una página; si detecta dos columnas, extrae la izquierda y luego la derecha."""
    w, h = page.width, page.height
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    body = [x for x in words if 0.09 * h < x["top"] < 0.92 * h]
    if len(body) >= 30:
        best_x, best_n = None, None
        for x in range(int(w * 0.35), int(w * 0.65), 2):
            n = sum(1 for wd in body if wd["x0"] < x < wd["x1"])
            if best_n is None or n < best_n:
                best_x, best_n = x, n
        left = sum(1 for wd in body if wd["x1"] <= best_x)
        right = sum(1 for wd in body if wd["x0"] >= best_x)
        if best_n is not None and best_n <= max(1, len(body) // 200) and min(left, right) > 0.15 * len(body):
            parts = [page.crop((0, 0, best_x, h)).extract_text() or "",
                     page.crop((best_x, 0, w, h)).extract_text() or ""]
            return "\n".join(parts)
    return page.extract_text() or ""


def pdf_to_text(path: str | Path, engine: str = "auto") -> str:
    """Extrae el texto del PDF. engine: 'auto' (pdfplumber y, si falla, pypdf), 'pdfplumber' o 'pypdf'."""
    path = Path(path)
    if engine in ("auto", "pdfplumber"):
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                txt = "\n".join(_page_text(p) for p in pdf.pages)
            if txt.strip():
                return txt
            log.warning("%s: pdfplumber no extrajo texto; probando pypdf", path.name)
        except Exception as e:  # PDF corrupto, fuente rara...
            if engine == "pdfplumber":
                raise
            log.warning("%s: pdfplumber falló (%s); probando pypdf", path.name, e)
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


# --------------------------------------------------------------------------- texto -> anuncios


def cabecera(text: str) -> dict:
    """Número de BORME y fecha de publicación leídos de la cabecera del PDF (si aparecen)."""
    m = RE_CABECERA_NUM.search(text)
    if not m:
        return {}
    num, d, mes, y = m.groups()
    mes_n = MESES.get(strip_accents(mes.lower()))
    try:
        fecha = dt.date(int(y), mes_n, int(d)) if mes_n else None
    except ValueError:
        fecha = None
    return {"borme_num": int(num), "fecha_publicacion": fecha}


def clean_lines(text: str) -> list[str]:
    """Quita cabeceras/pies y une palabras partidas con guion al final de línea."""
    out: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or any(r.search(line) for r in RUIDO_LINEAS):
            continue
        if out and out[-1].endswith("-") and line[:1].islower():
            out[-1] = out[-1][:-1] + line
        else:
            out.append(line)
    return out


def segment(text: str) -> list[tuple[int, str]]:
    """Divide el texto en anuncios [(nº de anuncio, texto completo del anuncio)].

    Un anuncio empieza en una línea "NNNNNN - ...". Para no confundir con líneas del cuerpo que
    empiecen por número, se exige que el número sea creciente y cercano al anterior.
    """
    lines = clean_lines(text)
    anuncios: list[tuple[int, list[str]]] = []
    last = None
    for line in lines:
        m = RE_ANUNCIO.match(line)
        if m:
            n = int(m.group(1))
            if last is None or last < n <= last + 5000:
                anuncios.append((n, [line]))
                last = n
                continue
        if anuncios:
            anuncios[-1][1].append(line)
    return [(n, re.sub(r"\s+", " ", " ".join(ls)).strip()) for n, ls in anuncios]


def split_actos(cuerpo: str) -> list[tuple[str, str]]:
    """Cuerpo del anuncio -> [(tipo_normalizado, argumento)]."""
    ms = list(RE_ACTO.finditer(cuerpo))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start(1) if i + 1 < len(ms) else len(cuerpo)
        arg = cuerpo[m.end(1):end].strip()
        arg = re.sub(r"^[.:]\s*", "", arg).strip()
        out.append((ACTOS[m.group(1)], arg))
    return out


# --------------------------------------------------------------------------- campos


def forma_juridica(denominacion: str) -> tuple[str, str]:
    """('EJEMPLO RESTAURACION 2026 SL') -> ('EJEMPLO RESTAURACION 2026', 'SL')."""
    d = norm(denominacion).rstrip(". ")
    for rx, forma in RE_FORMA:
        m = rx.search(d)
        if m:
            return d[:m.start()].rstrip(" ,"), forma
    return d, ""


def es_persona_juridica(nombre: str) -> bool:
    return bool(RE_PERSONA_JURIDICA.search(norm(nombre).rstrip(" .")))


def parse_cargos(arg: str) -> list[tuple[str, bool]]:
    """'Adm. Unico: PEREZ GARCIA JUAN. Apoderado: A SL;B C D.' -> [('Adm. Unico', False), ('Apoderado', True), ...]

    Devuelve (etiqueta_del_cargo, es_persona_juridica) por cada titular. Los nombres se descartan.
    """
    ms = list(RE_ETIQUETA_CARGO.finditer(arg))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start(1) if i + 1 < len(ms) else len(arg)
        valor = arg[m.end():end].strip().rstrip(".")
        for nombre in re.split(r"\s*;\s*", valor):
            nombre = nombre.strip(" .")
            if nombre:
                out.append((m.group(1).strip(), es_persona_juridica(nombre)))
    return out


def parse_constitucion(arg: str) -> dict:
    """Subcampos de la constitución: comienzo de operaciones, objeto, domicilio, capital."""
    ms = list(RE_SUB.finditer(arg))
    res: dict[str, str] = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start(1) if i + 1 < len(ms) else len(arg)
        res.setdefault(m.group(1), arg[m.end():end].strip().rstrip("."))
    return res


def parse_domicilio(dom: str | None) -> dict:
    """'C/ ALCALA 123 BAJO (MADRID).' -> domicilio, municipio, codigo_postal."""
    if not dom:
        return {"domicilio": None, "municipio": None, "codigo_postal": None}
    dom = dom.strip().rstrip(".").strip()
    municipio = None
    m = re.search(r"\(([^()]+)\)\s*$", dom)
    if m:
        municipio = norm(m.group(1))
    cp = None
    for c in RE_CP.findall(dom):
        # Un CP suele ir junto al municipio o tras la palabra C.P.; evita confundir con números de vía.
        if re.search(rf"(C\.?\s?P\.?\s*:?\s*{c}|{c}\s*[-,]?\s*\(|{c}\s*[A-Z]{{3,}}|\({c}|-\s*{c})", dom):
            cp = c
    return {"domicilio": dom, "municipio": municipio, "codigo_postal": cp}


def parse_cnae(text: str | None) -> list[str]:
    if not text:
        return []
    codes = []
    for m in RE_CNAE.finditer(text):
        for c in re.findall(r"\d{2}\.?\d{1,2}", m.group(1)):
            c = c.replace(".", "")
            if len(c) == 3:
                c = c + "0"
            if c not in codes:
                codes.append(c)
    return codes


def parse_datos_registrales(arg: str) -> dict:
    fechas = RE_DATOS_FECHA.findall(arg)
    hoja = RE_HOJA.search(arg)
    return {"fecha_inscripcion": parse_fecha(fechas[-1]) if fechas else None,
            "hoja_registral": f"{hoja.group(1)}-{hoja.group(2)}" if hoja else None}


@dataclass
class Anuncio:
    """Una fila de salida: un anuncio (una sociedad) de un BORME. Sin datos de personas físicas."""
    fecha_publicacion: dt.date | None
    provincia: str | None
    cod_provincia: str | None
    borme_id: str | None
    num_anuncio: int
    denominacion: str
    denominacion_base: str
    forma_juridica: str
    registro_mercantil: str | None = None
    tipos_acto: str = ""             # 'constitucion|nombramientos|datos_registrales'
    evento_principal: str | None = None
    objeto_social: str | None = None
    cnae: str | None = None          # códigos CNAE separados por '|', el primero es el principal
    domicilio: str | None = None
    municipio: str | None = None
    codigo_postal: str | None = None
    capital: float | None = None
    capital_tipo: str | None = None  # 'constitucion' | 'ampliacion' | 'reduccion'
    comienzo_operaciones: dt.date | None = None
    fecha_inscripcion: dt.date | None = None
    hoja_registral: str | None = None
    nueva_denominacion: str | None = None
    n_cargos_nombrados: int = 0
    n_cargos_cesados: int = 0
    n_cargos_pj: int = 0             # nombrados que son personas jurídicas
    admin_persona_juridica: bool = False
    socio_unico_persona_juridica: bool | None = None
    parse_ok: bool = True
    parse_warnings: str = ""
    extra: dict = field(default_factory=dict, repr=False)


def parse_anuncio(num: int, texto: str, meta: dict | None = None) -> Anuncio:
    """Texto completo de un anuncio -> Anuncio con los campos extraídos."""
    meta = meta or {}
    warnings = []
    # Cabecera: "NNNN - DENOMINACION SL(R.M. XXX)." seguida del primer acto.
    m0 = re.match(r"^\s*\d+\s+-\s+", texto)
    resto = texto[m0.end():] if m0 else texto
    first = RE_ACTO.search(resto)
    if first:
        cab, cuerpo = resto[:first.start(1)].strip(), resto[first.start(1):]
    else:
        cab, cuerpo = resto, ""
        warnings.append("sin_actos")
    registro = None
    mr = RE_REGISTRO.search(cab)
    if mr:
        registro = norm(mr.group(1))
        cab = cab[:mr.start()] + cab[mr.end():]
    denom = norm(cab).rstrip(". ").strip()
    denom = re.sub(r"\s+EN LIQUIDACION$", "", denom)
    base, forma = forma_juridica(denom)

    a = Anuncio(fecha_publicacion=meta.get("fecha_publicacion"), provincia=meta.get("provincia"),
                cod_provincia=meta.get("cod_provincia"), borme_id=meta.get("borme_id"), num_anuncio=num,
                denominacion=denom, denominacion_base=base, forma_juridica=forma, registro_mercantil=registro)
    tipos = []
    nombrados = cesados = pj = 0
    admin_pj = False
    for tipo, arg in split_actos(cuerpo):
        tipos.append(tipo)
        if tipo == "constitucion":
            sub = parse_constitucion(arg)
            a.comienzo_operaciones = parse_fecha(sub.get("Comienzo de operaciones"))
            if sub.get("Comienzo de operaciones") and a.comienzo_operaciones is None:
                warnings.append("fecha_comienzo_ilegible")
            a.objeto_social = sub.get("Objeto social") or a.objeto_social
            a.__dict__.update(parse_domicilio(sub.get("Domicilio")))
            cap = sub.get("Capital") or sub.get("Capital suscrito")
            a.capital, a.capital_tipo = parse_importe(cap), "constitucion" if cap else None
        elif tipo in ("cambio_objeto", "ampliacion_objeto"):
            a.objeto_social = arg.rstrip(".") or a.objeto_social
        elif tipo == "cambio_domicilio" and a.domicilio is None:
            a.__dict__.update(parse_domicilio(arg))
        elif tipo == "cambio_denominacion":
            a.nueva_denominacion = norm(arg).rstrip(". ")
        elif tipo in ("ampliacion_capital", "reduccion_capital") and a.capital is None:
            mcap = re.search(r"Capital:\s*([\d.,]+\s*(?:Euros|Ptas)?)", arg)
            a.capital = parse_importe(mcap.group(1) if mcap else arg)
            a.capital_tipo = "ampliacion" if tipo == "ampliacion_capital" else "reduccion"
        elif tipo == "datos_registrales":
            a.__dict__.update(parse_datos_registrales(arg))
        if tipo in ACTOS_CON_CARGOS and tipo != "constitucion":
            cargos = parse_cargos(arg)
            if tipo in ("nombramientos", "reelecciones"):
                nombrados += len(cargos)
                pj += sum(1 for _, es_pj in cargos if es_pj)
                admin_pj |= any(es_pj and norm(lbl).startswith("ADM") for lbl, es_pj in cargos)
            elif tipo in ("ceses_dimisiones", "revocaciones", "cancelacion_nombramientos"):
                cesados += len(cargos)
            elif tipo in ("declaracion_unipersonalidad", "sociedad_unipersonal"):
                socios = [es_pj for lbl, es_pj in cargos if "SOCIO" in norm(lbl)]
                if socios:
                    a.socio_unico_persona_juridica = socios[-1]
    a.tipos_acto = "|".join(dict.fromkeys(tipos))
    a.evento_principal = next((t for t in PRIORIDAD if t in tipos), tipos[0] if tipos else None)
    cnaes = parse_cnae(a.objeto_social)
    a.cnae = "|".join(cnaes) or None
    a.n_cargos_nombrados, a.n_cargos_cesados, a.n_cargos_pj = nombrados, cesados, pj
    a.admin_persona_juridica = admin_pj
    if "datos_registrales" not in tipos:
        warnings.append("sin_datos_registrales")
    if "constitucion" in tipos and not a.objeto_social:
        warnings.append("constitucion_sin_objeto")
    a.parse_warnings = "|".join(warnings)
    a.parse_ok = not warnings or warnings == ["fecha_comienzo_ilegible"]
    return a


# --------------------------------------------------------------------------- ficheros


RE_FICHERO = re.compile(r"BORME-A-(\d{4})-(\d+)-(\d{2})")


def meta_from_path(path: Path) -> dict:
    """Fecha y provincia a partir de .../AAAAMMDD/BORME-A-AAAA-NNN-PP.pdf."""
    meta: dict = {"borme_id": path.stem}
    m = RE_FICHERO.search(path.name)
    if m:
        meta["cod_provincia"] = m.group(3)
        meta["provincia"] = provincia_name(m.group(3))
    md = re.search(r"(20\d{2})(\d{2})(\d{2})", path.parent.name)
    if md:
        meta["fecha_publicacion"] = dt.date(*(int(x) for x in md.groups()))
    return meta


def parse_text(text: str, meta: dict | None = None) -> list[Anuncio]:
    meta = dict(meta or {})
    cab = cabecera(text)
    if cab.get("fecha_publicacion") and not meta.get("fecha_publicacion"):
        meta["fecha_publicacion"] = cab["fecha_publicacion"]
    return [parse_anuncio(n, t, meta) for n, t in segment(text)]


def parse_file(path: str | Path, engine: str = "auto") -> list[Anuncio]:
    """Parsea un PDF (o un .txt con el texto ya extraído, útil para pruebas)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.suffix.lower() == ".txt" else pdf_to_text(path, engine)
    return parse_text(text, meta_from_path(path))


def to_frame(anuncios: list[Anuncio]) -> pd.DataFrame:
    rows = []
    for a in anuncios:
        d = asdict(a)
        d.pop("extra", None)
        rows.append(d)
    return pd.DataFrame(rows, columns=[f for f in Anuncio.__dataclass_fields__ if f != "extra"])


def parse_dir(raw_dir: Path, desde: dt.date | None = None, hasta: dt.date | None = None,
              provincias: set[str] | None = None, engine: str = "auto") -> pd.DataFrame:
    """Parsea todos los PDF/TXT de data/raw/borme/AAAAMMDD/ que cumplan los filtros."""
    files = sorted(list(Path(raw_dir).glob("borme/*/BORME-A-*.pdf")) + list(Path(raw_dir).glob("borme/*/BORME-A-*.txt")))
    seen, todos = set(), []
    for f in files:
        meta = meta_from_path(f)
        if f.stem in seen:  # si existen .pdf y .txt del mismo BORME, basta uno
            continue
        fp = meta.get("fecha_publicacion")
        if (desde and fp and fp < desde) or (hasta and fp and fp > hasta):
            continue
        if provincias and meta.get("cod_provincia") not in provincias:
            continue
        seen.add(f.stem)
        try:
            res = parse_file(f, engine)
            log.info("%s: %d anuncios", f.name, len(res))
            todos.extend(res)
        except Exception as e:
            log.error("No se pudo parsear %s: %s", f, e)
    return to_frame(todos)
