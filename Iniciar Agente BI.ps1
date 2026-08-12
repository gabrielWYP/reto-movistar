param(
  [string]$Dataset = "C:\Disco D\Universidad\Hackathon MOVISTAR BOOTCAMP\SONIA_DESAFIO_03\DATASET",
  [int]$Port = 8502
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root "src"

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
  $python = $pythonCommand.Source
} else {
  $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (-not (Test-Path -LiteralPath $codexPython)) {
    throw "No se encontró Python. Instala Python 3 o configura python en PATH."
  }
  $python = $codexPython
}

& $python -m bi_agent.web_app --dataset $Dataset --port $Port --open
