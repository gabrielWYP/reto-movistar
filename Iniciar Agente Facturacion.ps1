param(
    [string]$Dataset = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Dataset) {
    $Dataset = Join-Path $Root "data\source\DATASET"
}
if (-not (Test-Path -LiteralPath $Dataset)) {
    Write-Host "No se encontró el dataset: $Dataset" -ForegroundColor Red
    Write-Host "Uso: .\Iniciar Agente Facturacion.ps1 -Dataset 'C:\ruta\DATASET'"
    exit 1
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Host "No se encontró Python en PATH. Instala Python 3.11+ y vuelve a intentar." -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = Join-Path $Root "src"
& $Python.Source -m billing_agent.web_app --dataset $Dataset --port 8503 --open
