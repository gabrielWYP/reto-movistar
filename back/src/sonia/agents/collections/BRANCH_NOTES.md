# Agente de Cobranzas/Recaudación SON-IA

Módulo integrado al backend compartido de SON-IA. Reconstruye cartera B2B, analiza aplicaciones
documentales y prioriza oportunidades de recupero. Los importes, estados, antigüedad e índices se
calculan de forma determinística; OpenAI solo interpreta la consulta, selecciona herramientas y
explica resultados respaldados por evidencia.

## Ubicación dentro de main

- Núcleo y API: `back/src/sonia/agents/collections/`.
- Interfaz: `front/agents/collections/`.
- API pública: `/api/collections/*` detrás del único frontend Nginx.
- Despliegue: los dos pods compartidos `front` y `back`; no existe un pod por agente.

## Capacidades

- Estado global de cartera y antigüedad de deuda.
- Situación de cobranza por cliente.
- Trazabilidad factura → pagos → notas de crédito → saldo.
- Ranking determinístico y explicable de clientes.
- Excepciones de aplicación documental.
- Carga temporal de CSV con validación previa y reemplazo atómico.
- Consulta opcional con OpenAI Responses API y function calling.

## Configuración

El backend puede iniciar sin dataset. El usuario puede cargar CSV desde la interfaz o configurar
`SONIA_COLLECTIONS_DATASET` con la ruta de un ZIP compatible disponible fuera de Git. La clave
`OPENAI_API_KEY` es opcional y se inyecta únicamente como secreto de entorno.

Los límites de costo y carga se controlan mediante las variables `SONIA_COLLECTIONS_*` descritas
en `.env.example`. El dataset completo nunca se envía al modelo; solo el resultado compacto de una
herramienta determinística.

## Contrato de integración

Cada herramienta devuelve JSON con `contract_version`, `agent`, `as_of_date`, `metrics`,
`findings`, `recommended_actions`, `evidence`, `data_quality` y `visualization_hints`. El futuro
Supervisor puede invocar `CollectionsBackend.execute_tool` sin depender de HTTP ni de la interfaz.

La conciliación es documental. No se presenta como conciliación bancaria porque el dataset no
contiene extractos bancarios ni comunicaciones.
