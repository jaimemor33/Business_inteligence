"""Backtest de apertura con Google Places API (New): ¿la sociedad constituida tiene hoy un local real?

Para cada constitución candidata:
1. **Text Search (Pro)** con "<denominación limpia> <municipio>". Si no hay emparejamiento suficiente y el
   domicilio parece un local, se hace una 2.ª búsqueda "<tipo de negocio> <dirección> <municipio>", que capta
   los nombres comerciales distintos de la denominación social.
2. Puntuación de emparejamiento (0-1) con nombre (rapidfuzz), dirección (vía + número) y coherencia del tipo de
   Google con el sector. Niveles: alta ≥ 0,75; media ≥ 0,55; baja < 0,55.
3. Solo para alta y media: **Place Details (Enterprise + Atmosphere)** con `reviews` y `userRatingCount`.
   - Fecha de apertura aproximada = la reseña más antigua devuelta. La API devuelve como mucho 5 reseñas,
     ordenadas por relevancia y sin opción de "más antiguas", así que la fecha solo es EXACTA si
     userRatingCount ≤ nº de reseñas devueltas. Si no, es una COTA SUPERIOR: el local abrió ese día o antes.
   - Si la reseña más antigua es anterior a la constitución en más de 60 días, el local es probablemente un
     negocio previo en esa dirección (p. ej. un traspaso) y no cuenta como apertura de esta sociedad.

Coste: tope duro con `presupuesto_usd`. El registro de gasto (data/interim/places_ledger.json) usa el precio de
lista SIN descontar el tramo gratuito mensual, así que el gasto real es igual o menor. Precios por defecto
(USD por 1.000 llamadas, tramo 0-100k; verificar en https://developers.google.com/maps/billing-and-pricing/pricing):
Text Search Pro 32 $; Place Details Enterprise + Atmosphere 40 $ (estimación conservadora).

Requiere GOOGLE_PLACES_API_KEY (o GOOGLE_MAPS_API_KEY) y acceso a places.googleapis.com.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .common import ensure, norm, split_address, street_key

log = logging.getLogger(__name__)

URL_SEARCH = "https://places.googleapis.com/v1/places:searchText"
URL_DETAILS = "https://places.googleapis.com/v1/places/{id}"
MASK_SEARCH = ("places.id,places.displayName,places.formattedAddress,places.types,places.primaryType,"
               "places.businessStatus,places.location")
MASK_DETAILS = "id,userRatingCount,reviews,businessStatus"

# Centro y radio (m) para el sesgo geográfico por código INE de provincia.
CENTROS = {"28": (40.4168, -3.7038, 50000.0), "08": (41.3874, 2.1686, 50000.0)}

# Tipos de Google (Places API New) coherentes con cada sector; sirve para puntuar y para la 2.ª búsqueda.
TIPOS_SECTOR: dict[str, tuple[str, set[str]]] = {
    "hosteleria": ("restaurante bar cafetería", {"restaurant", "bar", "cafe", "coffee_shop", "bakery", "meal_takeaway",
                                                "food", "pub", "fast_food_restaurant", "brunch_restaurant"}),
    "dental": ("clínica dental", {"dentist", "dental_clinic", "doctor", "health"}),
    "medicina_estetica": ("medicina estética", {"skin_care_clinic", "beauty_salon", "doctor", "health", "spa"}),
    "centro_estetica": ("centro de estética", {"beauty_salon", "spa", "nail_salon", "skin_care_clinic"}),
    "peluqueria": ("peluquería barbería", {"hair_salon", "hair_care", "barber_shop", "beauty_salon"}),
    "spa": ("spa", {"spa", "wellness_center", "sauna"}),
    "gimnasio": ("gimnasio", {"gym", "fitness_center", "sports_club"}),
    "boutique_fitness": ("pilates estudio", {"gym", "fitness_center", "yoga_studio", "sports_activity_location"}),
    "fisioterapia": ("fisioterapia", {"physiotherapist", "health", "doctor"}),
    "podologia": ("podología", {"podiatrist", "health", "doctor"}),
    "psicologia": ("psicología", {"psychologist", "health", "doctor"}),
    "optica": ("óptica", {"optician", "store", "health"}),
    "audiologia": ("audífonos centro auditivo", {"health", "store", "doctor"}),
    "veterinaria": ("clínica veterinaria", {"veterinary_care", "pet_store"}),
    "imagen_diagnostica": ("diagnóstico por imagen", {"medical_lab", "hospital", "doctor", "health"}),
    "fertilidad": ("clínica fertilidad", {"doctor", "hospital", "health"}),
    "laboratorio": ("laboratorio análisis clínicos", {"medical_lab", "health"}),
    "escuela_infantil": ("escuela infantil", {"preschool", "school", "child_care_agency"}),
    "academia": ("academia", {"school", "educational_institution", "tutoring_service", "language_school"}),
    "formacion": ("centro de formación", {"school", "educational_institution", "university"}),
    "colegio": ("colegio", {"school", "primary_school", "secondary_school"}),
    "residencia": ("residencia de mayores", {"nursing_home", "health", "lodging"}),
    "centro_dia": ("centro de día mayores", {"nursing_home", "health", "community_center"}),
    "hotel": ("hotel", {"hotel", "lodging", "hostel", "motel"}),
    "apartamentos_turisticos": ("apartamentos turísticos", {"lodging", "apartment_building", "hotel"}),
    "coliving": ("coliving residencia estudiantes", {"lodging", "apartment_building", "dormitory"}),
    "supermercado": ("supermercado", {"supermarket", "grocery_store", "convenience_store", "food_store"}),
    "farmacia": ("farmacia", {"pharmacy", "drugstore", "health"}),
    "retail": ("tienda", {"store", "clothing_store", "shoe_store", "home_goods_store", "book_store", "pet_store"}),
    "taller": ("taller mecánico", {"car_repair", "car_wash", "auto_parts_store"}),
    "lavanderia": ("lavandería", {"laundry", "dry_cleaning"}),
    "coworking": ("coworking", {"coworking_space", "corporate_office"}),
    "logistica": ("almacén logística", {"storage", "warehouse_store", "moving_company"}),
    "industria_alimentaria": ("obrador fábrica", {"food", "bakery", "food_store", "brewery", "winery"}),
}

FORMAS = r"\b(SOCIEDAD LIMITADA( PROFESIONAL| NUEVA EMPRESA| LABORAL)?|SOCIEDAD ANONIMA|S\.?L\.?(U|P|L|NE)?|S\.?A\.?U?|SLU|SLP|SLL|SA)\.?$"
GENERICAS = {"GRUPO", "GESTION", "SERVICIOS", "INVERSIONES", "HOLDING", "EMPRESAS", "SOCIEDAD", "Y", "DE", "DEL",
             "LA", "EL", "LOS", "LAS", "SPAIN", "ESPANA", "IBERIA", "PROYECTOS", "NEGOCIOS", "CB", "COMPANY"}


def nombre_limpio(denominacion: str | None) -> str:
    """'MA5 MAMEY RESTAURACION 2025 SL' -> 'MA5 MAMEY RESTAURACION'."""
    s = norm(denominacion)
    for _ in range(2):
        s = re.sub(FORMAS, "", s).strip(" .,")
    toks = [t for t in re.split(r"[\s,.\-]+", s) if t and not re.fullmatch(r"(19|20)\d{2}", t)]
    return " ".join(toks)


def _nucleo(nombre: str) -> str:
    return " ".join(t for t in nombre.split() if t not in GENERICAS)


@dataclass
class Gasto:
    """Registro de gasto acumulado (persistente) con tope duro."""
    path: Path
    presupuesto_usd: float
    precio_search: float = 32.0    # USD / 1.000 (Text Search Pro)
    precio_details: float = 40.0   # USD / 1.000 (Place Details Enterprise + Atmosphere, conservador)
    llamadas_search: int = 0
    llamadas_details: int = 0

    def __post_init__(self):
        if self.path.exists():
            d = json.loads(self.path.read_text())
            self.llamadas_search, self.llamadas_details = d.get("search", 0), d.get("details", 0)

    @property
    def usd(self) -> float:
        return self.llamadas_search * self.precio_search / 1000 + self.llamadas_details * self.precio_details / 1000

    def puede(self, tipo: str) -> bool:
        p = self.precio_search if tipo == "search" else self.precio_details
        return self.usd + p / 1000 <= self.presupuesto_usd + 1e-9

    def anota(self, tipo: str):
        if tipo == "search":
            self.llamadas_search += 1
        else:
            self.llamadas_details += 1
        ensure(self.path.parent)
        self.path.write_text(json.dumps({"search": self.llamadas_search, "details": self.llamadas_details,
                                         "usd_precio_lista": round(self.usd, 4)}))


class PresupuestoAgotado(Exception):
    pass


class PlacesClient:
    """Cliente mínimo de Places API (New) con caché en disco, reintentos y tope de gasto."""

    def __init__(self, cache_dir: Path, gasto: Gasto, api_key: str | None = None, session=None, pausa: float = 0.05):
        self.key = api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or os.environ.get("GOOGLE_MAPS_API_KEY")
        if not self.key and session is None:
            raise RuntimeError("Falta GOOGLE_PLACES_API_KEY (variable de entorno)")
        self.cache = ensure(Path(cache_dir))
        self.gasto, self.pausa = gasto, pausa
        if session is None:
            import requests
            session = requests.Session()
        self.s = session

    def _cached(self, tipo: str, payload: dict, call):
        k = hashlib.sha1(json.dumps([tipo, payload], sort_keys=True).encode()).hexdigest()
        f = self.cache / f"{tipo}_{k}.json"
        if f.exists():
            return json.loads(f.read_text())
        if not self.gasto.puede(tipo):
            raise PresupuestoAgotado(f"tope de {self.gasto.presupuesto_usd} USD alcanzado")
        for intento in range(4):
            r = call()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** intento)
                continue
            break
        self.gasto.anota(tipo)  # se cobra la llamada aunque devuelva error
        if r.status_code != 200:
            log.warning("Places %s HTTP %s: %s", tipo, r.status_code, r.text[:200])
            return {"_error": r.status_code}
        data = r.json()
        f.write_text(json.dumps(data, ensure_ascii=False))
        time.sleep(self.pausa)
        return data

    def search(self, query: str, cod_provincia: str | None) -> list[dict]:
        body = {"textQuery": query, "languageCode": "es", "regionCode": "ES", "pageSize": 5}
        if cod_provincia in CENTROS:
            lat, lng, rad = CENTROS[cod_provincia]
            body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": rad}}
        h = {"X-Goog-Api-Key": self.key or "", "X-Goog-FieldMask": MASK_SEARCH, "Content-Type": "application/json"}
        d = self._cached("search", body, lambda: self.s.post(URL_SEARCH, json=body, headers=h, timeout=30))
        return d.get("places", []) or []

    def details(self, place_id: str) -> dict:
        h = {"X-Goog-Api-Key": self.key or "", "X-Goog-FieldMask": MASK_DETAILS}
        url = URL_DETAILS.format(id=place_id)
        return self._cached("details", {"id": place_id},
                            lambda: self.s.get(url, params={"languageCode": "es"}, headers=h, timeout=30))


def puntuar(cand: dict, nombre: str, domicilio: str | None, sector: str | None) -> tuple[float, dict]:
    """Puntuación 0-1 de que el lugar `cand` sea el local de la sociedad."""
    from rapidfuzz import fuzz
    disp = norm((cand.get("displayName") or {}).get("text"))
    nuc = _nucleo(nombre)
    s_nombre = max(fuzz.token_set_ratio(nombre, disp), fuzz.token_set_ratio(nuc, disp) if nuc else 0) / 100
    if nuc and len(nuc) >= 4 and nuc in disp:
        s_nombre = max(s_nombre, 0.95)
    s_dir = 0.0
    via, num = split_address(domicilio)
    addr = norm(cand.get("formattedAddress"))
    if via and street_key(addr).find(via) >= 0:
        s_dir = 0.5
        if num and re.search(rf"\b{num}\b", addr):
            s_dir = 1.0
    tipos = set(cand.get("types") or [])
    s_tipo = 1.0 if sector in TIPOS_SECTOR and tipos & TIPOS_SECTOR[sector][1] else 0.0
    score = 0.55 * s_nombre + 0.30 * s_dir + 0.15 * s_tipo
    # 2.ª vía de evidencia: misma dirección exacta + tipo coherente aunque el nombre comercial sea otro
    score = max(score, 0.6 * s_dir + 0.3 * s_tipo + 0.1 * s_nombre)
    return round(score, 3), {"s_nombre": round(s_nombre, 3), "s_dir": s_dir, "s_tipo": s_tipo}


def nivel(score: float) -> str:
    return "alta" if score >= 0.75 else "media" if score >= 0.55 else "baja"


@dataclass
class ResultadoPlaces:
    empresa_key: str
    consulta: str = ""
    place_id: str | None = None
    nombre_google: str | None = None
    direccion_google: str | None = None
    tipos_google: str | None = None
    business_status: str | None = None
    score: float = 0.0
    confianza: str = "sin_resultado"
    detalle_score: str = ""
    n_resenas_total: int | None = None
    n_resenas_devueltas: int = 0
    primera_resena: dt.date | None = None
    fecha_apertura_exacta: bool = False
    negocio_previo: bool = False
    localizable: bool = False
    llamadas: list = field(default_factory=list)


def _local_probable(domicilio: str | None) -> bool:
    d = norm(domicilio)
    return bool(re.search(r"\b(BAJO|BJ|LOCAL|LOC\.?|PLANTA BAJA|PB|NAVE)\b", d)) or not re.search(r"\d+\s*º|\bPISO\b|\bPLANTA [1-9]", d)


def backtest_fila(row: dict, cli: PlacesClient) -> ResultadoPlaces:
    nombre = nombre_limpio(row.get("denominacion"))
    muni = norm(row.get("municipio")) or ""
    res = ResultadoPlaces(empresa_key=row.get("empresa_key") or row.get("denominacion"))
    sector = row.get("sector")
    consultas = [f"{nombre} {muni}".strip()]
    if sector in TIPOS_SECTOR and row.get("domicilio") and _local_probable(row.get("domicilio")):
        calle = re.sub(r"\([^)]*\)\s*$", "", norm(row["domicilio"])).strip()
        consultas.append(f"{TIPOS_SECTOR[sector][0]} {calle} {muni}".strip())
    best = None
    for q in consultas:
        res.llamadas.append("search")
        for c in cli.search(q, row.get("cod_provincia")):
            sc, det = puntuar(c, nombre, row.get("domicilio"), sector)
            if best is None or sc > best[0]:
                best = (sc, det, c, q)
        if best and best[0] >= 0.75:
            break
    if not best:
        return res
    sc, det, c, q = best
    res.consulta, res.score, res.confianza, res.detalle_score = q, sc, nivel(sc), json.dumps(det)
    res.place_id = c.get("id")
    res.nombre_google = (c.get("displayName") or {}).get("text")
    res.direccion_google, res.business_status = c.get("formattedAddress"), c.get("businessStatus")
    res.tipos_google = "|".join(c.get("types") or [])
    if res.confianza in ("alta", "media") and res.place_id:
        res.llamadas.append("details")
        d = cli.details(res.place_id)
        revs = d.get("reviews") or []
        fechas = sorted(pd.to_datetime(r["publishTime"]).date() for r in revs if r.get("publishTime"))
        res.n_resenas_total, res.n_resenas_devueltas = d.get("userRatingCount"), len(revs)
        res.business_status = d.get("businessStatus") or res.business_status
        if fechas:
            res.primera_resena = fechas[0]
            res.fecha_apertura_exacta = (res.n_resenas_total or 0) <= len(revs)
            ref = row.get("comienzo_operaciones") or row.get("fecha_publicacion")
            ref = pd.to_datetime(ref).date() if ref is not None and str(ref) not in ("", "nan", "NaT", "None") else None
            res.negocio_previo = bool(ref and (ref - fechas[0]).days > 60)
        res.localizable = not res.negocio_previo
    return res


def run(cands: pd.DataFrame, interim: Path, presupuesto_usd: float, session=None, api_key: str | None = None,
        precio_search: float = 32.0, precio_details: float = 40.0) -> tuple[pd.DataFrame, Gasto]:
    """Ejecuta el backtest sobre `cands` hasta agotar la lista o el presupuesto."""
    gasto = Gasto(Path(interim) / "places_ledger.json", presupuesto_usd, precio_search, precio_details)
    cli = PlacesClient(Path(interim) / "places_cache", gasto, api_key=api_key, session=session)
    out = []
    for row in cands.to_dict("records"):
        try:
            r = backtest_fila(row, cli)
        except PresupuestoAgotado as e:
            log.warning("Places: %s; se para tras %d sociedades", e, len(out))
            break
        d = asdict(r)
        d["llamadas"] = "|".join(r.llamadas)
        out.append(d)
    log.info("Places: %d sociedades, gasto a precio de lista %.2f USD", len(out), gasto.usd)
    return pd.DataFrame(out), gasto
