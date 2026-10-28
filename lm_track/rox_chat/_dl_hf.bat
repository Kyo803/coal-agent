@echo off
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\ROX-N\lm_track\rox_chat"
echo [dl] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_dl_hf.log"
python -u _dl_hf2.py >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_dl_hf.log" 2>&1
echo [dl] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_dl_hf.log"