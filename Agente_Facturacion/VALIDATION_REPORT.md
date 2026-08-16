# Validación final · 2026-08-14

## Baseline y alcance

- Rama: `camila`.
- HEAD funcional recibido: `4b2620df8a834081bb7af9f7c887a2e99014ac81`, descendiente de `73a873c99480d3cd47639329ba38185923b39895`.
- Baseline anterior al refactor: 28/28 pruebas OK.
- Checkpoint preparatorio del launcher ya validado: `540ba87f4c42f0bc828c193caec20aa72843e427`.
- Suite final: 66/66 pruebas OK.

## Validación local FRONT/BACK

- BACK: `127.0.0.1:8080`, proceso independiente, `/health` = 200.
- FRONT: `127.0.0.1:8503`, proceso independiente y proxy `/api/*` = 200.
- Bindings observados exclusivamente en localhost.
- Navegación visual verificada: Resumen, Factura, NC material y Quiebres de ciclo.
- Dataset predeterminado mostrado como `LISTO PARA ANALIZAR`, corte 07/08/2026 y conteos por fuente reales.

## Casos oficiales

| Caso | Resultado observado |
|---|---|
| Resumen | 3,364 facturas; 196 NC; 38 NC materiales; 22 gaps; 10 diferencias aritméticas. |
| `S300-0256413` | Diferencia absoluta S/ 0.06; `ARITHMETIC_MISMATCH`; requiere validación. |
| `FOBF-00121753` | `MISSING_CURRENCY`. |
| `S7AA-0067926518` | `ZERO_VALUE_INVOICE`; sin causa inferida. |
| `S1AA-0052649961` / `SJFE-0031656645` | Ratio 73.8%; severidad heurística alta; motivo no disponible. |
| `CLIENT_00434` / `993722637` | Mayo y julio con documento, junio sin evidencia; planta enlazada activa; candidato heurístico. |

## Recorrido conversacional

| Consulta | Intent / tool / resultado |
|---|---|
| ¿Qué debería revisar hoy? | `portfolio_health` / `billing_health_snapshot`. |
| Revisa la factura S300-0256413 | `invoice_review` / `invoice_quality_check`. |
| ¿Por qué requiere validación? | Mantiene factura mediante contexto explícito del navegador. |
| Analiza CLIENT_00434 | `customer_review` / `customer_billing_check`. |
| ¿Y la cuenta 993722637? | Filtra cuenta con contexto enviado por el cliente. |
| ¿Hay un quiebre en junio? | `cycle_gap_review` / `billing_cycle_gaps`. |
| Revisa S1AA-0052649961 y sus NC | `credit_note_review` / `credit_note_review`. |
| ¿Por qué ocurrió esa NC? | `DATA_LIMITATION`; el dataset no contiene motivo. |
| ¿Cuánto debe CLIENT_00434? | `HANDOFF_RECOMMENDED` a `collections`. |
| ¿Qué segmento tiene mayor riesgo de recuperación? | `HANDOFF_RECOMMENDED` a `bi`. |

## Dataset dinámico

- Cinco CSV oficiales cargados a través del proxy FRONT: `READY`, 3,364 facturas y corte 2026-08-07.
- Fixture sintético nuevo: `dataset_id` independiente, 2 facturas; Resumen recalculado a 2 y consulta de factura correcta.
- Retorno a `default`: Resumen volvió a 3,364.
- Archivo `.exe`: HTTP 422 con explicación en español.
- ZIP válido, fuente faltante, columna faltante, archivo vacío y traversal cubiertos por pruebas automatizadas.
- DELETE elimina el workspace temporal; IDs distintos no mezclan servicios ni métricas.

## Docker y K3S

- Docker no está instalado en el entorno de validación; no se declara `docker compose up --build` como ejecutado.
- Se validaron estáticamente Dockerfiles no-root, Compose con solo FRONT publicado, proxy parametrizado y filesystem read-only con tmpfs.
- Se inspeccionó el contrato público K3S sin modificarlo: puertos 8080, probe `/health`, usuarios 1001/101, `/tmp` escribible y proxy interno parametrizado. Los manifests standalone usan `billing-back`.

## Resultado

AC-01 a AC-11: PASS. Pruebas FAIL: 0. Queda pendiente únicamente ejecutar el build/smoke de Docker en una máquina con Docker disponible.

## Refactor estructural · 2026-08-15

- HEAD inicial preservado: `242051f9f1b2124930c8c6ae4ef7476480fd420e`.
- Baseline previo al movimiento: 66/66 pruebas OK.
- Implementación única: `Agente_Facturacion/BACK/src/billing_agent/` y `Agente_Facturacion/FRONT/`.
- Se eliminaron las rutas productivas legacy `back/`, `front/` y `compose.yaml` de la raíz.
- Los once módulos de dominio Billing y los activos JS/CSS/config conservan blobs idénticos al baseline; solo cambiaron imports, packaging y rutas de infraestructura.
- Suite posterior al movimiento: 66/66 pruebas OK; AC-01 a AC-11 PASS.
- Smoke real: BACK y FRONT independientes en `127.0.0.1:8080` y `127.0.0.1:8503`; cinco vistas, asistente y handoff respondieron por proxy HTTP.
- Carga real de cinco CSV y carga ZIP: `READY`, 3,364 facturas en ambos casos; DELETE ejecutado para ambas cargas temporales.
- Se añadieron manifests standalone en `DEPLOY/kubernetes/`, sin modificar `K3S_Infra`.
- Docker continúa no disponible en esta máquina; sus artefactos se verificaron estáticamente, no se declara build ejecutado.
