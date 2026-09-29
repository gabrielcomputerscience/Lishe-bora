@echo off
REM Switch the backend to the PILOT database (backend\lishebora_pilot.db). Restart the backend afterwards.
cd /d "%~dp0\..\backend"
if not exist lishebora_pilot.db ( echo No pilot database yet. Run scripts\setup-pilot.bat first. & pause & exit /b 1 )
powershell -NoProfile -Command "(Get-Content .env) -replace '^DATABASE_URL=.*','DATABASE_URL=sqlite:///./lishebora_pilot.db' | Set-Content .env"
echo Now using the pilot database. Restart the backend.
pause
