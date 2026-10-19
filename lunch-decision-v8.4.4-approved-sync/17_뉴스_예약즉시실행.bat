@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 오늘 예약 작업을 지금 실행합니다. 실제 OpenAI API 비용이 발생합니다. 같은 날짜·주제는 중복 생성하지 않습니다.
if not exist .venv\Scripts\python.exe goto failed
.venv\Scripts\python.exe -m news_service.automation --run-now
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo 실행에 실패했습니다. README_AUTOMATION.md와 화면의 안내를 확인하세요.
pause
exit /b 1
