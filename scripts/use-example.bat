@echo off
REM Switch the backend to the EXAMPLE database (backend\lishebora_example.db): one full Makueni / Kalulini cycle already done
REM by scripts\pilot_simulation.py --save. For browsing finished records. Restart the backend afterwards.
cd /d "%~dp0\..\backend"
if not exist lishebora_example.db (
  echo Building the example database first...
  "..\.venv\Scripts\python.exe" scripts\pilot_simulation.py --save
)
powershell -NoProfile -Command "(Get-Content .env) -replace '^DATABASE_URL=.*','DATABASE_URL=sqlite:///./lishebora_example.db' | Set-Content .env"
echo Now using the example database. Restart the backend.
pause
