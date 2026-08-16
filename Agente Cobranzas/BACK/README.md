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
El alcance conversacional cubre cartera, clientes identificados, trazabilidad de
facturas, prioridades y excepciones documentales. Si DeepSeek no devuelve
exactamente una tool válida, el selector reintenta una vez con un presupuesto
acotado y luego conserva el fallback determinístico. La telemetría registra
intento, `finish_reason`, cantidad de tools, latencia y tokens, sin almacenar la
pregunta ni evidencia del dataset.
El dataset se configura con `SONIA_COLLECTIONS_DATASET` o se carga por HTTP y
permanece en memoria.
