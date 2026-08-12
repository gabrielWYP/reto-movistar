param(
  [string]$Dataset = "C:\Disco D\Universidad\Hackathon MOVISTAR BOOTCAMP\SONIA_DESAFIO_03\DATASET",
  [int]$Port = 8502
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root "src"
python -m bi_agent.web_app --dataset $Dataset --port $Port --open
