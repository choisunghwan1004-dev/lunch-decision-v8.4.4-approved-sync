@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo 먼저 08_뉴스_설치.bat을 실행하세요.
 pause
 exit /b 1
)
start "FastAPI News 8001" cmd /k ".venv\Scripts\python.exe -m uvicorn news_service.app:app --host 127.0.0.1 --port 8001"
call npm start
pause
