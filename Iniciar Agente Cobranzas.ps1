param([int]$Port = 8501)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$codexPython = "C:\Users\Arian Zorrilla\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$dataset = Join-Path $repoRoot "data\source\SONIA_DESAFIO_03.zip"

if (-not (Test-Path -LiteralPath $codexPython)) {
    throw "No se encontró el Python de Codex. Abre este proyecto desde Codex o instala Python 3.11+."
}
if (-not (Test-Path -LiteralPath $dataset)) {
    throw "No se encontró el dataset. Copia SONIA_DESAFIO_03.zip en: $dataset"
}

$env:PYTHONPATH = Join-Path $repoRoot "src"
& $codexPython -m collections_agent.web_app --dataset $dataset --port $Port --open

