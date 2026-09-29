@echo off
setlocal

rem Double-click launcher for the existing Windows Compose startup script.
cd /d "%~dp0.." || goto :failed

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

echo Starting cognee from %CD% ...
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
