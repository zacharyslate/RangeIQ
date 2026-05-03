@echo off
setlocal

cd /d "%~dp0"
set "APP_URL=http://localhost:8501"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%' -TimeoutSec 2; if ($response.StatusCode -ge 200) { Start-Process '%APP_URL%'; exit 0 } } catch { exit 1 }"
if not errorlevel 1 exit /b 0

start "RangeIQ Server" /min cmd /k "\"%~dp0Run RangeIQ Server.cmd\""

powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(30); $ready = $false; do { Start-Sleep -Milliseconds 750; try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%' -TimeoutSec 2; $ready = $response.StatusCode -ge 200 } catch { $ready = $false } } while (-not $ready -and (Get-Date) -lt $deadline); Start-Process '%APP_URL%'"
