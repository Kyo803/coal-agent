@echo off
rem Launch the Coal terminal UI.
cd /d "%~dp0"
if not exist "coal-tui.exe" (
    echo coal-tui.exe not found - building...
    set GOPROXY=off
    set GOFLAGS=-mod=mod
    go build -o coal-tui.exe .
    if errorlevel 1 (
        echo build failed
        pause
        exit /b 1
    )
)
coal-tui.exe %*
