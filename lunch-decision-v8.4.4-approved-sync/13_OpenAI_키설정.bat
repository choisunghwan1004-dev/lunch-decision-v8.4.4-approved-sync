@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 키를 화면에 표시하지 않고 이 PC의 .env에 저장합니다. API 호출은 없습니다.
call scripts\ensure-news-python.bat
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r news_service\requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m news_service.openai_check --configure-key
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo 실행에 실패했습니다. 화면의 안내와 README_OPENAI.md를 확인하세요.
pause
exit /b 1
