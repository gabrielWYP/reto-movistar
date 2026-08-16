# Backend del Agente de Cobranzas/Recaudación

Paquete Python instalable `collections_agent`. Expone tools determinísticas y un
router reutilizado por el backend compartido de SON-IA.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m collections_agent
```

La API queda en `http://localhost:8080/api/docs`. `OPENAI_API_KEY` habilita
las consultas conversacionales mediante el SDK oficial y Responses API; las
tools determinísticas no requieren IA.
El alcance conversacional cubre cartera, clientes identificados, trazabilidad de
facturas, prioridades y excepciones documentales. OpenAI puede seleccionar una
o más tools dentro de un máximo configurable. La telemetría registra proveedor,
modelo, latencia y tokens, sin almacenar la pregunta ni evidencia del dataset.
El dataset se configura con `SONIA_COLLECTIONS_DATASET` o se carga por HTTP y
permanece en memoria.
