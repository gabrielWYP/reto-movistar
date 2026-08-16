# Referencia standalone del Agente BI

> No aplicar estos manifiestos al despliegue integrado de SON-IA. Crearían pods
> `bi-back` y `bi-front` adicionales y violarían el contrato de dos contenedores.

Producción debe usar los `back/Dockerfile` y `front/Dockerfile` del repositorio.
El primero instala `bi_agent`; el segundo sirve BI bajo `/bi/`. El dataset se
carga por HTTP y permanece únicamente en la memoria del contenedor `back`.

Los manifiestos de `kubernetes/` son una referencia standalone de dos pods:

```text
Ingress externo → bi-front (Nginx) → /api/* → bi-back (FastAPI)
```

No deben aplicarse sin adaptar imágenes, namespace y almacenamiento al entorno
del equipo. Este directorio no modifica ni sustituye `gabrielWYP/K3S_Infra`.

## Contrato del dataset en memoria

No requiere PVC, `hostPath` ni object storage. `POST /api/bi/dataset` recibe los
seis CSV o un ZIP, aplica límites de tamaño y conserva el contenido en RAM. Un
reinicio o rollout elimina el dataset y obliga a cargarlo nuevamente.

La clave OpenCode Go debe proceder de un Secret llamado `bi-agent-opencode`,
con la entrada `OPENCODE_KEY`; nunca de ConfigMap, imagen, frontend o Git. El
modelo no secreto `deepseek-v4-flash` se define en el ConfigMap.

No se incluye Ingress: la plataforma debe exponer únicamente `bi-front` según
su convención. `bi-back` permanece como `ClusterIP` interno.
