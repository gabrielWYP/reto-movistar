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
- Dos contenedores: todos los fronts en `front` y todos los backends en `back`.
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
├── src/sonia/agents/{billing,collections}/
├── tests/
├── Dockerfile
└── pyproject.toml
Agente BI/
├── BACK/src/bi_agent/
└── FRONT/
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

El centro de operaciones sirve el front BI en `http://localhost:8080/bi/` y el
backend compartido publica sus contratos en `/api/bi/*`. El dataset se carga
desde esa interfaz o mediante `POST /api/bi/dataset`; permanece en RAM dentro
del contenedor `back` y se pierde al reiniciar el pod.

El Agente de Cobranzas se abre desde su tarjeta o directamente en
`http://localhost:8080/agents/collections/index.html`. Su API vive bajo
`/api/collections/*`; los CSV validados también permanecen en RAM y no se
mezclan con el dataset anterior cuando una carga es incompatible.

Las consultas BI usan OpenCode Go cuando `OPENCODE_KEY` está disponible en el
entorno del backend. El modelo predeterminado es `deepseek-v4-flash`: selecciona
una tool cerrada, Python calcula el resultado y el modelo redacta la respuesta
solo con evidencia compacta. La clave nunca se envía al frontend ni se incluye
en la imagen.

## Ejecutar solo el backend

```bash
cd back
python -m venv .venv
.venv/bin/pip install -e '../Agente BI/BACK[dev]'
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sonia
```

Los contratos operativos están disponibles en `GET /health`, `GET /api/agents`,
`GET /api/collections/status` y `GET /api/bi/status`. Producción publica las dos imágenes compartidas desde
`front/Dockerfile` y `back/Dockerfile`; el `Dockerfile` raíz se conserva
solo para compatibilidad local.
