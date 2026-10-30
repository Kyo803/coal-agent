@echo off
set PATH=C:\iverilog\bin;%PATH%
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
echo [cpu3] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_cpu3.log"
python -u coal.py --say "build a complete project: a 4-bit CPU in Verilog. Include a 4-bit ALU (add, subtract, AND, OR, XOR with zero and carry flags), a register file, a program counter, an instruction decoder, a top-level cpu_top module, a data memory module, a testbench that loads a small program and verifies execution, and an assembler. The testbench must instantiate cpu_top using only its declared ports. Make sure iverilog compiles cleanly and the testbench passes." >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_cpu3.log" 2>&1
echo [cpu3] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_cpu3.log"