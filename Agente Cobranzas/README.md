# Agente de Cobranzas/Recaudación SON-IA

MVP autónomo para reconstruir la cartera B2B, conciliar aplicaciones documentales y priorizar recupero. Los cálculos financieros se ejecutan de forma determinística en Python; una capa de IA sólo debe seleccionar una tool, interpretar resultados compactos y explicar acciones respaldadas por evidencia.

## Qué resuelve

- Estado de cliente: facturado, pagado, saldo, vencido, ageing y recomendación.
- Trazabilidad de factura: factura → pago(s) → nota(s) de crédito → saldo → estados.
- Cartera global y ageing con fecha de corte explícita.
- Ranking explicable de cobranza.
- Excepciones de conciliación: pagos fuera de corte, sobreaplicación y anomalías temporales.

## Ejecución

Desde la raíz del repositorio:

```powershell
$env:PYTHONPATH = "src"
python -m collections_agent.cli portfolio
python -m collections_agent.cli customer CLIENT_00385
python -m collections_agent.cli invoice S1AA-0052403449
python -m collections_agent.cli priorities --limit 10
python -m collections_agent.cli exceptions --limit 10
```

## Interfaz para usuarios no técnicos

Haz doble clic en `Abrir Agente Cobranzas.vbs`. No requiere instalar Python ni escribir comandos. Se abrirá una ventana de PowerShell; déjala abierta mientras uses la interfaz.

Si Windows no ejecuta archivos VBS por la configuración de tu equipo, usa `Iniciar Agente Cobranzas.cmd` con clic derecho y **Abrir**.

También puedes iniciarlo desde PowerShell:

```powershell
& ".\Iniciar Agente Cobranzas.ps1"
```

Se abrirá automáticamente `http://127.0.0.1:8501` en el navegador. La interfaz es local: sólo expone este agente de Cobranzas/Recaudación y no envía información fuera de la computadora. Para cerrarla, vuelve a la ventana de PowerShell y presiona `Ctrl+C`.

La pantalla permite cargar uno o varios archivos `.csv`. Antes de usarlos, valida encabezados, registros, fechas e importes. La tabla de **Facturas** es obligatoria; Pagos y Notas de Crédito son opcionales. Si hay un error o una tabla duplicada, el agente conserva el dataset anterior y no mezcla información. Los archivos se procesan temporalmente en memoria y se descartan al cerrar la aplicación.

Para ejecutar la demo, copia el ZIP anonimizado `SONIA_DESAFIO_03.zip` a `data/source/SONIA_DESAFIO_03.zip`; el cargador lee el ZIP anidado sin extraerlo en el repositorio. El archivo se excluye de Git para no incrementar el repositorio con datos de trabajo. Se puede usar otro archivo con `--dataset RUTA`.

## Modo GPT-5.6 y control de costo

Sin API key, las cinco tools se ejecutan localmente y sin consumo de tokens. Con `OPENAI_API_KEY`, el modo opcional `ask` usa `gpt-5.6-terra` por defecto, selecciona una sola tool y realiza como máximo dos llamadas: selección y explicación. El ZIP y los CSV nunca se envían al modelo; sólo se envía el resultado JSON filtrado de una tool. Puede cambiarse el modelo con `SONIA_MODEL` o `--model`.

```powershell
$env:OPENAI_API_KEY = "..."
python -m collections_agent.cli ask "¿Qué clientes deberían priorizarse?" --as-of-date 2026-08-07
```

La integración usa la Responses API con function calling y `store: false`.

La interfaz también tiene el bloque **Consulta con IA**. Configura la clave sólo en tu sesión local antes de iniciar el agente:

```powershell
$env:OPENAI_API_KEY = "tu_clave"
$env:SONIA_MODEL = "gpt-5.6-terra" # opcional
& ".\Iniciar Agente Cobranzas.ps1"
```

La clave nunca se envía al navegador, no se escribe en archivos del proyecto y no se incluye en Git. La IA recibe la pregunta y resultados compactos de las tools; los CSV y el ZIP permanecen locales.

## Contrato de integración

Cada tool devuelve JSON con `contract_version`, `agent`, `as_of_date`, `metrics`, `findings`, `recommended_actions`, `evidence`, `data_quality` y `visualization_hints`. Esto permite que un Supervisor dirija la consulta y que el agente BI visualice los resultados sin recalcularlos.

## Principios

- Los importes usan `Decimal` internamente y tolerancia de S/ 0.01.
- `RAZON_SOCIAL` es la llave de cliente confiable del dataset anonimizado; el RUC sólo es evidencia, no clave de join.
- Los pagos a documentos ausentes se marcan `FUERA_DE_CORTE`; no se reportan como un error financiero confirmado.
- No se afirma conciliación bancaria real: no existen extractos bancarios ni comunicaciones en el dataset.
