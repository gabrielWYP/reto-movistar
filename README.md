# SON-IA · Billing Assurance

Implementación del Agente de Facturación B2B en la rama `camila`. El producto transforma cinco extractos CSV/ZIP en excepciones determinísticas, evidencia auditable y siguientes validaciones humanas.

La arquitectura productiva está separada:

```text
Navegador → FRONT HTML/CSS/JS + Nginx → /api/* → BACK FastAPI
                                                   ↓
                               BillingAgentRuntime → BillingService → DatasetSource
```

Inicio local simple:

```powershell
& ".\Iniciar Agente Facturacion.ps1" -Dataset ".\data\source\DATASET"
```

El launcher crea/reutiliza `.venv`, inicia BACK y FRONT como procesos diferentes, y abre `http://127.0.0.1:8503`.

Despliegue con contenedores:

```powershell
$env:SONIA_DATASET = ".\data\source\DATASET"
docker compose up --build
```

Abrir `http://127.0.0.1:8080`. Consulta [Agente_Facturacion/README.md](Agente_Facturacion/README.md) para alcance, API, seguridad, pruebas y casos demo.
