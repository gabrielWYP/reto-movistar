# Agentes integrados

| ID estable | Rama de origen | Paquete backend | Módulo frontend |
|---|---|---|---|
| `billing` | `camila` | `sonia.agents.billing` | `front/agents/billing` |
| `collections` | `Arian` | `sonia.agents.collections` | `front/agents/collections` |
| `bi` | `Mauricio` | `bi_agent` | `Agente BI/FRONT` |

Los paquetes comparten el proceso FastAPI y deben usar imports relativos dentro
de su límite. Los contratos públicos se incorporan mediante la capa
`application`; ningún módulo se expone como servidor independiente.

Los módulos heredados conservan por ahora el estilo de sus ramas y están fuera
del gate estricto de Ruff y mypy. Sus pruebas funcionales sí forman parte de la
suite obligatoria; la homologación de estilo y tipos queda como deuda explícita.
