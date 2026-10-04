# Fase 4c: Guion de validación telefónica del timing

## Objetivo
Medir en negocios reales y recién abiertos **cuándo se comprometió cada partida de compra respecto a la constitución de la sociedad (y, por tanto, respecto al BORME)**. Es la única forma de convertir las estimaciones de la desk research en datos propios. Las llamadas sirven además para medir **cómo les contactaron los proveedores**: si ya les llegaron comerciales antes de abrir, el hueco es menor.

## Muestra
- **Universo**: negocios de los sectores finalistas abiertos hace 3-6 meses en Madrid.
- **Cómo construir el listado** (por orden de preferencia):
  1. Censo de locales de Madrid: locales que pasan a "Abierto" con epígrafe del sector en los últimos 6 meses (script `pipeline/backtest.py`). Priorizar los que tienen match con una constitución en el BORME, porque ya conocemos su fecha de escritura y de publicación y la llamada solo tiene que fechar las compras.
  2. Google Maps: fichas creadas recientemente o con reseñas solo de los últimos meses.
  3. Registro sectorial (p. ej. altas recientes en el registro de centros sanitarios de la Comunidad de Madrid).
- **Tamaño**: 15 llamadas completadas por sector finalista (unos 45 en total con 3 sectores). Hacen falta unos 40-60 intentos por sector, contando una tasa de respuesta útil del 25-35% en llamadas en frío a pymes [EST].
- **Estratificación** dentro de las 15: unas 10 independientes y unas 5 franquicias o cadenas. Unas 10 con sociedad en el BORME y unas 5 como autónomos (para medir el sesgo de cobertura).
- **Cuándo llamar**: en franjas valle del sector (hostelería, de 16:00 a 18:00; clínicas, primera hora o mediodía).
- **Legal**: es una encuesta de investigación, no una llamada comercial, así que no hay que ofrecer nada en la llamada. Aun así, llama al teléfono público del negocio, identifícate, explica el propósito, pide consentimiento para tomar notas, no grabes sin consentimiento explícito y no guardes datos personales del interlocutor más allá del nombre del negocio. El art. 66 de la Ley 11/2022 restringe las llamadas comerciales no consentidas: si la llamada deriva en una oferta, se convierte en comercial.
- **Incentivo** (opcional): enviar después el informe agregado del sector ("cuánto tardan y gastan los que abren como tú").

## Guion (5-7 minutos)

> "Hola, soy [nombre], estoy haciendo un estudio sobre cómo se abren negocios de [sector] en Madrid. Son 5 minutos y no vendo nada. ¿Me ayudaría con unas preguntas sobre su apertura? Al final le puedo enviar el informe con los resultados."

| # | Pregunta | Qué medimos | Codificación |
|---|---|---|---|
| 1 | **¿En qué mes decidieron abrir y en qué mes abrieron al público?** | Duración total del proyecto (S0 → apertura) | Dos fechas (mes/año) |
| 2 | **¿Montaron una sociedad para este negocio? ¿Firmaron en el notario antes o después de firmar el contrato del local, y cuántas semanas antes o después?** | Posición de la escritura (y, por tanto, del BORME) respecto al local | Antes / después / misma semana, ± semanas, o "autónomo" o "sociedad existente" |
| 3 | **De estas partidas, ¿cuándo cerraron el pedido o firmaron el presupuesto, y con quién?** Recorrer la lista: obra y reforma; instalaciones (climatización, electricidad, extracción); equipamiento principal del sector [p. ej. cocina, sillón dental, máquinas]; mobiliario; software y TPV; seguros; financiación o renting. | Semana de compromiso de cada partida | Para cada partida: mes, o "semanas antes de abrir"; tipo de proveedor; ¿venía con el local (traspaso)? |
| 4 | **¿Cuánto invirtieron en total, más o menos, y qué partida fue la más grande?** | CAPEX real y su composición | Tramo: <30 k€, 30-80 k€, 80-150 k€, 150-300 k€, >300 k€ |
| 5 | **¿Cómo encontraron a esos proveedores? ¿Les contactó alguno antes de que ustedes les buscaran? ¿Cuándo, y cómo supieron que iban a abrir?** | Competencia actual en la captación y antelación con que llegan hoy los proveedores | Por partida: recomendación (arquitecto, franquicia, colega), búsqueda en Google, feria, visita comercial espontánea (fecha), otro |
| 6 | **Si alguien le hubiera presentado 2-3 proveedores comparados para [partida], ¿en qué momento le habría servido y cuándo ya era tarde?** | Ventana percibida por el comprador | Hito: "antes de firmar el local", "durante el proyecto", "durante la obra", "ya tarde" |
| 7 (opcional) | **¿Algo que compraran tarde o mal por no conocer opciones a tiempo?** | Dolor del comprador (argumento de venta del lado de la demanda) | Texto libre |

## Hoja de registro (una fila por llamada)
`id | sector | tipo (indep/franquicia/cadena) | forma (SL/autónomo) | fecha_decision | fecha_escritura | fecha_borme (si hay match) | fecha_firma_local | fecha_apertura | capex_tramo | por cada partida: fecha_compromiso, proveedor_tipo, canal_captacion, venia_con_local | contactado_por_proveedor_antes (s/n, cuándo) | ventana_percibida | notas`

## Análisis
Para cada sector y partida: **% del CAPEX comprometido después de la fecha de publicación en el BORME** = Σ(ticket de las partidas con fecha de compromiso > fecha del BORME) / CAPEX total. Si no hay match en el BORME, se usa como proxy la fecha de escritura + la mediana del retraso de publicación de la provincia (fase 3).

**Reglas de decisión** (para pasar del sector a test comercial):
- Mediana de **% del CAPEX abierto al BORME ≥ 50%** y **≥ 6 semanas** de ventana para las partidas principales → el sector sigue en el test.
- Si **≥ 40%** de los entrevistados recibieron contacto de proveedores **antes** de la apertura sin pedirlo → la competencia informal es fuerte. Hay que diferenciarse por antelación o por cualificación.
- Si **≥ 50%** de las aperturas del sector son de autónomos o vía traspaso con equipamiento → el BORME no sirve como fuente principal en ese sector. Hay que replantear las fuentes (censo en "obras", registros sectoriales).
