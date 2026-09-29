@echo off
REM Deletes the local SQLite database and uploaded files, then rebuilds and reseeds. Development only!
cd /d "%~dp0\..\backend"
if exist lishebora.db del lishebora.db
"..\.venv\Scripts\python.exe" -m alembic upgrade head
"..\.venv\Scripts\python.exe" -m app.seed.run --demo
