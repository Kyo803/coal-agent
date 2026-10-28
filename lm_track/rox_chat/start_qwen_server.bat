@echo off
set BACKEND=C:\Users\WERU1\.lmstudio\extensions\backends\llama.cpp-win-x86_64-avx2-2.31.2
set MODEL=C:\Users\WERU1\.lmstudio\models\lmstudio-community\Qwen3.6-35B-A3B-GGUF\Qwen3.6-35B-A3B-Q4_K_M.gguf
cd /d "%BACKEND%"
llama-server.exe -m "%MODEL%" --port 1234 --host 127.0.0.1 -c 4096 -ngl 0 --no-webui > "%TEMP%\llama_srv.log" 2>&1
