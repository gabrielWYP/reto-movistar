# Backend del Agente de Cobranzas/Recaudación

Paquete Python independiente `collections_agent`. Expone tools determinísticas,
un router reutilizable por SON-IA y una aplicación FastAPI standalone.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m collections_agent
```

La API queda en `http://localhost:8080/api/docs`. `OPENAI_API_KEY` habilita
las consultas conversacionales; las consultas determinísticas no requieren IA.
El dataset se configura con `SONIA_COLLECTIONS_DATASET` o se carga por HTTP y
permanece en memoria.
