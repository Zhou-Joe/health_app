@echo off
REM 本地Windows电脑启动MinerU和frp客户端

echo ==========================================
echo   本地GPU电脑 - MinerU + frp 客户端启动脚本
echo   连接到阿里云: 8.218.181.186
echo ==========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请先安装Python
    pause
    exit /b 1
)

REM ============================================
REM Step 1: 启动MinerU服务 (端口8001)
REM ============================================
echo [1/2] 启动MinerU服务 (端口8001)...
start "MinerU Server" cmd /k "python -m mineru.server --port 8001"
echo MinerU服务已在新窗口启动
timeout /t 3 /nobreak >nul

REM ============================================
REM Step 2: 启动frp客户端
REM ============================================
echo [2/2] 启动frp客户端...

REM 检查frpc.exe是否存在
if not exist "frpc.exe" (
    echo.
    echo 错误: 未找到frpc.exe
    echo 请从以下地址下载frp客户端:
    echo https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_windows_amd64.zip
    echo.
    echo 下载后解压，将frpc.exe放到当前目录
    pause
    exit /b 1
)

REM 检查frpc.ini配置文件
if not exist "frpc.ini" (
    echo.
    echo 错误: 未找到frpc.ini配置文件
    echo 请确保frpc.ini在当前目录
    pause
    exit /b 1
)

start "frp Client" cmd /k "frpc.exe -c frpc.ini"
echo frp客户端已在新窗口启动
echo.

REM ============================================
REM 等待服务启动
REM ============================================
echo 等待服务启动...
timeout /t 5 /nobreak >nul

REM ============================================
REM 测试MinerU服务
REM ============================================
echo.
echo ==========================================
echo   测试MinerU服务
echo ==========================================
echo 正在测试本地MinerU服务...
curl -s http://localhost:8001/docs >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 本地MinerU服务运行正常
    echo 访问地址: http://localhost:8001/docs
) else (
    echo [警告] 无法访问MinerU服务，请检查日志
)

echo.
echo ==========================================
echo   服务启动完成！
echo ==========================================
echo.
echo 已启动的服务:
echo   1. MinerU服务 (端口8001)
echo   2. frp客户端 (连接到8.218.181.186:7000)
echo.
echo 阿里云可以通过以下地址访问MinerU:
echo   http://8.218.181.186:8001
echo.
echo frp管理面板:
echo   http://8.218.181.186:7500
echo   用户名: admin
echo   密码: Health@2026MinerU
echo.
echo 按任意键关闭此窗口（服务将继续运行）...
pause >nul
