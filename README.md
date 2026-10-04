# Business Intelligence: oportunidades de apertura antes de que se cierren las compras

Investigación para un servicio que detecta en España negocios antes de que abran, amplíen, reformen o cambien de titular, y vende esa oportunidad a sus futuros proveedores.

- **[research/INFORME.md](research/INFORME.md)**: informe de síntesis con la respuesta corta, la mecánica del timing, el ranking de 46 sectores, el top 5, la recomendación de test de 90 días y los criterios de descarte.
- `research/sectores/`: fichas sectoriales con mapa de compras, cronología, señales, ventana, volumen, compradores y riesgos.
- `research/transversal/`: competencia y precios, fuentes de señales, RGPD y volúmenes macro.
- `research/validacion_telefonica.md`: guion y muestra para validar el timing con negocios recién abiertos.
- `research/scoring/`: matriz de scoring reproducible (`python research/scoring/scoring.py`).
- `pipeline/`: código de las fases 3 y 4 (BORME y backtest con el censo de locales de Madrid). Ver `pipeline/README.md`.
