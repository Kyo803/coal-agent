@echo off
cd /d "C:\Users\WERU1\OneDrive\Documents\Default Project\ROX-N\lm_track\rox_chat"
echo [finish] start %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_p2_games.log"
python -u rox.py --say "finish the game arcade project" --finish arcade-frontend >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_p2_games.log" 2>&1
echo [finish] done %date% %time% >> "C:\Users\WERU1\OneDrive\Documents\Default Project\_p2_games.log"