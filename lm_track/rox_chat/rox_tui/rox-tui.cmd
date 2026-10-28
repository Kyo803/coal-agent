@echo off
rem Launch the ROX N terminal UI.
cd /d "%~dp0"
if not exist "rox-tui.exe" (
    echo rox-tui.exe not found - building...
    set GOPROXY=off
    set GOFLAGS=-mod=mod
    go build -o rox-tui.exe .
    if errorlevel 1 (
        echo build failed
        pause
        exit /b 1
    )
)
rox-tui.exe %*
