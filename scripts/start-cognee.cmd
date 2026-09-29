@echo off
setlocal

rem Double-click launcher for the Sbs branch and Windows Compose startup script.
cd /d "%~dp0.." || goto :failed

where git >nul 2>&1
if errorlevel 1 (
    echo Git was not found. Install Git and try again.
    goto :failed
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo This script must run from the cognee Git checkout.
    goto :failed
)

git show-ref --verify --quiet refs/heads/Sbs
if errorlevel 1 (
    echo The local Sbs branch was not found. Fetch or create it first.
    goto :failed
)

for /f "delims=" %%B in ('git branch --show-current') do set "CURRENT_BRANCH=%%B"
if /I not "%CURRENT_BRANCH%"=="Sbs" (
    echo Switching from %CURRENT_BRANCH% to Sbs...
    git switch Sbs
    if errorlevel 1 (
        echo Could not switch to Sbs. Commit or stash local changes and try again.
        goto :failed
    )
)

where docker >nul 2>&1
if errorlevel 1 (
    echo Docker was not found. Install Docker Desktop and try again.
    goto :failed
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo Docker Compose is not available. Check your Docker Desktop installation.
    goto :failed
)

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Start Docker Desktop and try again.
    goto :failed
)

echo Starting cognee from the Sbs branch in %CD% ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0compose-up.ps1" %*
if errorlevel 1 goto :failed

echo.
echo Cognee containers started. Use "docker compose ps" to check their status.
pause
exit /b 0

:failed
echo.
echo Startup failed. Review the message above.
pause
exit /b 1
