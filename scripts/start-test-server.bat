@echo off
REM ============================================================================================================
REM  LisheBora local TEST server: run the system on this computer so colleagues on the same office network
REM  (Wi-Fi/LAN) can use it from their own laptops or phones at http://<this-computer>:3000
REM
REM    scripts\start-test-server.bat            start (builds the website the first time)
REM    scripts\start-test-server.bat rebuild    rebuild the website first (after updates to the code)
REM
REM  Three windows open: API (backend), worker (messages and reminders) and website. Close them to stop.
REM  Keep this computer awake and plugged in during the test.
REM ============================================================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0\.."
set ROOT=%CD%
set PY=%ROOT%\.venv\Scripts\python.exe
if not exist "%PY%" (echo Python environment not found. Run scripts\setup.bat first. & pause & exit /b 1)

REM --- 1. this computer's address on the office network -------------------------------------------------------
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|VirtualBox|VMware|Loopback' } | Sort-Object -Property @{Expression={ if ($_.PrefixOrigin -eq 'Dhcp') {0} else {1} }} | Select-Object -First 1).IPAddress"`) do set LANIP=%%i
if "%LANIP%"=="" set LANIP=127.0.0.1
set HOSTN=%COMPUTERNAME%

REM --- 2. allow the website to be opened from those addresses (sign-in protection checks the address) ----------
set ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://%LANIP%:3000,http://%HOSTN%:3000
powershell -NoProfile -Command "$f='backend\.env'; $c=Get-Content $f; if ($c -match '^CORS_ORIGINS=') { $c=$c -replace '^CORS_ORIGINS=.*','CORS_ORIGINS=%ORIGINS%' } else { $c += 'CORS_ORIGINS=%ORIGINS%' }; Set-Content $f $c"

REM --- 3. open port 3000 in the Windows firewall (needs administrator rights the first time) -------------------
netsh advfirewall firewall show rule name="LisheBora test 3000" >nul 2>nul
if errorlevel 1 (
  netsh advfirewall firewall add rule name="LisheBora test 3000" dir=in action=allow protocol=TCP localport=3000 profile=domain,private >nul 2>nul
  if errorlevel 1 (
    echo.
    echo  NOTE: could not open port 3000 in the firewall. Right-click this file and choose "Run as administrator"
    echo        once, or ask IT to allow incoming TCP port 3000 on this computer. Until then only this computer can connect.
    echo.
  )
)

REM --- 4. which database is in use ------------------------------------------------------------------------------
for /f "tokens=2 delims==" %%d in ('findstr /b "DATABASE_URL=" backend\.env') do set DB=%%d
echo Database: %DB%

REM --- 5. start the API, the worker and the website ---------------------------------------------------------------
start "LisheBora API" /d "%ROOT%\backend" cmd /k "..\.venv\Scripts\python.exe -m alembic upgrade head & ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "LisheBora worker" /d "%ROOT%\backend" cmd /k "timeout /t 8 >nul && ..\.venv\Scripts\python.exe -m app.jobs all --loop 60"
pushd frontend
if /i "%1"=="rebuild" goto build
if exist ".next\BUILD_ID" goto run
:build
echo Building the website (2-4 minutes the first time)...
call npm run build || (echo Website build failed. & popd & pause & exit /b 1)
:run
start "LisheBora website" /d "%ROOT%\frontend" cmd /k "npx next start -p 3000 -H 0.0.0.0"
popd

echo.
echo ==============================================================================================
echo   LisheBora test server is starting. Give it about 20 seconds.
echo.
echo   On this computer:      http://localhost:3000
echo   Colleagues (same network):  http://%LANIP%:3000     or  http://%HOSTN%:3000
echo   Administrators sign in at /admin/sign-in ; everyone else at /sign-in
echo.
echo   Demo accounts: see docs\pilot_test\LisheBora_Pilot_Test_Script.xlsx (sheet "Accounts")
echo   Phones on this network cannot use "Use my location" (GPS needs https); type or pick the point on the map.
echo ==============================================================================================
start "" http://localhost:3000
pause
