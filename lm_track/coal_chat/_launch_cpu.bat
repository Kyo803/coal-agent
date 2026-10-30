@echo off
set PATH=C:\iverilog\bin;%PATH%
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
echo [cpu-f] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_p3_cpu.log"
python -u coal.py --say "finish the 4-bit cpu project" --finish 4bit-verilog-cpu >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_p3_cpu.log" 2>&1
echo [cpu-f] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_p3_cpu.log"