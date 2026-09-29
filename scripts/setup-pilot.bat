@echo off
REM Creates a CLEAN pilot database (no demo accounts, suppliers, orders or prices) and switches the backend to it.
REM The demo database (backend\lishebora.db) is kept; switch back any time with scripts\use-demo.bat.
REM Stop the backend before running this.
cd /d "%~dp0\..\backend"
if exist lishebora_pilot.db (
  echo A pilot database already exists: backend\lishebora_pilot.db
  echo It was NOT changed. To start again, rename or move that file first.
  goto switch
)
set DATABASE_URL=sqlite:///./lishebora_pilot.db
"..\.venv\Scripts\python.exe" -m alembic upgrade head || goto fail
"..\.venv\Scripts\python.exe" -m app.seed.run || goto fail
:switch
powershell -NoProfile -Command "(Get-Content .env) -replace '^DATABASE_URL=.*','DATABASE_URL=sqlite:///./lishebora_pilot.db' | Set-Content .env"
echo.
echo Pilot database ready and selected. Start the backend, then sign in at http://localhost:3000/admin/sign-in
echo as the Super Administrator (SEED_ADMIN_EMAIL in backend\.env) and open Administration ^> Pilot readiness.
goto end
:fail
echo Something went wrong; the backend .env was not changed.
:end
pause
