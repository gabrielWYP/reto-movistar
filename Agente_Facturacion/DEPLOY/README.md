# Contrato de despliegue del Agente de Facturación

Los manifiestos de `kubernetes/` son una referencia standalone de dos pods:

```text
Ingress externo -> billing-front (Nginx) -> /api/* -> billing-back (FastAPI)
```

No deben aplicarse sin adaptar imágenes, namespace y almacenamiento al entorno del equipo. Este directorio no modifica ni sustituye `gabrielWYP/K3S_Infra`.

BACK requiere `SONIA_DATASET=/data` para el dataset predeterminado. Las cargas por UI se almacenan temporalmente en `/tmp/sonia-billing`; no son persistencia definitiva. `back.yaml` usa el placeholder `replace-with-billing-dataset-pvc`, que debe reemplazarse o parchearse antes de desplegar.

La clave OpenAI es opcional y, si se usa, debe provenir de un Secret `billing-agent-openai`. No se incluye Ingress: la plataforma debe exponer solo `billing-front`; `billing-back` permanece interno.
