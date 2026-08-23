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
├── agents/{billing,collections}/   # integración mínima y tarjeta
├── assets/
└── Dockerfile
back/
├── src/sonia/agents/billing/
├── tests/
├── Dockerfile
└── pyproject.toml
Agente Cobranzas/
├── BACK/src/collections_agent/
└── FRONT/
Agente BI/
├── BACK/src/bi_agent/
├── FRONT/
└── DEPLOY/
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

El Supervisor en `http://localhost:8080/` es la única superficie de carga
manual. `POST /api/supervisor/dataset` valida las seis fuentes contra
Facturación, Cobranzas y BI antes de publicarlas de forma atómica en RAM. Si un
agente rechaza el paquete, ninguno cambia. El dataset se pierde al reiniciar el
pod.

El Agente de Cobranzas se abre desde su tarjeta o directamente en
`http://localhost:8080/agents/collections/index.html`. Su API vive bajo
`/api/collections/*`. Las pestañas de especialistas son de solo lectura respecto
a la fuente y muestran exclusivamente lo publicado por Supervisor.

BI y Cobranzas usan OpenCode Go con `deepseek-v4-flash` cuando `OPENCODE_KEY`
está disponible. Ambos agentes ejecutan los cálculos en Python y solo entregan
evidencia compacta al modelo. La clave nunca se envía al frontend ni se incluye
en la imagen.

## Ejecutar solo el backend

### Entorno de desarrollo Python 3.12

La versión de referencia es Python 3.12, igual que en CI. Desde la raíz del
repositorio se puede crear un único entorno para el backend compartido y los
tres agentes:

```bash
uv venv --python 3.12 .venv-py312
uv pip install --python .venv-py312/bin/python \
  --editable './Agente BI/BACK[dev]' \
  --editable './Agente Cobranzas/BACK[dev]' \
  --editable './Agente_Facturacion/BACK[dev]' \
  --editable './back[dev]'
source .venv-py312/bin/activate
python --version
```

El resultado esperado es `Python 3.12.x`. El entorno `.venv` anterior no es la
referencia de validación porque fue creado con Python 3.14.

### Iniciar la API

```bash
source .venv-py312/bin/activate
python -m sonia
```

Los contratos operativos están disponibles en `GET /health`, `GET /api/agents`,
`GET /api/collections/status` y `GET /api/bi/status`. Producción publica las dos imágenes compartidas desde
`front/Dockerfile` y `back/Dockerfile`; el `Dockerfile` raíz se conserva
solo para compatibilidad local.
