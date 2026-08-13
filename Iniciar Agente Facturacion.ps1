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

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($PythonCommand) {
    $Python = $PythonCommand.Source
} else {
    # Codex desktop can provide a managed Python runtime even when Python is not
    # installed in PATH. Keep the normal PATH resolution as the first option.
    $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $CodexPython) {
        $Python = $CodexPython
    } else {
        Write-Host "No se encontró Python en PATH ni el runtime administrado por Codex." -ForegroundColor Red
        Write-Host "Instala Python 3.11+ o inicia Codex para que configure su runtime local." -ForegroundColor Red
        exit 1
    }
}

$env:PYTHONPATH = Join-Path $Root "src"
& $Python -m billing_agent.web_app --dataset $Dataset --port 8503 --open
