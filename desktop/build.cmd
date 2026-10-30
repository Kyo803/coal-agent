@echo off
rem Build the ROX N desktop app: icon -> Rust shell -> Go launcher.
setlocal
cd /d "%~dp0"

echo [1/3] icon
py -3.15 make_icon.py || goto :err

echo [2/3] Rust shell (first build downloads Tauri and takes minutes)
pushd src-tauri
cargo build --release || (popd & goto :err)
popd

echo [3/3] Go launcher
pushd launcher
set GOFLAGS=-mod=mod
go build -o rox-n-launcher.exe . || (popd & goto :err)
popd

echo.
echo done. run:  launcher\rox-n-launcher.exe
exit /b 0

:err
echo.
echo build failed
exit /b 1
