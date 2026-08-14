@echo off
setlocal

REM Inicio local de la interfaz SON-IA. La política se aplica solo a este proceso.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Iniciar Agente Cobranzas.ps1"

if errorlevel 1 (
  echo.
  echo No se pudo iniciar la interfaz. Revise el mensaje anterior.
  pause
)
