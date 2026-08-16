# Proceso inicial de Facturación

## Entrada

- Archivo PxQ ficticio.
- Cliente y servicio ficticios.
- Periodo contractual y moneda.

## Flujo

1. Registrar el archivo y calcular su hash.
2. Extraer cantidad, tarifa, periodo, moneda y total.
3. Aplicar reglas deterministas.
4. Mostrar campos, evidencia y excepciones.
5. Solicitar aprobación humana.
6. Invocar el adaptador de emisión simulada.

## Excepciones mínimas

- Diferencia entre cantidad por tarifa y total.
- Tarifa ausente o no vigente.
- Periodo fuera del contrato.
- Moneda incompatible.
- Campo crítico sin evidencia.
