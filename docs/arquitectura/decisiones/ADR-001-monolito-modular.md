# ADR-001: Monolito modular para el MVP

- Estado: Aceptada
- Fecha: 2026-08-11
- Responsables: equipo SON-IA

## Decisión

SON-IA se desplegará inicialmente como una sola aplicación FastAPI en el puerto `8080`. El supervisor, los agentes, skills, adaptadores y persistencia estarán separados por módulos internos, no por servicios de red.

## Motivo

El equipo tiene una sola persona técnica y tres colaboradores funcionales. Separar cada agente en un microservicio aumentaría despliegues, contratos, observabilidad y puntos de fallo sin aportar valor demostrable durante el hackatón.

## Consecuencias

- Un solo build, despliegue e IngressRoute.
- Transacciones y auditoría más fáciles de mantener consistentes.
- Los módulos conservarán interfaces explícitas para poder extraerse posteriormente.
- Un fallo del proceso puede afectar a toda la aplicación; se mitiga con límites, timeouts y estados recuperables.
- Los trabajos largos deberán migrar a workers cuando la latencia o carga real lo justifique.

## Criterio para reconsiderar

La decisión se revisará si un módulo necesita escalado independiente, aislamiento de seguridad, runtime distinto o un objetivo de disponibilidad incompatible con el resto de la aplicación.
