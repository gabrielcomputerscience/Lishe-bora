@echo off
REM One-time setup on Windows. Run from the project root:  scripts\setup.bat
setlocal
cd /d "%~dp0\.."

echo === Backend: installing Python packages into .venv ===
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -m venv .venv || python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :error

if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul

echo === Backend: creating database and seed data ===
pushd backend
"..\.venv\Scripts\python.exe" -m alembic upgrade head || goto :error
"..\.venv\Scripts\python.exe" -m app.seed.run --demo || goto :error
popd

echo === Frontend: installing Node packages (needs Node.js 20+) ===
where npm >nul 2>nul || (echo Node.js not found. Install from https://nodejs.org and re-run. & goto :error)
pushd frontend
if not exist ".env.local" copy ".env.example" ".env.local" >nul
call npm install || goto :error
popd

echo.
echo Setup complete. Start with:  scripts\start-backend.bat  and  scripts\start-frontend.bat
echo Then open http://localhost:3000   (API docs: http://localhost:8000/api/docs)
exit /b 0
:error
echo Setup failed. See the messages above.
exit /b 1
