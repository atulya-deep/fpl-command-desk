@echo off
REM Weekly FPL refresh - pulls live data, rewrites the dashboard, publishes it.
REM   refresh.cmd          refresh, publish, then open the dashboard
REM   refresh.cmd /quiet   refresh and publish only (used by the scheduled task)
cd /d "%~dp0"

py update.py
if errorlevel 1 (
  echo.
  echo Update failed. Check your internet connection, then run again.
  if /i not "%~1"=="/quiet" pause
  exit /b 1
)

call "%~dp0publish.cmd"

if /i not "%~1"=="/quiet" start "" "%~dp0dashboard.html"
