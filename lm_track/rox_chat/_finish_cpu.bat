@echo off
set PATH=C:\iverilog\bin;%PATH%
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\ROX-N\lm_track\rox_chat"
echo [cfin] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_cfin.log"
python -u rox.py --say "finish the 4-bit cpu project so it compiles with iverilog and the testbench passes" --finish 4bit-cpu >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_cfin.log" 2>&1
echo [cfin] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_cfin.log"