@echo off
set PATH=C:\iverilog\bin;%PATH%
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\ROX-N\lm_track\rox_chat"
echo [c3f] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_c3f.log"
python -u rox.py --say "finish the 4-bit cpu verilog project so iverilog compiles and the testbench passes" --finish 4bit-cpu-verilog >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_c3f.log" 2>&1
echo [c3f] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_c3f.log"