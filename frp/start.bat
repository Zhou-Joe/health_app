@echo off
echo Starting frp client (MinerU running in WSL)...
echo.

REM Start frp client only
echo [1/1] Starting frp client...
start "frp Client" cmd /k "frpc.exe -c frpc.ini"
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo Services Started!
echo ========================================
echo MinerU: http://localhost:8001
echo frp Dashboard: http://8.218.181.186:7500
echo   User: admin
echo   Pass: Health@2026MinerU
echo ========================================
echo.
pause
