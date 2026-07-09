# Contratos Vigentes - Complete PDF Extraction

## Source PDFs

- `Informe_Contratos_Vigentes_al_Momento_de_Transicion.pdf` -> `ACUDEN_2024`
- `Contratos_Vigentes_ACT.pdf` -> `ACT_2020`

## Files

- `contratos_vigentes_complete_extraction.xlsx`: Excel workbook with Summary, Combined_Canonical, raw PDF extractions, and page validation.
- `contratos_vigentes_combined_canonical.csv`: Combined canonical row-level list.
- `ACUDEN_2024_raw_extracted.csv`: Raw extraction of all ACUDEN rows.
- `ACT_2020_raw_extracted.csv`: Raw extraction of all ACT rows.
- `page_extraction_validation.csv`: Rows extracted by page.

## Row counts

| Dataset | Pages | Rows extracted |
|---|---:|---:|
| ACUDEN_2024 | 49 | 1147 |
| ACT_2020 | 41 | 656 |
| Combined | 90 | 1803 |

## Validation

- ACUDEN Sec range: 1-1147
- ACUDEN missing Sec values: none
- ACUDEN duplicate Sec values: none
- ACT duplicate contract-number values: 5 duplicated keys; see canonical table if needed.
- Dates are preserved as raw source text.
- `amount_numeric` parses `Cuantía` where numeric and leaves blank/dash values empty.

## ACUDEN service-type counts

- Transferencia de Fondos: 1042
- Servicios de adiestramiento y capacitación: 18
- Servicios relacionados a Sistema de Información: 15
- Servicios de Consultoría: 14
- Servicios de Coordinación y Producción de Eventos: 9
- Servicios de Gerencia de Proyectos: 9
- Servicio de Empleo Temporero: 7
- Servicios de Consultoría Legal: 6
- Servicios de Monitorías: 6
- Contrato de Arrendamiento: 4
- Servicios de Coordinación de Eventos: 3
- Servicios de Diseño: 3
- Oficinas: 2
- Servicios de Publicidad: 2
- Arrendamiento de máquinas multifuncionales: 1
- Servicios administrativos: 1
- Servicios de Consultoría e Implementación: 1
- Servicios de Mentoría y Monitoreo: 1
- Servicios de Planificación Estatégica: 1
- Servicios de orientación y actividades: 1
- Servicios de relaciones públicas: 1

## ACT service-type counts

- CONSTRUCCION Y REPARACION DE VIAS PUBLICAS: 165
- SERVICIOS PROFESIONALES: 161
- INTERAGENCIALES: 144
- ACUERDOS FINANCIEROS Y NO FINANCIEROS: 61
- COMPRA, VENTA Y ALQUILER DE EQUIPO, VEHICULOS Y OTROS: 29
- COMPRA, VENTA, ALQUILER Y/O DESARROLLO DE INMUEBLES: 24
- SERVICIOS PERSONALES NO PROFESIONALES: 18
- SERVICIOS DE CONSULTORIA: 17
- SERVICIOS TÉCNICOS: 13
- SERVICIOS RELACIONADOS A LOS SISTEMAS DE INFORMACIÓN: 11
- SERVICIOS MISCELÁNEOS NO PERSONALES: 8
- CONSTRUCCION Y REPARACION DE ESTRUCTURAS: 3
- COMPRA DE MATERIALES, SUMINISTROS Y EFECTOS: 2
