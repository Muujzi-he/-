@echo off
chcp 65001 >nul
title ETF 买入诊断器
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python etf_advisor.py --lan
) else (
    py -3 etf_advisor.py --lan
)
pause
