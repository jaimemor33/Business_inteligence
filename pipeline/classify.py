"""Clasificador sectorial del objeto social (BORME) y del epígrafe (censo de Madrid).

Capa (a), reglas: código CNAE -> sector y diccionario de palabras clave ponderadas por sector,
más una categoría de RUIDO (sociedades que no abren un local con compras: holdings,
patrimoniales, inversión, consultoría genérica, comercio online...). Devuelve sector,
confianza 0-1 y la regla que disparó la clasificación.

Capa (b), opcional, LLM: los casos de baja confianza se envían a la API de Anthropic
(ver classify_llm). Solo se activa si existe ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .common import norm

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- sectores
# Pesos: 3 = término inequívoco, 2 = fuerte, 1 = débil/ambiguo. Patrones sobre texto normalizado
# (mayúsculas, sin tildes). '\b' se añade automáticamente al inicio del patrón.
SECTORES: dict[str, dict] = {
    "hosteleria": {"kw": {
        r"RESTAURANTES?\b": 3, r"BAR(ES)?\b": 3, r"CAFETERIAS?\b": 3, r"HOSTELERIA": 3, r"TABERNAS?\b": 3,
        r"CERVECERIAS?\b": 3, r"PIZZERIAS?\b": 3, r"HELADERIAS?\b": 2, r"ASADOR": 2, r"BRUNCH": 2,
        r"COMIDAS? (PREPARADAS )?PARA LLEVAR": 2, r"OCIO NOCTURNO": 2, r"DISCOTECAS?\b": 2, r"PUBS?\b": 2,
        r"SERVICIOS? DE COMIDAS Y BEBIDAS": 3, r"RESTAURACION\b(?! DE (MUEBLES|OBRAS|ARTE|EDIFICIOS))": 2,
        r"CATERING": 1, r"GASTROBAR": 3, r"COCTELERIA": 3, r"CHURRERIA": 2, r"BOCATERIA": 3}},
    "dental": {"kw": {
        r"CLINICAS? DENTAL(ES)?": 3, r"ODONTOLOG": 3, r"ESTOMATOLOG": 3, r"ORTODONCIA": 3, r"IMPLANTOLOG": 3,
        r"BUCODENTAL": 3, r"DENTAL(ES)?\b": 1, r"DENTISTA": 3}},
    "medicina_estetica": {"kw": {
        r"MEDICINA ESTETICA": 3, r"CIRUGIA (PLASTICA|ESTETICA)": 3, r"CLINICAS? (DE MEDICINA )?ESTETICA": 2,
        r"TRATAMIENTOS (MEDICO[- ])?ESTETICOS? MEDICOS": 3, r"MEDICINA ANTIENVEJECIMIENTO": 2,
        r"INFILTRACIONES": 1, r"CAPILAR(ES)? INJERTO|INJERTO CAPILAR": 3}},
    "centro_estetica": {"kw": {
        r"CENTROS? DE ESTETICA": 3, r"CENTROS? DE BELLEZA": 3, r"TRATAMIENTOS DE BELLEZA": 3, r"ESTETICA\b": 1,
        r"MANICURA": 2, r"PEDICURA": 2, r"DEPILACION": 2, r"UÑAS\b": 2, r"PESTAÑAS": 2, r"MICROPIGMENTACION": 2,
        r"BRONCEADO|SOLARIUM": 2, r"COSMETOLOG": 1, r"MASAJES?\b": 1}},
    "peluqueria": {"kw": {
        r"PELUQUERIAS?\b(?! CANINA)": 3, r"BARBERIAS?\b": 3, r"BARBEROS?\b": 2, r"SALON(ES)? DE BELLEZA": 2}},
    "spa": {"kw": {
        r"SPA\b": 3, r"BALNEARIO": 3, r"CIRCUITOS? (DE )?AGUAS?": 3, r"SAUNAS?\b": 2, r"HAMMAM|BAÑOS ARABES": 3,
        r"HIDROTERAPIA": 2, r"WELLNESS": 2}},
    "gimnasio": {"kw": {
        r"GIMNASIOS?\b": 3, r"INSTALACIONES DEPORTIVAS": 2, r"CENTROS? DEPORTIVOS?": 2, r"FITNESS": 1,
        r"MUSCULACION": 2, r"ACTIVIDADES? DE MANTENIMIENTO FISICO": 2}},
    "boutique_fitness": {"kw": {
        r"PILATES": 3, r"YOGA": 3, r"CROSSFIT|CROSS TRAINING": 3, r"ENTRENAMIENTO PERSONAL": 3,
        r"ENTRENADOR PERSONAL": 2, r"CICLO INDOOR|INDOOR CYCLING|SPINNING": 3, r"BOUTIQUE FITNESS": 3,
        r"ESTUDIOS? DE (ENTRENAMIENTO|FITNESS|BAILE|DANZA)": 2, r"BOXEO|ARTES MARCIALES": 1, r"BARRE\b": 2}},
    "fisioterapia": {"kw": {
        r"FISIOTERAP": 3, r"OSTEOPAT": 3, r"QUIROMASAJE": 2, r"QUIROPRACT": 2, r"REHABILITACION FISICA": 2,
        r"READAPTACION DEPORTIVA": 2, r"REHABILITACION\b": 1}},
    "podologia": {"kw": {r"PODOLOG": 3, r"QUIROPODIA": 3, r"BIOMECANICA DE LA MARCHA": 2}},
    "psicologia": {"kw": {
        r"PSICOLOG": 3, r"PSICOTERAP": 3, r"PSIQUIATR": 2, r"LOGOPEDIA": 2, r"NEUROPSICOLOG": 3,
        r"TERAPIA OCUPACIONAL": 1, r"SALUD MENTAL": 2}},
    "optica": {"kw": {
        r"OPTICAS?\b": 3, r"OPTOMETR": 3, r"GAFAS": 2, r"LENTES DE CONTACTO": 3, r"ARTICULOS? DE OPTICA": 3}},
    "audiologia": {"kw": {
        r"AUDIOLOG": 3, r"AUDIFONOS": 3, r"AUDIOPROTES": 3, r"CENTROS? AUDITIVOS?": 3, r"AUDIOMETR": 2}},
    "veterinaria": {"kw": {
        r"VETERINARI": 3, r"HOSPITAL(ES)? VETERINARIO": 3, r"ANIMALES DE COMPAÑIA": 1, r"PELUQUERIA CANINA": 1}},
    "imagen_diagnostica": {"kw": {
        r"DIAGNOSTICO POR (LA )?IMAGEN": 3, r"RADIOLOG": 3, r"RESONANCIA MAGNETICA": 3, r"ECOGRAF": 2,
        r"MAMOGRAF": 3, r"TOMOGRAF": 3, r"DENSITOMETR": 2}},
    "fertilidad": {"kw": {
        r"REPRODUCCION (HUMANA )?ASISTIDA": 3, r"FERTILIDAD": 3, r"FECUNDACION IN VITRO": 3, r"CRIOPRESERV": 2,
        r"BANCO DE (OVULOS|SEMEN)": 3}},
    "laboratorio": {"kw": {
        r"LABORATORIOS? DE ANALISIS CLINICOS": 3, r"ANALISIS CLINICOS": 3, r"LABORATORIOS? CLINICOS?": 3,
        r"LABORATORIOS? DENTAL(ES)?": 3, r"PROTESIS DENTAL(ES)?": 2, r"PROTESICO DENTAL": 3,
        r"EXTRACCION(ES)? DE (MUESTRAS|SANGRE)": 2, r"LABORATORIO\b": 1}},
    "escuela_infantil": {"kw": {
        r"ESCUELAS? INFANTIL(ES)?": 3, r"GUARDERIAS?\b": 3, r"PRIMER CICLO DE EDUCACION INFANTIL": 3,
        r"EDUCACION INFANTIL": 2, r"CENTROS? DE EDUCACION INFANTIL": 3, r"LUDOTECAS?\b": 1}},
    "academia": {"kw": {
        r"ACADEMIAS?\b": 3, r"CLASES PARTICULARES": 3, r"REFUERZO ESCOLAR": 3, r"ENSEÑANZA DE IDIOMAS": 3,
        r"ESCUELA DE IDIOMAS": 3, r"IDIOMAS": 1, r"AUTOESCUELA": 2, r"PREPARACION DE OPOSICIONES": 2,
        r"ESCUELA DE (MUSICA|DANZA|BAILE)": 2, r"CLASES DE (MUSICA|DANZA|BAILE|PINTURA)": 2}},
    "formacion": {"kw": {
        r"FORMACION PROFESIONAL PARA EL EMPLEO": 3, r"CENTROS? DE FORMACION": 3, r"CURSOS DE FORMACION": 2,
        r"FORMACION (PRESENCIAL|PROFESIONAL|CONTINUA)": 2, r"FORMACION\b": 1, r"CERTIFICADOS DE PROFESIONALIDAD": 3}},
    "colegio": {"kw": {
        r"COLEGIOS?\b(?! (OFICIAL|PROFESIONAL))": 3, r"CENTROS? EDUCATIVOS?": 2, r"EDUCACION PRIMARIA": 3,
        r"EDUCACION SECUNDARIA": 3, r"BACHILLERATO": 3, r"CENTROS? DOCENTES?": 2, r"ENSEÑANZA REGLADA": 2}},
    "residencia": {"kw": {
        r"RESIDENCIAS? (DE|PARA) (PERSONAS )?(MAYORES|ANCIANOS|LA TERCERA EDAD)": 3, r"RESIDENCIAS? GERIATRICAS?": 3,
        r"TERCERA EDAD": 2, r"PERSONAS (MAYORES|DEPENDIENTES)": 1, r"ATENCION RESIDENCIAL": 3,
        r"CENTROS? SOCIOSANITARIOS?": 2, r"GERIATR": 2, r"DEPENDENCIA": 1}},
    "centro_dia": {"kw": {r"CENTROS? DE DIA": 3, r"ESTANCIAS DIURNAS": 3, r"CENTROS? DE NOCHE": 2}},
    "hotel": {"kw": {
        r"HOTEL(ES|ERO|ERA|EROS|ERAS)?\b": 3, r"HOSTALE?S?\b": 3, r"ALBERGUES?\b": 2, r"PENSION(ES)?\b(?! DE)": 2,
        r"ESTABLECIMIENTOS? HOTELEROS?": 3, r"ALOJAMIENTO HOTELERO": 3}},
    "apartamentos_turisticos": {"kw": {
        r"APARTAMENTOS? TURISTICOS?": 3, r"VIVIENDAS? DE USO TURISTICO": 3, r"VIVIENDAS? TURISTICAS?": 3,
        r"VUT\b": 3, r"ALQUILER VACACIONAL": 3, r"ALQUILER (DE )?CORTA ESTANCIA": 2, r"ALOJAMIENTOS? TURISTICOS?": 2}},
    "coliving": {"kw": {
        r"CO-?LIVING": 3, r"RESIDENCIAS? (DE ESTUDIANTES|UNIVERSITARIAS?)": 3, r"COLEGIOS? MAYOR(ES)?": 3,
        r"ALOJAMIENTO COMPARTIDO": 3, r"VIVIENDA COMPARTIDA": 2}},
    "supermercado": {"kw": {
        r"SUPERMERCADOS?\b": 3, r"AUTOSERVICIOS?\b(?! DE LAVADO)": 2, r"HIPERMERCADO": 3,
        r"TIENDAS? DE ALIMENTACION": 3, r"ULTRAMARINOS": 3, r"COMERCIO AL (POR )?MENOR DE (PRODUCTOS )?ALIMENT": 2,
        r"FRUTERIAS?\b": 2, r"CARNICERIAS?\b": 2, r"PESCADERIAS?\b": 2, r"ALIMENTACION\b": 1}},
    "farmacia": {"kw": {r"OFICINAS? DE FARMACIA": 3, r"FARMACIAS?\b": 3, r"PARAFARMACIA": 2}},
    "retail": {"kw": {
        r"COMERCIO AL (POR )?MENOR": 2, r"TIENDAS?\b": 1, r"VENTA AL PUBLICO": 2, r"ESTABLECIMIENTOS? COMERCIAL": 2,
        r"PRENDAS DE VESTIR|ROPA\b|MODA\b": 1, r"CALZADO": 1, r"FLORISTERIA": 3, r"LIBRERIA": 2, r"FERRETERIA": 3,
        r"JOYERIA": 2, r"PAPELERIA": 2, r"JUGUETERIA": 3, r"ESTANCO|EXPENDEDURIA DE TABACO": 3, r"DROGUERIA": 2,
        r"PANADERIAS?\b": 1, r"PASTELERIAS?\b": 1, r"ESTABLECIMIENTOS? DE CONVENIENCIA": 2}},
    "taller": {"kw": {
        r"TALLER(ES)? (MECANICO|DE REPARACION|DE AUTOMOVILES|DE VEHICULOS)": 3,
        r"(MANTENIMIENTO Y )?REPARACION DE (VEHICULOS|AUTOMOVILES|MOTOCICLETAS)": 3, r"CHAPA Y PINTURA": 3,
        r"ELECTROMECANICA": 2, r"NEUMATICOS": 2, r"MECANICA DEL AUTOMOVIL": 3, r"TALLER(ES)?\b": 1}},
    "lavanderia": {"kw": {r"LAVANDERIAS?\b": 3, r"TINTORERIAS?\b": 3, r"AUTOSERVICIO DE LAVADO": 3,
                          r"LIMPIEZA EN SECO": 3, r"LAVADO DE (ROPA|PRENDAS)": 2}},
    "coworking": {"kw": {r"CO-?WORKING": 3, r"ESPACIOS? DE TRABAJO COMPARTIDO": 3, r"CENTROS? DE NEGOCIOS": 2,
                         r"OFICINAS? COMPARTIDAS": 2, r"DESPACHOS? COMPARTIDOS?": 2, r"OFICINAS? FLEXIBLES": 2}},
    "logistica": {"kw": {
        r"LOGISTICA": 2, r"OPERADOR(ES)? LOGISTICOS?": 3, r"ALMACENAJE": 2, r"ALMACENAMIENTO Y DISTRIBUCION": 3,
        r"TRANSPORTE DE MERCANCIAS": 2, r"PAQUETERIA": 2, r"MENSAJERIA": 2, r"ULTIMA MILLA": 3,
        r"CROSS-?DOCKING": 3, r"CENTROS? DE DISTRIBUCION": 2}},
    "industria_alimentaria": {"kw": {
        r"(FABRICACION|ELABORACION|PRODUCCION|TRANSFORMACION) DE (PRODUCTOS )?ALIMENT": 3, r"INDUSTRIA ALIMENTARIA": 3,
        r"OBRADOR": 2, r"CONSERVAS": 2, r"MATADERO": 3, r"ELABORACION DE (CERVEZA|VINOS?|PAN|BOLLERIA|QUESOS?)": 3,
        r"CERVECERA ARTESANAL|MICROCERVECERIA": 3, r"ENVASADO DE (ALIMENTOS|PRODUCTOS ALIMENTICIOS)": 3,
        r"COCINA CENTRAL|DARK KITCHEN|COCINAS? FANTASMA": 2, r"PLATOS PREPARADOS": 2}},
    # Sectores que sí son actividad real pero quedan fuera del alcance del producto.
    "otros": {"kw": {
        r"CONSTRUCCION": 1, r"REFORMAS": 1, r"INSTALACIONES ELECTRICAS": 1, r"FONTANERIA": 1, r"PINTURA\b": 1,
        r"TRANSPORTE DE VIAJEROS": 1, r"TAXI\b|VTC\b": 2, r"AGRICULTURA|AGRICOLA": 1, r"GANADERIA": 1,
        r"AGENCIA DE VIAJES": 1, r"SEGURIDAD PRIVADA": 1, r"LIMPIEZA DE (EDIFICIOS|LOCALES|OFICINAS)": 1}},
}

# Ruido: sociedades sin apertura de local (o sin compras de apertura relevantes).
RUIDO_KW: dict[str, float] = {
    r"TENENCIA (Y GESTION )?DE (PARTICIPACIONES|ACCIONES|VALORES)": 3, r"HOLDING": 3, r"SOCIEDAD HOLDING": 3,
    r"GESTION (Y ADMINISTRACION )?DE(L)? (SU )?PATRIMONIO": 3, r"PATRIMONIAL": 2,
    r"ARRENDAMIENTO DE (BIENES )?INMUEBLES": 2, r"ALQUILER DE (BIENES )?INMUEBLES": 2, r"ARRENDAMIENTO DE VIVIENDAS": 2,
    r"COMPRA ?VENTA (Y ARRENDAMIENTO )?DE (BIENES )?INMUEBLES": 2, r"PROMOCION INMOBILIARIA": 2,
    r"ACTIVIDADES INMOBILIARIAS": 2, r"INVERSION(ES)? (FINANCIERAS|EN VALORES|INMOBILIARIAS)": 2,
    r"INVERSION(ES)?\b": 1, r"ADQUISICION,? (TENENCIA|ENAJENACION)": 2, r"CAPITAL RIESGO": 3, r"SOCIMI": 3,
    r"CONSULTORIA (DE GESTION|EMPRESARIAL|ESTRATEGICA)": 2, r"CONSULTORIA\b": 1, r"ASESORAMIENTO (EMPRESARIAL|FINANCIERO)": 2,
    r"COMERCIO ELECTRONICO": 2, r"VENTA (ONLINE|ON LINE|POR INTERNET|A TRAVES DE INTERNET)": 2, r"E-?COMMERCE": 2,
    r"MARKETING DIGITAL": 2, r"DESARROLLO DE SOFTWARE": 2, r"SERVICIOS INFORMATICOS": 1, r"PROGRAMACION INFORMATICA": 2,
    r"INTERMEDIACION": 1, r"IMPORTACION Y EXPORTACION": 1, r"GESTION DE (CARTERAS|ACTIVOS)": 2,
    r"CRIPTO": 2, r"TRADING": 2, r"SOCIEDAD DE GESTION": 1, r"PRESTACION DE SERVICIOS PROFESIONALES": 1,
}

# CNAE -> sector. Prefijos (2, 3 o 4 dígitos); gana el prefijo más largo. Se mezclan CNAE-2009 y
# CNAE-2025 (en vigor desde 2025); donde ambas versiones discrepan se comenta.
# NOTA: verificar contra la tabla oficial del INE de CNAE-2025 antes de usar en producción.
CNAE_SECTOR: dict[str, str] = {
    "56": "hosteleria", "5621": "hosteleria", "10": "industria_alimentaria",
    "11": "industria_alimentaria", "12": "otros",
    "8623": "dental", "8622": "sanitario_generico", "8621": "sanitario_generico", "8610": "sanitario_generico",
    "8690": "sanitario_generico",          # CNAE-2009: cajón de sastre (fisio, podología, psicología, labs...)
    "8691": "imagen_diagnostica",          # CNAE-2025: diagnóstico por imagen y laboratorios médicos (ambiguo)
    "8693": "psicologia",                  # CNAE-2025: psicólogos y psicoterapeutas
    "8695": "fisioterapia",                # CNAE-2025: fisioterapia
    "8699": "sanitario_generico",
    "3250": "laboratorio",                 # fabricación de prótesis dentales (laboratorio protésico)
    "9602": "peluqueria",                  # CNAE-2009: peluquería y otros tratamientos de belleza
    "9621": "peluqueria", "9622": "centro_estetica", "9623": "spa",   # CNAE-2025
    "9604": "spa",                         # CNAE-2009: actividades de mantenimiento físico (spa, sauna)
    "9313": "gimnasio", "9311": "gimnasio", "9319": "gimnasio",
    "8510": "escuela_infantil", "8520": "colegio", "8531": "colegio", "8532": "formacion",
    "8541": "formacion", "8551": "academia", "8552": "academia", "8553": "academia", "8559": "academia",
    "8710": "residencia", "8730": "residencia", "8731": "residencia", "8732": "residencia", "8790": "residencia",
    "8811": "centro_dia", "8812": "centro_dia",
    "5510": "hotel", "5520": "apartamentos_turisticos", "5530": "otros", "5590": "coliving",
    "4711": "supermercado", "472": "supermercado", "4721": "supermercado", "4722": "supermercado",
    "4723": "supermercado", "4724": "retail", "4729": "supermercado",
    "4773": "farmacia", "4774": "audiologia", "4778": "retail",
    "47": "retail", "4791": "ruido", "4799": "retail",
    "7500": "veterinaria", "75": "veterinaria",
    "4520": "taller", "4540": "taller", "9531": "taller", "9532": "taller",  # 95.3x: reparación de vehículos (CNAE-2025)
    "9601": "lavanderia", "9610": "lavanderia",
    "52": "logistica", "4941": "logistica", "5320": "logistica", "5310": "logistica",
    "6420": "ruido", "6430": "ruido", "6499": "ruido", "6810": "ruido", "6820": "ruido", "4110": "ruido",
    "7010": "ruido", "7022": "ruido", "6201": "ruido", "6202": "ruido", "6209": "ruido", "7311": "ruido",
    "41": "otros", "42": "otros", "43": "otros", "49": "otros", "01": "otros", "62": "ruido",
}
# Sectores CNAE que necesitan las palabras clave para concretar (p. ej. 8690).
CNAE_GENERICOS = {"sanitario_generico", "retail", "otros"}
SANITARIOS = {"dental", "medicina_estetica", "fisioterapia", "podologia", "psicologia", "optica", "audiologia",
              "imagen_diagnostica", "fertilidad", "laboratorio"}
TODOS_SECTORES = list(SECTORES) + ["ruido", "sin_clasificar"]

_COMPILED = {s: [(re.compile(r"\b" + p), w) for p, w in d["kw"].items()] for s, d in SECTORES.items()}
_RUIDO = [(re.compile(r"\b" + p), w) for p, w in RUIDO_KW.items()]


@dataclass
class Clasificacion:
    sector: str
    confianza: float
    regla: str
    metodo: str  # 'cnae' | 'keywords' | 'ruido' | 'llm' | 'ninguno'


def _cnae_sector(codes: list[str]) -> tuple[str | None, str | None]:
    for code in codes:
        for n in (4, 3, 2, 1):
            s = CNAE_SECTOR.get(code[:n])
            if s:
                return s, code
    return None, None


def _scores(text: str, patterns, cabeza_chars: int = 160) -> tuple[float, list[str], int]:
    """Suma de pesos de patrones distintos encontrados; bonificación x1.5 si aparecen al principio
    del objeto social (la primera actividad enumerada suele ser la principal). Devuelve también la
    posición de la primera coincidencia (desempate)."""
    total, hits, first = 0.0, [], 10**9
    for rx, w in patterns:
        m = rx.search(text)
        if m:
            total += w * (1.5 if m.start() < cabeza_chars else 1.0)
            hits.append(m.group(0).strip())
            first = min(first, m.start())
    return total, hits, first


def classify_text(objeto: str | None, denominacion: str | None = None, cnae: str | list[str] | None = None) -> Clasificacion:
    """Clasifica un objeto social (+ denominación y CNAE si los hay)."""
    texto = norm(objeto)
    den = norm(denominacion)
    codes = [c for c in (cnae.split("|") if isinstance(cnae, str) else (cnae or [])) if c]

    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    pos: dict[str, int] = {}
    for s, pats in _COMPILED.items():
        sc, h, p = _scores(texto, pats)
        sd, hd, _ = _scores(den, pats, cabeza_chars=0)
        if sc or sd:
            scores[s] = sc + 0.5 * sd
            hits[s] = h + [f"den:{x}" for x in hd]
            pos[s] = p
    ruido, ruido_hits, _ = _scores(texto, _RUIDO)
    ranking = sorted(scores.items(), key=lambda kv: (-kv[1], pos[kv[0]]))
    s1, v1 = ranking[0] if ranking else (None, 0.0)
    v2 = ranking[1][1] if len(ranking) > 1 else 0.0

    # 1) CNAE explícito en el objeto social.
    cs, code = _cnae_sector(codes)
    if cs and cs not in CNAE_GENERICOS:
        acuerdo = s1 == cs
        conf = 0.95 if acuerdo or not s1 else (0.85 if v1 < 4 else 0.7)
        return Clasificacion(cs, conf, f"cnae:{code}" + (f"+kw:{','.join(hits.get(cs, [])[:3])}" if acuerdo else ""), "cnae")
    if cs in CNAE_GENERICOS and s1:
        if cs == "sanitario_generico" and s1 in SANITARIOS:
            return Clasificacion(s1, min(0.9, 0.6 + 0.05 * v1), f"cnae:{code}+kw:{','.join(hits[s1][:3])}", "cnae")
        if cs == "retail" and s1 in ("retail", "supermercado", "optica", "audiologia", "farmacia"):
            return Clasificacion(s1, min(0.9, 0.6 + 0.05 * v1), f"cnae:{code}+kw:{','.join(hits[s1][:3])}", "cnae")

    # 2) Palabras clave.
    if not s1 and not ruido:
        if cs:  # CNAE genérico sin palabras clave
            return Clasificacion(cs if cs != "sanitario_generico" else "sin_clasificar", 0.4, f"cnae:{code}", "cnae")
        return Clasificacion("sin_clasificar", 0.0, "sin_coincidencias", "ninguno")
    if ruido >= v1 or (ruido >= 3 and v1 < 3):
        conf = min(0.95, 0.5 + 0.1 * ruido) * (0.6 if v1 >= 3 else 1.0)
        return Clasificacion("ruido", round(conf, 3), "ruido:" + ",".join(ruido_hits[:3]), "ruido")
    margen = (v1 - v2) / v1 if v1 else 0.0
    conf = min(0.9, 0.3 + 0.1 * v1) * (0.5 + 0.5 * margen)
    if len(ranking) >= 4:  # objeto "cajón de sastre" con muchas actividades
        conf *= 0.8
    if ruido:
        conf *= 0.85
    return Clasificacion(s1, round(conf, 3), f"kw:{s1}[{','.join(hits[s1][:4])}]", "keywords")


def classify_frame(df: pd.DataFrame, objeto_col: str = "objeto_social", den_col: str = "denominacion",
                   cnae_col: str = "cnae") -> pd.DataFrame:
    """Añade sector, confianza, regla y metodo. Conserva siempre el objeto social original."""
    def col(c):
        if c not in df.columns:
            return [None] * len(df)
        return [None if (v is None or (isinstance(v, float) and v != v)) else v for v in df[c]]

    res = [classify_text(o, d, c) for o, d, c in zip(col(objeto_col), col(den_col), col(cnae_col))]
    out = df.copy()
    out["sector"] = [r.sector for r in res]
    out["confianza"] = [r.confianza for r in res]
    out["regla"] = [r.regla for r in res]
    out["metodo"] = [r.metodo for r in res]
    out["justificacion_llm"] = None
    return out


# --------------------------------------------------------------------------- capa LLM (opcional)
# Modelo barato y actual para clasificación de textos cortos: Claude Haiku 4.5. Salida estructurada
# con JSON Schema (output_config.format) para garantizar JSON válido con un sector del catálogo.
# Más de `batch_threshold` casos -> Message Batches API (50 % más barata, asíncrona).
LLM_MODEL = os.environ.get("BI_LLM_MODEL", "claude-haiku-4-5")
PROMPT_VERSION = "v1"
SECTORES_LLM = [s for s in TODOS_SECTORES if s != "sin_clasificar"] + ["sin_clasificar"]

SYSTEM_PROMPT = f"""Clasificas sociedades españolas recién inscritas en el BORME según el tipo de local que van a abrir.
Recibes la denominación y el objeto social. Devuelve el sector principal (la actividad que más probablemente
se ejercerá en un local abierto al público o en una nave), una confianza entre 0 y 1 y una justificación
de una frase en español.

Sectores permitidos: {", ".join(SECTORES_LLM)}.
- "ruido": holdings, tenencia de participaciones, sociedades patrimoniales, alquiler o compraventa de inmuebles,
  inversión, consultoría genérica, comercio online sin local, software, intermediación.
- "otros": actividad real fuera de los sectores listados (construcción, transporte de viajeros, agricultura...).
- "sin_clasificar": el texto no permite decidir.
Los objetos sociales "cajón de sastre" que enumeran muchas actividades distintas deben llevar confianza baja,
salvo que la denominación aclare la actividad (p. ej. "... DENTAL SL")."""

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "sector": {"type": "string", "enum": SECTORES_LLM},
        "confianza": {"type": "number"},
        "justificacion": {"type": "string"},
    },
    "required": ["sector", "confianza", "justificacion"],
    "additionalProperties": False,
}


def _llm_params(denominacion: str | None, objeto: str | None) -> dict:
    return {
        "model": LLM_MODEL,
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Denominación: {denominacion or '-'}\nObjeto social: {objeto or '-'}"}],
        "output_config": {"format": {"type": "json_schema", "schema": LLM_SCHEMA}},
    }


def _cache_key(denominacion, objeto) -> str:
    return hashlib.sha1(f"{LLM_MODEL}|{PROMPT_VERSION}|{denominacion}|{objeto}".encode()).hexdigest()


def _parse_llm_message(msg) -> dict | None:
    if getattr(msg, "stop_reason", None) in ("refusal", "max_tokens"):
        return None
    text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), None)
    if not text:
        return None
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return None
    if d.get("sector") not in SECTORES_LLM:
        return None
    d["confianza"] = max(0.0, min(1.0, float(d.get("confianza", 0))))
    return d


def classify_llm(rows: list[dict], cache_path: Path, client=None, batch_threshold: int = 50,
                 poll_seconds: int = 60) -> dict[int, dict]:
    """Clasifica con Claude las filas [{'idx', 'denominacion', 'objeto_social'}].

    Devuelve {idx: {'sector', 'confianza', 'justificacion'}}. Usa una caché JSONL en disco para no
    pagar dos veces el mismo texto. Requiere ANTHROPIC_API_KEY (o un `client` inyectado).
    """
    import time

    cache: dict[str, dict] = {}
    cache_path = Path(cache_path)
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                cache[rec["key"]] = rec["result"]
    out: dict[int, dict] = {}
    pending: list[tuple[int, str, dict]] = []
    for r in rows:
        key = _cache_key(r.get("denominacion"), r.get("objeto_social"))
        if key in cache:
            out[r["idx"]] = cache[key]
        else:
            pending.append((r["idx"], key, _llm_params(r.get("denominacion"), r.get("objeto_social"))))
    if not pending:
        return out

    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    nuevos: dict[str, dict] = {}

    if len(pending) <= batch_threshold:
        import anthropic
        for idx, key, params in pending:
            try:
                msg = client.messages.create(**params)
            except anthropic.RateLimitError as e:  # el SDK ya reintenta; si persiste, se deja sin clasificar
                log.warning("LLM rate limit en fila %s: %s", idx, e)
                continue
            except anthropic.APIStatusError as e:
                log.warning("LLM error HTTP %s en fila %s: %s", e.status_code, idx, e.message)
                continue
            except anthropic.APIConnectionError as e:
                log.warning("LLM sin conexión en fila %s: %s", idx, e)
                continue
            d = _parse_llm_message(msg)
            if d:
                nuevos[key] = d
                out[idx] = d
    else:
        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request
        by_custom = {f"r{idx}": (idx, key) for idx, key, _ in pending}
        batch = client.messages.batches.create(requests=[
            Request(custom_id=f"r{idx}", params=MessageCreateParamsNonStreaming(**params))
            for idx, _, params in pending])
        log.info("Lote LLM %s enviado (%d peticiones)", batch.id, len(pending))
        while True:
            b = client.messages.batches.retrieve(batch.id)
            if b.processing_status == "ended":
                break
            log.info("Lote %s: %s", batch.id, b.processing_status)
            time.sleep(poll_seconds)
        for res in client.messages.batches.results(batch.id):
            idx, key = by_custom[res.custom_id]  # los resultados llegan en cualquier orden
            if res.result.type != "succeeded":
                log.warning("Lote: %s -> %s", res.custom_id, res.result.type)
                continue
            d = _parse_llm_message(res.result.message)
            if d:
                nuevos[key] = d
                out[idx] = d

    if nuevos:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("a", encoding="utf-8") as f:
            for k, v in nuevos.items():
                f.write(json.dumps({"key": k, "result": v}, ensure_ascii=False) + "\n")
    return out


def apply_llm(df: pd.DataFrame, cache_path: Path, umbral: float = 0.6, client=None, max_filas: int | None = None,
              **kw) -> pd.DataFrame:
    """Reclasifica con LLM las filas con confianza < umbral que tengan objeto social.

    Solo actúa si hay cliente inyectado o ANTHROPIC_API_KEY; si no, devuelve df sin cambios.
    """
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        log.info("ANTHROPIC_API_KEY no definida: se omite la capa LLM")
        return df
    mask = (df["confianza"] < umbral) & df["objeto_social"].notna() & (df["objeto_social"].astype(str).str.len() > 10)
    cand = df[mask]
    if max_filas:
        cand = cand.head(max_filas)
    rows = [{"idx": i, "denominacion": r.denominacion, "objeto_social": r.objeto_social} for i, r in cand.iterrows()]
    log.info("Capa LLM: %d filas de baja confianza", len(rows))
    res = classify_llm(rows, cache_path, client=client, **kw)
    out = df.copy()
    for idx, d in res.items():
        if d["confianza"] > out.at[idx, "confianza"]:
            out.at[idx, "sector"] = d["sector"]
            out.at[idx, "confianza"] = round(d["confianza"], 3)
            out.at[idx, "regla"] = f"llm:{LLM_MODEL}"
            out.at[idx, "metodo"] = "llm"
            out.at[idx, "justificacion_llm"] = d["justificacion"]
    return out
