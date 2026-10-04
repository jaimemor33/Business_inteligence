"""Utilidades compartidas: rutas, normalización de texto, fechas y provincias."""
from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------- rutas


def data_dir(override: str | os.PathLike | None = None) -> Path:
    """Directorio de datos: argumento > variable BI_DATA_DIR > ./data."""
    p = Path(override or os.environ.get("BI_DATA_DIR", "data"))
    return p


def ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------- texto


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str | None) -> str:
    """Mayúsculas, sin tildes (conserva la Ñ), espacios colapsados."""
    if not s:
        return ""
    s = str(s).upper().replace("Ñ", "\0")
    s = strip_accents(s).replace("\0", "Ñ")
    return re.sub(r"\s+", " ", s).strip()


def norm_key(s: str | None) -> str:
    """Normalización para nombres de columna: minúsculas, ascii, '_' como separador."""
    s = strip_accents(str(s or "")).lower().strip().lstrip("\ufeff")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


# --------------------------------------------------------------------------- fechas

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _year(y: int) -> int:
    return y + 2000 if y < 100 else y


def parse_fecha(s: str | None) -> dt.date | None:
    """Fechas del BORME: '15.07.26', '1.9.2026', '15/07/2026', '15-07-26', '15 de julio de 2026'."""
    if not s:
        return None
    s = s.strip().lower()
    m = re.search(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})", s)
    try:
        if m:
            d, mo, y = (int(x) for x in m.groups())
            return dt.date(_year(y), mo, d)
        m = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", strip_accents(s))
        if m and m.group(2) in MESES:
            return dt.date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
    return None


def parse_iso(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def daterange(desde: dt.date, hasta: dt.date, laborables: bool = True):
    """Días entre dos fechas (inclusive). El BORME se publica de lunes a viernes."""
    d = desde
    while d <= hasta:
        if not laborables or d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def parse_importe(s: str | None) -> float | None:
    """'3.000,00 Euros' -> 3000.0 ; '500.000 Ptas' -> euros (166,386)."""
    if not s:
        return None
    m = re.search(r"(\d[\d.]*(?:,\d+)?)\s*(Euros|EUROS|euros|€|Ptas|PTAS|pesetas)?", s)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None
    if m.group(2) and m.group(2).lower().startswith(("pta", "peseta")):
        v = round(v / 166.386, 2)
    return v


# --------------------------------------------------------------------------- provincias
# Código INE (el que usa el identificador BORME-A-AAAA-NNN-PP) -> nombre canónico y alias.

PROVINCIAS: dict[str, tuple[str, ...]] = {
    "01": ("ARABA/ALAVA", "ALAVA", "ARABA"), "02": ("ALBACETE",), "03": ("ALICANTE/ALACANT", "ALICANTE", "ALACANT"),
    "04": ("ALMERIA",), "05": ("AVILA",), "06": ("BADAJOZ",), "07": ("ILLES BALEARS", "BALEARES", "ISLAS BALEARES"),
    "08": ("BARCELONA",), "09": ("BURGOS",), "10": ("CACERES",), "11": ("CADIZ",),
    "12": ("CASTELLON/CASTELLO", "CASTELLON", "CASTELLO"), "13": ("CIUDAD REAL",), "14": ("CORDOBA",),
    "15": ("A CORUÑA", "LA CORUÑA", "CORUÑA", "A CORUNA"), "16": ("CUENCA",), "17": ("GIRONA", "GERONA"),
    "18": ("GRANADA",), "19": ("GUADALAJARA",), "20": ("GIPUZKOA", "GUIPUZCOA"), "21": ("HUELVA",),
    "22": ("HUESCA",), "23": ("JAEN",), "24": ("LEON",), "25": ("LLEIDA", "LERIDA"), "26": ("LA RIOJA", "RIOJA"),
    "27": ("LUGO",), "28": ("MADRID",), "29": ("MALAGA",), "30": ("MURCIA",), "31": ("NAVARRA",),
    "32": ("OURENSE", "ORENSE"), "33": ("ASTURIAS",), "34": ("PALENCIA",), "35": ("LAS PALMAS", "PALMAS"),
    "36": ("PONTEVEDRA",), "37": ("SALAMANCA",), "38": ("SANTA CRUZ DE TENERIFE", "TENERIFE"),
    "39": ("CANTABRIA",), "40": ("SEGOVIA",), "41": ("SEVILLA",), "42": ("SORIA",), "43": ("TARRAGONA",),
    "44": ("TERUEL",), "45": ("TOLEDO",), "46": ("VALENCIA", "VALENCIA/VALENCIA"), "47": ("VALLADOLID",),
    "48": ("BIZKAIA", "VIZCAYA"), "49": ("ZAMORA",), "50": ("ZARAGOZA",), "51": ("CEUTA",), "52": ("MELILLA",),
}


def provincia_code(name_or_code: str | None) -> str | None:
    """Devuelve el código INE de 2 dígitos a partir de un nombre (con o sin tildes/alias) o código."""
    if not name_or_code:
        return None
    s = norm(name_or_code)
    if re.fullmatch(r"\d{1,2}", s):
        c = s.zfill(2)
        return c if c in PROVINCIAS else None
    for code, aliases in PROVINCIAS.items():
        if s in aliases or any(s == a or s in a.split("/") for a in aliases):
            return code
    for code, aliases in PROVINCIAS.items():  # coincidencia laxa ("ALICANTE/ALACANT" en el sumario)
        if len(s) > 3 and any(a in s or s in a for a in aliases if len(a) > 3):
            return code
    return None


def provincia_name(code: str | None) -> str | None:
    if not code or code not in PROVINCIAS:
        return None
    return PROVINCIAS[code][0].split("/")[0]


def parse_provincias(arg: str | None) -> set[str] | None:
    """'MADRID,BARCELONA' -> {'28','08'}; None/''/'TODAS' -> None (sin filtro)."""
    if not arg or norm(arg) in ("TODAS", "ALL", "*"):
        return None
    out = set()
    for tok in arg.split(","):
        tok = tok.strip()
        if not tok:
            continue
        c = provincia_code(tok)
        if c is None:
            raise ValueError(f"Provincia desconocida: {tok!r}")
        out.add(c)
    return out


# --------------------------------------------------------------------------- tablas markdown


def md_table(df, floatfmt: str = "{:.1f}", max_rows: int | None = None) -> str:
    """Tabla markdown sin depender de 'tabulate'."""
    if df is None or len(df) == 0:
        return "_(sin datos)_\n"
    if max_rows is not None:
        df = df.head(max_rows)
    cols = [str(c) for c in df.columns]

    def fmt(v):
        if v is None or (isinstance(v, float) and v != v):
            return ""
        if isinstance(v, float):
            return floatfmt.format(v)
        return str(v).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(fmt(v) for v in row) + " |")
    return "\n".join(lines) + "\n"
