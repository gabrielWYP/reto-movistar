# SON-IA - Reto Movistar

Prototipo para el Desafío 3 del AI Telecom Challenge: orquestación controlada
de tres agentes para Facturación, Cobranzas/Conciliación e Inteligencia de
Negocio.

## Inicio rápido

1. Lee [la guía de inicio](docs/00-inicio-rapido.md).
2. Revisa [la propuesta de arquitectura](docs/propuesta-arquitectura-sonia.md).
3. Selecciona una tarea del [backlog MVP](docs/backlog-mvp.md).

## Principios

- Una sola entrada pública y un monolito modular para el MVP.
- Dos pods: cliente estático `front` y API modular `back`.
- Aprobación humana antes de acciones financieras.
- Reglas deterministas para cálculos y conciliaciones.
- IA con salidas estructuradas, evidencia y trazabilidad.
- Solo datos ficticios o anonimizados.

## Estado

El primer MVP visual permite recorrer un caso ficticio con los agentes de las
ramas `camila`, `Arian` y `Mauricio`, integrados respectivamente como
Facturación, Cobranzas y BI. Incluye una máquina de estados controlada, dos
aprobaciones humanas, evidencia por agente y una línea de auditoría demostrativa.

La emisión de facturas, la aplicación de pagos y las integraciones corporativas siguen siendo simuladas hasta contar con autorización y contratos técnicos reales.

## Arquitectura del repositorio

```text
front/
├── agents/{billing,collections,bi}/
├── assets/
└── Dockerfile
back/
├── src/sonia/agents/{billing,collections,bi}/
├── tests/
├── Dockerfile
└── pyproject.toml
```

El Ingress publica solo `front`; Nginx enruta `/api/*` y `/health` al Service
`back`. La decisión y el contrato para K3S están en
[ADR-002](docs/arquitectura/decisiones/ADR-002-client-server-two-pods.md).

## Ejecutar localmente en dos contenedores

```bash
docker compose up --build --wait
```

Abrir `http://localhost:8080`. Para detener el entorno:

```bash
docker compose down --volumes
```

## Ejecutar solo el backend

```bash
cd back
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sonia
```

Los contratos operativos están disponibles en `GET /health`, `GET /api/agents`
y `/api/bi/*`. Para ejecutar análisis BI, el pod `back` debe recibir un montaje
de solo lectura configurado con `SONIA_BI_DATASET_PATH`; la API y sus health
checks pueden iniciar sin ese dataset.

Producción publica imágenes independientes desde
`front/Dockerfile` y `back/Dockerfile`; el `Dockerfile` raíz se conserva
solo para compatibilidad local.
