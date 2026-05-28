' ============================================================
' Jarvis AI - Silent Startup Launcher
' Runs at Windows Login via Registry (HKCU Run key).
' Launches Jarvis in voice-listening mode with no console window.
' ============================================================

Option Explicit

Dim WShell
Set WShell = CreateObject("WScript.Shell")

' ---- Paths ----
Dim sBase, sScript, sModels, sOllama
sBase   = "D:\My Projects Dekstop\Jarvis"
sScript = sBase & "\main.py"
sModels = sBase & "\Models"

' ---- Set OLLAMA_MODELS for this session so Jarvis finds local models ----
WShell.Environment("PROCESS")("OLLAMA_MODELS") = sModels

' ---- Start Ollama server in background (silent) ----
' This ensures the local AI server is running before Jarvis needs it.
Dim sOllamaCmd
sOllamaCmd = "ollama serve"
WShell.Run "cmd /c set OLLAMA_MODELS=" & sModels & " && " & sOllamaCmd, 0, False

' ---- Wait 3 seconds for Ollama to start ----
WScript.Sleep 3000

' ---- Launch Jarvis (0 = no console window, False = don't wait) ----
Dim sCmd
sCmd = "python """ & sScript & """ --voice --startup"
WShell.Run sCmd, 0, False

Set WShell = Nothing
