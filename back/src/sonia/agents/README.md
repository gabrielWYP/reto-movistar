# Agentes integrados

| ID estable | Rama de origen | Paquete backend | Módulo frontend |
|---|---|---|---|
| `billing` | `camila` | `sonia.agents.billing` | `front/agents/billing` |
| `collections` | `Arian` | `collections_agent` | `Agente Cobranzas/FRONT` |
| `bi` | `Mauricio` | `bi_agent` | `Agente BI/FRONT` |

Los paquetes comparten el proceso FastAPI integrado y mantienen límites propios.
Los contratos públicos se incorporan mediante la capa `application`; BI y
Cobranzas también pueden ejecutarse de forma independiente para desarrollo.

Los módulos heredados conservan por ahora el estilo de sus ramas y están fuera
del gate estricto de Ruff y mypy. Sus pruebas funcionales sí forman parte de la
suite obligatoria; la homologación de estilo y tipos queda como deuda explícita.
