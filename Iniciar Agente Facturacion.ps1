param(
    [string]$Dataset = "",
    [int]$Port = 8503
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = Join-Path $Root "Agente_Facturacion"
$BackendRoot = Join-Path $AgentRoot "BACK"
$FrontendRoot = Join-Path $AgentRoot "FRONT"

if (-not $Dataset) { $Dataset = $env:SONIA_DATASET }
if (-not $Dataset) { $Dataset = [Environment]::GetEnvironmentVariable("SONIA_DATASET", "User") }
if (-not $Dataset) {
    $Candidate = Join-Path $env:USERPROFILE "Downloads\SONIA_DESAFIO_03\SONIA_DESAFIO_03\DATASET\DATASET"
    if (Test-Path -LiteralPath $Candidate) { $Dataset = $Candidate }
}
if (-not $Dataset) { $Dataset = Join-Path $Root "data\source\DATASET" }
if (-not (Test-Path -LiteralPath $Dataset)) {
    Write-Host "No se encontró el dataset predeterminado: $Dataset" -ForegroundColor Red
    Write-Host "Uso: .\Iniciar Agente Facturacion.ps1 -Dataset 'C:\ruta\DATASET'"
    exit 1
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $BasePython = if ($PythonCommand) { $PythonCommand.Source } else { $null }
    if (-not $BasePython) {
        $Installed = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe") -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($Installed) { $BasePython = $Installed.FullName }
    }
    if (-not $BasePython) {
        $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
        if (Test-Path -LiteralPath $CodexPython) { $BasePython = $CodexPython }
    }
    if (-not $BasePython) {
        Write-Host "No se encontró Python 3.11+ en PATH, instalación local ni runtime de Codex." -ForegroundColor Red
        exit 1
    }
    Write-Host "Creando entorno virtual local..." -ForegroundColor Cyan
    & $BasePython -m venv (Join-Path $Root ".venv")
}

$Python = $VenvPython
& $Python -c "import fastapi, uvicorn, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando dependencias declaradas del backend..." -ForegroundColor Cyan
    & $Python -m pip install -e $BackendRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:SONIA_DATASET = (Resolve-Path -LiteralPath $Dataset).Path
$env:SONIA_HOST = "127.0.0.1"
$env:SONIA_PORT = "8080"
$env:PYTHONPATH = Join-Path $BackendRoot "src"

$BackendArguments = @("-m", "uvicorn", "billing_agent.app:app", "--host", "127.0.0.1", "--port", "8080")
$Backend = Start-Process -FilePath $Python -ArgumentList $BackendArguments -WorkingDirectory $BackendRoot -WindowStyle Hidden -PassThru
try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        try {
            $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8080/health" -TimeoutSec 1
            if ($Response.StatusCode -eq 200) { $Ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) { throw "El backend no respondió en el tiempo esperado." }
    $Url = "http://127.0.0.1:$Port"
    Start-Process $Url
    Write-Host "SON-IA Billing FRONT: $Url" -ForegroundColor Green
    Write-Host "SON-IA Billing BACK: http://127.0.0.1:8080" -ForegroundColor DarkGray
    Write-Host "Presiona Ctrl+C para cerrar ambos procesos." -ForegroundColor Yellow
    & $Python (Join-Path $FrontendRoot "dev_server.py") --host 127.0.0.1 --port $Port --backend-host 127.0.0.1 --backend-port 8080
} finally {
    if ($Backend -and -not $Backend.HasExited) { Stop-Process -Id $Backend.Id }
}
