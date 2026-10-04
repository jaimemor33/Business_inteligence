# ¿En qué sectores se puede vender una apertura antes de que se cierren las compras?

*Informe de síntesis. Fecha: 4 de octubre de 2026. Ámbito: España, con el foco en Madrid.*

> **Cómo leer este informe.** **[DATO]** es una cifra con fuente enlazada, que está en las fichas sectoriales. **[EST]** es una estimación razonada. Casi todas las cifras de *ventana* y de *% del CAPEX abierto* son **[EST]**: salen de cruzar cronologías publicadas (plazos de licencias, entrega de equipos y obra) con el retraso de publicación del BORME. Todavía no se han medido sobre aperturas reales. Las fases 3 y 4 empíricas (BORME y censo de Madrid) no se han podido ejecutar en esta sesión porque la red bloquea boe.es y datos.madrid.es. El código está listo en `pipeline/` (ver §6).
>
> Detalle por sector, con fichas completas, fuentes y cronologías:
> - [01 Hostelería](sectores/01_hosteleria.md)
> - [02 Salud ambulatoria](sectores/02_salud_ambulatoria.md)
> - [03 Salud de alta inversión y sociosanitario](sectores/03_salud_alta_y_sociosanitario.md)
> - [04 Belleza, fitness y educación](sectores/04_belleza_fitness_educacion.md)
> - [05 Alojamiento, retail, industria y otros](sectores/05_alojamiento_retail_industria_otros.md)
> - [Transversal: competencia, fuentes, legal y volúmenes](transversal/competencia_fuentes_legal.md)
> - [Guion de validación telefónica](validacion_telefonica.md)
> - [Scoring (script y CSV)](scoring/)

---

## 1. Respuesta corta

1. **El BORME es una señal de mitad de ciclo.** Su utilidad depende de la duración de la apertura en cada sector. Hay tres regímenes:

   | Régimen | Sectores | Qué pasa cuando sale el BORME | ¿Se puede vender? |
   |---|---|---|---|
   | **A. Ciclo medio (6-12 meses) con un CAPEX fuerte en obra y equipamiento** | Restaurante independiente, clínica dental, boutique fitness, gimnasio independiente, escuela infantil, cafetería y obrador, veterinaria [EST], taller | Sigue abierto el **60-90 % del CAPEX** [EST], durante **2-14 semanas** para el equipamiento y algo más para el mobiliario, el software y los servicios | **Sí. Es el núcleo del negocio**, pero la ventana es estrecha y muy sensible al retraso de publicación |
   | **B. Ciclo largo (2-4 años)** | Residencias, hoteles, colegios, fertilidad, longevidad, cocinas centrales, senior living, pádel indoor y self-storage [EST] | El BORME llega **demasiado pronto**: la SPV aparece 1-3 años antes de abrir y con un objeto social genérico. Sigue abierto el 90-100 % | **Sí, como seguimiento de proyectos**, cruzando el BORME con licencias de obra, prensa y operador. Aquí ya compiten Construdatos, Alimarket y TOPHOTELPROJECTS |
   | **C. Ciclo corto, ticket bajo o canal cerrado** | Peluquería, estética, fisioterapia, psicología, podología, bares (traspasos), academias, franquicias de todo tipo, supermercados franquiciados, VUT, laboratorios y ópticas o audiología de cadena | El BORME **no existe** (autónomos), **llega tarde** o **compra la central** (en franquicias queda abierto el 5-25 %) | **No como producto de CAPEX.** Como mucho, sirve para vender recurrentes (software, seguros, consumibles) |

2. **La primera señal útil no suele ser el BORME.** En el régimen A, la combinación ganadora en Madrid es:
   - el **BORME** (quién, qué y con cuánto capital);
   - más las **declaraciones responsables y licencias** (dataset 300193, mensual, desde 2015);
   - más el **censo de locales en "obras"** (dataset 200085).

   Las dos fuentes municipales dicen *dónde* y *en qué fase* está la apertura, y la señal de obra cae justo antes de la compra de equipamiento. En el régimen B, la señal es la **licencia de obra o la prensa**, enlazada después con la SPV del BORME.

3. **Hay hueco de mercado.** El dato bruto de "empresa nueva" ya es una mercancía: de 0,05 a 0,12 € por registro y de 25 a 50 € al mes en alertas (Informa, Axesor, InfoNIF, LibreBOR, Apispain, scrapers en Apify) [DATO]. **Nadie en España vende la oportunidad de apertura de local pequeño o mediano verificada y filtrada por vertical**: local identificado, fase, fecha prevista y partidas pendientes. En EE. UU. ese producto existe: RestaurantData, con 400-600 leads semanales de restaurantes antes de abrir [DATO], y BuildCentral.

4. **Recomendación para el test comercial de 90 días** (detalle en §5):
   - **Clínicas dentales independientes**: mejor equilibrio entre ticket, ventana, detectabilidad y calidad de datos.
   - **Restaurantes independientes**: volumen y densidad de proveedores; es el banco de pruebas de la máquina.
   - **Residencias (aperturas y reformas)**: track de proyecto de ticket alto.
   - Alternativa al tercero si se quiere un modelo de flujo puro: **boutique fitness y gimnasios independientes**.

---

## 2. La mecánica del timing (por qué la ventana es estrecha en el régimen A)

Cronología tipo de una apertura independiente con local y obra. Se ha armonizado a partir de las fichas de dental, restaurante, boutique y escuela infantil [EST]:

```
S0      Decisión y plan de negocio ─────────────┐
S2-S8   Búsqueda de local y financiación        │  En dental y franquicias, el "llave en mano" o la central
S4-S12  Escritura de la SL/SLP (notaría)        │  capturan al cliente aquí (S0-S6)
S6-S14  Firma del local (normalmente a nombre de la SL)
S5-S24  ► PUBLICACIÓN EN EL BORME (escritura + 1-12 semanas)
S8-S18  Proyecto técnico → declaración responsable o licencia   ◄ el proyecto FIJA las instalaciones, la extracción y el trazado de los equipos
S12-S26 Obra (8-14 semanas)                     ◄ se compromete la obra (40-60 % del CAPEX)
S16-S28 Pedido del equipamiento principal       ◄ cocina 6-10 semanas, sillón 4-5 semanas (hasta 12 si es importado), reformer 2-12 semanas
S24-S32 Mobiliario, TPV, software, seguros, uniformes y marketing
S28-S40 Apertura ─ autorización sanitaria o educativa (inspección): llega DESPUÉS de comprar
```

Consecuencias:
- **El retraso de publicación (1-12 semanas, según la muestra del brief) es la variable que más cambia el negocio.** Con 2-3 semanas de retraso, el BORME llega antes del proyecto técnico y queda abierto casi todo el CAPEX. Con 10-12 semanas, se pierden la obra y la cocina, y solo quedan el mobiliario, el TPV, el software y los servicios: un 20-40 % del CAPEX [EST]. **La fase 3 debe medir este retraso por provincia antes de decidir dónde lanzar.**
- **El orden entre la SL y el local también importa.** Las guías recomiendan constituir la SL antes de firmar el local, porque la licencia exige CIF y contrato y ceder el contrato después requiere consentimiento [DATO, ver hostelería]. Si se cumple, el BORME cae en S7-S20. Si la SL se monta después, cae en S11-S26 [EST]. **Se valida con el guion telefónico (pregunta 2).**
- **Las autorizaciones sectoriales con inspección son tardías**: autorización sanitaria de funcionamiento (2-6 meses, hasta 8, tras montar el centro) [DATO], registro de rayos X (exige los equipos instalados) [DATO] y autorización de escuela infantil o BOCM [DATO]. **No sirven para el CAPEX, sino para los recurrentes.** Hay una excepción: la **autorización sanitaria de instalación**, que se pide con planos que sitúan los equipos, antes de comprar [DATO]. No consta que se publique; **pedirla por transparencia** es la apuesta de señal temprana en salud.
- **El escenario manda más que el sector.** Para un mismo sector, el porcentaje abierto cambia mucho:

  | Escenario | % del CAPEX abierto al salir el BORME |
  |---|---|
  | Independiente | 60-90 % |
  | Franquicia | 5-25 % (la central homologa el equipamiento) |
  | Cadena | <10 % |
  | Grupo con SPV | Depende de si la compra está centralizada |

  **El clasificador debe detectar la franquicia o la cadena** (denominación, administrador persona jurídica, domicilio en la sede de la central) **para descartarla o venderla a otro comprador.**

---

## 3. Universo de sectores (fase 1) y hallazgos por bloque

Las 46 actividades analizadas están en las fichas. Lo que más cambia la decisión, por bloque:

### Hostelería
- **Restaurante independiente**:
  - CAPEX de 80.000-250.000 € (obra ~60 %, cocina ~20 %, mobiliario ~10 %) [DATO].
  - Al salir el BORME sigue abierto el 60-85 %, con una ventana de 2-10 semanas [EST].
  - Madrid abre más de 500 restaurantes al año [DATO]; en España, unos 7.000-9.000 independientes [EST].
- **Lastres de la hostelería**:
  - El **57 % de las empresas son personas físicas** [DATO], invisibles en el BORME.
  - La hostelería genera el **38 % de los anuncios de traspaso** de España [DATO]. Un traspaso con equipamiento deja comprable solo el 20-40 % del CAPEX [EST].
  - Las **cerveceras y marcas de café** ceden equipamiento a cambio de exclusividad [DATO]. Son competencia y, a la vez, cliente potencial.
- **Franquicias**: la central impone proveedores y queda abierto el 5-20 % [EST]. El comprador sería la propia central, no sus proveedores.
- **Cocinas centrales y catering**: nicho de ticket muy alto (0,4-3 M€) y ventana larga, pero con poco volumen y cifras sin verificar.

### Salud ambulatoria
- **Dental es el mejor sector con datos** (confianza A):
  - Parque de 23.559 clínicas, 3.582 en Madrid [DATO]. Unas 900-1.400 aperturas al año en España y 140-220 en Madrid [EST].
  - CAPEX de 150.000-250.000 € con dos gabinetes [DATO]. Sigue abierto el 65-85 % durante 6-14 semanas [EST].
  - Objeto social inequívoco (SLP odontológica) y sociedad profesional obligatoria [DATO].
  - En contra: las **cadenas** (Donte con 417 clínicas, Sanitas con 181, Adeslas con 149 [DATO]) y la **competencia informal** de los depósitos con servicio de diseño y de las empresas llave en mano, que captan en S0-S6.
- **Medicina estética**: suele ser un alta de la unidad U.48 en un centro existente, sin rastro en el BORME, y el láser se cierra pronto con el distribuidor o en renting. Ventana de 0-8 semanas.
- **Fisioterapia, podología y psicología**: autónomos, ticket bajo y sin ventana.
- **Veterinaria**: prometedora (60-150 k€, independientes, objeto social claro), pero **ninguna cifra verificada**. Es candidata para la siguiente ronda de investigación.
- **Ópticas y audiología**: compran a través de cadenas y grupos de compra.
- **Dato abierto útil**: la Comunidad de Madrid publica a diario los centros sanitarios autorizados [DATO]. Llega tarde, pero sirve para verificar y para vender recurrentes.

### Salud de alta inversión y sociosanitario
- **Residencias**:
  - 5.573 centros [DATO] y unas 44.000 plazas en cartera hasta 2027 [DATO]: 100-130 aperturas al año [EST].
  - CAPEX de 7-20 M€, del que el equipamiento y las instalaciones especiales son 1,2-2,5 M€ (unos 8 k€ por plaza en mobiliario y equipamiento según una licitación real) [DATO].
  - El equipamiento se decide 6-9 meses antes de abrir.
  - **Oportunidad poco explotada: las reformas para el modelo de unidades de convivencia.** El plazo estatal acaba el 31-12-2029 y Madrid limita a 25 usuarios por unidad y exige ≥50 % de habitaciones individuales [DATO]. Estas reformas no salen en el BORME, sino en licencias y licitaciones.
- **Fertilidad**: 333 centros [DATO]. Gran ventana en los independientes, pero el sector se está concentrando (Eugin compró el Instituto Bernabeu en 2025) [DATO].
- **Imagen**: el fabricante del equipo ya está decidido. Solo queda negocio para los proveedores secundarios (sala, blindaje, climatización, RIS/PACS) y en la renovación: el 45 % de las RM tiene más de 10 años [DATO].
- **Laboratorios**: descartados. Los analizadores se ceden a cambio del consumo de reactivos.

### Belleza, fitness y educación
- **Boutique fitness (pilates reformer)**:
  - Unos 2.561 estudios, el 91 % independientes, 268 en Madrid [DATO de un directorio, fiabilidad media].
  - CAPEX de 85.000-175.000 € con 6 reformers.
  - Las máquinas se piden en las últimas 2-10 semanas [DATO de plazos]. **No hay competencia en información**, y Matrix patrocina un "mapa de aperturas" [DATO], señal de que los fabricantes valoran el dato.
- **Gimnasios**:
  - 5.806 centros, el 69 % independientes [DATO], y 307 aperturas de cadenas entre enero y agosto de 2026 [DATO].
  - El independiente mediano tiene 15-30 semanas de ventana [EST].
  - El low-cost de cadena compra de forma centralizada.
- **Escuela infantil 0-3**: la obra de adaptación es obligatoria (Decreto 18/2008) y la apertura va ligada a septiembre. La autorización educativa o el BOCM llegan tarde. Sigue abierto el 75-90 % durante 15-30 semanas [EST], pero con poco volumen y concentrado en el calendario.
- **Peluquería, estética y academias**: un 70-85 % de autónomos [EST] y ticket bajo. Se descartan como producto de CAPEX.

### Alojamiento, retail, industria y otros
- **Hoteles**:
  - Más de 900 proyectos en el pipeline nacional y 66 en Madrid [DATO]. El FF&E se contrata 8-15 meses antes de abrir.
  - Competencia directa con precio público: TOPHOTELPROJECTS (1.300-3.000 €/año) y Alimarket Hoteles (871 €/año) [DATO].
  - Las **reformas** (ciclo de 7-10 años) superan en número a las aperturas [EST].
- **Farmacias**:
  - **1.877 transmisiones en 2024** [DATO], unas 170 al año en Madrid [EST].
  - Reforma de 60.000-120.000 € más robot de 21.000-130.000 € [DATO].
  - Pero el titular es una persona física: **no aparece en el BORME y el riesgo RGPD es alto**. La señal sería el cambio de rótulo o el estado "obras" en el censo.
- **VUT**: el Supremo anuló el registro único estatal en mayo de 2026 [DATO]. La señal autonómica llega después de amueblar. Descartadas para CAPEX.
- **Sin verificar (🔸) pero con perfil atractivo**: pádel indoor, self-storage, industria alimentaria artesana, talleres y centros de lavado. Son SL con un objeto social muy descriptivo, fácil de filtrar por palabra clave, y con poca competencia. **Barato de validar con el conteo del BORME** (fase 3).

---

## 4. Competencia, precio y marco legal (resumen)

**Competencia por capas:**

| Capa | Quién | Antelación | ¿Cualifica? | Precio |
|---|---|---|---|---|
| 1. Dato bruto de constitución | Informa, Axesor, InfoNIF, LibreBOR, Apispain, Apify | = BORME | No | 0,05-0,12 € por registro; 8-50 €/mes [DATO] |
| 2. Proyectos de obra y sector | Construdatos, Construdata21, Alimarket, TOPHOTELPROJECTS | Alta | Sí, pero en obra grande, hoteles y cadenas | 350-3.000 €/año o a medida [DATO] |
| 3. Oportunidad de apertura de local, verificada y por vertical | **Nadie en España** (RestaurantData y BuildCentral en EE. UU.; Glenigan en Reino Unido) | Media | Sí | — |
| Informal | Depósitos dentales con diseño, llave en mano, cerveceras, comerciales de zona | Muy alta (S0-S6), pero solo para su propia venta | — | — |

**Precio de referencia:**
- Lo que se paga hoy:
  - Lead B2B industrial en España: 60-200 € [DATO].
  - Lead de Google Search: 30-80 € [DATO].
  - Habitissimo: 12-14 € por contacto de reforma [DATO].
- Propuesta [EST], a validar con entrevistas a proveedores:
  - **40-120 € por oportunidad verificada no exclusiva**.
  - 150-400 € en exclusiva por zona.
  - O una **suscripción de 150-600 € al mes por vertical y provincia**.
  - En el régimen B (proyectos), a la manera de TOPHOTELPROJECTS: **1.000-3.000 € al año** o 200-500 € por proyecto cualificado.

**Legal** (resumen; validar con un abogado, porque parte no se pudo verificar en esta sesión):
- **Sociedades**: sus datos quedan fuera del RGPD.
- **Administradores y autónomos**: hace falta interés legítimo documentado, informar al interesado (art. 14 RGPD) y atender la oposición. **No hay que publicar ni indexar los nombres de los administradores.**
- **Email**: el email comercial no solicitado está prohibido también hacia empresas (LSSI art. 21).
- **Llamadas**: las llamadas en frío están restringidas (Ley 11/2022, art. 66).

⇒ **El producto debe ser información entregada al proveedor bajo contrato, no campañas en su nombre.** Con autónomos, la oportunidad se vende **sin nombre** (dirección, actividad y fase) o con *opt-in* del promotor.

---

## 5. Scoring y ranking (fase 5)

### Pesos (suma 100 %) y su justificación

El valor de una oportunidad es aproximadamente:

**valor ≈ volumen × ticket × P(compras aún abiertas) × P(detectarla) × nº de proveedores que pagan**

Los cinco factores multiplicativos llevan casi todo el peso. Coste, competencia y riesgo son correctores.

| Criterio | Peso | Justificación |
|---|---|---|
| Ventana (semanas con compras abiertas tras la señal y % del CAPEX abierto) | **20 %** | Es la pregunta central. Sin ventana, el producto no existe |
| Ticket comprable por apertura | 15 % | Determina cuánto paga un proveedor por una oportunidad |
| Volumen de aperturas | 15 % | Determina los ingresos recurrentes y si se puede testar en 90 días |
| Detectabilidad con fuentes públicas | 15 % | Proporción de aperturas reales que vemos (autónomos, traspasos) |
| Densidad y fragmentación de proveedores que pagarían | 15 % | Cuántos clientes distintos compran la misma oportunidad |
| Coste de verificación | 8 % | Margen operativo. Es mejorable con proceso |
| Competencia existente | 7 % | Hay competencia informal en casi todos los sectores; la formal solo en proyectos grandes |
| Riesgo legal y operativo | 5 % | Es mitigable con el diseño del producto (sin nombres, B2B) |

**Escalas comunes** (recalibran las puntuaciones que propuso cada bloque):

| Criterio | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| Volumen (aperturas/año en España) | >5.000 | 1.500-5.000 | 500-1.500 | 100-500 | <100 |
| Ticket comprable | ≥500 k€ | 150-500 k€ | 60-150 k€ | 25-60 k€ | <25 k€ |
| Ventana (independiente) | ≥12 semanas y ≥70 % abierto | 8-12 semanas o ≥60 % | 4-8 semanas o ≥50 % | 1-4 semanas o 30-50 % | ~0 |

**Ajuste por incertidumbre**: a la nota se le resta **0,20** si la confianza de los datos es C (casi todo [EST]) y **0,05** si es B, para no premiar a los sectores que suenan bien sin que se haya verificado nada.

### Ranking completo
(Generado con `research/scoring/scoring.py`; el CSV está en `research/scoring/ranking.csv`.)

| # | Sector | Conf. | Vent | Tick | Vol | Det | Prov | Verif | Comp | Riesgo | Score | Ajust. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Residencia de mayores (+ reformas) | A | 5 | 5 | 2 | 4 | 4 | 3 | 2 | 4 | 3.83 | 3.83 |
| 2 | Clínica dental independiente | A | 4 | 4 | 3 | 4 | 4 | 4 | 3 | 4 | 3.78 | 3.78 |
| 3 | Restaurante independiente | B | 3 | 4 | 5 | 3 | 5 | 3 | 3 | 4 | 3.80 | 3.75 |
| 4 | Hotel (apertura + reforma) | B | 5 | 5 | 2 | 3 | 4 | 3 | 2 | 5 | 3.73 | 3.68 |
| 5 | Cocina central / catering | C | 5 | 5 | 2 | 4 | 3 | 3 | 4 | 4 | 3.82 | 3.62 |
| 6 | Pádel indoor | C | 5 | 4 | 2 | 4 | 3 | 4 | 5 | 4 | 3.82 | 3.62 |
| 7 | Escuela infantil 0-3 | B | 5 | 3 | 2 | 4 | 3 | 3 | 5 | 5 | 3.64 | 3.59 |
| 8 | Fertilidad independiente | B | 5 | 5 | 1 | 3 | 3 | 3 | 5 | 4 | 3.59 | 3.54 |
| 9 | Longevidad / preventiva premium | C | 5 | 5 | 1 | 3 | 4 | 3 | 5 | 3 | 3.69 | 3.49 |
| 10 | Centro de día | C | 5 | 4 | 2 | 3 | 4 | 3 | 4 | 4 | 3.67 | 3.47 |
| 11 | Industria alimentaria artesana | C | 4 | 4 | 2 | 4 | 3 | 4 | 5 | 5 | 3.67 | 3.47 |
| 12 | Boutique fitness (pilates reformer) | B | 4 | 3 | 3 | 3 | 3 | 4 | 5 | 4 | 3.47 | 3.42 |
| 13 | Gimnasio independiente / franquicia | B | 5 | 4 | 2 | 3 | 3 | 3 | 3 | 4 | 3.45 | 3.40 |
| 14 | Taller mecánico | C | 4 | 3 | 3 | 3 | 4 | 4 | 4 | 4 | 3.55 | 3.35 |
| 15 | Senior living | C | 5 | 5 | 1 | 3 | 4 | 3 | 2 | 4 | 3.53 | 3.33 |
| 16 | Farmacia (transmisión / reforma) | B | 4 | 3 | 4 | 2 | 4 | 3 | 4 | 2 | 3.37 | 3.32 |
| 17 | Self-storage | C | 4 | 4 | 2 | 4 | 2 | 4 | 5 | 5 | 3.52 | 3.32 |
| 18 | Cafetería / specialty coffee | B | 3 | 3 | 4 | 3 | 4 | 3 | 3 | 4 | 3.35 | 3.30 |
| 19 | Residencia estudiantes / coliving | C | 5 | 5 | 1 | 3 | 3 | 3 | 3 | 5 | 3.50 | 3.30 |
| 20 | Coworking | C | 4 | 4 | 2 | 3 | 4 | 3 | 3 | 4 | 3.40 | 3.20 |
| 21 | FP privada | C | 4 | 5 | 1 | 3 | 3 | 3 | 4 | 5 | 3.37 | 3.17 |
| 22 | Veterinaria | C | 4 | 3 | 2 | 3 | 4 | 3 | 4 | 4 | 3.32 | 3.12 |
| 23 | Spa / wellness | C | 5 | 5 | 1 | 3 | 2 | 3 | 3 | 4 | 3.30 | 3.10 |
| 24 | Obrador / panadería-cafetería | C | 3 | 3 | 4 | 3 | 3 | 3 | 4 | 4 | 3.27 | 3.07 |
| 25 | Colegio privado | C | 5 | 5 | 1 | 3 | 2 | 2 | 3 | 5 | 3.27 | 3.07 |
| 26 | Centro de lavado | C | 4 | 4 | 2 | 3 | 2 | 3 | 4 | 4 | 3.17 | 2.97 |
| 27 | Diagnóstico por imagen (prov. secundarios) | B | 3 | 5 | 1 | 3 | 2 | 3 | 4 | 4 | 2.97 | 2.92 |
| 28 | Hostal | C | 3 | 3 | 2 | 3 | 4 | 3 | 4 | 4 | 3.12 | 2.92 |
| 29 | Bar (incl. traspasos) | B | 2 | 2 | 5 | 2 | 4 | 2 | 2 | 3 | 2.80 | 2.75 |
| 30 | Medicina estética | B | 2 | 3 | 3 | 2 | 4 | 3 | 3 | 3 | 2.80 | 2.75 |
| 31 | Vivienda de uso turístico | B | 1 | 1 | 4 | 4 | 4 | 4 | 3 | 2 | 2.78 | 2.73 |
| 32 | Centro de estética | C | 2 | 2 | 4 | 2 | 4 | 3 | 4 | 2 | 2.82 | 2.62 |
| 33 | Academia | C | 2 | 2 | 4 | 2 | 3 | 3 | 4 | 3 | 2.72 | 2.52 |
| 34 | Tienda especializada | C | 2 | 2 | 3 | 3 | 3 | 3 | 4 | 3 | 2.72 | 2.52 |
| 35 | Óptica | C | 2 | 3 | 2 | 3 | 2 | 4 | 4 | 4 | 2.70 | 2.50 |
| 36 | Lavandería autoservicio | C | 2 | 3 | 2 | 3 | 2 | 4 | 4 | 4 | 2.70 | 2.50 |
| 37 | Supermercado franquiciado | B | 2 | 1 | 3 | 3 | 2 | 4 | 3 | 4 | 2.48 | 2.43 |
| 38 | Heladería / yogurtería | C | 2 | 3 | 2 | 2 | 3 | 3 | 4 | 4 | 2.62 | 2.42 |
| 39 | Peluquería / barbería | B | 1 | 2 | 4 | 1 | 4 | 3 | 4 | 2 | 2.47 | 2.42 |
| 40 | Restaurante franquicia | B | 1 | 2 | 3 | 3 | 2 | 4 | 3 | 4 | 2.43 | 2.38 |
| 41 | Dark kitchen | C | 2 | 4 | 1 | 2 | 3 | 3 | 4 | 3 | 2.57 | 2.37 |
| 42 | Fisioterapia | C | 2 | 2 | 4 | 2 | 2 | 3 | 4 | 3 | 2.57 | 2.37 |
| 43 | Laboratorio clínico | B | 2 | 2 | 1 | 2 | 2 | 3 | 4 | 4 | 2.17 | 2.12 |
| 44 | Audiología | C | 1 | 2 | 2 | 3 | 1 | 4 | 4 | 4 | 2.20 | 2.00 |
| 45 | Podología | C | 2 | 2 | 2 | 1 | 2 | 3 | 4 | 3 | 2.12 | 1.92 |
| 46 | Psicología | C | 1 | 1 | 3 | 1 | 1 | 2 | 5 | 2 | 1.71 | 1.51 |

**Lectura.** La parte alta está muy apretada: del puesto 1 al 13 hay menos de 0,5 puntos. **El ranking ordena hipótesis, no certezas.** Lo que más puede moverlo es la ventana real, que se mide en la fase 4. Los sectores con 🔸 o confianza C (pádel, cocinas centrales, longevidad, industria artesana, self-storage) aparecen arriba **por ticket y ventana teóricos**, sin ningún dato verificado. Por eso entran en la lista de "validar barato con el conteo del BORME", no en el test comercial.

### Top 5
1. **Residencias de mayores (aperturas y reformas)**: el ticket y la ventana más altos, con datos sólidos. Es un producto de **seguimiento de proyectos**, no de alertas del BORME. Tiene competencia (Construdatos, Alimarket), así que la diferenciación son las **reformas por el modelo de convivencia** y la verificación del equipamiento pendiente.
2. **Clínicas dentales independientes**: el mejor sector del régimen A con datos. El objeto social es inequívoco, el ticket va de 150.000 a 250.000 € y la ventana de 6 a 14 semanas.
3. **Restaurantes independientes**: el volumen y la densidad de proveedores más altos. La ventana es más estrecha (2-10 semanas) y hay ruido (traspasos, autónomos, cerveceras), pero es el sector donde el cruce BORME + licencias + censo aporta más.
4. **Hoteles (apertura y reforma)**: ticket máximo, pero con competencia de precio público y un comprador real (interiorista o agencia de compras) muy concentrado.
5. **Escuelas infantiles y boutique fitness** (empate práctico): ventana larga o muy poca competencia, con un volumen moderado.

### Recomendación: test comercial de 90 días en Madrid

| Sector | Por qué | Producto del test | Volumen esperado en Madrid [EST] |
|---|---|---|---|
| **1. Clínicas dentales independientes** | El mejor ratio de ticket × ventana × detectabilidad, con datos de confianza A | Alerta semanal verificada: SLP nueva + local + fase + partidas pendientes, para depósitos, UTPR, software clínico, mobiliario, renting y llave en mano | 12-18 aperturas al mes |
| **2. Restaurantes independientes** | Volumen y muchos tipos de proveedor por apertura (cocina, frío, extracción, mobiliario, TPV, café, menaje, seguros); es la prueba de escala | Igual, filtrado por fase de obra para cocina y extracción frente a mobiliario y TPV | 50-75 aperturas al mes |
| **3. Residencias (aperturas y reformas por el modelo de convivencia)** | Ticket por oportunidad 10-50 veces mayor; prueba el modelo "proyecto" | Ficha de proyecto (operador, plazas, fase, fecha prevista, partidas) para fabricantes de camas y mobiliario geriátrico, cocina y lavandería industrial, llamada a enfermera y software | 10-20 proyectos activos en la Comunidad de Madrid + reformas |

*Alternativa al n.º 3 si se quiere probar solo el modelo de flujo:* **boutique fitness y gimnasios independientes**, con 5-10 aperturas al mes en Madrid, sin competencia en información y con fabricantes que ya valoran el dato.

**Plan de 90 días:**
- **Días 0-20, datos.** Ejecutar `pipeline/`:
  - BORME de los últimos 6 meses: conteos y retraso de publicación por provincia.
  - Backtest del censo de Madrid: % de aperturas con match en el BORME y lag hasta "obras".
  - Clasificación por sector.
  - 45 llamadas de validación (15 por sector).
- **Días 10-40, oferta.** 20 entrevistas o demos por sector a proveedores, con 5-10 oportunidades reales verificadas de muestra.
  - Medir tres cosas: si las oportunidades son "nuevas para mí", si hay intención de pago y el precio.
  - Probar dos modelos de precio: por oportunidad (40-120 €) y suscripción (150-600 € al mes).
- **Días 40-90, venta.** Piloto de pago con 3-5 clientes por sector y seguimiento del resultado: contacto, presupuesto y venta.

**Criterios de descarte** (si se cumple cualquiera, el sector sale del test):
1. **Timing**: con 10-15 llamadas, la mediana del % del CAPEX comprometido **después** de la publicación en el BORME es **<50 %**, o la ventana para las partidas principales es **<6 semanas**.
2. **Cobertura**: en el backtest, **<30 %** de las aperturas reales del sector tienen una señal detectable (BORME, declaración responsable o censo en "obras") **antes** del pedido del equipamiento.
3. **Ruido y verificación**: **<40 %** de las señales del BORME se convierten en una apertura real verificada (local identificado y fase conocida), o la verificación cuesta **>45 minutos** de analista por oportunidad.
4. **Competencia informal**: **≥40 %** de los entrevistados ya recibió una oferta de proveedores antes de abrir sin pedirla, y los proveedores de la demo dicen que ya conocían **>50 %** de las oportunidades enseñadas.
5. **Demanda**: el día 60 hay **<3 clientes de pago** (o <15 % de conversión de demo a piloto) en el sector.
6. **Unit economics**: el precio aceptado por oportunidad es **< 3 × el coste de verificación** (equivale a un margen bruto <66 %).

---

## 6. Estado de las fases empíricas (3 y 4) y cómo completarlas

**Por qué no se ejecutaron.** La política de red del entorno cloud de esta sesión **bloquea `www.boe.es`, `datos.madrid.es` e `ine.es`**, y también la lectura de casi cualquier web. Solo funcionó la búsqueda web, con un cupo de 200 búsquedas compartido entre los agentes, que se agotó. Para ejecutarlas hay dos opciones:
- **Opción A**: correr `pipeline/` en tu máquina.
- **Opción B**: añadir `www.boe.es` y `datos.madrid.es` a los dominios permitidos del entorno (menú del entorno cloud → Edit → Network access → Custom → Allowed domains) y abrir una sesión nueva.

**Qué hay listo en `pipeline/`** (ver su `README.md`):
- `borme_fetch` y `borme_parse`: descarga los sumarios de la API del BOE y los PDF de la sección A por provincia, y extrae los actos (constitución, cambio de objeto, de domicilio y de denominación) con objeto social, CNAE, domicilio, capital, comienzo de operaciones, inscripción y publicación. **No guarda los nombres de los administradores.**
- `classify`: reglas de CNAE y palabras clave para los 46 sectores, más ruido (holdings, patrimoniales), con capa LLM opcional para los casos dudosos. Guarda el texto original y la confianza.
- `metrics`: actos por mes, sector y provincia; capital; % de domicilio tipo local frente a piso u oficina; retraso escritura → publicación (mediana y percentiles); % de ruido.
- `madrid_census` y `backtest`: aperturas reales en el censo, meses previos en "obras" y cruce con el BORME por rótulo, denominación y dirección.

**Novedad que hay que comprobar primero.** Según la documentación del BOE, la **API v2.0 del BORME (28-05-2026) añade XML y HTML para la Sección Primera** [DATO, ver transversal §C.1]. Si el XML trae los actos estructurados, el parseo de PDF pasa a ser un plan B.

**Segunda fuente municipal que incorporar al backtest.** El dataset **300193** (licencias y declaraciones responsables de Madrid, mensual, desde 2015) [DATO] probablemente da la señal de obra más temprana a nivel de local. Conviene añadirlo como tercera fuente del cruce. Está pendiente en el código.

**Preguntas que la fase 3 responde en un día de ejecución:**
1. Retraso real entre escritura y publicación por provincia, con su mediana y p90. **Es lo que más mueve la ventana.**
2. Constituciones al mes por sector en Madrid y en España, y % de ruido. Valida o desmonta las estimaciones de volumen de las fichas, sobre todo las 🔸.
3. % de domicilios tipo local frente a piso u oficina por sector: cuántas SL ya tienen local al constituirse.

---

## 7. Lagunas principales y cómo cerrarlas

| Laguna | Impacto | Cómo cerrarla | Coste |
|---|---|---|---|
| Retraso del BORME y volumen real por sector | Alto | Ejecutar `pipeline/` con la red habilitada | 1 día |
| % del CAPEX abierto al salir el BORME (todas las ventanas son [EST]) | **Crítico** | Guion telefónico: 15 llamadas por sector finalista | 3-4 días por sector |
| Orden SL → local | Alto | Pregunta 2 del guion más 10 gestorías | 1-2 días |
| Solicitudes de autorización sanitaria de instalación (señal temprana en salud) | Alto en dental | Petición de transparencia a la DG de Inspección y Ordenación Sanitaria de Madrid | 1 mes de plazo |
| Precio que pagan hoy los proveedores por un lead | Alto | 20 entrevistas por sector (fase de oferta) | Incluido en el test |
| Veterinaria, talleres, pádel, self-storage e industria artesana (casi todo 🔸) | Medio | Conteo del BORME por palabra clave más 5 llamadas | Bajo |
| Validación legal (AEPD sobre la reutilización del BORME, art. 66 de la Ley 11/2022 en B2B) | Medio | Consulta a un abogado especializado en protección de datos | 500-1.500 € [EST] |
| Tarifas de Construdatos y Axesor | Medio (residencias) | Pedir presupuesto como cliente potencial | 0 € |
