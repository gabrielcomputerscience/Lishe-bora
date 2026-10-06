@echo off
REM Re-run the automated pilot simulation (Makueni / Kalulini, every process) and rebuild the example database.
REM Writes docs\pilot_test\LisheBora_Simulation_Report.xlsx. Your demo and pilot databases are not changed.
cd /d "%~dp0\..\backend"
"..\.venv\Scripts\python.exe" scripts\pilot_simulation.py --save
pause
