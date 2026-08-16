# Backend del Agente de Cobranzas/Recaudación

Paquete Python instalable `collections_agent`. Expone tools determinísticas y un
router reutilizado por el backend compartido de SON-IA.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m collections_agent
```

La API queda en `http://localhost:8080/api/docs`. `OPENCODE_KEY` habilita
las consultas conversacionales con OpenCode Go; las tools determinísticas no
requieren IA.
El dataset se configura con `SONIA_COLLECTIONS_DATASET` o se carga por HTTP y
permanece en memoria.
