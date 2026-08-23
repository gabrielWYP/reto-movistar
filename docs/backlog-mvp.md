# Backlog MVP - SON-IA

Este backlog convierte la arquitectura aprobada en unidades verificables. El objetivo de salida es una demo E2E repetible con datos ficticios, aprobaciones humanas y auditoría completa.

## Estado verificado del repositorio

Corte: `main@5cf41c9`, auditado el 2026-08-23 contra código, pruebas y workflows.

| Estado | Cantidad | Lectura operativa |
|---|---:|---|
| `DONE` | 11 | Los criterios de la tarea tienen implementación y evidencia verificable. |
| `IN_PROGRESS` | 14 | Existe una parte ejecutable, pero falta al menos un criterio de aceptación. |
| `BACKLOG` | 7 | No existe todavía una implementación ejecutable del alcance descrito. |

La demo visual prueba navegación, estados y aprobaciones explícitas, pero no se
usa como evidencia de persistencia, emisión real, clasificación de mensajes ni
conciliación bancaria. Los tres agentes productivos siguen compartiendo un
backend y un frontend en el despliegue SON-IA; sus manifests independientes son
artefactos de referencia, no la topología pública vigente.

### Evidencia principal

| Área | Implementado | Brecha que mantiene tareas abiertas |
|---|---|---|
| Fundaciones | FastAPI, health, CI, imágenes front/back, CODEOWNERS y plantilla de PR. | El gate G0 espera escaneo automático de secretos y PII. |
| Supervisor visual | Máquina de estados tipada, transiciones válidas, dos gates humanos y rechazo de saltos. | La API es stateless; no existe `Case` persistente ni event store append-only. |
| Facturación | Reglas funcionales, Billing Assurance, carga aislada en memoria, evidencia y validaciones documentales. | El agente declara que no calcula PxQ contractual ni emite facturas. |
| Cobranzas/Recaudo | Cartera, trazabilidad documental, pagos vinculados, prioridades y excepciones. | No clasifica mensajes ni realiza conciliación bancaria con extractos. |
| BI | KPIs deterministas, evidencias, visualizaciones y consultas opcionales con LLM. | La invocación coordinada desde el Supervisor sigue pendiente. |
| Calidad | Tests unitarios/integración, smoke tests de contenedores y demo pública. | `evals/` conserva scaffolding; no hay golden set ni métricas automatizadas por intención/campo. |
| Observabilidad | Logs JSON del backend con `request_id`, latencia y errores; agentes registran uso del proveedor. | Falta cobertura E2E uniforme y resource tracking. |
| Release | Imágenes inmutables multi-arquitectura, validación K3S y smoke público. | G3 no cierra hasta completar evaluación y observabilidad. |

## Cómo usarlo

1. Cerrar primero las tareas `P0` que están `IN_PROGRESS`.
2. Promover una tarea de `BACKLOG` a `READY` solo cuando sus dependencias estén terminadas.
3. Incluir el ID en la rama, PR y evidencia de validación.
4. Actualizar a `DONE` solo cuando se cumplan todos los criterios de aceptación.

## Convenciones

| Campo | Valores |
|---|---|
| Prioridad | `P0` demo obligatoria, `P1` calidad importante, `P2` extensión |
| Estado | `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE` |
| Responsable | Técnico, Facturación, Cobranzas/Recaudo, Demo/Calidad |

## Gates de entrega

| Gate | Resultado verificable | Tareas mínimas | Estado actual |
|---|---|---|---|
| G0 - Fundaciones | Repositorio instalable, contenedor saludable y contratos de colaboración. | FND-01..04, SEC-01 | `IN_PROGRESS` |
| G1 - Facturación | PxQ ficticio validado, aprobado y emitido mediante adaptador simulado. | DOM-01..03, DAT-01..02, BIL-01..04, APR-01, UX-01 | `IN_PROGRESS` |
| G2 - Cobranza/Recaudo | Mensaje de pago clasificado y conciliación propuesta con aprobación. | COL-01..02, REC-01..03, APR-02 | `IN_PROGRESS` |
| G3 - Demo integrada | Journey E2E, tablero, evaluaciones y despliegue repetible. | AI-01..02, BI-01, EVAL-01..02, OBS-01, DEMO-01, REL-01 | `IN_PROGRESS` |

## Índice priorizado

| ID | P | Descripción | Responsable | Dependencias | Estado |
|---|---|---|---|---|---|
| FND-01 | P0 | Crear estructura modular y contratos para colaboradores. | Técnico | - | DONE |
| FND-02 | P0 | Exponer aplicación mínima y `GET /health` en `:8080`. | Técnico | FND-01 | DONE |
| FND-03 | P0 | Añadir CI para lint, tipos, tests y build de contenedores. | Técnico | FND-02 | DONE |
| FND-04 | P0 | Configurar plantillas de PR y ownership técnico. | Técnico | FND-01 | DONE |
| SEC-01 | P0 | Aplicar política de datos sintéticos y escaneo de secretos. | Técnico + Demo/Calidad | FND-01 | IN_PROGRESS |
| DOM-01 | P0 | Modelar `Case` y estados permitidos. | Técnico | FND-01 | IN_PROGRESS |
| DOM-02 | P0 | Implementar transiciones y bloqueos del supervisor. | Técnico | DOM-01 | DONE |
| DOM-03 | P0 | Registrar auditoría inmutable por transición. | Técnico | DOM-02 | IN_PROGRESS |
| DAT-01 | P0 | Definir esquemas PxQ, factura, pago y evidencia. | Técnico + áreas funcionales | FND-01 | IN_PROGRESS |
| DAT-02 | P0 | Crear dataset sintético del journey principal y excepciones. | Facturación + Cobranzas/Recaudo | DAT-01 | IN_PROGRESS |
| BIL-01 | P0 | Documentar proceso y reglas PxQ. | Facturación | FND-01 | DONE |
| BIL-02 | P0 | Cargar y versionar un PxQ ficticio. | Técnico | DAT-01, BIL-01 | BACKLOG |
| BIL-03 | P0 | Extraer campos con evidencia y esquema tipado. | Técnico | BIL-02 | BACKLOG |
| BIL-04 | P0 | Ejecutar validaciones deterministas y excepciones. | Técnico + Facturación | BIL-03 | IN_PROGRESS |
| APR-01 | P0 | Aprobar o rechazar la emisión con identidad y comentario. | Técnico + Facturación | DOM-03, BIL-04 | IN_PROGRESS |
| INT-01 | P0 | Simular emisión idempotente de factura. | Técnico | APR-01 | BACKLOG |
| UX-01 | P0 | Mostrar caso, evidencia, excepciones y aprobación. | Técnico + Demo/Calidad | BIL-04, APR-01 | DONE |
| COL-01 | P1 | Documentar mensajes e intenciones de cobranza. | Cobranzas/Recaudo | FND-01 | DONE |
| COL-02 | P1 | Clasificar mensajes y extraer referencias de pago. | Técnico | DAT-02, COL-01 | BACKLOG |
| REC-01 | P1 | Modelar depósitos y conciliaciones. | Técnico + Cobranzas/Recaudo | DAT-01 | IN_PROGRESS |
| REC-02 | P1 | Implementar matching determinista factura-pago. | Técnico | INT-01, REC-01 | IN_PROGRESS |
| REC-03 | P1 | Explicar diferencias y enviar ambigüedades a revisión. | Técnico | REC-02 | IN_PROGRESS |
| APR-02 | P1 | Confirmar aplicación del pago y cerrar el caso. | Técnico + Cobranzas/Recaudo | REC-03 | IN_PROGRESS |
| AI-01 | P1 | Orquestar agentes mediante máquina de estados. | Técnico | DOM-02, BIL-04, COL-02, REC-03 | IN_PROGRESS |
| AI-02 | P1 | Abstraer proveedor LLM y versionar prompts. | Técnico | FND-02 | IN_PROGRESS |
| BI-01 | P1 | Calcular KPIs E2E y quiebres del caso. | Técnico + Demo/Calidad | APR-02 | DONE |
| EVAL-01 | P1 | Crear golden set y rúbricas por agente. | Demo/Calidad + áreas funcionales | DAT-02 | BACKLOG |
| EVAL-02 | P1 | Automatizar métricas de extracción y clasificación. | Técnico | EVAL-01, COL-02, BIL-03 | BACKLOG |
| OBS-01 | P0 | Registrar logs JSON, latencia, errores y health. | Técnico | FND-02 | IN_PROGRESS |
| DEMO-01 | P1 | Preparar guion E2E y evidencias reproducibles. | Demo/Calidad | G1, G2, BI-01 | DONE |
| REL-01 | P1 | Desplegar imagen inmutable y ejecutar smoke tests públicos. | Técnico | FND-03, DEMO-01 | DONE |
| PRED-01 | P2 | Evaluar probabilidad o tiempo hasta pago con corte temporal. | Técnico | DAT-02, BI-01 | BACKLOG |

## Criterios de aceptación por unidad

### FND - Fundaciones

**FND-01 - Estructura modular**

- Las carpetas de negocio, datos, prompts, evaluaciones, `front`, `back` y tests existen en Git.
- Cada colaborador funcional tiene una carpeta, ejemplos y límites de edición claros.
- La arquitectura y el backlog son accesibles desde el README principal.

**FND-02 - Runtime mínimo**

- La aplicación inicia con un único comando.
- `GET /health` devuelve HTTP 200 y un payload tipado con estado y versión.
- El proceso escucha en `0.0.0.0:8080` dentro del contenedor.

**FND-03 - CI**

- Un PR ejecuta lint, formato, tipos, tests y build del contenedor.
- Un fallo en cualquier gate bloquea el merge.
- La publicación GHCR usa un tag inmutable derivado del commit.

**FND-04 - Colaboración**

- El PR solicita ID de backlog, evidencia y checklist de datos sintéticos.
- `CODEOWNERS` exige revisión técnica para runtime, seguridad y CI/CD.

**SEC-01 - Datos seguros**

- Existe una política explícita de datos prohibidos.
- CI detecta secretos y patrones básicos de PII.
- Todos los ejemplos públicos son ficticios y están marcados como tales.

### DOM - Dominio y supervisor

**DOM-01/02 - Caso y estados**

- Solo se permiten transiciones definidas en la arquitectura.
- Una transición inválida falla sin modificar el caso.
- Estados financieros requieren actor y motivo.

**DOM-03 - Auditoría**

- Cada transición registra caso, estado anterior, estado nuevo, actor, timestamp y correlación.
- Los eventos se agregan; no se sobrescriben.
- La UI puede reconstruir la línea de tiempo desde los eventos.

### DAT/BIL - Datos y facturación

**DAT-01/02 - Contratos y datos sintéticos**

- Los esquemas definen tipos, obligatoriedad y ejemplos válidos/erróneos.
- El journey contiene al menos un caso feliz y tres excepciones.
- No existen identificadores reales.

**BIL-01..04 - PxQ**

- El área funcional aprueba campos, reglas y severidades.
- Cada campo extraído referencia archivo y ubicación.
- Montos y periodos se validan de forma determinista.
- Falta de evidencia o una regla bloqueante produce `MANUAL_REVIEW`.

**APR-01/INT-01 - Emisión simulada**

- Solo un caso aprobado puede llamar al adaptador.
- Reintentar con la misma clave no crea otra factura.
- La respuesta y la aprobación quedan auditadas.

### COL/REC - Cobranzas y recaudo

**Contrato transversal de datos**

- Supervisor es la única superficie de carga manual.
- Facturación, Cobranzas y BI consumen la misma publicación en memoria.
- La publicación se rechaza completa si cualquier agente no valida el paquete.
- Las pestañas especialistas muestran estado y resultados, pero no reemplazan la fuente.

**COL-01/02 - Mensajes**

- El catálogo funcional incluye pago informado, promesa de pago, disputa y mensaje irrelevante.
- La salida contiene intención, cliente, documento, monto, fecha, evidencia y confianza.
- Baja confianza o campos críticos ausentes requieren revisión humana.

**REC-01..03/APR-02 - Conciliación**

- El matching usa referencia, cliente, moneda, monto y ventana temporal.
- Diferencias de moneda o monto nunca se aplican automáticamente.
- El cierre registra quién confirmó el pago y la evidencia utilizada.

### AI/EVAL/OBS - IA y calidad

**AI-01/02 - Orquestación y proveedor**

- El LLM no puede modificar el estado directamente.
- Toda salida se valida contra un esquema antes de usarse.
- Se registra proveedor, modelo, versión de prompt, latencia y tokens.

**EVAL-01/02 - Evaluación**

- Los casos golden están versionados y tienen resultado esperado.
- Extracción reporta exactitud por campo y cobertura de evidencia.
- Clasificación reporta precision, recall y F1 por intención.

**OBS-01 - Observabilidad**

- Logs estructurados incluyen `request_id` y no contienen documentos completos.
- Health no expone secretos ni configuración interna.
- Errores de agente e integración son distinguibles.

## Definition of Ready

- [ ] El problema y usuario están identificados.
- [ ] Existen ejemplos ficticios de entrada y salida.
- [ ] Las dependencias están en `DONE`.
- [ ] Los criterios de aceptación son verificables.
- [ ] La persona responsable acepta la tarea.

## Definition of Done

- [ ] Criterios de aceptación cumplidos.
- [ ] Tests o evidencias incluidos con el cambio.
- [ ] Datos revisados como ficticios.
- [ ] Logs y errores relevantes son observables.
- [ ] Documentación actualizada.
- [ ] PR aprobado y CI exitoso.

## Orden recomendado

1. Terminar G0 y congelar contratos de colaboración.
2. Ejecutar G1 como primer vertical slice demostrable.
3. Construir G2 reutilizando estados, auditoría y aprobaciones.
4. Integrar G3 y ensayar la demo con datos nuevos, no solo con el caso conocido.
