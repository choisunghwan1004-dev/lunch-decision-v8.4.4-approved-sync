@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Lunch Travel News - One Click
where node >nul 2>nul
if errorlevel 1 goto no_node
node scripts\start-all.js
if errorlevel 1 goto failed
endlocal
exit /b 0
:no_node
echo Node.js 설치가 필요합니다. https://nodejs.org 에서 설치 후 다시 실행하세요.
:failed
echo.
echo 위 안내를 확인하세요. 상세 설명: README_ONE_CLICK.md
pause
endlocal
exit /b 1
