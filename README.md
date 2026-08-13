# SON-IA - Reto Movistar

Prototipo para el Desafío 3 del AI Telecom Challenge: orquestación controlada de agentes para facturación, cobranzas, recaudo e inteligencia de negocio.

## Inicio rápido

1. Lee [la guía de inicio](docs/00-inicio-rapido.md).
2. Revisa [la propuesta de arquitectura](docs/propuesta-arquitectura-sonia.md).
3. Selecciona una tarea del [backlog MVP](docs/backlog-mvp.md).

## Principios

- Una sola entrada pública y un monolito modular para el MVP.
- Aprobación humana antes de acciones financieras.
- Reglas deterministas para cálculos y conciliaciones.
- IA con salidas estructuradas, evidencia y trazabilidad.
- Solo datos ficticios o anonimizados.

## Estado

El primer MVP visual permite recorrer un caso ficticio con tres agentes: Facturación, Cobranzas y Recaudo. Incluye una máquina de estados controlada, dos aprobaciones humanas, evidencia por agente y una línea de auditoría demostrativa.

La emisión de facturas, la aplicación de pagos y las integraciones corporativas siguen siendo simuladas hasta contar con autorización y contratos técnicos reales.

## Ejecutar localmente

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m sonia
```

Abrir `http://localhost:8080`. El contrato operativo está disponible en `GET /health`.
