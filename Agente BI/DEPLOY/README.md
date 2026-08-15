# Contrato de despliegue del Agente BI

Los manifiestos de `kubernetes/` son una referencia standalone de dos pods:

```text
Ingress externo → bi-front (Nginx) → /api/* → bi-back (FastAPI)
```

No deben aplicarse sin adaptar imágenes, namespace y almacenamiento al entorno
del equipo. Este directorio no modifica ni sustituye `gabrielWYP/K3S_Infra`.

## Contrato del dataset

El contenedor BACK necesita:

```text
SONIA_BI_DATASET_PATH=/data/bi
```

y que en esa ruta estén disponibles, con permisos de solo lectura, los seis CSV
oficiales o el ZIP del reto. El origen definitivo no está decidido: puede ser
PVC, `hostPath`, object storage con init container u otro mecanismo acordado.

`back.yaml` usa deliberadamente el placeholder
`replace-with-bi-dataset-pvc`. Debe reemplazarse o parchearse antes de desplegar;
no representa una decisión de almacenamiento.

La clave OpenAI es opcional. Si se usa, debe proceder de un Secret llamado
`bi-agent-openai`; nunca de ConfigMap, imagen, frontend o Git.

No se incluye Ingress: la plataforma debe exponer únicamente `bi-front` según
su convención. `bi-back` permanece como `ClusterIP` interno.
