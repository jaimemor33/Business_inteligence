# Fuentes de verificación de la fase 1 (oficiales primero, Google al final)

*Actualizado el 4 de octubre de 2026.*

**Etiquetas.** VERIFICADO quiere decir que lo confirma la documentación oficial encontrada por búsqueda web. NO VERIFICADO quiere decir que hay que comprobarlo con el fichero real: en esta sesión la red bloquea sanidad.gob.es, regcess.mscbs.es, datos.madrid.es, gestiona.madrid.org, datos.comunidad.madrid y opendata-ajuntament.barcelona.cat, así que no se ha podido abrir ningún fichero.

## 1. REGCESS (Ministerio de Sanidad)

| Aspecto | Detalle | Estado |
|---|---|---|
| URL de descarga | [Área de descarga del REGCESS](http://regcess.mscbs.es/regcessWeb/inicioDescargarCentrosAction.do); portal en [sanidad.gob.es/areas/saludDigital/regCess](https://www.sanidad.gob.es/areas/saludDigital/regCess/home.htm) | VERIFICADO |
| Formato | Excel, un fichero por tipo de centro: C1 hospitales, C2 centros sin internamiento (las clínicas dentales son C.2.5.1), C3 servicios dentro de organizaciones no sanitarias y E establecimientos | VERIFICADO |
| Frecuencia | Mensual: el Ministerio ofrece descargas periódicas mensuales; el registro se actualiza en tiempo real con lo que envían las CCAA ([manual de definiciones](https://regcess.mscbs.es/regcessWeb/descargaManualDefinicionesInformacion.do)) | VERIFICADO |
| Campos | Según el manual: Código Autonómico del Centro, Nombre del Centro, Fecha Autorización de Funcionamiento y otros | VERIFICADO (parcial) |
| Campo titular | No se ha podido confirmar que la descarga incluya el nombre del titular | **NO VERIFICADO** |
| Fotos históricas | No se ha encontrado documentación de que se publiquen las fotos de meses anteriores ("día 1 de cada mes, con centros activos y cerrados"). Las búsquedas solo describen la descarga vigente | **NO VERIFICADO; probablemente solo existe la actual** |
| Retraso frente al hecho real | La autorización de funcionamiento llega tras la inspección con el centro montado: 2-6 meses en la práctica (ver la ficha de salud ambulatoria). Después, la comunidad autónoma la comunica al registro estatal con un retraso desconocido | ESTIMADO |
| Cobertura | Todos los centros autorizados por las CCAA, públicos y privados | VERIFICADO |

**Si solo existe la foto actual, la pipeline lo resuelve sola.** `regcess.centros()` detecta que hay una sola foto y usa el campo **Fecha Autorización de Funcionamiento** como fecha de alta.
- **Riesgo**: si el centro ha renovado la autorización, la fecha puede ser la de la renovación. Se detecta como "centro autorizado antes de la sociedad" y se informa aparte.
- **Sesgo**: los centros cerrados que no salgan en la foto actual se pierden, lo que sesga a la baja el % con centro.
- **Para medirlo**: guardar desde ya una foto al mes (descarga automática programada).

**Alternativa para Madrid** (si el REGCESS no trae titular o histórico): [Centros, servicios y establecimientos sanitarios](https://datos.comunidad.madrid/catalogo/dataset/centros_servicios_establecimientos_sanitarios) de la Comunidad de Madrid.
- CSV y JSON, con **actualización diaria** (VERIFICADO), publicado por la DG de Inspección y Ordenación Sanitaria.
- Campos exactos NO VERIFICADOS.
- La pipeline acepta este fichero con el mismo cargador (`--regcess`).
- El buscador [gestiona.madrid.org/cyes_web_reg](https://gestiona.madrid.org/cyes_web_reg) es una consulta web una a una. Automatizarlo sería scraping de un buscador: se descarta mientras exista el CSV.

## 2. Censo de locales y actividades de Madrid

| Aspecto | Detalle | Estado |
|---|---|---|
| Actual | [Dataset 200085](https://datos.madrid.es/dataset/200085-0-censo-locales): microdatos de locales y actividades con situación (abierto, cerrado, obras...). La ficha indica actualización mensual (último dato hasta el 31-08-2026, publicado el 15-09-2026) | VERIFICADO |
| Histórico | [Dataset 209548, Histórico](https://datos.madrid.es/egob/catalogo/209548-0-censo-locales-historico): ficheros mensuales desde marzo de 2014 | VERIFICADO |
| Estructura | [Estructura_DS_FicheroCLA.pdf](https://datos.madrid.es/FWProjects/egob/Catalogo/Economia/Ficheros/Estructura_DS_FicheroCLA.pdf). Hay un fichero de locales (una fila por local) y otro de actividades (local × epígrafe) | VERIFICADO |
| Licencias | Existe documentación de un fichero de "locales con información de licencias" (144 KB de documentación) | VERIFICADO (existencia) |
| Campos de licencias | Campos y valores (p. ej. situación "En tramitación") | **NO VERIFICADO** |
| Retraso frente al hecho real | Un mes de resolución, más unos 15 días de publicación | VERIFICADO (por la ficha) |
| Cobertura | Locales con acceso desde la calle o agrupados del municipio de Madrid, con independencia de la forma jurídica: incluye a los autónomos | VERIFICADO |

Relacionado: el [dataset 300193 de licencias urbanísticas y declaraciones responsables](https://datos.madrid.es/dataset/300193-0-licencias-urbanisticas) es mensual, desde 2015. Ya tiene cargador opcional (`madrid_licencias.py`).

## 3. Google Places (último recurso)

- Solo se consulta para las sociedades que no se han emparejado en el REGCESS ni en el censo.
- Text Search con **ID y campos básicos** (nombre, dirección, tipos, estado), **sin reseñas ni Place Details**, con **tope duro de 20 USD**.
- Precio de lista de Text Search Pro: 32 USD por 1.000 llamadas, con 5.000 gratis al mes ([precios](https://developers.google.com/maps/billing-and-pricing/pricing)). 20 USD dan para unas 600 búsquedas.
- Google solo confirma que el local existe; no da fecha de apertura.

## 4. Barcelona (investigado, NO se ejecuta)

| Fuente | Qué es | Frecuencia | ¿Sirve para el backtest? |
|---|---|---|---|
| [Cens de locals en planta baixa](https://opendata-ajuntament.barcelona.cat/data/ca/dataset/cens-locals-planta-baixa-act-economica) (Open Data BCN) | Locales en planta baja con actividad. Desde 2022 solo incluye los activos o pendientes de actividad | "Segons disponibilitat/necessitat" (irregular, en olas) | **No**: sin frecuencia mensual no se puede fechar la apertura |
| [Llista de codis del cens d'activitats](https://opendata-ajuntament.barcelona.cat/data/ca/dataset/cens-activitats-economiques-class-bcn) | Solo la clasificación de actividades | Irregular | No |
| [Establiments sanitaris autoritzats a Catalunya](https://analisi.transparenciacatalunya.cat/Salut/Establiments-sanitaris-autoritzats-a-Catalunya/nrmq-ytje) (Generalitat, Socrata) | Farmacias, ópticas, centros auditivos y ortopedias autorizados | **Semanal** | Parcial: sirve para ópticas y audiología, **no para clínicas dentales**. Es el candidato a un piloto sanitario en Barcelona |
| Registro de centros sanitarios de Cataluña (clínicas) | No se ha encontrado dataset abierto con clínicas | — | Pendiente |
| [Cens d'activitats i establiments](https://dadesobertes.diba.cat/datasets/cens-dactivitats-i-establiments) (Diputació de Barcelona) | Censo de actividades de municipios de la provincia | NO VERIFICADO | Pendiente de revisar frecuencia y si incluye Barcelona ciudad |
| Licencias o comunicados de obras (Ajuntament) | No se ha encontrado un dataset abierto con frecuencia mensual | — | Pendiente. Alternativa: solicitud de reutilización a la Gerència d'Ecologia Urbana |

Conclusión: **hoy no hay en Barcelona un equivalente al censo mensual de Madrid**. Barcelona queda fuera del backtest. La primera candidata para reincorporarla es la fuente semanal de la Generalitat (solo para óptica y audiología).

## 5. Qué hace falta para ejecutar la fase 1 con estas fuentes

1. **Red** (menú del entorno cloud → Edit → Network access → Custom → Allowed domains):
   - `www.boe.es`
   - `regcess.mscbs.es` y `www.sanidad.gob.es`
   - `datos.comunidad.madrid`
   - `datos.madrid.es`
   - `places.googleapis.com` ya está accesible.
2. **Variables de entorno**: `ANTHROPIC_API_KEY` (clasificación) y `GOOGLE_PLACES_API_KEY` (opcional, último recurso).
3. **Descargas** a `data/raw/`. Las del censo y el REGCESS se automatizan en cuanto haya red; los portales sirven ficheros por URL directa. Si alguna resulta ser solo un formulario web (p. ej. el REGCESS con sesión), se documentará como NO AUTOMATIZABLE y se usará la alternativa de la Comunidad de Madrid.
4. Comando:
   ```bash
   python -m pipeline.cli -v fase1-oficial --desde 2025-04-01 --hasta 2026-03-31 \
       --regcess data/raw/regcess/ --censo data/raw/censo/ --licencias-censo data/raw/censo_licencias/ \
       --google-tope 20
   ```
