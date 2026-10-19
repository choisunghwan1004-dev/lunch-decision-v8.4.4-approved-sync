@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 실제 Node·FastAPI·MySQL을 임시 DB로 연결하며 AI 응답만 테스트 대역으로 바꿉니다.
if not exist .venv\Scripts\python.exe goto failed
.venv\Scripts\python.exe -m pip install playwright
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m news_service.run_checks --mode browser
if errorlevel 1 goto failed
echo test-results\checks-browser.json 과 화면 캡처를 확인하세요.
pause
exit /b 0
:failed
echo 10번 무료 테스트와 11번 MySQL 테스트부터 확인하세요.
pause
exit /b 1
