@echo off
REM Switch the backend to the DEMO / training database (backend\lishebora.db). Restart the backend afterwards.
cd /d "%~dp0\..\backend"
powershell -NoProfile -Command "(Get-Content .env) -replace '^DATABASE_URL=.*','DATABASE_URL=sqlite:///./lishebora.db' | Set-Content .env"
echo Now using the demo database. Restart the backend.
pause
