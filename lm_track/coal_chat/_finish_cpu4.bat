@echo off
set PATH=C:\iverilog\bin;%PATH%
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
echo [c4f] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_c4f.log"
python -u coal.py --say "finish the 4-bit cpu verilog project so iverilog compiles and the testbench passes" --finish 4bit-cpu-verilog >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_c4f.log" 2>&1
echo [c4f] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_c4f.log"