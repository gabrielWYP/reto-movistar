# Empezar a colaborar en SON-IA

Este repositorio separa decisiones de negocio, datos sintéticos y código para que cada integrante pueda aportar sin modificar componentes críticos.

## Ruta rápida

1. Identifica tu área en la tabla de responsables.
2. Elige una tarea `READY` del [backlog](backlog-mvp.md).
3. Copia el ejemplo más cercano dentro de tu carpeta.
4. Modifica únicamente datos ficticios.
5. Abre un Pull Request y completa la plantilla.

## Responsables

| Rol | Carpeta principal |
|---|---|
| Responsable técnico | `back/`, `front/`, `.github/`, Dockerfiles y `compose.yaml` |
| Facturación | `business/01-facturacion/` y `data/synthetic/billing/` |
| Cobranzas/Recaudo | `business/02-cobranzas-recaudo/` y datos sintéticos relacionados |
| Demo/Calidad | `business/03-demo-calidad/` y `evals/` |

## Qué puede editar una persona no técnica

- Markdown (`.md`) para describir procesos, excepciones y guiones.
- YAML (`.yaml`) para reglas y criterios de aceptación.
- CSV (`.csv`) para casos ficticios con resultados esperados.

No debe editar secretos, workflows, Dockerfiles, manifiestos Kubernetes ni código Python sin acompañamiento técnico.

## Checklist antes de abrir un PR

- [ ] La tarea del backlog está identificada en el PR.
- [ ] Los ejemplos contienen solo datos ficticios.
- [ ] Cada regla tiene un caso válido y uno inválido.
- [ ] El resultado esperado puede comprobarse sin interpretación adicional.
- [ ] No se incluyeron credenciales, correos, teléfonos o cuentas reales.

## Ayuda

Si una regla no puede expresarse con los campos actuales, documenta el ejemplo y la evidencia esperada. El responsable técnico decidirá si corresponde ampliar el esquema o implementar una regla en código.
