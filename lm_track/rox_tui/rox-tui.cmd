@echo off
REM ROX N — Go terminal UI launcher.
REM Keeps the 19.7 GB model off (ROX_NO_35B=1) so it runs safely beside
REM other work; the TUI talks to the small local Ollama model instead.
set ROX_NO_35B=1
cd /d "%~dp0"
rox-tui.exe %*
