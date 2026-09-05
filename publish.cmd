@echo off
REM Commits the refreshed dashboard and pushes it to GitHub Pages.
REM Does nothing (quietly) until a remote named "origin" exists, so the
REM weekly task keeps working before GitHub is set up.
cd /d "%~dp0"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo [publish] not a git repository - skipping
  exit /b 0
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo [publish] no "origin" remote yet - skipping push
  echo [publish] see README.md, "Put it on GitHub Pages"
  exit /b 0
)

git add -A
git diff --cached --quiet
if not errorlevel 1 (
  echo [publish] no changes to publish
  exit /b 0
)

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul ^| find "="') do set DT=%%I
set STAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%
git commit -m "Dashboard refresh %STAMP%" >nul
if errorlevel 1 (
  echo [publish] commit failed
  exit /b 1
)

git push origin HEAD
if errorlevel 1 (
  echo [publish] push failed - run "gh auth login" or check your remote
  exit /b 1
)
echo [publish] pushed - GitHub Pages will rebuild in about a minute
exit /b 0
