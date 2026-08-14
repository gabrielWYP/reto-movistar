' Inicio con doble clic para Windows. Abre PowerShell y conserva la ventana
' visible mientras la interfaz local está activa.
Option Explicit

Dim shell, fileSystem, folder, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

folder = fileSystem.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File """ & _
          folder & "\Iniciar Agente Cobranzas.ps1"""

shell.Run command, 1, False
















