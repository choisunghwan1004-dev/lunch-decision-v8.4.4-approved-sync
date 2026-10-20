@echo off
chcp 65001 >nul
cd /d "%~dp0"
call scripts\ensure-news-python.bat
if errorlevel 1 goto failed
.venv\Scripts\python.exe -c "import uvicorn, mysql.connector, dotenv" >nul 2>nul
if errorlevel 1 goto failed
if not exist node_modules\express goto failed
rem 서버를 켜기 전에 내부 연결 설정을 준비합니다. DB 설치나 AI 유료 호출은 하지 않습니다.
.venv\Scripts\python.exe -m news_service.setup --init-env-only
if errorlevel 1 goto failed
echo 기존 Node 또는 FastAPI 창이 실행 중이면 Ctrl+C로 종료한 뒤 실행하세요.
start "FastAPI News 8001" cmd /k ".venv\Scripts\python.exe -m uvicorn news_service.app:app --host 127.0.0.1 --port 8001"
call npm start
pause
exit /b 0
:failed
echo 뉴스 실행 준비가 필요합니다. 18_뉴스_연결복구.bat을 먼저 실행하세요.
pause
exit /b 1
