# Referencia standalone del Agente de Cobranzas/Recaudación

Estos manifiestos documentan el despliegue independiente en dos pods:

```text
Ingress → collections-front (Nginx) → /api/* → collections-back (FastAPI)
```

No deben aplicarse al despliegue integrado de SON-IA, que usa las imágenes
compartidas de `back/Dockerfile` y `front/Dockerfile`. El dataset cargado por
HTTP permanece en memoria y se pierde al reiniciar el backend.

`OPENAI_API_KEY` debe provenir de un Secret llamado `collections-agent-openai`:

```bash
kubectl create secret generic collections-agent-openai \
  --from-literal=OPENAI_API_KEY='valor-real'
```

Nunca se incluye la clave en ConfigMap, imagen, frontend o repositorio.
