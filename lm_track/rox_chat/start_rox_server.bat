@echo off
set BACKEND=C:\Users\WERU1\AppData\Local\Programs\ROX N\server
set MODEL=C:\Users\WERU1\AppData\Local\Programs\ROX N\models\ROX-N-35B-A3B-Q4_K_M.gguf
set MMPROJ=C:\Users\WERU1\AppData\Local\Programs\ROX N\models\ROX-N-35B-A3B-mmproj-BF16.gguf
cd /d "%BACKEND%"
llama-server.exe -m "%MODEL%" --mmproj "%MMPROJ%" --image-min-tokens 1024 --port 1234 --host 127.0.0.1 -c 8192 -ngl 8 --no-webui > "%TEMP%\llama_srv.log" 2>&1