@echo off
chcp 65001 >nul
title ETF 买入诊断器（网页版）
cd /d "%~dp0"
echo.
echo   ┌───────────────────────────────────────────────┐
echo   │  ETF 买入诊断器 · 网页版                       │
echo   │                                                │
echo   │  手机/电脑都能用，电脑关机也不影响：            │
echo   │  https://etf-advisor-34742.app.workbuddy.host/ │
echo   │                                                │
echo   │  本脚本同时在本机启动本地服务（供内网/调试）：  │
echo   │  http://127.0.0.1:8734                         │
echo   └───────────────────────────────────────────────┘
echo.
where python >nul 2>nul
if %errorlevel%==0 (
    python etf_advisor.py
) else (
    py -3 etf_advisor.py
)
pause
