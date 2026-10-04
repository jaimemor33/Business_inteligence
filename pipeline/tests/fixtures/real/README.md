# Fixtures reales

- `BORME-A-2026-189-28.xml`: extracto del XML oficial de la sección A (Madrid, 30-09-2026), formato de la API v2.0 del BOE. Procede de la muestra publicada en el repositorio público `BquantFinance/Administracion-fuentes-publicas` (`scripts/clientes/muestras/`). Los nombres de personas ya venían sustituidos por `APELLIDO APELLIDO NOMBRE`; aquí se ha sustituido además el nombre del juez. Fuente original: Agencia Estatal BOE (https://www.boe.es).
- `sumario_20260930.json`: sumario real del BORME del 30-09-2026 (misma procedencia). Sin datos personales.
- El PDF real `BORME-A-2015-27-10.pdf` (Cáceres, 10-02-2015, tomado de `PabloCastellano/bormeparser/examples/`) **no se incluye** en el repositorio porque contiene nombres de personas físicas. El test que lo usa se salta si no existe; para ejecutarlo, apunta `BI_REAL_PDF` a una copia local.
