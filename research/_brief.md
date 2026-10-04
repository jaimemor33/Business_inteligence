# Brief común para todos los bloques de investigación

## Negocio
Servicio en España que detecta negocios ANTES de que abran (o amplíen, reformen, trasladen o cambien de titular) y vende esa oportunidad a sus futuros proveedores (equipamiento, mobiliario, instalaciones, software, servicios). El producto es información anticipada, verificada y accionable. No es una base de datos.

Fuentes ya identificadas:
- **BORME sección A** (API de datos abiertos del BOE + PDF por provincia): constituciones, cambios de objeto social, de domicilio y de denominación. Incluye objeto social (a veces con CNAE), domicilio, capital, administradores y "Comienzo de operaciones" (fecha de la escritura). En una muestra real, el retraso entre escritura y publicación fue de 1 a 12 semanas.
- **Censo de locales y actividades de Madrid** (datos.madrid.es, dataset 200085, mensual con histórico): situación del local (abierto, cerrado, obras, baja), epígrafe, rótulo y coordenadas.
- **Registros sectoriales autonómicos** (p. ej. registro de centros sanitarios de la Comunidad de Madrid).

## Pregunta central
Para cada sector: cuando aparece la primera señal pública detectable (sobre todo el BORME), ¿el promotor ya ha comprometido las compras principales o siguen abiertas? ¿Qué % del gasto de apertura sigue "en juego" y durante cuántas semanas?

## Reglas de rigor (obligatorias)
- Etiqueta cada cifra como **[DATO]** (con fuente y enlace markdown) o **[EST]** (estimación, con razonamiento en una línea).
- No inventes cifras. Si no hay dato, escribe "Sin dato público" y propón cómo obtenerlo (llamada, consulta a asociación, petición de transparencia, conteo en el BORME...).
- Sé cuantitativo: rangos en € y en semanas. Mejor un rango honesto que una cifra falsamente precisa.
- Escribe en español.

## Restricciones técnicas del entorno
- **Solo funciona WebSearch.** WebFetch y curl están bloqueados para casi todos los dominios (boe.es, datos.madrid.es, ine.es, webs de sector...). No pierdas tiempo reintentando; basa la investigación en los resúmenes y enlaces que devuelve WebSearch.
- Haz muchas búsquedas específicas (en español; a veces en inglés para benchmarks): "cuánto cuesta abrir una clínica dental desglose", "plazo autorización sanitaria clínica dental Comunidad de Madrid", "plazo entrega sillón dental", "franquicia X calendario apertura semanas", "proveedores equipamiento hostelería leads", etc.
- Cita la URL de cada dato.

## Plantilla de ficha por sector (úsala para CADA sector del bloque)

### <Sector>
**Definición y CNAE/IAE relevantes**: códigos CNAE-2009 y epígrafes del IAE o del censo de Madrid que lo identifican.

**1. Mapa de compras**: tabla con las columnas Partida | Ticket típico (€) | % del CAPEX | Tipo de proveedor | ¿Se compra a un proveedor local o fragmentado?
Incluye, cuando aplique: reforma y obra civil, instalaciones (climatización, electricidad, fontanería, extracción, contra incendios), equipamiento específico, mobiliario, rótulo e imagen, software de gestión, TPV, telecomunicaciones, seguros, financiación o renting, marketing de apertura, suministros (luz, gas, agua), consumibles recurrentes, uniformes, limpieza, PRL, gestoría y asesoría, alarma o seguridad. Añade el CAPEX total típico (rango) para local independiente pequeño, mediano y franquicia.

**2. Cronología de la apertura**: tabla con las columnas Hito | Duración típica | Semana relativa (S0 = decisión) | Partidas que se comprometen en ese hito.
Hitos: decisión y plan de negocio, financiación, constitución de la SL (notaría → inscripción en el Registro Mercantil → BORME), búsqueda y firma del local, proyecto técnico, licencia o declaración responsable, autorización sectorial, obra, compras de equipamiento, contratación de personal y apertura.
Indica explícitamente **en qué semana relativa cae la publicación en el BORME** según el escenario (la SL suele constituirse ¿antes o después de firmar el local?), sumando el retraso de publicación de 1 a 12 semanas.

**3. Señales por hito**: tabla con las columnas Hito | Rastro público | Fuente | Acceso (API, scraping, manual) | Coste | Antelación frente a la apertura.
Fuentes posibles: BORME; licencias y declaraciones responsables municipales (¿se publican?); BOP o boletín autonómico; registro sectorial (sanitario, servicios sociales, educativo, turístico, RGSEAA); colegios profesionales; portales de empleo (InfoJobs, Indeed, LinkedIn); Google Maps ("próximamente"); redes sociales; prensa local; portales de locales y traspasos (Idealista, Fotocasa, Milanuncios); licitaciones; subvenciones (BDNS); y censo de locales en "obras".

**4. Ventana de oportunidad**: semanas entre la primera señal detectable y el compromiso de las compras principales, y **% del CAPEX aún sin comprometer** cuando sale el BORME. Desglosa los escenarios (a) independiente, (b) franquicia y (c) grupo o cadena. Razona con la cronología.

**5. Volumen**: aperturas o altas anuales en España y en Madrid (INE DIRCE por CNAE, registros sectoriales, asociaciones, franquicias, prensa sectorial). Indica la fracción que opera como sociedad frente a autónomo, porque los autónomos son invisibles en el BORME.

**6. Compradores de la información**: qué proveedores pagarían; cómo captan clientes hoy (comerciales de zona, distribuidores, ferias, Google Ads, recomendación del arquitecto o instalador); si ya compran leads y a qué precio; quién vende ya información parecida en España (competencia) y a qué precio.

**7. Riesgos**: RGPD (persona física frente a sociedad; administradores), sesgo de cobertura, compras centralizadas en cadenas y franquicias (la central compra), estacionalidad y tasa de fracaso.

**8. Puntuación propuesta (1-5) con una línea de justificación por criterio**: Volumen | Ticket comprable | Ventana | Detectabilidad | Coste de verificación (5 = barato) | Densidad y fragmentación de proveedores | Competencia existente (5 = poca) | Riesgo legal y operativo (5 = bajo).

## Eventos que no son aperturas (cúbrelos si aplican a tu bloque)
Ampliaciones, reformas integrales, traslados (cambio de domicilio en el BORME + nuevo local) y cambios de titularidad o traspasos: qué compras disparan y qué señales dejan.

## Formato de salida
Un único fichero markdown en la ruta indicada, con:
1. Un resumen ejecutivo del bloque (10-15 líneas): qué sectores tienen ventana real y cuáles no.
2. Una ficha por sector con la plantilla.
3. Una tabla resumen final con una fila por sector y las columnas Sector | Aperturas/año ES | Aperturas/año Madrid | CAPEX comprable medio (€) | % CAPEX abierto al salir el BORME (indep. / franq.) | Ventana en semanas (indep. / franq.) | Mejor señal temprana | 8 puntuaciones.
4. Una lista de fuentes con enlaces.
