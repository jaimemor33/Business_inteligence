# Pipeline BORME-A + censo de locales de Madrid (fases 3 y 4)

Código de las fases 3 y 4 de la investigación descrita en `research/_brief.md`:

- **Fase 3**: análisis empírico del BORME sección A (constituciones, cambios de objeto, de domicilio y de
  denominación), con la clasificación por sector, el % de domicilios en local, los retrasos de publicación y el % de ruido.
- **Fase 4**: backtest del *timing*: ¿cuántas aperturas del censo de locales de Madrid tienen antes
  una constitución o un traslado en el BORME, y con cuántas semanas de antelación?

> **Aviso importante sobre los datos de prueba.** Todo lo que hay en `pipeline/tests/fixtures/` es
> **SINTÉTICO**: lo genera `tests/fixtures/make_fixtures.py` y lo he escrito imitando el formato documentado.
> No contiene datos reales del BORME, del censo ni de licencias. El código **no se ha probado contra los
> PDF reales**, porque la red del entorno de desarrollo bloqueaba boe.es y datos.madrid.es (ver "Limitaciones").

## Instalación

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
python -m pytest pipeline/tests -q          # 75 tests, todos con fixtures sintéticos
```

Dominios que hay que permitir en el proxy o el cortafuegos:

| Dominio | Para qué |
|---|---|
| `www.boe.es` (y `boe.es`) | API de sumarios del BORME, PDF y XML de la sección A |
| `datos.madrid.es` | descarga manual o automática del censo de locales (200085) y de las licencias (300193) |
| `api.anthropic.com` | solo si se usa la capa LLM (`--llm`) |


## Fase 1 con fuentes oficiales (estrategia vigente)

```bash
python -m pipeline.cli -v fase1-oficial --desde 2025-04-01 --hasta 2026-03-31   # descarga todo y genera research/BACKTEST.md
```

Orden de verificación de cada sociedad:
1. **REGCESS** (dental; `regcess.py`), o los centros sanitarios de la Comunidad de Madrid como alternativa.
2. **Censo de locales de Madrid** (histórico mensual; `censo_borme.py`), con la señal temprana «Obras» + licencia «En tramitación».
3. **Google Places en modo básico** (ID y campos básicos, sin reseñas, tope de 20 USD) solo para las sociedades sin emparejar.

`descargas.py` baja automáticamente los datasets CKAN y el área de descarga del REGCESS. Cada métrica del informe lleva su fuente y la marca MEDIDO o ESTIMADO. Las fuentes, su estado de verificación y el análisis de Barcelona están en `research/FUENTES_FASE1.md`.

## Fase 1 en un comando (variante anterior, Google con reseñas) (datos reales → `research/BACKTEST.md`)

```bash
export ANTHROPIC_API_KEY=...        # clasificación con Claude (por defecto claude-opus-5-5, effort low; BI_LLM_MODEL para cambiarlo)
export GOOGLE_PLACES_API_KEY=...    # backtest de apertura
python -m pipeline.cli -v fase1 --desde 2025-04-01 --hasta 2026-03-31 --provincias MADRID,BARCELONA \
       --places-presupuesto 100 --muestra-por-celda 60
```

Qué hace cada paso:

1. **Descarga** el sumario y el **XML oficial** de la sección A de cada día; el PDF solo se baja si falla el XML.
2. **Parsea** los anuncios. Los administradores y el socio único se guardan como seudónimo HMAC (`admins_id`, `socio_unico_id`), nunca el nombre. La clave está en `data/.hash_key` o en `$BI_HASH_KEY`.
3. **Clasifica con Claude** todas las constituciones (categoría `generico` para los objetos "cajón de sastre"). El resto de actos se clasifica con reglas.
4. **Filtro de ruido** (`noise.py`):
   - `expansion_mismo_sector`: un administrador ya administra otra sociedad del mismo sector.
   - `filial_de_grupo`: administrador o socio único persona jurídica.
   - `holding_patrimonial`.
   - `apertura_nueva`: el resto.
5. **Google Places** (`places.py`) sobre una muestra aleatoria estratificada de aperturas nuevas por sector × ciudad:
   - Text Search (nombre, y si no encuentra nada, tipo de negocio + dirección) y puntuación de emparejamiento con nivel alta, media o baja.
   - Place Details con reseñas: la fecha de apertura aproximada es la reseña más antigua. Es EXACTA solo si el lugar tiene ≤ 5 reseñas; si no, es una cota superior.
   - Tope duro de gasto, registrado en `data/interim/places_ledger.json` a precio de lista. Las respuestas se guardan en caché y no se vuelven a pagar.
6. **Informe** (`fase1.py`): `research/BACKTEST.md` y `research/backtest/*.csv` con volumen mensual (total y tras ruido), % genéricos, % reestructuraciones, % localizable con IC95, desfase BORME → apertura (p25/mediana/p75) y los 3 criterios de descarte evaluados.

Coste orientativo de una ejecución de 12 meses en Madrid y Barcelona (ESTIMADO):
- **Claude**: unas 45.000-50.000 constituciones; unos 140 USD con Opus 5.5 en lote, unos 25 USD con Haiku 4.5. `--max-llm` pone un tope.
- **Places**: unas 2.000 sociedades; como mucho unos 140 USD a precio de lista, normalmente menos por el tramo gratuito mensual (5.000 Text Search Pro y 1.000 Enterprise). El tope por defecto es 100 USD.
- **Descarga**: unos 500 XML, unos 10 minutos.

**Validación con datos reales** (`tests/test_real.py`):
- XML oficial de Madrid del 30-09-2026: los 6 anuncios bien separados. Antes se perdían 3, porque el XML no viene ordenado por número.
- Sumario real del BORME.
- PDF real de Cáceres (2015), con 30 de 30 anuncios y 8 de 8 constituciones completas. Este test se ejecuta solo con `BI_REAL_PDF`, porque el PDF contiene nombres.

## Uso

Todos los comandos se ejecutan desde la raíz del repositorio. Los datos van a `./data` (o a `--data-dir` o `$BI_DATA_DIR`).

```bash
# 1. Descarga (caché idempotente en data/raw/; volver a ejecutarlo solo baja lo que falte)
python -m pipeline.cli -v fetch --desde 2026-04-01 --hasta 2026-09-30 --provincias MADRID,BARCELONA

# 2. Parseo PDF/XML -> data/processed/borme_actos.csv
python -m pipeline.cli -v parse --desde 2026-04-01 --hasta 2026-09-30 --provincias MADRID,BARCELONA

# 3. Clasificación sectorial (reglas; --llm añade Claude para los casos de baja confianza)
python -m pipeline.cli classify                 # solo reglas
python -m pipeline.cli classify --llm --umbral 0.6 --max-llm 2000

# 4. Métricas e informe -> data/output/metrics_*.csv + informe_borme.md
python -m pipeline.cli metrics

# 5. Backtest con el censo de Madrid (mínimo 2 meses; mejor 6-12)
#    Descargar a mano los CSV mensuales del dataset 200085 en data/raw/censo/
python -m pipeline.cli backtest --censo data/raw/censo/
#    ...revisar a mano data/output/backtest_muestra_revision.csv (columna es_correcto = 1/0) y:
python -m pipeline.cli backtest --censo data/raw/censo/ --revisado data/output/backtest_muestra_revision.csv
#    Opcional (NO VALIDADO): licencias y declaraciones responsables (dataset 300193)
python -m pipeline.cli backtest --censo data/raw/censo/ --licencias data/raw/licencias/

# Atajo: fetch + parse + classify + metrics
python -m pipeline.cli all --desde 2026-04-01 --hasta 2026-09-30 --provincias MADRID
```

`--provincias` acepta nombres (`MADRID`, `A CORUÑA`, `ALICANTE`...) o códigos INE (`28,08`). Si se omite, se descargan todas.
El nombre de cada fichero del censo debe incluir el mes (`..._202606.csv`, `..._06_2026.csv`, `...2026-06...`);
si no lo incluye, se usa la columna `fx_carga`.

## Qué hace cada paso

| Módulo | Qué hace |
|---|---|
| `borme_fetch.py` | Pide `https://www.boe.es/datosabiertos/api/borme/sumario/AAAAMMDD` (`Accept: application/json`) para cada día laborable, localiza en el sumario los PDF de la sección A (uno por provincia) y los descarga. Parseo **defensivo**: recorre todo el JSON buscando ítems con identificador `BORME-A-AAAA-NNN-PP` o colgados de la sección `A` y, si cambian las claves, recurre a buscar URLs `BORME-A-*.pdf` en el JSON. Excluye las secciones B y C y los índices. Hace reintentos con *backoff* en 429/5xx y errores de red, aplica un *rate limit* (1 petición/s por defecto, `--pausa`) y envía un User-Agent identificable. La caché queda en `data/raw/sumarios/AAAAMMDD.json` (o `.none` si ese día no hay BORME) y `data/raw/borme/AAAAMMDD/BORME-A-*.pdf`, más un `manifest.csv`. Las escrituras son atómicas (`.part` → renombrado). Si el sumario trae `url_xml` (API v2.0, ver abajo), descarga también el XML. |
| `borme_parse.py` | Convierte el PDF en texto con pdfplumber (detecta si la página está a dos columnas y lee primero la izquierda y luego la derecha), con pypdf de respaldo. Elimina cabeceras y pies (`BOLETÍN OFICIAL...`, `Núm. ... Pág.`, `cve:`, `Verificable en...`), vuelve a unir las palabras partidas con guion y segmenta en anuncios por `^NNNNNN - DENOMINACION.`, exigiendo números crecientes. Después separa los actos por palabra clave (lista basada en bormeparser 0.5.0) y extrae la denominación, la forma jurídica, el registro mercantil, los tipos de acto, el evento principal, el objeto social, el CNAE, el domicilio, el municipio, el CP, el capital, la fecha de comienzo de operaciones, la fecha de inscripción (la de "Datos registrales"), la hoja registral, la fecha de publicación, la provincia y el nº de anuncio. Orden de formatos por BORME: XML → PDF → `.txt`; si un formato no produce anuncios, pasa al siguiente. |
| `classify.py` | (a) Reglas: mapa CNAE (2009 y 2025) → sector y diccionario de palabras clave ponderadas para 34 sectores, más **ruido** y **otros**. Bonifica la primera actividad enumerada y penaliza los objetos "cajón de sastre". Guarda `sector`, `confianza` (0-1), `regla` (p. ej. `cnae:5610+kw:BARES` o `ruido:TENENCIA DE PARTICIPACIONES`) y `metodo`. (b) LLM opcional, ver abajo. Conserva siempre el `objeto_social` original. |
| `metrics.py` | Agrega por sector × provincia × mes: actos por tipo, capital medio y mediano (constituciones), % de domicilios en local / piso u oficina / indeterminado, retraso comienzo→publicación e inscripción→publicación (p10, p25, mediana, p75, p90 en días) y % de ruido. Escribe los CSV y `informe_borme.md`. |
| `madrid_census.py` | Lee N meses del censo 200085 (`;` o `,`; UTF-8, UTF-8 con BOM o latin-1; coma decimal) y normaliza los nombres de columna con una tabla de alias. Detecta las aperturas: `nuevo_local` (aparece por primera vez ya abierto), `reapertura_actividad_nueva` (de obras/cerrado/baja a abierto con un epígrafe nuevo), `cambio_actividad` (abierto con un epígrafe nuevo) y `reapertura_misma_actividad` (excluida del backtest). Cuenta los meses previos en obras o cerrado y asigna el sector por epígrafe. El primer mes del panel está censurado. |
| `backtest.py` | Empareja cada apertura con constituciones o cambios de domicilio de la provincia de Madrid publicados entre 730 días antes y 62 días después, por similitud rótulo~denominación (rapidfuzz, quitando SL, SOCIEDAD LIMITADA, etc.) y por dirección normalizada (vía + número). Hay tres niveles: **A** dirección + nombre ≥ 60; **B** solo dirección (≤ 3 sociedades en esa dirección, para evitar gestorías); **C** solo nombre ≥ 90 (los rótulos genéricos como "BAR" se excluyen). Saca el % de match por sector, la distribución del lag BORME→apertura y obras→apertura, una muestra estratificada para revisión manual y la tabla de precisión cuando hay muestra revisada. |
| `madrid_licencias.py` | Opcional y **no validado**: carga el dataset 300193 (licencias urbanísticas y declaraciones responsables), normaliza las columnas y cruza por dirección con las aperturas para medir el lag licencia/DR → apertura. |
| `cli.py` | Comandos `fetch`, `parse`, `classify`, `metrics`, `backtest` y `all`. |

### Capa LLM (opcional)

- Solo se activa con `--llm` **y** si existe `ANTHROPIC_API_KEY`. Si no, el pipeline funciona solo con reglas.
- Modelo: `claude-haiku-4-5` (el más barato de la gama actual, suficiente para clasificar textos cortos).
  Se puede cambiar con `BI_LLM_MODEL`.
- Usa salida estructurada (`output_config.format` con JSON Schema): `sector` (enum del catálogo), `confianza` y `justificacion`.
- Hasta 50 casos: llamadas síncronas. Con más: **Message Batches API** (un 50 % más barata y asíncrona;
  suele tardar menos de 1 h). Los resultados se emparejan por `custom_id`.
- Caché en `data/interim/llm_cache.jsonl` (clave: modelo + versión del prompt + texto), para no pagar dos veces el mismo objeto social.
- Solo sustituye la clasificación por reglas si la confianza del LLM es mayor. Marca `metodo=llm` y guarda la justificación.
- Coste **[EST]**: unos 600 tokens de entrada y 60 de salida por caso → del orden de 0,5-1 € por cada 1.000 casos
  (la mitad con batch). Pasar solo los casos de baja confianza (`--umbral`) y limitar con `--max-llm`.

## Salidas

| Fichero | Contenido |
|---|---|
| `data/processed/borme_actos.csv` | Un anuncio por fila, sin datos de personas físicas |
| `data/processed/borme_clasificado.csv` | Lo anterior más `sector`, `confianza`, `regla`, `metodo` y `justificacion_llm` |
| `data/output/metrics_sector_provincia_mes.csv` | Agregados por sector × provincia × mes |
| `data/output/metrics_actos_por_tipo.csv`, `metrics_sector.csv`, `metrics_ruido_provincia_mes.csv` | Desgloses |
| `data/output/informe_borme.md` | Informe de la fase 3 |
| `data/output/censo_aperturas_todas.csv` | Todas las aperturas detectadas en el censo |
| `data/output/backtest_aperturas.csv` | Aperturas usadas en el backtest, con su match del BORME (y, opcionalmente, su licencia) |
| `data/output/backtest_resumen_sector.csv`, `backtest_muestra_revision.csv`, `backtest_precision.csv` | Resultados del backtest |
| `data/output/informe_backtest.md` | Informe de la fase 4 |

`data/` no debe versionarse: añádelo a `.gitignore`.

## RGPD: minimización de datos

- **No se guardan nombres de personas físicas** (administradores, apoderados, consejeros, socios únicos,
  liquidadores). El parser los lee en memoria solo para calcular `n_cargos_nombrados`, `n_cargos_cesados`,
  `n_cargos_pj` (cuántos son personas jurídicas), `admin_persona_juridica` y `socio_unico_persona_juridica`.
  Un test (`test_rgpd_sin_nombres_de_personas`) comprueba que no aparecen en la salida.
- Tampoco se guarda el texto íntegro del anuncio, solo los campos estructurados y el objeto social.
- Los nombres de personas jurídicas (denominación, nueva denominación) sí se guardan, porque son datos de empresas.
- El **domicilio social** de una SL pequeña puede ser la vivienda del socio. Es un dato publicado en un boletín
  oficial y referido a la sociedad, pero conviene no cruzarlo con personas y limitar su uso a la finalidad del estudio.
- La caché `data/raw/` contiene los PDF originales del BOE, que **sí incluyen nombres de personas** (fuente pública).
  Hay que restringir el acceso a esa carpeta y borrarla cuando ya no haga falta reprocesar.

## Tiempo estimado de ejecución (6 meses, todas las provincias) [EST]

Unos 125 BORME (días laborables) × unas 52 provincias ≈ 6.500 PDF + 125 sumarios.

| Paso | Todas las provincias | Solo MADRID + BARCELONA | Razonamiento |
|---|---|---|---|
| fetch | 2-3 h | 10-20 min | 1 petición/s de *rate limit* + transferencia; unos 15-25 MB/día en total → **2-3 GB** en disco |
| parse (pdfplumber) | 3-5 h | 1-1,5 h | unas 400 páginas/día × 125 días × 0,2-0,35 s/página |
| parse (`--engine pypdf`) | 40-80 min | 15-25 min | más rápido, pero sin detección de columnas |
| classify (reglas) | < 2 min | < 1 min | |
| classify `--llm` (batch) | 0,5-2 h de espera | | depende del nº de casos de baja confianza |
| metrics / backtest | < 5 min | < 5 min | |

Las descargas son idempotentes: si se interrumpen, se relanza el mismo comando.

## Limitaciones conocidas (léase antes de usar las cifras)

1. **No se ha probado con datos reales.** Todo el pipeline se ha probado de extremo a extremo con fixtures
   sintéticos (incluidos PDF sintéticos de una y dos columnas generados con reportlab). Riesgos de parseo previstos con los PDF reales:
   - El orden de lectura de pdfplumber puede mezclar columnas si la maqueta real no tiene un hueco central limpio,
     o si la cabecera ocupa más del 9 % superior de la página. Revisar `parse_warnings` y comparar el nº de anuncios con el índice.
   - Las líneas de cabecera y pie reales pueden diferir de los patrones `RUIDO_LINEAS` (por ejemplo, el texto del logo).
   - Denominaciones partidas en dos líneas, con puntos (`S.L.`) o con paréntesis (`(R.M. ...)`): cubiertas, pero solo con casos sintéticos.
   - Una línea del cuerpo que empiece por `NNN - ` y tenga un número cercano al del anuncio anterior se tomaría como anuncio nuevo.
   - Palabras clave de acto con variantes no previstas (sin tilde, en mayúsculas o en catalán en algunos registros):
     esos actos se quedarían dentro del argumento del acto anterior.
   - Etiquetas de cargo en MAYÚSCULAS (p. ej. `PRESIDENTE:`): no se cuentan como cargos.
   - Fechas con formatos raros en "Comienzo de operaciones" (se marca `fecha_comienzo_ilegible`).
   - Las fuentes con codificación propia en el PDF pueden extraer caracteres incorrectos (º, Ñ): pypdf es el respaldo.
2. **API v2.0 del BORME (XML/HTML de la sección primera, 28-05-2026): NO VALIDADO.** No se conoce la estructura real
   del XML. `borme_fetch` descarga `url_xml` si el sumario la trae (también busca `urlXml`, `xml`...).
   `borme_parse.xml_to_text` vuelca los nodos de texto y segmenta con los mismos patrones; si no encuentra
   anuncios, toma como anuncio cada elemento con un único "Datos registrales" y busca el número en sus
   atributos. El PDF sigue siendo el respaldo. Hay que revisarlo con el primer XML real.
3. **Dataset 300193 (licencias urbanísticas y declaraciones responsables): NO VALIDADO.** El esquema real
   es desconocido; `madrid_licencias.ALIAS` contiene nombres de columna supuestos (fecha de concesión, tipo de
   procedimiento, objeto, régimen de uso, obras, emplazamiento, coordenadas) y una coincidencia parcial de respaldo.
   El cruce es solo por dirección normalizada; las licencias de obras en viviendas del mismo portal pueden dar falsos positivos.
4. **Los autónomos son invisibles**: el BORME solo recoge sociedades. Sectores con mucho autónomo (peluquería,
   estética, fisioterapia, farmacia, que es propiedad del farmacéutico persona física) saldrán infrarrepresentados.
5. **Ruido**: holdings, patrimoniales, inmobiliarias de alquiler, consultoría genérica y comercio online se
   etiquetan como `ruido` por reglas. Un objeto social genérico ("cualquier actividad lícita") queda como `sin_clasificar`.
6. **Domicilio social ≠ local**: muchas SL se domicilian en la gestoría o en casa del socio; `pct_local` y el
   cruce por dirección dependen de ello.
7. **"Comienzo de operaciones"** suele ser la fecha de la escritura, no la de apertura.
8. **Censo de Madrid**: resolución mensual (la apertura se fecha el día 1 del mes en que aparece abierta), primer
   mes censurado, rótulos a menudo vacíos o distintos de la denominación social. Con pocos meses, las obras largas
   quedan censuradas (`obras_censurado`). Los valores de `desc_situacion_local` se normalizan buscando
   "ABIERT", "OBRA", "CERRAD" y "BAJA"; hay que confirmar los valores reales. Se supone que los 4 primeros dígitos de
   `id_epigrafe` son la clase CNAE-2009.
9. **CNAE-2025**: el mapa de códigos mezcla CNAE-2009 y CNAE-2025 (en vigor desde 2025); los códigos 2025 se han
   escrito de memoria y deben verificarse con la tabla oficial del INE.
10. Las direcciones con números en el nombre de la vía ("CALLE 2 DE MAYO 5") no se normalizan bien.
11. Si se pide el sumario del día antes de que se publique, el 404 se cachea como "sin BORME" (`.none`): en ese caso, relanzar con `--refresh`.

## Créditos

El conocimiento del formato (palabras clave de actos, patrón de "Datos registrales", siglas societarias)
procede de [bormeparser](https://github.com/PabloCastellano/bormeparser) 0.5.0 (Pablo Castellano, GPLv3).
El código de este directorio es una reimplementación y no importa bormeparser.
