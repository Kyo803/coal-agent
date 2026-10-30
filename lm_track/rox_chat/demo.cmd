@echo off
rem One-command launch for the demo recording.
rem Reads the API key from %USERPROFILE%\.rox\nebius.key if not already set,
rem points the agent at Nebius Token Factory, and starts the TUI.
rem
rem   demo.cmd
rem
setlocal

cd /d "%~dp0"

if not defined NEBIUS_API_KEY (
    if exist "%USERPROFILE%\.rox\nebius.key" (
        set /p NEBIUS_API_KEY=<"%USERPROFILE%\.rox\nebius.key"
    )
)

if not defined NEBIUS_API_KEY (
    echo [!] NEBIUS_API_KEY is not set.
    echo     Set it, or create %%USERPROFILE%%\.rox\nebius.key containing it.
    echo     Continuing on the local model instead.
)

if defined NEBIUS_API_KEY (
    set "ROX_BASE_URL=https://api.studio.nebius.com/v1"
    if not defined ROX_AGENT_MODEL set "ROX_AGENT_MODEL=nvidia/nemotron-3-super-120b-a12b"
    echo [i] provider: nebius   model: %ROX_AGENT_MODEL%
)

rem never load the 19.7 GB 35B on a 24 GB machine
set "ROX_NO_35B=1"

rem keep the gate fast and quiet for a one-take recording
set "PYTHONUNBUFFERED=1"

if not exist "rox_tui\rox-tui.exe" (
    echo [i] building the TUI...
    pushd rox_tui
    set GOPROXY=off
    set GOFLAGS=-mod=mod
    go build -o rox-tui.exe .
    popd
)

rox_tui\rox-tui.exe %*

endlocal
