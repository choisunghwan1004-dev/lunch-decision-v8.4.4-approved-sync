@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 노션 토큰·상위 페이지·주제 번호를 설정합니다. 노션 DB 2개를 만들고 SQL 05를 설치합니다.
if not exist .venv\Scripts\python.exe goto failed
.venv\Scripts\python.exe -m news_service.automation --configure
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo 실행에 실패했습니다. README_AUTOMATION.md와 화면의 안내를 확인하세요.
pause
exit /b 1
