@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 현재 사용자에게 매일 16시 Windows 작업을 등록합니다. 예약된 날에는 API 비용이 발생합니다.
if not exist .venv\Scripts\python.exe goto failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\register-news-task.ps1"
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo 실행에 실패했습니다. README_AUTOMATION.md와 화면의 안내를 확인하세요.
pause
exit /b 1
