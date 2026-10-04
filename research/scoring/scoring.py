"""Matriz de scoring (fase 5). Puntuaciones 1-5 recalibradas con escalas comunes
(ver ../INFORME.md, sección 5). Ejecutar: python research/scoring/scoring.py"""
import csv
from pathlib import Path

PESOS = {  # suma 1.0
    "ventana": 0.20, "ticket": 0.15, "volumen": 0.15, "detect": 0.15,
    "proveedores": 0.15, "verif": 0.08, "competencia": 0.07, "riesgo": 0.05,
}
COLS = list(PESOS)

# sector, bloque, confianza de los datos (A = con datos, B = mixto, C = mayoría EST sin verificar), 8 puntuaciones
SECTORES = [
    ("Restaurante independiente", "Hostelería", "B", 3, 4, 5, 3, 5, 3, 3, 4),
    ("Cafetería / specialty coffee", "Hostelería", "B", 3, 3, 4, 3, 4, 3, 3, 4),
    ("Obrador / panadería-cafetería", "Hostelería", "C", 3, 3, 4, 3, 3, 3, 4, 4),
    ("Cocina central / catering", "Hostelería", "C", 5, 5, 2, 4, 3, 3, 4, 4),
    ("Bar (incl. traspasos)", "Hostelería", "B", 2, 2, 5, 2, 4, 2, 2, 3),
    ("Restaurante franquicia", "Hostelería", "B", 1, 2, 3, 3, 2, 4, 3, 4),
    ("Dark kitchen", "Hostelería", "C", 2, 4, 1, 2, 3, 3, 4, 3),
    ("Heladería / yogurtería", "Hostelería", "C", 2, 3, 2, 2, 3, 3, 4, 4),
    ("Clínica dental independiente", "Salud", "A", 4, 4, 3, 4, 4, 4, 3, 4),
    ("Medicina estética", "Salud", "B", 2, 3, 3, 2, 4, 3, 3, 3),
    ("Fisioterapia", "Salud", "C", 2, 2, 4, 2, 2, 3, 4, 3),
    ("Podología", "Salud", "C", 2, 2, 2, 1, 2, 3, 4, 3),
    ("Psicología", "Salud", "C", 1, 1, 3, 1, 1, 2, 5, 2),
    ("Óptica", "Salud", "C", 2, 3, 2, 3, 2, 4, 4, 4),
    ("Audiología", "Salud", "C", 1, 2, 2, 3, 1, 4, 4, 4),
    ("Veterinaria", "Salud", "C", 4, 3, 2, 3, 4, 3, 4, 4),
    ("Diagnóstico por imagen (prov. secundarios)", "Salud alta", "B", 3, 5, 1, 3, 2, 3, 4, 4),
    ("Fertilidad independiente", "Salud alta", "B", 5, 5, 1, 3, 3, 3, 5, 4),
    ("Laboratorio clínico", "Salud alta", "B", 2, 2, 1, 2, 2, 3, 4, 4),
    ("Longevidad / preventiva premium", "Salud alta", "C", 5, 5, 1, 3, 4, 3, 5, 3),
    ("Residencia de mayores (+ reformas)", "Sociosanitario", "A", 5, 5, 2, 4, 4, 3, 2, 4),
    ("Centro de día", "Sociosanitario", "C", 5, 4, 2, 3, 4, 3, 4, 4),
    ("Senior living", "Sociosanitario", "C", 5, 5, 1, 3, 4, 3, 2, 4),
    ("Peluquería / barbería", "Belleza", "B", 1, 2, 4, 1, 4, 3, 4, 2),
    ("Centro de estética", "Belleza", "C", 2, 2, 4, 2, 4, 3, 4, 2),
    ("Spa / wellness", "Belleza", "C", 5, 5, 1, 3, 2, 3, 3, 4),
    ("Gimnasio independiente / franquicia", "Fitness", "B", 5, 4, 2, 3, 3, 3, 3, 4),
    ("Boutique fitness (pilates reformer)", "Fitness", "B", 4, 3, 3, 3, 3, 4, 5, 4),
    ("Escuela infantil 0-3", "Educación", "B", 5, 3, 2, 4, 3, 3, 5, 5),
    ("Academia", "Educación", "C", 2, 2, 4, 2, 3, 3, 4, 3),
    ("FP privada", "Educación", "C", 4, 5, 1, 3, 3, 3, 4, 5),
    ("Colegio privado", "Educación", "C", 5, 5, 1, 3, 2, 2, 3, 5),
    ("Hotel (apertura + reforma)", "Alojamiento", "B", 5, 5, 2, 3, 4, 3, 2, 5),
    ("Hostal", "Alojamiento", "C", 3, 3, 2, 3, 4, 3, 4, 4),
    ("Vivienda de uso turístico", "Alojamiento", "B", 1, 1, 4, 4, 4, 4, 3, 2),
    ("Residencia estudiantes / coliving", "Alojamiento", "C", 5, 5, 1, 3, 3, 3, 3, 5),
    ("Supermercado franquiciado", "Retail", "B", 2, 1, 3, 3, 2, 4, 3, 4),
    ("Farmacia (transmisión / reforma)", "Retail", "B", 4, 3, 4, 2, 4, 3, 4, 2),
    ("Tienda especializada", "Retail", "C", 2, 2, 3, 3, 3, 3, 4, 3),
    ("Taller mecánico", "Servicios", "C", 4, 3, 3, 3, 4, 4, 4, 4),
    ("Lavandería autoservicio", "Servicios", "C", 2, 3, 2, 3, 2, 4, 4, 4),
    ("Coworking", "Servicios", "C", 4, 4, 2, 3, 4, 3, 3, 4),
    ("Industria alimentaria artesana", "Industria", "C", 4, 4, 2, 4, 3, 4, 5, 5),
    ("Pádel indoor", "Otros", "C", 5, 4, 2, 4, 3, 4, 5, 4),
    ("Self-storage", "Otros", "C", 4, 4, 2, 4, 2, 4, 5, 5),
    ("Centro de lavado", "Otros", "C", 4, 4, 2, 3, 2, 3, 4, 4),
]


def puntuar():
    filas = []
    for s in SECTORES:
        nombre, bloque, conf, *p = s
        d = dict(zip(COLS, p))
        total = sum(d[c] * PESOS[c] for c in COLS)
        # Penaliza la incertidumbre para el ranking operativo: C = datos casi todos estimados
        ajustado = total - {"A": 0, "B": 0.05, "C": 0.20}[conf]
        filas.append({"sector": nombre, "bloque": bloque, "confianza": conf, **d,
                      "score": round(total, 2), "score_ajustado": round(ajustado, 2)})
    return sorted(filas, key=lambda f: -f["score_ajustado"])


if __name__ == "__main__":
    filas = puntuar()
    out = Path(__file__).with_name("ranking.csv")
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)
    print("| # | Sector | Conf. | Vent | Tick | Vol | Det | Prov | Verif | Comp | Riesgo | Score | Ajust. |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, f in enumerate(filas, 1):
        print(f"| {i} | {f['sector']} | {f['confianza']} | " + " | ".join(str(f[c]) for c in COLS)
              + f" | {f['score']:.2f} | {f['score_ajustado']:.2f} |")
