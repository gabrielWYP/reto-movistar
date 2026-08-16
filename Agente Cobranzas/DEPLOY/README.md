# Despliegue independiente

Los manifiestos crean dos Deployments y dos Services: `collections-back` y
`collections-front`. El frontend consume el backend por DNS interno; ningún
secret se entrega al navegador.

Antes de aplicar los manifiestos, publica las imágenes y reemplaza
`replace-with-tag`. Crea el secret sin versionar su valor:

```bash
kubectl create secret generic collections-agent-openai \
  --from-literal=OPENAI_API_KEY='valor-administrado-fuera-de-git'
kubectl apply -k "Agente Cobranzas/DEPLOY/kubernetes"
```

El secret es necesario únicamente para consultas en lenguaje natural. Las
rutas determinísticas continúan disponibles sin él.
