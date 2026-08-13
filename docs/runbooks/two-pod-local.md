# Validar la arquitectura de dos pods

## Inicio

```bash
docker compose up --build --wait
```

La única URL pública local es `http://localhost:8080`.

Si ese puerto está ocupado, se puede cambiar sin modificar el contenedor:

```bash
SONIA_PUBLIC_PORT=18081 docker compose up --build --wait
```

## Smoke tests

```bash
curl --fail http://localhost:8080/health
curl --fail http://localhost:8080/api/agents
curl --fail http://localhost:8080/
```

`/api/agents` debe devolver, en orden, `billing`, `collections` y `bi`.

## Cierre

```bash
docker compose down --volumes
```
