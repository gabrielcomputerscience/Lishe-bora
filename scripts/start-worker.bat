@echo off
REM Background worker: sends SMS/email and runs reminders (overdue approvals, expiring documents, late payments).
cd /d "%~dp0\..\backend"
"..\.venv\Scripts\python.exe" -m app.jobs all --loop 60
