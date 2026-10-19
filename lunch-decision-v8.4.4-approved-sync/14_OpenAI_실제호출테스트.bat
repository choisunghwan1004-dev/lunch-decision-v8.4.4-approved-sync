@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 가상 Fact로 실제 gpt-6-luna API를 한 번 호출합니다. API 비용이 발생합니다.
if not exist .venv\Scripts\python.exe (
 py -3 -m venv .venv
 if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r news_service\requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m news_service.openai_check --live
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo 실행에 실패했습니다. 화면의 안내와 README_OPENAI.md를 확인하세요.
pause
exit /b 1
