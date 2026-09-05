@echo off
REM Manual FPL refresh - syncs, rebuilds the dashboard, publishes it.
REM   refresh.cmd          refresh, publish, then open the dashboard
REM   refresh.cmd /quiet   refresh and publish only
cd /d "%~dp0"

REM Pull BEFORE generating. dashboard.html and index.html are fully derived, so
REM rebuilding on top of the latest commit avoids conflicting with whatever the
REM scheduled cloud run has already published.
git rev-parse --is-inside-work-tree >nul 2>&1
if not errorlevel 1 (
  git remote get-url origin >nul 2>&1
  if not errorlevel 1 (
    echo [refresh] syncing with the remote first...
    git pull --rebase --autostash origin main
    if errorlevel 1 (
      echo [refresh] could not rebase cleanly - resolve by hand, then rerun.
      if /i not "%~1"=="/quiet" pause
      exit /b 1
    )
  )
)

py update.py
if errorlevel 1 (
  echo.
  echo Update failed. Check your internet connection, then run again.
  if /i not "%~1"=="/quiet" pause
  exit /b 1
)

call "%~dp0publish.cmd"

if /i not "%~1"=="/quiet" start "" "%~dp0dashboard.html"
