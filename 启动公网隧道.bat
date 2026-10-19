@echo off
chcp 65001 >nul
title ETF 诊断器 - 公网隧道
cd /d "%~dp0"

rem 先确保诊断服务在跑（没有就静默拉起）
netstat -ano | findstr ":8734" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    where python >nul 2>nul
    if %errorlevel%==0 (
        start "" /min python etf_advisor.py --lan --silent
    ) else (
        start "" /min py -3 etf_advisor.py --lan --silent
    )
    timeout /t 3 /nobreak >nul
)

rem cloudflared 不存在就自动下载（走国内镜像加速）
if not exist cloudflared.exe (
    echo 首次运行：正在下载 cloudflared（约 53MB，走国内镜像）...
    curl.exe -L -s -o cloudflared.exe "https://ghfast.top/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)

echo.
echo 正在建立公网隧道，"Your quick Tunnel has been created" 下面那个
echo https://xxxx.trycloudflare.com 就是公网地址（每次启动随机变化），
echo 手机、平板、任何设备用流量或别的 WiFi 都能打开。
echo 关掉本窗口即停止公网访问（本机 8734 不受影响）。
echo.
.\cloudflared.exe tunnel --url http://127.0.0.1:8734 --no-autoupdate
pause
