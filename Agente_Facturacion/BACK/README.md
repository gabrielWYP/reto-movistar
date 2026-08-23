# SON-IA Billing Backend

Backend FastAPI independiente que expone el `BillingAgentRuntime`, las cinco tools determinísticas y la carga aislada de datasets en memoria. No sirve HTML ni contiene lógica de cobranzas.

Variables principales: `SONIA_DATASET`, `SONIA_HOST`, `SONIA_PORT`, `SONIA_MAX_UPLOAD_MB`, `SONIA_MAX_UNCOMPRESSED_MB`, `SONIA_DATASET_TTL_SECONDS`, `OPENCODE_KEY` y `SONIA_BILLING_MODEL`.

Ejecución local desde la raíz:

```powershell
cd .\Agente_Facturacion\BACK
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:SONIA_DATASET = "RUTA_DATASET"
.\.venv\Scripts\python.exe -m billing_agent
```

Pruebas: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
