@echo off
REM Coal — Go terminal UI launcher.
REM Keeps the 19.7 GB model off (CoalO_35B=1) so it runs safely beside
REM other work; the TUI talks to the small local Ollama model instead.
set CoalO_35B=1
cd /d "%~dp0"
coal-tui.exe %*
